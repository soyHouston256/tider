"""Puntuación de la campaña desde las trazas, sin proveedores (Fase 6, ítem 36; A09, A21-A24, P2, P4).

    uv run python -m eval.pilot.score --runs out/runs/pilot-campaign [--judge decisiones.jsonl]
        [--kappa a.csv b.csv --kappa-key clave.json] [--validation out/runs/pilot-validation]

Reutiliza `proportion()` (Wilson) y `paired()` (McNemar exacto) de `eval/quality/score.py`.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median

from eval.quality.score import paired, proportion

from . import protocol as P

FIRMAS = ("servicio-sin-instancias", "configuracion-incorrecta", "dependencia-lenta", "saturacion-cpu")


# --- Entidades ---------------------------------------------------------------------------------------


def entity_match(label: P.Etiqueta, entidad: dict | None) -> dict:
    """Etiqueta de servicio: solo el servicio. Etiqueta de enlace: el enlace exacto; un extremo es parcial."""
    if not entidad or label.tipo == "ninguna":
        return {"exacto": False, "parcial": False}
    if label.tipo == "servicio":
        return {"exacto": entidad.get("tipo") == "servicio" and entidad.get("servicio") == label.servicio,
                "parcial": False}
    if entidad.get("tipo") == "enlace":
        exact = (entidad.get("origen"), entidad.get("destino")) == (label.origen, label.destino)
        return {"exacto": exact, "parcial": False}
    return {"exacto": False, "parcial": entidad.get("servicio") in {label.origen, label.destino}}


def entity_key(entidad: dict | None) -> str:
    if not entidad:
        return "ninguna"
    return entidad["servicio"] if entidad.get("tipo") == "servicio" else f"{entidad['origen']}->{entidad['destino']}"


def top1(analysis: dict | None) -> dict:
    if not analysis:
        return {"entidad": None, "razon": None, "status": "error", "clave": "error"}
    hips = analysis.get("hipotesis") or []
    h = hips[0] if hips else None
    entidad = h["entidad"] if h else None
    return {"entidad": entidad, "razon": h["razon"] if h else None, "status": analysis.get("status"),
            "clave": f"{entity_key(entidad)}|{h['razon'] if h else '-'}"}


def score_rep(label: P.Etiqueta, corrida: dict) -> dict:
    t = top1(corrida.get("analysis"))
    m = entity_match(label, t["entidad"])
    supported = t["status"] == "hypothesis"
    return {**t, **m, "razon_ok": t["razon"] == label.razon, "respaldado": supported,
            "afirmacion_incorrecta": supported and not m["exacto"],
            "elapsed_seconds": corrida.get("elapsed_seconds"), "error": corrida.get("error")}


def collapse(reps: list[dict]) -> dict:
    """P4/A21: una repetición vale por sí sola; con 3, mayoría sobre (entidad, razón); sin mayoría, error."""
    if not reps:
        raise ValueError("Caso sin repeticiones")
    latency = median(r["elapsed_seconds"] for r in reps if r["elapsed_seconds"] is not None) if any(
        r["elapsed_seconds"] is not None for r in reps) else None
    if len(reps) == 1:
        return {**reps[0], "mayoria": True, "repeticiones": 1, "latencia_caso": latency}
    key, votes = Counter(r["clave"] for r in reps).most_common(1)[0]
    if votes * 2 > len(reps):
        chosen = next(r for r in reps if r["clave"] == key)
        return {**chosen, "mayoria": True, "repeticiones": len(reps), "latencia_caso": latency}
    return {"clave": "sin_mayoria", "entidad": None, "razon": None, "status": "sin_mayoria", "exacto": False,
            "parcial": False, "razon_ok": False, "respaldado": False,
            "afirmacion_incorrecta": any(r["afirmacion_incorrecta"] for r in reps),
            "mayoria": False, "repeticiones": len(reps), "latencia_caso": latency, "error": None}


def p95(values: list[float]) -> float | None:
    """Rango más cercano."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    return vals[max(0, math.ceil(0.95 * len(vals)) - 1)]


