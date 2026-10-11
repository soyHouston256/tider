"""kubectl de solo lectura. El guardia rechaza cualquier verbo fuera de la lista, aunque el LLM lo pida."""
from __future__ import annotations
import subprocess
from .base import Tool

READ_VERBS = {"get", "describe", "logs", "top"}
READ_ROLLOUT = {"history", "status"}
BAD_FLAGS = {"--force", "-f", "--token", "--as", "--kubeconfig"}


def guard(args: list[str]) -> None:
    if not args:
        raise PermissionError("kubectl vacío")
    verb = args[0]
    if verb == "rollout":
        if len(args) < 2 or args[1] not in READ_ROLLOUT:
            raise PermissionError(f"rollout {args[1:2]} no permitido en modo lectura")
    elif verb not in READ_VERBS:
        raise PermissionError(f"verbo '{verb}' no permitido en modo lectura")
    if any(a in BAD_FLAGS for a in args):
        raise PermissionError("flag no permitido")


def kubectl(args: list[str], timeout: int = 20) -> str:
    guard(args)
    r = subprocess.run(["kubectl", *args], capture_output=True, text=True, timeout=timeout)
    return (r.stdout or r.stderr)[:6000]


def tools() -> list[Tool]:
    ns = lambda n: ["-n", n]
    return [
        Tool("kube_get_pods", "Estado de pods. args: namespace", "k8s",
             lambda namespace="otel-demo": kubectl(["get", "pods", "-o", "wide", *ns(namespace)])),
        Tool("kube_describe", "kubectl describe. args: kind, name, namespace", "k8s",
             lambda kind, name, namespace="otel-demo": kubectl(["describe", kind, name, *ns(namespace)])),
        Tool("kube_events", "Eventos recientes. args: namespace", "k8s",
             lambda namespace="otel-demo": kubectl(["get", "events", "--sort-by=.lastTimestamp", *ns(namespace)])),
        Tool("kube_logs_previous", "Logs del contenedor anterior. args: pod, namespace", "log",
             lambda pod, namespace="otel-demo": kubectl(["logs", pod, "--previous", "--tail=100", *ns(namespace)])),
        Tool("rollout_history", "Historial de rollouts. args: deployment, namespace", "deploy",
             lambda deployment, namespace="otel-demo": kubectl(["rollout", "history", f"deployment/{deployment}", *ns(namespace)])),
    ]
