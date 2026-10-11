"""Ejecutor de runbooks: arma el comando desde plantillas fijas (nunca texto libre del LLM)."""
from __future__ import annotations
import re, subprocess
from ..config import dry_run

NAME = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


def build(action: str, params: dict, namespace: str) -> list[str]:
    dep = params.get("deployment", "")
    if not NAME.match(dep) or not NAME.match(namespace):
        raise ValueError(f"nombre inválido: {dep!r}/{namespace!r}")
    base = ["kubectl", "-n", namespace]
    if action == "rollout-restart":
        return base + ["rollout", "restart", f"deployment/{dep}"]
    if action == "rollout-undo":
        return base + ["rollout", "undo", f"deployment/{dep}"]
    if action == "scale":
        return base + ["scale", f"deployment/{dep}", f"--replicas={int(params['replicas'])}"]
    raise ValueError(f"acción no soportada: {action}")


def execute(action: str, params: dict, namespace: str) -> dict:
    cmd = build(action, params, namespace)
    if dry_run():
        return {"executed": False, "dry_run": True, "command": " ".join(cmd)}
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return {"executed": r.returncode == 0, "dry_run": False, "command": " ".join(cmd),
            "output": (r.stdout or r.stderr)[:1000]}