# --- Carga -------------------------------------------------------------------------------------------


def load_runs(folder: str | Path) -> tuple[list[dict], dict[str, dict]]:
    folder = Path(folder)
    index_path = folder / "casos.jsonl"
    rows = [json.loads(x) for x in index_path.read_text(encoding="utf-8").splitlines() if x] if index_path.exists() else []
    latest = {}
    for r in rows:  # la última fila de cada caso manda (un no_corrido puede reintentarse)
        latest[r["case_id"]] = r
    traces = {}
    for cid, r in latest.items():
        if r.get("trace"):
            path = Path(r["trace"])
            path = path if path.is_absolute() or path.exists() else folder / path.name
            traces[cid] = json.loads(path.read_text(encoding="utf-8"))
    return list(latest.values()), traces


def _arm(trace: dict, brazo: str) -> list[dict]:
    return sorted((c for c in trace.get("corridas") or [] if c["brazo"] == brazo), key=lambda c: c["repeticion"])


def _protocol_ok(trace: dict, protocol: dict):
    if trace["hashes"]["protocolo"] != protocol["hash"]:
        raise ValueError(f"La traza {trace['case_id']} pertenece a otro protocolo.")


# --- Campaña -----------------------------------------------------------------------------------------


def score_case(protocol: dict, row: dict, trace: dict | None) -> dict:
    label = P.etiqueta(protocol, row.get("servicio"), row.get("mecanismo"))
    base = {"case_id": row["case_id"], "conjunto": row["conjunto"], "estrato": row["estrato"],
            "etiqueta": label.clave, "razon_esperada": label.razon}
    if row["estado"] != "corrido" or trace is None:
        return {**base, "admitido": False, "motivo": row.get("motivo") or row["estado"]}
    _protocol_ok(trace, protocol)
    if row["conjunto"] == "evaluacion" and not (trace.get("admision") or {}).get("sintoma"):
        return {**base, "admitido": False, "motivo": "sin_sintoma"}
    out = {**base, "admitido": True, "motivo": None,
           "mas_de_una_confirmada": len(trace.get("firmas_confirmadas_tienda") or []) > 1,
           "acciones": sum(bool(((c.get("analysis") or {}).get("workflow") or {}).get("execution", {}).get("executed"))
                           for c in trace.get("corridas") or [])}
    for brazo in ("tider", "reglas"):
        reps = [score_rep(label, c) for c in _arm(trace, brazo)]
        out[brazo] = collapse(reps) if reps else None
    if row["conjunto"] == "control":
        out["control_ok"] = control_ok(row, trace)
    return out


def control_ok(row: dict, trace: dict) -> bool:
    corridas = _arm(trace, "tider") or _arm(trace, "reglas")
    analysis = (corridas[0].get("analysis") if corridas else None) or {}
    if row.get("mecanismo") is None:  # sin falla: ninguna causa respaldada
        return bool(analysis) and analysis.get("status") != "hypothesis"
    tienda = {n["servicio"] for n in analysis.get("nodos") or [] if n.get("tipo") == "tienda"}
    hip = (analysis.get("hipotesis") or [None])[0]
    sin_causa_tienda = hip is None or entity_key(hip["entidad"]).split("->")[0] not in tienda
    aviso = any("Generación de tráfico detenida" in a for a in (analysis.get("investigation") or {}).get("avisos") or [])
    return bool(analysis) and sin_causa_tienda and aviso


