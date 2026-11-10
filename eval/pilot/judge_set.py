"""Conjunto de candidatos del juez (Fase 6, ítem 35; A08, A22, P2).

    uv run python -m eval.pilot.judge_set --runs out/runs/pilot-campaign [--call-judge]

* Naturales: el diagnóstico de la primera ronda de la repetición 1 del brazo tider de cada caso de
  evaluación admitido. Su decisión "con juez" sale de la traza (reglas fijas y Juez LLM de esa ronda).
* Fabricados: falsos por construcción, a partir de naturales verdaderos con la receta del protocolo
  (intercambio causa/víctima, razón cambiada, citas irrelevantes, solo antecedentes). Se muestrean con la
  semilla del protocolo hasta la proporción verdaderos:falsos. Solo se presentan al Juez LLM (`--call-judge`,
  necesita OPENAI_API_KEY y JUDGE_MODEL); las reglas fijas no se re-ejecutan.
La verdad de cada candidato nunca entra en el payload que ve el juez.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path

from . import protocol as P
from .score import FIRMAS, entity_match, load_runs, score_case


def _round1(trace: dict) -> dict | None:
    """Primera ronda de tider#1: respuesta del Investigador, entrada del juez (si la hubo) y decisión."""
    calls = [c for c in trace.get("llamadas") or [] if c.get("corrida") == "tider#1"]
    inv = [c for c in calls if c["agent"] == "investigator"]
    if not inv or not isinstance(inv[0].get("output"), dict) or not inv[0]["output"].get("hipotesis"):
        return None
    first_inv = calls.index(inv[0])
    nxt = inv[1] if len(inv) > 1 else None
    end = calls.index(nxt) if nxt else len(calls)
    judge = next((c for c in calls[first_inv:end] if c["agent"] == "judge"), None)
    aprobado = bool(judge and isinstance(judge.get("output"), dict) and judge["output"].get("supported") is True)
    return {"investigador": inv[0]["output"], "juez_input": json.loads(judge["input"]) if judge else None,
            "aprobado": aprobado}


def _entidad(clave: str) -> dict:
    if "->" in clave:
        o, d = clave.split("->", 1)
        return {"tipo": "enlace", "origen": o.strip(), "destino": d.strip()}
    return {"tipo": "servicio", "servicio": clave.strip()}


def natural_candidates(protocol: dict, index: list[dict], traces: dict[str, dict]) -> list[dict]:
    out = []
    for row in index:
        if row.get("conjunto") != "evaluacion" or row["case_id"] not in traces:
            continue
        if not score_case(protocol, row, traces[row["case_id"]])["admitido"]:
            continue
        r1 = _round1(traces[row["case_id"]])
        if r1 is None:
            continue
        label = P.etiqueta(protocol, row.get("servicio"), row.get("mecanismo"))
        h = sorted(r1["investigador"]["hipotesis"], key=lambda x: x.get("orden", 99))[0]
        verdadero = entity_match(label, _entidad(h["entidad"]))["exacto"] and h.get("firma_id") == label.razon
        out.append({"id": f"{row['case_id']}-N", "case_id": row["case_id"], "origen": "natural",
                    "transformacion": None, "verdadero": verdadero, "aprobado": r1["aprobado"],
                    "payload": r1["juez_input"]})
    return out


def _evidencia(trace: dict) -> dict:
    ev = ((trace.get("entradas") or {}).get("evidencia_congelada") or {}).get("evidencia") or {}
    lines = {}
    for group in ev.values() if isinstance(ev, dict) else []:
        for item in group if isinstance(group, list) else []:
            if isinstance(item, dict) and str(item.get("id", "")).startswith("S") and "servicio" in item:
                lines[item["id"]] = item
    return lines


