"""Traza por corrida del pipeline v2 (A09): lo necesario para re-puntuar sin llamar a ningún proveedor.

Una traza es un JSON con:
* `entradas`: la solicitud, `t0` y la evidencia congelada del barrido (copia de lo leído, neutralizada P9);
* `hashes`: de los prompts de sistema (`sha256` del texto exacto), del catálogo de firmas, del manifiesto
  del Lake y del protocolo de la campaña;
* `llamadas`: cada llamada a un LLM en orden, con el hash del sistema y de la entrada, la entrada (texto ya
  enmascarado y neutralizado: es lo que recibió el proveedor), la salida JSON y la metadata de uso;
* `corridas`: el `Analysis` completo de cada brazo y repetición, con sus ids de evidencia citados.

Nunca guarda claves: `RecordingLLM` solo copia `last_response_metadata` (proveedor, modelo, tokens), y
`settings_publicos` lista campos permitidos. El ground truth no entra: quien arma la traza no lo conoce.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRACE_VERSION = 1
# Campos de Settings que pueden ir a la traza (lista permitida; nunca claves ni rutas con credenciales).
PUBLIC_SETTINGS = (
    "pipeline", "evidence_mode", "gcp_namespace", "llm_provider", "tider_model", "judge_provider",
    "judge_model", "agent_timeout_seconds", "sweep_quota_per_service", "sweep_info_quota_per_service",
    "healthy_traffic_min_lines", "anomaly_bucket_seconds", "anomaly_min_events", "lifecycle_grace_seconds",
    "judge_min_coverage", "recorder_interval_seconds",
)


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def canonical_hash(obj: Any) -> str:
    return sha256_text(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str))


def prompt_hashes() -> dict[str, str]:
    """Hash de los prompts de sistema del pipeline v2, tal como se envían."""
    from .pipeline_v2 import INVESTIGATOR_SYSTEM, JUDGE_SYSTEM

    return {"investigator": sha256_text(INVESTIGATOR_SYSTEM), "judge": sha256_text(JUDGE_SYSTEM)}


def settings_publicos(settings) -> dict:
    return {k: getattr(settings, k, None) for k in PUBLIC_SETTINGS}


class RecordingLLM:
    """Envuelve un cliente con `complete_json` y registra cada llamada en `log` (compartible entre clientes).

    Conserva la interfaz que inspecciona el pipeline (`timeout` solo si el cliente interno lo acepta),
    `model` y `last_response_metadata`."""

    def __init__(self, inner, log: list[dict], *, role: str):
        self.inner, self.log, self.role = inner, log, role
        self.tag: str | None = None  # brazo/repetición en curso; lo fija quien orquesta
        self.model = getattr(inner, "model", None)
        self._timeout = "timeout" in inspect.signature(inner.complete_json).parameters

    @property
    def last_response_metadata(self) -> dict:
        return dict(getattr(self.inner, "last_response_metadata", {}) or {})

    def complete_json(self, agent: str, system: str, user: str, *, timeout: float | None = None) -> dict:
        entry = {"n": len(self.log) + 1, "corrida": self.tag, "role": self.role, "agent": agent, "model": self.model,
                 "system_sha256": sha256_text(system), "input_sha256": sha256_text(user), "input": user}
        self.log.append(entry)
        try:
            out = (self.inner.complete_json(agent, system, user, timeout=timeout) if self._timeout
                   else self.inner.complete_json(agent, system, user))
        except Exception as exc:
            entry["error"] = type(exc).__name__
            raise
        finally:
            meta = self.last_response_metadata
            entry["metadata"] = {k: meta.get(k) for k in ("provider", "model", "stop_reason", "input_tokens",
                                                          "output_tokens") if k in meta}
        entry["output"] = out
        entry["output_sha256"] = canonical_hash(out)
        return out


def evidence_ids(analysis: dict) -> dict:
    """Ids citados por la primera hipótesis y por las firmas CONFIRMADAS (para auditar sin el proveedor)."""
    hips = analysis.get("hipotesis") or []
    firmas = (analysis.get("investigation") or {}).get("firmas") or []
    return {"hipotesis_1": [c["id"] for c in (hips[0]["citas"] if hips else [])],
            "confirmadas": sorted({i for f in firmas if f.get("veredicto") == "CONFIRMADA"
                                   for i in f.get("evidencia_ids") or []})}


def build_trace(*, case_id: str, request: dict, t0: datetime, evidencia_congelada: dict | None,
                corridas: list[dict], llamadas: list[dict], catalog_hash: str, lake_manifest: dict | None,
                protocol_hash: str, settings=None, extra: dict | None = None) -> dict:
    """`corridas`: [{"brazo", "repeticion", "elapsed_seconds", "analysis": dict}]."""
    return {
        "trace_version": TRACE_VERSION,
        "case_id": case_id,
        "creada": datetime.now(timezone.utc).isoformat(),
        "entradas": {"request": request, "t0": t0.isoformat(), "evidencia_congelada": evidencia_congelada},
        "hashes": {
            "prompts": prompt_hashes(),
            "catalogo": catalog_hash,
            "lake_manifest": (lake_manifest or {}).get("hash"),
            "protocolo": protocol_hash,
            "evidencia_congelada": canonical_hash(evidencia_congelada) if evidencia_congelada else None,
        },
        "settings": settings_publicos(settings) if settings is not None else {},
        "llamadas": llamadas,
        "corridas": [{**c, "evidence_ids": evidence_ids(c["analysis"])} for c in corridas],
        **(extra or {}),
    }


def write_trace(trace: dict, folder: str | Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{trace['case_id']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(trace, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def read_trace(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