def score_campaign(protocol: dict, index: list[dict], traces: dict[str, dict]) -> dict:
    casos = [score_case(protocol, r, traces.get(r["case_id"])) for r in index]
    ev = [c for c in casos if c["conjunto"] == "evaluacion" and c["admitido"] and c.get("tider")]
    u = protocol["umbrales"]
    exact = proportion([c["tider"]["exacto"] for c in ev])
    claims = proportion([c["tider"]["afirmacion_incorrecta"] for c in ev])
    lat = p95([c["tider"]["latencia_caso"] for c in ev])
    acciones = sum(c.get("acciones", 0) for c in casos if c["admitido"])
    n_obj = protocol["conjuntos"]["evaluacion"]["n_objetivo"]
    checks = {
        "n_suficiente": exact["n"] >= n_obj or protocol["conjuntos"]["evaluacion"]["aceptar_n_menor"],
        "exactitud": bool(exact["wilson95"]) and exact["wilson95"][0] >= u["exactitud_wilson_inferior_min"],
        "afirmaciones_incorrectas": bool(claims["wilson95"]) and claims["wilson95"][1] <= u["incorrectas_wilson_superior_max"],
        "latencia_p95": lat is not None and lat <= u["latencia_p95_s_max"],
        "acciones": acciones <= u["acciones_max"],
    }
    minimo = protocol["conjuntos"]["evaluacion"]["minimo_por_estrato"]
    estratos = {}
    for estrato in protocol["conjuntos"]["evaluacion"]["estratos"]:
        sub = [c for c in ev if c["estrato"] == estrato]
        estratos[estrato] = {"n": len(sub), "reportable": len(sub) >= minimo,
                             "exactitud": proportion([c["tider"]["exacto"] for c in sub]),
                             "parcial": proportion([c["tider"]["parcial"] for c in sub]),
                             "conjunta": proportion([c["tider"]["exacto"] and c["tider"]["razon_ok"] for c in sub])}
    reglas = [c for c in ev if c.get("reglas")]
    controles = {}
    for estrato in ("loadgenerator", "sin_falla"):
        sub = [c for c in casos if c["conjunto"] == "control" and c["estrato"] == estrato and c["admitido"]]
        controles[estrato] = proportion([c["control_ok"] for c in sub])
    return {
        "protocolo": protocol["hash"],
        "principal": {"exactitud": exact, "afirmaciones_incorrectas": claims, "latencia_p95_s": lat,
                      "acciones": acciones, "umbrales": checks, "pasa": all(checks.values())},
        "descriptivo": {
            "parcial_enlace": proportion([c["tider"]["parcial"] for c in ev]),
            "conjunta_entidad_razon": proportion([c["tider"]["exacto"] and c["tider"]["razon_ok"] for c in ev]),
            "mas_de_una_confirmada": proportion([c["mas_de_una_confirmada"] for c in ev]),
            "sin_mayoria": sum(not c["tider"]["mayoria"] for c in ev),
            "errores_tecnicos": sum(c["tider"]["status"] == "error" for c in ev),
            "estratos": estratos, "controles": controles,
            "reglas_exactitud": proportion([c["reglas"]["exacto"] for c in reglas]),
            "tider_vs_reglas": paired([c["tider"]["exacto"] for c in reglas], [c["reglas"]["exacto"] for c in reglas])
            if reglas else None,
        },
        "excluidos": [{"case_id": c["case_id"], "motivo": c["motivo"]} for c in casos if not c["admitido"]],
        "casos": casos,
    }


# --- Juez (P2: descriptivo; McNemar exploratorio solo sobre naturales) --------------------------------


def judge_scores(decisions: list[dict]) -> dict:
    """`decisions`: [{"origen": natural|fabricado, "verdadero": bool, "aprobado": bool | None}]."""
    out = {}
    for origen in ("natural", "fabricado"):
        sub = [d for d in decisions if d["origen"] == origen and d.get("aprobado") is not None]
        out[origen] = {"falsa_aprobacion": proportion([d["aprobado"] for d in sub if not d["verdadero"]]),
                       "falso_rechazo": proportion([not d["aprobado"] for d in sub if d["verdadero"]])}
    nat = [d for d in decisions if d["origen"] == "natural" and d.get("aprobado") is not None]
    out["mcnemar_natural_exploratorio"] = paired(
        [d["aprobado"] == d["verdadero"] for d in nat], [d["verdadero"] for d in nat]) if nat else None
    return out


# --- Matriz de confusión de firmas y go/no-go (A12) ---------------------------------------------------


