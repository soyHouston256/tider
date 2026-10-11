"""Herramientas de SOLO LECTURA. Cada una devuelve {summary, kind, ref}: el investigador cita eso como evidencia."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    kind: str
    fn: Callable[..., str]


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {t.name: t for t in (tools or [])}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def describe(self) -> str:
        return "\n".join(f"- {t.name}: {t.description}" for t in self._tools.values())

    def call(self, name: str, **kwargs) -> dict:
        if name not in self._tools:
            return {"summary": f"herramienta desconocida: {name}", "kind": "error", "ref": None}
        t = self._tools[name]
        try:
            out = t.fn(**kwargs)
        except Exception as e:  # el agente debe poder recuperarse de un error de herramienta
            out = f"ERROR {type(e).__name__}: {e}"
        return {"summary": out[:3000], "kind": t.kind, "ref": f"{name}({json.dumps(kwargs, sort_keys=True)})"}


class FixtureRegistry(ToolRegistry):
    """Reproduce telemetría grabada: eval/fixtures/<escenario>.json -> {"tool_name": "salida", ...}.
    Permite evaluar de forma reproducible, sin clúster."""
    KINDS = {"prom": "metric", "kube": "k8s", "traces": "trace", "logs": "log", "rollout": "deploy"}

    def __init__(self, fixture_path: str | Path):
        super().__init__()
        self.data = json.loads(Path(fixture_path).read_text())

    def describe(self) -> str:
        return "\n".join(f"- {name}" for name in self.data)

    def call(self, name: str, **kwargs) -> dict:
        if name in self.data:
            kind = self.KINDS.get(name.split("_")[0], "k8s")
            return {"summary": self.data[name], "kind": kind, "ref": f"{name}({json.dumps(kwargs, sort_keys=True)})"}
        return {"summary": f"sin datos grabados para {name}", "kind": "error", "ref": None}
