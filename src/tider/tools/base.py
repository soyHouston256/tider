"""Herramientas de SOLO LECTURA. Cada una devuelve {summary, kind, ref, data}: el investigador cita eso como evidencia.
Un fallo o una consulta vacía NO son evidencia: se marcan kind=error / kind=empty y el juez no los cuenta."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

EMPTY = {"", "[]", "{}", "null"}


@dataclass
class Tool:
    name: str
    description: str
    kind: str
    fn: Callable[..., str | dict]


def to_result(out: Any, kind: str, ref: str | None) -> dict:
    data = out if isinstance(out, dict) else None
    summary = json.dumps(out, ensure_ascii=False) if data is not None else str(out)
    if summary.strip() in EMPTY:
        return {"summary": "sin resultados", "kind": "empty", "ref": ref, "data": None}
    return {"summary": summary[:3000], "kind": kind, "ref": ref, "data": data}


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {t.name: t for t in (tools or [])}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def describe(self) -> str:
        return "\n".join(f"- {t.name}: {t.description}" for t in self._tools.values())

    def call(
        self, tool: str, /, **kwargs
    ) -> dict:  # posicional: las herramientas reciben args llamados "name"
        if tool not in self._tools:
            return {"summary": f"herramienta desconocida: {tool}", "kind": "error", "ref": None, "data": None}
        t, ref = self._tools[tool], f"{tool}({json.dumps(kwargs, sort_keys=True)})"
        try:
            out = t.fn(**kwargs)
        except Exception as e:  # el agente se recupera del error, pero un error no respalda ninguna hipótesis
            return {
                "summary": f"ERROR {type(e).__name__}: {e}"[:3000],
                "kind": "error",
                "ref": ref,
                "data": None,
                "error_type": type(e).__name__,
            }
        return to_result(out, t.kind, ref)