def signature_confusion(protocol: dict, index: list[dict], traces: dict[str, dict]) -> dict:
    """Filas: mecanismo inyectado (o sin_falla). Columnas: firmas CONFIRMADAS sobre la tienda (o ninguna)."""
    filas, corridas = {}, []
    for row in index:
        trace = traces.get(row["case_id"])
        if row["estado"] == "no_corrido":
            continue
        mecanismo = row.get("mecanismo")
        verdad = protocol["mecanismos"][mecanismo]["razon"] if mecanismo else "ninguna"
        label = P.etiqueta(protocol, row.get("servicio"), mecanismo)
        confirmadas = [c.split("@", 1) for c in (trace or {}).get("firmas_confirmadas_tienda") or []]
        cols = filas.setdefault(verdad, Counter())
        for firma, _ in confirmadas:
            cols[firma] += 1
        if not confirmadas:
            cols["ninguna"] += 1
        esperado = [(f, e) for f, e in confirmadas if f == verdad and e == label.clave]
        ok = (row["estado"] == "corrido" and row.get("acreditada", True)
              and (not confirmadas if mecanismo is None else len(esperado) == 1 and len(confirmadas) == 1))
        corridas.append({"case_id": row["case_id"], "verdad": verdad, "entidad_esperada": label.clave,
                         "confirmadas": ["@".join(c) for c in confirmadas], "estado": row["estado"],
                         "motivo": row.get("motivo"), "ok": ok})
    return {"matriz": {k: dict(v) for k, v in filas.items()}, "corridas": corridas}


def signature_gate(protocol: dict, index: list[dict], catalog_hash: str, traces: dict | None = None) -> dict:
    if traces is None:
        traces = {}
        for r in index:
            if r.get("trace") and Path(r["trace"]).exists():
                traces[r["case_id"]] = json.loads(Path(r["trace"]).read_text(encoding="utf-8"))
    latest = {r["case_id"]: r for r in index}
    conf = signature_confusion(protocol, list(latest.values()), traces)
    esperadas = {c.case_id for c in P.validation_plan(protocol)}
    hechas = {c["case_id"] for c in conf["corridas"]}
    go = esperadas <= hechas and all(c["ok"] for c in conf["corridas"])
    return {"go": go, "faltan": sorted(esperadas - hechas), "catalogo_hash": catalog_hash,
            "protocol_hash": protocol["hash"], **conf}


# --- Informe -----------------------------------------------------------------------------------------


def _fmt(p: dict) -> str:
    if not p or not p.get("n"):
        return "n = 0"
    lo, hi = p["wilson95"]
    return f"{p['hits']}/{p['n']} = {p['rate']:.1%} (Wilson 95 % [{lo:.1%}, {hi:.1%}])"


