"""Fakes del pipeline v2: kubectl simulado y Cloud Logging simulado sobre fixtures recortadas de PM-0N.

Las líneas de `fixtures/postmortems/*.json` se copiaron tal cual de los exports de los postmortems
(Context Lake V3), recortando campos y sin líneas con datos de tarjeta o correo. Las ClusterIP de
paymentservice (10.49.5.115), cartservice (10.49.8.13), productcatalogservice (10.49.2.83),
currencyservice (10.49.1.235) y adservice (10.49.10.33) son las observadas en PM-04/01/02/03/05;
las demás son inventadas para las pruebas (marcadas abajo).
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

FIXTURES = Path(__file__).parent / "fixtures" / "postmortems"
NS = "boutique"

# nombre -> (ClusterIP, puerto del Service). `None` = sin Service (loadgenerator).
SERVICES = {
    "adservice": ("10.49.10.33", 9555),
    "cartservice": ("10.49.8.13", 7070),
    "checkoutservice": ("10.49.3.10", 5050),  # inventada
    "currencyservice": ("10.49.1.235", 7000),
    "emailservice": ("10.49.4.20", 5000),  # inventada
    "frontend": ("10.49.0.80", 80),  # inventada
    "loadgenerator": None,
    "paymentservice": ("10.49.5.115", 50051),
    "productcatalogservice": ("10.49.2.83", 3550),
    "recommendationservice": ("10.49.9.8", 8080),  # inventada
    "redis-cart": ("10.49.7.20", 6379),  # inventada
    "shippingservice": ("10.49.6.40", 50051),  # inventada; comparte puerto con paymentservice
}
PROXY = ("chaosforge-proxy", "10.49.7.99", 6379)  # inventada; comparte puerto con redis-cart


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeCluster:
    """Estado del namespace en función del tiempo. `overrides(t, name)` puede cambiar réplicas o env."""

    def __init__(self, services=None, proxy=False, overrides=None):
        self.services = dict(services or SERVICES)
        self.proxy = proxy
        self.overrides = overrides or (lambda t, name: {})
        self.calls: list[list[str]] = []

    def _workload(self, t, name):
        o = {"replicas": 1, "ready": 1, "env": [], "image": f"img/{name}:v0.10.4", **self.overrides(t, name)}
        kind = "StatefulSet" if o.get("statefulset") else "Deployment"
        item = {
            "kind": kind,
            "metadata": {"name": name, "generation": o.get("generation", 1)},
            "spec": {
                "replicas": o["replicas"],
                "selector": {"matchLabels": {"app": name}},
                "template": {
                    "spec": {
                        "containers": [
                            {"name": "server", "image": o["image"], "env": o["env"], "resources": {}}
                        ]
                    }
                },
            },
            "status": {"readyReplicas": o["ready"]},
        }
        return kind, item, o

    def raw(self, t, kind):
        items = []
        names = list(self.services) + ([PROXY[0]] if self.proxy else [])
        for name in names:
            wkind, item, o = self._workload(t, name)
            svc = self.services.get(name) if name != PROXY[0] else (PROXY[1], PROXY[2])
            if kind == "deployments" and wkind == "Deployment":
                items.append(item)
            elif kind == "statefulsets" and wkind == "StatefulSet":
                items.append(item)
            elif kind == "services" and svc:
                items.append(
                    {"metadata": {"name": name}, "spec": {"clusterIP": svc[0], "ports": [{"port": svc[1]}]}}
                )
            elif kind == "endpointslices" and svc:
                ready = o["ready"]
                items.append(
                    {
                        "metadata": {"labels": {"kubernetes.io/service-name": name}},
                        "endpoints": [
                            {"addresses": [f"10.48.0.{i + 10}"], "conditions": {"ready": True}}
                            for i in range(ready)
                        ]
                        or None,
                    }
                )
            elif kind == "pods":
                for i in range(o["ready"]):
                    items.append(
                        {
                            "metadata": {"name": f"{name}-7987f697ff-p{i:04}", "labels": {"app": name}},
                            "status": {
                                "phase": "Running",
                                "podIP": f"10.48.1.{i + 100}",
                                "containerStatuses": [
                                    {"name": "server", "ready": True, "restartCount": 0, "state": {}}
                                ],
                            },
                        }
                    )
        return {"items": items}


class FakeKubectl:
    """Sustituto de `subprocess.run` para `kubectl get <kind> -o json`; registra cada llamada."""

    def __init__(self, cluster: FakeCluster, clock, fail_kinds=()):
        self.cluster, self.clock, self.fail_kinds = cluster, clock, set(fail_kinds)

    def __call__(self, args, **kwargs):
        self.cluster.calls.append(list(args))
        kind = args[args.index("get") + 1]
        if kind in self.fail_kinds:
            return SimpleNamespace(returncode=1, stdout="", stderr="forbidden")
        return SimpleNamespace(
            returncode=0, stdout=json.dumps(self.cluster.raw(self.clock(), kind)), stderr=""
        )


def record(recorder_cls, db_path, cluster, start, end, step=timedelta(seconds=30), **kwargs):
    """Llena un registrador con instantáneas cada `step` entre `start` y `end` usando kubectl simulado."""
    now = [start]
    recorder = recorder_cls(
        db_path,
        NS,
        "reader.kubeconfig",
        "lab",
        run=FakeKubectl(cluster, lambda: now[0], **kwargs),
        now=lambda: now[0],
        retention=timedelta(days=3650),
    )
    while now[0] <= end:
        recorder.capture()
        now[0] += step
    return recorder


def _entry(raw):
    payload = raw.get("jsonPayload", raw.get("textPayload", ""))
    return SimpleNamespace(
        payload=payload,
        labels=raw.get("labels", {}),
        resource=raw.get("resource", {}),
        severity=raw.get("severity", "DEFAULT"),
        timestamp=ts(raw["timestamp"]),
    )


_RANK = ["DEFAULT", "DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY"]


class FakeLogging:
    """Cliente con la interfaz de `BoundedLoggingClient` que aplica, sobre las fixtures, los filtros que
    construye el código real (servicio, ventana, severidad)."""

    instances: list = []

    def __init__(self, rows):
        self.rows = rows
        self.filters: list[str] = []

    def __call__(self, project, deadline, client=None):  # se usa como clase
        return self

    def list_entries(self, filter_, order_by, page_size, max_results):
        self.filters.append(filter_)
        start = ts(re.search(r'timestamp ?>= ?"([^"]+)"', filter_)[1])
        end = ts(re.search(r'timestamp ?<= ?"([^"]+)"', filter_)[1])
        apps = re.findall(r'labels\."k8s-pod/app"="([^"]+)"', filter_)
        sev = re.search(r"severity(>=|<)([A-Z]+)", filter_)
        out = []
        for raw in self.rows:
            entry = _entry(raw)
            if not start <= entry.timestamp <= end:
                continue
            if apps and entry.labels.get("k8s-pod/app") not in apps:
                continue
            if sev:
                rank, limit = _RANK.index(entry.severity), _RANK.index(sev[2])
                if (sev[1] == ">=" and rank < limit) or (sev[1] == "<" and rank >= limit):
                    continue
            out.append(entry)
        out.sort(key=lambda e: e.timestamp, reverse="desc" in order_by)
        return iter(out[:max_results])

    def close(self):
        pass


def install_logging(monkeypatch, log_rows, event_rows):
    logs, events = FakeLogging(log_rows), FakeLogging(event_rows)
    monkeypatch.setattr("tider.console.providers.logging_sdk.BoundedLoggingClient", logs)
    monkeypatch.setattr("tider.console.providers.kubernetes_events.BoundedLoggingClient", events)
    return logs, events


def utc(h, m, s=0):
    return datetime(2026, 11, 9, h, m, s, tzinfo=timezone.utc)