def mutate(payload: dict, transformacion: str, trace: dict, rng: random.Random) -> dict | None:
    """Devuelve el payload fabricado o None si la transformación no aplica a este caso."""
    p = copy.deepcopy(payload)
    hips = p["diagnostico"]["hipotesis"]
    if not hips:
        return None
    h = hips[0]
    ent = h["entidad"]
    causa = ent.get("servicio") or ent.get("origen")
    if transformacion == "intercambio_causa_victima":
        if ent["tipo"] == "enlace":
            h["entidad"] = {"tipo": "enlace", "origen": ent["destino"], "destino": ent["origen"]}
            nuevo = ent["destino"]
        else:
            victimas = sorted(f["servicio"] for f in p.get("tabla") or [] if f.get("rol") == "victima")
            if not victimas:
                return None
            nuevo = rng.choice(victimas)
            h["entidad"] = {"tipo": "servicio", "servicio": nuevo}
        p["diagnostico"]["resumen"] = (p["diagnostico"].get("resumen") or "").replace(causa, nuevo)
    elif transformacion == "razon_cambiada":
        otra = rng.choice([f for f in FIRMAS if f != h.get("firma_id")])
        p["diagnostico"]["resumen"] = (p["diagnostico"].get("resumen") or "").replace(h.get("firma_id") or "", otra)
        h["firma_id"] = h["razon"] = otra
    elif transformacion == "citas_irrelevantes":
        ajenos = {f["servicio"] for f in p.get("tabla") or [] if f.get("rol") in {"ninguno", None}} - {causa}
        lineas = {i: x for i, x in _evidencia(trace).items() if x.get("servicio") in ajenos}
        if not lineas:
            return None
        elegidas = rng.sample(sorted(lineas), min(3, len(lineas)))
        h["citas"] = [c for c in h["citas"] if c["id"].startswith("D")] + [{"id": i, "clase": "evidencia"} for i in elegidas]
        p["citas_resueltas"] = {k: v for k, v in p.get("citas_resueltas", {}).items() if k.startswith("D")}
        p["citas_resueltas"].update({i: {"tiempo": lineas[i].get("tiempo"), "servicio": lineas[i]["servicio"],
                                         "texto": str(lineas[i].get("texto_original", ""))[:500]} for i in elegidas})
    elif transformacion == "solo_antecedentes":
        h["citas"] = [c for c in h["citas"] if c["id"].startswith("D")]
        p["citas_resueltas"] = {k: v for k, v in p.get("citas_resueltas", {}).items() if k.startswith("D")}
    else:
        raise ValueError(f"Transformación desconocida: {transformacion}")
    return p


def build(protocol: dict, index: list[dict], traces: dict[str, dict]) -> list[dict]:
    cfg = protocol["juez"]
    rng = random.Random(protocol["semilla"])
    naturales = natural_candidates(protocol, index, traces)
    t, f = cfg["proporcion_verdaderos_falsos"]
    n_true = sum(c["verdadero"] for c in naturales)
    n_false = len(naturales) - n_true
    faltan = max(0, round(n_true * f / t) - n_false)
    pool: dict[str, list[dict]] = {}
    for c in naturales:
        if not c["verdadero"] or c["payload"] is None:
            continue
        for receta in cfg["receta_mutaciones"]:
            m = mutate(c["payload"], receta["id"], traces[c["case_id"]], rng)
            if m is not None:
                pool.setdefault(receta["id"], []).append(
                    {"id": f"{c['case_id']}-F-{receta['id']}", "case_id": c["case_id"], "origen": "fabricado",
                     "transformacion": receta["id"], "verdadero": False, "aprobado": None, "payload": m})
    for items in pool.values():
        rng.shuffle(items)
    fabricados, orden = [], [r["id"] for r in cfg["receta_mutaciones"]]
    while len(fabricados) < faltan and any(pool.get(k) for k in orden):
        for k in orden:  # round-robin entre transformaciones
            if pool.get(k) and len(fabricados) < faltan:
                fabricados.append(pool[k].pop())
    return naturales + fabricados


def run_judge(candidates: list[dict], judge) -> list[dict]:
    """Presenta los fabricados al Juez LLM con el mismo prompt del pipeline. Los naturales ya tienen decisión."""
    from tider.console.pipeline_v2 import JUDGE_SYSTEM, _texto_llm

    out = []
    for c in candidates:
        c = dict(c)
        if c["origen"] == "fabricado":
            try:
                r = judge.complete_json("judge", JUDGE_SYSTEM, _texto_llm(c["payload"]))
                c["aprobado"] = r.get("supported") is True
            except Exception as exc:  # una falla del juez se registra y no aprueba
                c["aprobado"], c["error"] = False, type(exc).__name__
        out.append(c)
    return out


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(prog="eval.pilot.judge_set")
    parser.add_argument("--runs", required=True)
    parser.add_argument("--protocol", default=str(P.PROTOCOL))
    parser.add_argument("--call-judge", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    protocol = P.load(args.protocol)
    index, traces = load_runs(args.runs)
    candidates = build(protocol, index, traces)
    if args.call_judge:
        from tider.console.agentic import build_judge
        from tider.console.settings import Settings

        candidates = run_judge(candidates, build_judge(Settings.from_env()))
    out = Path(args.out or Path(args.runs) / "decisiones_juez.jsonl")
    out.write_text("".join(json.dumps({k: v for k, v in c.items() if k != "payload"} | {"payload": c["payload"]},
                                      ensure_ascii=False) + "\n" for c in candidates), encoding="utf-8")
    nat = sum(c["origen"] == "natural" for c in candidates)
    print(f"{len(candidates)} candidatos ({nat} naturales, {len(candidates) - nat} fabricados) -> {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