def report_markdown(result: dict, judge: dict | None = None, kappa: dict | None = None,
                    gate: dict | None = None) -> str:
    pr, d = result["principal"], result["descriptivo"]
    u = pr["umbrales"]
    si = {True: "cumple", False: "NO cumple"}
    lines = ["# Piloto Tider: resultado de la campaña", "", f"Protocolo `{result['protocolo'][:12]}`.", "",
             "## Resultado principal", "",
             f"* Exactitud de la primera hipótesis: {_fmt(pr['exactitud'])}; límite inferior ≥ 70 %: {si[u['exactitud']]}.",
             f"* Afirmaciones incorrectas: {_fmt(pr['afirmaciones_incorrectas'])}; límite superior ≤ 15 %: "
             f"{si[u['afirmaciones_incorrectas']]}.",
             f"* Latencia p95 de la mediana por caso: {pr['latencia_p95_s']} s; ≤ 120 s: {si[u['latencia_p95']]}.",
             f"* Acciones ejecutadas: {pr['acciones']}; = 0: {si[u['acciones']]}.",
             f"* n suficiente: {si[u['n_suficiente']]}.",
             f"* **Veredicto: {'PASA' if pr['pasa'] else 'NO PASA'}.**", "",
             "## Descriptivo", "",
             f"* Acierto parcial (extremo de un enlace): {_fmt(d['parcial_enlace'])}.",
             f"* Entidad y razón: {_fmt(d['conjunta_entidad_razon'])}.",
             f"* Casos con más de una firma CONFIRMADA (repetidos 3 veces): {_fmt(d['mas_de_una_confirmada'])}; "
             f"sin mayoría: {d['sin_mayoria']}.",
             f"* Errores técnicos (cuentan como fallo): {d['errores_tecnicos']}.",
             f"* Modo sin LLM (reglas): {_fmt(d['reglas_exactitud'])}.", "",
             "| Estrato | n | Exactitud | Parcial | Entidad + razón |", "|---|---|---|---|---|"]
    for k, e in d["estratos"].items():
        nota = "" if e["reportable"] else " (n bajo el mínimo)"
        lines.append(f"| {k}{nota} | {e['n']} | {_fmt(e['exactitud'])} | {_fmt(e['parcial'])} | {_fmt(e['conjunta'])} |")
    lines += ["", "Controles:", ""] + [f"* {k}: {_fmt(v)}" for k, v in d["controles"].items()]
    if d.get("tider_vs_reglas"):
        t = d["tider_vs_reglas"]
        lines.append(f"* Tider vs reglas (exploratorio, McNemar exacto): {t['first_only']} vs {t['second_only']}, "
                     f"p = {t['exact_two_sided_p']:.3f}.")
    if judge:
        lines += ["", "## Juez (descriptivo, P2)", ""]
        for origen in ("natural", "fabricado"):
            lines.append(f"* {origen}: falsa aprobación {_fmt(judge[origen]['falsa_aprobacion'])}; "
                         f"falso rechazo {_fmt(judge[origen]['falso_rechazo'])}.")
        m = judge.get("mcnemar_natural_exploratorio")
        if m:
            lines.append(f"* McNemar exacto sobre naturales (exploratorio): con juez {m['first_only']} vs sin juez "
                         f"{m['second_only']}, p = {m['exact_two_sided_p']:.3f}.")
    if kappa:
        lines += ["", "## Acuerdo entre evaluadores (κ de Cohen)", ""]
        for q, k in kappa.items():
            lines.append(f"* {q}: κ = {k['kappa']:.2f} (IC 95 % [{k['ic95'][0]:.2f}, {k['ic95'][1]:.2f}]), n = {k['n']}.")
    if gate:
        lines += ["", "## Validación de firmas", "", f"Go/no-go: **{'go' if gate['go'] else 'no-go'}**.", ""]
        cols = sorted({c for v in gate["matriz"].values() for c in v})
        lines += ["| inyectado \\ confirmada | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
        lines += [f"| {r} | " + " | ".join(str(v.get(c, 0)) for c in cols) + " |" for r, v in gate["matriz"].items()]
    lines += ["", "## Casos excluidos", ""] + ([f"* {e['case_id']}: {e['motivo']}" for e in result["excluidos"]] or ["* ninguno"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from .kappa_form import kappa_from_files

    parser = argparse.ArgumentParser(prog="eval.pilot.score")
    parser.add_argument("--runs", required=True)
    parser.add_argument("--protocol", default=str(P.PROTOCOL))
    parser.add_argument("--judge", default=None, help="decisiones.jsonl de judge_set")
    parser.add_argument("--kappa", nargs=2, default=None)
    parser.add_argument("--kappa-key", default=None)
    parser.add_argument("--validation", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    protocol = P.load(args.protocol)
    index, traces = load_runs(args.runs)
    result = score_campaign(protocol, index, traces)
    judge = None
    if args.judge:
        decisions = [json.loads(x) for x in Path(args.judge).read_text(encoding="utf-8").splitlines() if x]
        judge = judge_scores(decisions)
    kappa = kappa_from_files(protocol, *args.kappa, key_path=args.kappa_key) if args.kappa else None
    gate = None
    if args.validation:
        gate_path = Path(args.validation) / "gate.json"
        gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.exists() else None
    report = report_markdown(result, judge, kappa, gate)
    out = Path(args.out or Path(args.runs) / "informe.md")
    out.write_text(report, encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps({"campana": result, "juez": judge, "kappa": kappa},
                                                   ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(report)
    return 0 if result["principal"]["pasa"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
