"""Herramientas de SOLO LECTURA. Cada una devuelve {summary, kind, ref, data}: el investigador cita eso como evidencia.
Un fallo o una consulta vacía NO son evidencia: se marcan kind=error / kind=empty y el juez no los cuenta."""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
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


class FixtureRegistry(ToolRegistry):
    """Reproduce telemetría grabada (eval/fixtures/<escenario>.json) con las MISMAS herramientas que producción:
    mismo describe(), mismos tipos y misma firma, así el prompt del eval es el de producción. Formato por herramienta:
      "tool": "salida" | {...}                                       -> cualquier argumento
      "tool": [{"match": {"arg": "subcadena" | [alternativas]}, "out": "salida" | {...}}, ...]  -> primera que coincida
    Herramientas o argumentos sin grabación devuelven "sin resultados" (kind=empty), como una consulta vacía.
    Se graban con scripts/record_fixture.py."""

    def __init__(self, fixture_path: str | Path, spec: ToolRegistry | None = None):
        from . import default_registry

        super().__init__(list((spec or default_registry())._tools.values()))
        self.data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))

    def call(self, tool: str, /, **kwargs) -> dict:
        if tool not in self._tools:
            return {"summary": f"herramienta desconocida: {tool}", "kind": "error", "ref": None, "data": None}
        t, ref = self._tools[tool], f"{tool}({json.dumps(kwargs, sort_keys=True)})"
        try:
            inspect.signature(t.fn).bind(**kwargs)  # args inválidos fallan igual que en producción
        except TypeError as e:
            return {"summary": f"ERROR TypeError: {e}", "kind": "error", "ref": ref, "data": None}
        return to_result(self._lookup(self.data.get(tool), kwargs) or "", t.kind, ref)

    @staticmethod
    def _lookup(rec: Any, kwargs: dict) -> Any:
        if rec is None or isinstance(rec, (str, dict)):
            return rec

        def hit(arg: str, want: Any) -> bool:
            value = str(kwargs.get(arg, "")).lower()
            return any(str(w).lower() in value for w in (want if isinstance(want, list) else [want]))

        return next((e["out"] for e in rec if all(hit(a, w) for a, w in e.get("match", {}).items())), None)
