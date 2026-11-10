"""Interfaz mínima de LLM. Un solo método (JSON), fácil de simular en pruebas y de comparar entre modelos."""

from __future__ import annotations

import json
import re
from typing import Protocol

from .config import env


class ModelResponseError(ValueError):
    """Safe, machine-readable failure; never include the provider's raw response."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def error_details(exc: Exception) -> dict:
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    if not isinstance(code, str):
        code = ("timeout" if "timeout" in name.lower() or "deadline" in name.lower()
                else "authentication" if status in {401, 403}
                else "rate_limit" if status == 429
                else "invalid_response" if isinstance(exc, ValueError)
                else "provider_error")
    return {"code": code, "type": name, "http_status": status}


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
    def __init__(self, model: str | None = None, temperature: float = 0.0, *, effort: str | None = None):
        import anthropic

        self.client = anthropic.Anthropic(timeout=25.0, max_retries=0)
        self.model = model or env("TIDER_MODEL", "claude-sonnet-5-5")
        self.temperature = temperature
        self.effort = effort
        self.last_response_metadata: dict = {}

    def complete_text(self, agent: str, system: str, user: str, *, timeout: float | None = None) -> str:
        self.last_response_metadata = {}
        r = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user}],
            **({"timeout": timeout} if timeout is not None else {}),
            **({"output_config": {"effort": self.effort}} if getattr(self, "effort", None) else {}),
        )
        self.last_response_metadata = {
            "stop_reason": r.stop_reason,
            "input_tokens": r.usage.input_tokens,
            "output_tokens": r.usage.output_tokens,
        }
        if r.stop_reason == "max_tokens":
            raise ModelResponseError("truncated_response")
        return "".join(b.text for b in r.content if b.type == "text")

    def complete_json(self, agent: str, system: str, user: str, *, timeout: float | None = None) -> dict:
        text = self.complete_text(agent, system + "\nResponde SOLO con un objeto JSON válido.", user,
                                  timeout=timeout)
        try:
            result = parse_json(text)
            if not isinstance(result, dict):
                raise ValueError("Expected object")
            return result
        except ValueError as exc:
            raise ModelResponseError("invalid_json") from exc


class OpenAILLM:
    """Juez de otra familia (decisión 23). Misma interfaz `complete_json(agent, system, user, timeout)`.

    Requiere el extra `judge-openai` (`openai>=1`) y `OPENAI_API_KEY`; si falta algo, falla al construirse
    con un mensaje claro, antes de cualquier llamada. La clave nunca se guarda en la metadata."""

    def __init__(self, model: str | None = None, api_key: str | None = None, temperature: float = 0.0):
        key = api_key or env("OPENAI_API_KEY", "")
        self.model = model or env("JUDGE_MODEL", "")
        if not self.model:
            raise ValueError("Configura JUDGE_MODEL para el juez de OpenAI.")
        if not key:
            raise ValueError("Falta OPENAI_API_KEY para el juez de OpenAI (JUDGE_PROVIDER=openai).")
        try:
            import openai
        except ImportError as exc:
            raise ValueError(
                "El juez de OpenAI necesita el paquete `openai`: instala el extra `tider[judge-openai]`."
            ) from exc
        self.client = openai.OpenAI(api_key=key, timeout=25.0, max_retries=0)
        self.temperature = temperature
        self.last_response_metadata: dict = {}

    def complete_json(self, agent: str, system: str, user: str, *, timeout: float | None = None) -> dict:
        self.last_response_metadata = {}
        r = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system + "\nResponde SOLO con un objeto JSON válido."},
                {"role": "user", "content": user},
            ],
            **({"timeout": timeout} if timeout is not None else {}),
        )
        choice = r.choices[0]
        usage = getattr(r, "usage", None)
        self.last_response_metadata = {
            "provider": "openai",
            "model": getattr(r, "model", self.model),
            "stop_reason": choice.finish_reason,
            "input_tokens": getattr(usage, "prompt_tokens", None),
            "output_tokens": getattr(usage, "completion_tokens", None),
        }
        if choice.finish_reason == "length":
            raise ModelResponseError("truncated_response")
        try:
            result = parse_json(choice.message.content or "")
            if not isinstance(result, dict):
                raise ValueError("Expected object")
            return result
        except ValueError as exc:
            raise ModelResponseError("invalid_json") from exc


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
