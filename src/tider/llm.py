"""Interfaz mínima de LLM. Un solo método (JSON), fácil de simular en pruebas y de comparar entre modelos."""

from __future__ import annotations

import json
import re
from typing import Protocol

from .config import env


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"La respuesta no contiene JSON: {text[:200]}")
    return json.loads(text[start : end + 1])


class LLM(Protocol):
    def complete_json(self, agent: str, system: str, user: str) -> dict: ...
    def complete_text(self, agent: str, system: str, user: str) -> str: ...


class AnthropicLLM:
    def __init__(self, model: str | None = None, temperature: float = 0.0):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model or env("TIDER_MODEL", "claude-sonnet-5-5")
        self.temperature = temperature

    def complete_text(self, agent: str, system: str, user: str) -> str:
        r = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in r.content if b.type == "text")

    def complete_json(self, agent: str, system: str, user: str) -> dict:
        return parse_json(
            self.complete_text(agent, system + "\nResponde SOLO con un objeto JSON válido.", user)
        )


class ScriptedLLM:
    """LLM de prueba: por agente devuelve un dict/str fijo, una lista (se consume en orden) o un callable."""

    def __init__(self, script: dict[str, object]):
        self.script = {k: (list(v) if isinstance(v, list) else v) for k, v in script.items()}
        self.calls: list[tuple[str, str]] = []

    def _next(self, agent: str, user: str):
        self.calls.append((agent, user))
        v = self.script[agent]
        if callable(v):
            return v(user)
        if isinstance(v, list):
            return v.pop(0) if len(v) > 1 else v[0]
        return v

    def complete_json(self, agent, system, user):
        return self._next(agent, user)

    def complete_text(self, agent, system, user):
        v = self._next(agent, user)
        return v if isinstance(v, str) else json.dumps(v)
