"""Run-local, read-only capabilities. The model never chooses credentials or endpoints."""

import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from time import monotonic

import httpx

from tider.tools.base import Tool, ToolRegistry

from .providers.cloud_logging import gcp_signals
from .providers.mock import mock_signals
from .providers.redaction import sanitize


def catalog_summary(catalog):
    """Keep the confirmed topology in the prompt, without repeating document excerpts."""
    confirmed = catalog.get("confirmed") or {}
    return {"status": catalog["status"], "revision": catalog.get("revision"),
            "services": [{k: s[k] for k in ("id", "name", "aliases") if k in s}
                         for s in confirmed.get("services", [])],
            "relations": [{k: r[k] for k in ("source", "target", "label") if k in r}
                          for r in confirmed.get("relations", [])]}


class InvestigationTools:
    def __init__(self, settings, request, lake):
        self.settings, self.request, self.lake = settings, request, lake
        self.deadline = monotonic() + settings.agent_timeout_seconds
        if lake:
            with lake.lock:
                self.catalog = lake.catalog()
                self.documents = lake.snapshot_documents()
        else:
            self.catalog, self.documents = {"status": "empty", "revision": 0}, []
        self.mock = (request.mode or settings.evidence_mode) == "mock"
        if not self.mock and self.catalog["status"] != "confirmed":
            raise ValueError("Confirma el catálogo antes de iniciar la investigación autónoma.")
        confirmed = self.catalog.get("confirmed") or {}
        self.names = {s["name"] for s in confirmed.get("services", [])}
        if self.mock:
            self.names |= {s.service for s in mock_signals(None, request.start, request.end, request.scenario)}
        if request.service and request.service not in self.names and not self.mock:
            raise ValueError("El servicio no pertenece al catálogo confirmado.")
        self.signals, self.seen = [], set()
        self.log_remaining = settings.agent_log_budget
        self.web_calls = 0
        self.registry = ToolRegistry([
            Tool("context_search", "Documentos cargados. args: query (texto), limit (1..4).", "doc", self.context_search),
            Tool("service_catalog", "Catálogo confirmado y relaciones. Sin argumentos.", "doc", lambda: catalog_summary(self.catalog)),
            Tool("search_logs", "Consulta NUEVA. args opcionales: services (lista de nombres del catálogo), "
                 "start/end (ISO con zona dentro del intervalo), text (literal), errors_only (bool), "
                 "offset (página de grupos, 0 por defecto), limit (1..500, 200 por defecto). "
                 "Devuelve resumen por servicio, grupos y referencias. truncated indica cobertura incompleta; "
                 "acota servicio/tiempo o aumenta limit para contrastar otras señales.", "log", self.search_logs),
        ])
        if not self.mock and settings.agent_reader_kubeconfig and settings.agent_kube_context:
            self.registry.register(Tool("service_state", "Estado ACTUAL, no histórico: réplicas, pods y endpoints. "
                                       "args: service (nombre del catálogo).", "k8s", self.service_state))
        if not self.mock and settings.agent_metrics_enabled:
            self.registry.register(Tool("service_metrics", "Cloud Monitoring en la ventana del incidente. "
                                       "args: service, metric (cpu|memory).", "metric", self.service_metrics))
        if settings.agent_web_enabled and settings.tavily_api_key:
            self.registry.register(Tool("search_documentation", "Documentación oficial externa; no es telemetría. "
                                       "args: query (pregunta técnica genérica sin datos privados). Máximo 2 consultas.",
                                       "doc", self.search_documentation))
        self.cache = {}

    def check(self):
        if monotonic() >= self.deadline:
            raise TimeoutError("Presupuesto temporal agotado.")

    def validate_service(self, service):
        if service not in self.names:
            raise ValueError("Servicio fuera del catálogo confirmado.")
        return service

    def context_search(self, query: str, limit: int = 4):
        if not isinstance(query, str) or not 1 <= len(query) <= 2000 or not 1 <= limit <= 4:
            raise ValueError("Consulta documental inválida.")
        if not self.lake:
            return ""
        with self.lake.lock:
            if self.lake.catalog()["revision"] != self.catalog["revision"]:
                raise ValueError("El contexto cambió durante la investigación; inicia una nueva.")
            matches = self.lake.search(query, k=limit)
        return {"matches": matches, "revision": self.catalog["revision"]} if matches else ""

    def search_logs(self, services=None, start=None, end=None, text="", errors_only=True, offset=0, limit=200):
        self.check()
        services = sorted(self.names) if services is None else services
        if not isinstance(services, list) or not services or len(services) > len(self.names):
            raise ValueError("Selecciona servicios del catálogo.")
        for name in services:
            self.validate_service(name)
        start = datetime.fromisoformat(start) if start else self.request.start
        end = datetime.fromisoformat(end) if end else self.request.end
        if start.tzinfo is None or end.tzinfo is None or not self.request.start <= start < end <= self.request.end:
            raise ValueError("La consulta debe estar dentro de la ventana autorizada.")
        if not isinstance(text, str) or len(text) > 200 or type(errors_only) is not bool:
            raise ValueError("Filtro inválido.")
        if type(offset) is not int or offset < 0:
            raise ValueError("Página inválida.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("Límite de consulta inválido.")
        key = json.dumps([services, start.isoformat(), end.isoformat(), text, errors_only, limit])
        if key not in self.cache:
            if self.log_remaining <= 0:
                raise ValueError("Presupuesto de registros agotado; no se consultó otra página.")
            if self.mock:
                records = [s for s in mock_signals(None, self.request.start, self.request.end, self.request.scenario)
                           if s.source == "log" and s.service in services and start <= s.timestamp <= end
                           and text.lower() in s.message.lower()
                           and (not errors_only or s.severity in {"ERROR", "CRITICAL", "FATAL"}
                                or re.search(r"error|failed|unavailable|refused|timeout", s.message, re.I))]
            else:
                records = gcp_signals("general", start, end, self.settings, services,
                                      max_records=min(limit, self.log_remaining) + 1, text=text, errors_only=errors_only, deadline=self.deadline)
            cap = min(limit, self.log_remaining)
            incomplete = getattr(records, "incomplete", None)
            truncated = len(records) > cap
            records = records[:cap]
            self.log_remaining -= len(records)
            groups = defaultdict(list)
            for s in records:
                s = s.model_copy(update={"message": sanitize(s.message)})
                identity = (s.timestamp, s.service, s.source, s.message)
                if identity not in self.seen:
                    self.seen.add(identity)
                    s.id = f"S{len(self.signals)+1:02}"
                    self.signals.append(s)
                else:
                    s = next(x for x in self.signals if (x.timestamp, x.service, x.source, x.message) == identity)
                groups[(s.service, s.source, s.message)].append(s)
            summaries = [{"service": name, "source": kind, "message": msg[:800], "count": len(rows),
                          "first": min(r.timestamp for r in rows).isoformat(),
                          "last": max(r.timestamp for r in rows).isoformat(),
                          "signal_ids": [r.id for r in rows[:3]]} for (name, kind, msg), rows in groups.items()]
            # Interleave services so a noisy component does not fill the first page of groups.
            by_service = defaultdict(list)
            for group in summaries:
                by_service[group["service"]].append(group)
            summaries = [rows[i] for i in range(max(map(len, by_service.values()), default=0))
                         for rows in by_service.values() if i < len(rows)]
            overview = [{"service": name, "records": sum(g["count"] for g in rows),
                         "first": min(g["first"] for g in rows), "last": max(g["last"] for g in rows)}
                        for name, rows in by_service.items()]
            self.cache[key] = {"groups": summaries, "services_with_signals": overview,
                               "queried_services": services, "records": len(records), "truncated": truncated,
                               "incomplete": incomplete}
        result = self.cache[key]
        groups = result["groups"]
        if not groups:
            return ""
        return {**result, "groups": groups[offset:offset+5], "total_groups": len(groups),
                "next_offset": offset+5 if offset+5 < len(groups) else None,
                "remaining_log_budget": self.log_remaining, "start": start.isoformat(), "end": end.isoformat()}

    def service_state(self, service: str):
        self.validate_service(service)
        self.check()
        def get(kind, name=None, selector=None):
            args = ["kubectl", "--kubeconfig", self.settings.agent_reader_kubeconfig,
                    "--context", self.settings.agent_kube_context, "--namespace", self.settings.gcp_namespace,
                    "--request-timeout=10s", "get", kind]
            if name:
                args.append(name)
            if selector:
                args.extend(["-l", selector])
            args.extend(["-o", "json"])
            result = subprocess.run(args, capture_output=True, text=True,
                                    timeout=max(1, min(12, self.deadline-monotonic())))
            if result.returncode:
                raise RuntimeError("No se pudo leer el recurso de Kubernetes; comprueba permisos y contexto.")
            return json.loads(result.stdout)
        dep = get("deployment", name=service)
        selector = dep["spec"]["selector"].get("matchLabels", {})
        label = ",".join(f"{k}={v}" for k, v in selector.items())
        if not label:
            raise ValueError("Deployment sin selector de etiquetas.")
        pods = get("pods", selector=label).get("items", [])
        endpoints = get("endpointslices", selector=f"kubernetes.io/service-name={service}").get("items", [])
        return {"service": service, "observed_at": datetime.now(timezone.utc).isoformat(),
                "temporal_scope": "current_only_not_incident_history", "context": self.settings.agent_kube_context,
                "desired": dep["spec"].get("replicas", 1), "ready": dep.get("status", {}).get("readyReplicas", 0),
                "pods": [{"name": p["metadata"]["name"], "phase": p.get("status", {}).get("phase"),
                          "containers": [{"name": c["name"], "ready": c.get("ready"),
                                          "restarts": c.get("restartCount"), "state": c.get("state")}
                                         for c in p.get("status", {}).get("containerStatuses", [])]} for p in pods],
                "endpoints": [e for item in endpoints for e in item.get("endpoints", [])]}

    def service_metrics(self, service: str, metric: str = "cpu"):
        self.validate_service(service)
        self.check()
        metrics = {"cpu": "kubernetes.io/container/cpu/core_usage_time",
                   "memory": "kubernetes.io/container/memory/used_bytes"}
        if metric not in metrics:
            raise ValueError("Métrica no permitida.")
        import google.auth
        from google.auth.transport.requests import Request
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/monitoring.read"])
        credentials.refresh(Request())
        q = json.dumps
        filters = [f'metric.type={q(metrics[metric])}', 'resource.type="k8s_container"',
                   f'resource.labels.cluster_name={q(self.settings.gcp_cluster)}',
                   f'resource.labels.location={q(self.settings.gcp_location)}',
                   f'resource.labels.namespace_name={q(self.settings.gcp_namespace)}',
                   f'resource.labels.pod_name=starts_with({q(service + "-")})']
        response = httpx.get(
            f"https://monitoring.googleapis.com/v3/projects/{self.settings.google_cloud_project}/timeSeries",
            headers={"Authorization": f"Bearer {credentials.token}"}, timeout=15,
            params={"filter": " AND ".join(filters), "interval.startTime": self.request.start.isoformat(),
                    "interval.endTime": self.request.end.isoformat(), "pageSize": 5,
                    "aggregation.alignmentPeriod": "60s", "aggregation.perSeriesAligner": "ALIGN_RATE" if metric == "cpu" else "ALIGN_MEAN", "view": "FULL"})
        response.raise_for_status()
        data = response.json()
        return {"series": data.get("timeSeries", []), "truncated": bool(data.get("nextPageToken")),
                "mapping": "pod name prefix; verify ownership with service_state"} if data.get("timeSeries") else ""

    def search_documentation(self, query: str):
        self.check()
        if self.web_calls >= 2 or not isinstance(query, str) or not 3 <= len(query) <= 300:
            raise ValueError("Consulta externa inválida o presupuesto agotado.")
        # External search never receives full logs, addresses or environment identifiers.
        forbidden = [self.settings.google_cloud_project, self.settings.gcp_cluster, self.settings.gcp_namespace]
        if sanitize(query) != query or any(x and x.lower() in query.lower() for x in forbidden) or re.search(
                r"https?://|\b\d{1,3}(?:\.\d{1,3}){3}\b|@", query):
            raise ValueError("Usa una pregunta técnica genérica sin datos del entorno.")
        self.web_calls += 1
        response = httpx.post("https://api.tavily.com/search", timeout=15,
                              headers={"Authorization": f"Bearer {self.settings.tavily_api_key}"},
                              json={"query": query, "max_results": 3, "include_answer": False,
                                    "include_domains": ["cloud.google.com", "kubernetes.io", "grpc.io"]})
        response.raise_for_status()
        results = response.json().get("results", [])
        return {"results": [{"title": r.get("title"), "url": r.get("url"),
                             "content": sanitize(r.get("content", ""))[:1200]} for r in results]} if results else ""
