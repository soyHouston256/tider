"""kubectl de solo lectura. Tres barreras, aunque el LLM pida otra cosa:
1. los argumentos del LLM se validan (nombres DNS-1123, tipos y namespaces permitidos), así no pueden colar flags;
2. el guardia solo deja pasar verbos de lectura y flags de una lista cerrada (también en forma --flag=valor);
3. kubectl corre con la credencial del lector (TIDER_READER_KUBECONFIG o la ServiceAccount tider-reader del pod)."""
from __future__ import annotations
import json, os, re, subprocess
from datetime import datetime, timezone
from functools import lru_cache
from ..config import env
from ..decision.policy import load_policy
from .base import Tool

READ_VERBS = {"get", "describe", "logs", "top"}
READ_ROLLOUT = {"history", "status"}
FLAGS = {"-n", "-o", "--sort-by", "--previous", "--tail", "--timeout"}   # lista cerrada: cualquier otro flag se rechaza
KINDS = {"pod", "deployment", "replicaset", "statefulset", "service", "configmap"}
NAME = re.compile(r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$")


def guard(args: list[str]) -> None:
    if not args:
        raise PermissionError("kubectl vacío")
    verb = args[0]
    if verb == "rollout":
        if len(args) < 2 or args[1] not in READ_ROLLOUT:
            raise PermissionError(f"rollout {args[1:2]} no permitido en modo lectura")
    elif verb not in READ_VERBS:
        raise PermissionError(f"verbo '{verb}' no permitido en modo lectura")
    for a in args[1:]:
        if a.startswith("-") and a.split("=", 1)[0] not in FLAGS:
            raise PermissionError(f"flag no permitido: {a.split('=', 1)[0]}")
    i = args.index("-n") if "-n" in args else -1
    if i < 0 or i + 1 >= len(args) or args[i + 1] not in _namespaces():
        raise PermissionError("kubectl de lectura exige -n con un namespace permitido")


@lru_cache(maxsize=1)
def _namespaces() -> frozenset[str]:
    return frozenset(load_policy()["namespaces"])


def _name(value: object, what: str = "nombre") -> str:
    if not isinstance(value, str) or not NAME.match(value):
        raise ValueError(f"{what} inválido: {value!r}")
    return value


def _kind(value: object) -> str:
    k = str(value).lower().rstrip("s")
    if k not in KINDS:
        raise ValueError(f"tipo no permitido: {value!r} (usa {', '.join(sorted(KINDS))})")
    return k


def _ns(namespace: object) -> list[str]:
    if namespace not in _namespaces():
        raise PermissionError(f"namespace {namespace!r} fuera de la lista permitida")
    return ["-n", str(namespace)]


def _run(args: list[str], timeout: int = 20) -> str:
    guard(args)
    kc = env("TIDER_READER_KUBECONFIG")
    r = subprocess.run(["kubectl", *args], capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "KUBECONFIG": kc} if kc else None)
    if r.returncode != 0:   # un fallo de kubectl no es evidencia: sube como error
        raise RuntimeError((r.stderr or r.stdout).strip()[:500])
    return r.stdout


def kubectl(args: list[str], timeout: int = 20) -> str:
    return _run(args, timeout)[:6000]


def deployment_status(deployment: str, namespace: str = "otel-demo") -> dict:
    """Datos estructurados que el decisor verifica sin LLM: réplicas, revisión, edad del último rollout y HPA."""
    dep_name, ns = _name(deployment, "deployment"), _ns(namespace)
    dep = json.loads(_run(["get", "deployment", dep_name, "-o", "json", *ns]))
    rev = dep["metadata"].get("annotations", {}).get("deployment.kubernetes.io/revision", "0")
    own = [rs for rs in json.loads(_run(["get", "replicasets", "-o", "json", *ns]))["items"]
           if any(o.get("kind") == "Deployment" and o.get("name") == dep_name for o in rs["metadata"].get("ownerReferences", []))]
    cur = next((rs for rs in own if rs["metadata"].get("annotations", {}).get("deployment.kubernetes.io/revision") == rev), None)
    age = None
    if cur:
        created = datetime.fromisoformat(cur["metadata"]["creationTimestamp"].replace("Z", "+00:00"))
        age = round((datetime.now(timezone.utc) - created).total_seconds() / 60)
    try:
        hpas = json.loads(_run(["get", "hpa", "-o", "json", *ns]))["items"]
        hpa = next((h["metadata"]["name"] for h in hpas if h["spec"]["scaleTargetRef"].get("name") == dep_name), None)
    except RuntimeError:
        hpa = "desconocido"   # sin permiso o sin API: el decisor lo trata como "hay HPA" y no escala
    return {"deployment": dep_name, "replicas": dep["spec"].get("replicas", 1),
            "ready": dep.get("status", {}).get("readyReplicas", 0), "revision": int(rev), "revisions": len(own),
            "last_rollout_age_minutes": age, "hpa": hpa,
            "images": [c["image"] for c in dep["spec"]["template"]["spec"]["containers"]]}


def rollout_status(deployment: str, namespace: str = "otel-demo", timeout_s: int = 300) -> str:
    """Lo usa el verificador (no el LLM): espera a que el rollout termine o falla."""
    return kubectl(["rollout", "status", f"deployment/{_name(deployment, 'deployment')}", f"--timeout={int(timeout_s)}s",
                    *_ns(namespace)], timeout=int(timeout_s) + 15)


def tools() -> list[Tool]:
    return [
        Tool("kube_get_pods", "Estado de pods. args: namespace", "k8s",
             lambda namespace="otel-demo": kubectl(["get", "pods", "-o", "wide", *_ns(namespace)])),
        Tool("kube_describe", f"kubectl describe. args: kind ({'|'.join(sorted(KINDS))}), name, namespace", "k8s",
             lambda kind, name, namespace="otel-demo": kubectl(["describe", _kind(kind), _name(name), *_ns(namespace)])),
        Tool("kube_events", "Eventos recientes. args: namespace", "k8s",
             lambda namespace="otel-demo": kubectl(["get", "events", "--sort-by=.lastTimestamp", *_ns(namespace)])),
        Tool("kube_logs_previous", "Logs del contenedor anterior. args: pod, namespace", "log",
             lambda pod, namespace="otel-demo": kubectl(["logs", _name(pod, "pod"), "--previous", "--tail=100", *_ns(namespace)])),
        Tool("rollout_history", "Historial de rollouts. args: deployment, namespace", "deploy",
             lambda deployment, namespace="otel-demo": kubectl(["rollout", "history", f"deployment/{_name(deployment, 'deployment')}", *_ns(namespace)])),
        Tool("deployment_status", "Réplicas, revisión, minutos desde el último rollout y HPA (JSON). args: deployment, namespace. "
             "El decisor lo EXIGE para runbook:rollout-undo y runbook:scale", "deploy", deployment_status),
    ]
