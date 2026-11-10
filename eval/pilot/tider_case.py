"""Corre Tider v2 sobre la ventana de un caso y escribe su traza (A09). Se ejecuta en un proceso aparte.

El runner lo lanza como `python -m eval.pilot.tider_case --spec <spec.json> --out <carpeta>` con un entorno
sin la URL de administración de ChaosForge ni la carpeta del ground truth: este proceso solo conoce la
solicitud (síntoma neutro + ventana + t0), el clúster de solo lectura, Cloud Logging, el registrador y el
Lake. Por qué en proceso (PipelineV2) y no por la API de la consola: así se graban las entradas y salidas
exactas de cada llamada LLM, se congela la evidencia del barrido una sola vez y todos los brazos y
repeticiones del caso leen exactamente la misma evidencia.

`spec` = {"case_id", "request": {...AnalyzeRequest}, "t0": iso, "brazos": ["reglas", "tider"],
          "repeticiones": {"n": 3, "cuando": "mas_de_una_firma_confirmada"}, "protocol_hash": str}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Callable

from tider.console.models import AnalyzeRequest
from tider.console.pipeline_v2 import PipelineV2
from tider.console.signatures import cargar_catalogo
from tider.console.topology import neutralizar
from tider.console.trace import RecordingLLM, build_trace, write_trace

GRAVES = {"WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY"}
# El proceso de Tider nunca debe ver estas variables (las quita el runner; aquí se comprueba).
FORBIDDEN_ENV = ("CHAOSFORGE_ADMIN_URL", "PILOT_GT_DIR")


def store_confirmed(analysis: dict) -> list[str]:
    """Firmas CONFIRMADAS sobre la tienda (los auxiliares no cuentan como causa)."""
    auxiliares = {n["servicio"] for n in analysis.get("nodos") or [] if n.get("tipo") == "auxiliar"}
    return [f"{f['firma_id']}@{f['entidad']}" for f in (analysis.get("investigation") or {}).get("firmas") or []
            if f.get("veredicto") == "CONFIRMADA" and f["entidad"].split("->")[0] not in auxiliares]


def symptom(barrido, analysis: dict) -> dict:
    """Criterio de admisión (2): alguna línea WARNING o más grave de un servicio de la tienda en [t0, fin]."""
    auxiliares = {n["servicio"] for n in analysis.get("nodos") or [] if n.get("tipo") == "auxiliar"}
    con_errores = sorted(f.servicio for f in barrido.filas if f.servicio not in auxiliares
                         and sum(v for k, v in f.severidades.items() if k.upper() in GRAVES) > 0)
    return {"sintoma": bool(con_errores), "servicios_con_errores": con_errores}


def run_case(spec: dict, *, settings, lake, sweeper: Callable, investigator=None, judge=None,
             catalogo=None) -> dict:
    """Devuelve la traza. `sweeper(request) -> Barrido` se llama una sola vez (evidencia congelada)."""
    request = AnalyzeRequest(**spec["request"])
    t0 = datetime.fromisoformat(spec["t0"])
    catalogo = catalogo or cargar_catalogo()
    cache: dict = {}

    def frozen(req):
        if "barrido" not in cache:
            cache["barrido"] = sweeper(req)
        return cache["barrido"]

    llamadas: list[dict] = []
    corridas: list[dict] = []
    inv = RecordingLLM(investigator, llamadas, role="investigator") if investigator is not None else None
    jud = RecordingLLM(judge, llamadas, role="judge") if judge is not None else None

    def correr(brazo: str, rep: int):
        tag = f"{brazo}#{rep}"
        for client in (inv, jud):
            if client is not None:
                client.tag = tag
        con_llm = brazo == "tider"
        if con_llm and (inv is None or jud is None):
            raise ValueError("El brazo tider necesita Investigador y Juez.")
        pipe = PipelineV2(settings, lake, investigator=inv if con_llm else None, judge=jud if con_llm else None,
                          sweeper=frozen, catalogo=catalogo)
        started = monotonic()
        try:
            analysis = json.loads(pipe.run(request).model_dump_json())
            error = None
        except Exception as exc:  # error técnico: cuenta como fallo al puntuar, no como exclusión
            analysis, error = None, f"{type(exc).__name__}: {exc}"[:300]
        corridas.append({"brazo": brazo, "repeticion": rep, "elapsed_seconds": round(monotonic() - started, 3),
                         "error": error, "analysis": analysis})
        return analysis

    brazos = spec.get("brazos") or ["reglas", "tider"]
    for brazo in brazos:
        primera = correr(brazo, 1)
        rep_cfg = spec.get("repeticiones") or {}
        if (brazo == "tider" and primera is not None and rep_cfg.get("cuando") == "mas_de_una_firma_confirmada"
                and len(store_confirmed(primera)) > 1):
            for rep in range(2, int(rep_cfg.get("n", 3)) + 1):
                correr(brazo, rep)

    barrido = cache.get("barrido")
    congelada = json.loads(neutralizar(barrido.model_dump_json())) if barrido is not None else None
    primera_ok = next((c["analysis"] for c in corridas if c["analysis"]), {}) or {}
    extra = {"admision": symptom(barrido, primera_ok) if barrido is not None else {"sintoma": False,
                                                                                    "servicios_con_errores": []},
             "firmas_confirmadas_tienda": store_confirmed(primera_ok)}
    manifest = lake.manifest() if lake is not None and hasattr(lake, "manifest") else None
    return build_trace(case_id=spec["case_id"], request=json.loads(request.model_dump_json()), t0=t0,
                       evidencia_congelada=congelada, corridas=corridas, llamadas=llamadas,
                       catalog_hash=catalogo.hash, lake_manifest=manifest, protocol_hash=spec["protocol_hash"],
                       settings=settings, extra=extra)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - proceso real del laboratorio
    parser = argparse.ArgumentParser(prog="eval.pilot.tider_case")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    leaked = [k for k in FORBIDDEN_ENV if os.environ.get(k)]
    if leaked:
        print(f"El proceso de Tider no puede ver {', '.join(leaked)}.", file=sys.stderr)
        return 2
    from tider.console.agentic import build_judge
    from tider.console.context_lake import ContextLake
    from tider.console.lake_loader import load_v3
    from tider.console.recorder import Recorder
    from tider.console.settings import Settings
    from tider.console.sweep import sweep
    from tider.llm import AnthropicLLM

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    settings = Settings.from_env()
    lake = ContextLake(max_documents=settings.lake_max_documents, max_chunks=settings.lake_max_chunks)
    load_v3(settings.lake_v3_path, lake)
    recorder = Recorder.from_settings(settings)
    t0 = datetime.fromisoformat(spec["t0"])
    brazos = spec.get("brazos") or ["reglas", "tider"]
    investigator = judge = None
    if "tider" in brazos:
        investigator = AnthropicLLM(model=settings.tider_model, effort=settings.agent_model_effort)
        judge = build_judge(settings)
    trace = run_case(spec, settings=settings, lake=lake,
                     sweeper=lambda req: sweep(req, settings, t0=t0, recorder=recorder),
                     investigator=investigator, judge=judge)
    print(write_trace(trace, args.out))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
