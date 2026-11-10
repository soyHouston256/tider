"""Formulario ciego para los 2 evaluadores y κ de Cohen (Fase 6, ítem 37; A08).

    uv run python -m eval.pilot.kappa_form export --runs out/runs/pilot-campaign --out kappa/
        -> kappa/formulario.csv (para cada evaluador) y kappa/clave.json (privado: ítem -> caso y variante)
    uv run python -m eval.pilot.kappa_form kappa kappa/alberto.csv kappa/jose.csv --key kappa/clave.json

El formulario no muestra la variante (brazo), ni la etiqueta, ni el servicio inyectado: solo lo que el
informe de Tider dice (hipótesis, citas resueltas a su texto y recomendación). Los ítems se barajan.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter
from pathlib import Path

from . import protocol as P
from .score import load_runs, score_case

FIELDS = ["item", "hipotesis", "evidencia_citada", "recomendacion"]


def sample_cases(protocol: dict, index: list[dict], traces: dict[str, dict]) -> list[dict]:
    """Muestreo estratificado proporcional (mínimo 3 por estrato) entre casos de evaluación admitidos."""
    cfg = protocol["kappa"]
    rng = random.Random(protocol["semilla"])
    by = {}
    for row in index:
        if row.get("conjunto") == "evaluacion" and row["case_id"] in traces and \
                score_case(protocol, row, traces[row["case_id"]])["admitido"]:
            by.setdefault(row["estrato"], []).append(row)
    total, n = sum(len(v) for v in by.values()), cfg["casos"]
    if total <= n:
        chosen = [r for v in by.values() for r in v]
    else:
        quota = {k: min(len(v), max(3, round(n * len(v) / total))) for k, v in by.items()}
        while sum(quota.values()) > n:
            k = max(quota, key=lambda k: quota[k])
            quota[k] -= 1
        while sum(quota.values()) < n:
            k = max((k for k in quota if quota[k] < len(by[k])), key=lambda k: len(by[k]) - quota[k])
            quota[k] += 1
        chosen = [r for k in sorted(by) for r in rng.sample(sorted(by[k], key=lambda r: r["case_id"]), quota[k])]
    rng.shuffle(chosen)
    return chosen


def _item_text(analysis: dict) -> dict:
    hips = analysis.get("hipotesis") or []
    citas = [c["id"] for c in (hips[0]["citas"] if hips else [])]
    ev = {e.get("id"): e for e in analysis.get("evidence") or []}
    evid = " | ".join(f"{i}: {str(ev[i].get('message', ''))[:200]}" for i in citas if i in ev) or "(sin citas de evidencia)"
    return {"hipotesis": analysis.get("hypothesis", ""), "evidencia_citada": evid,
            "recomendacion": analysis.get("recommendation", "")}


def export(protocol: dict, index: list[dict], traces: dict[str, dict], out: Path) -> tuple[Path, Path]:
    rng = random.Random(protocol["semilla"] + 1)
    casos = sample_cases(protocol, index, traces)
    variantes = (["tider", "reglas"] * len(casos))[:len(casos)]
    rng.shuffle(variantes)
    rows, key = [], {}
    preguntas = [q["id"] for q in protocol["kappa"]["preguntas"]]
    for i, (row, variante) in enumerate(zip(casos, variantes, strict=True), 1):
        corrida = next((c for c in traces[row["case_id"]]["corridas"] if c["brazo"] == variante and c["analysis"]), None)
        if corrida is None:
            variante = "reglas" if variante == "tider" else "tider"
            corrida = next(c for c in traces[row["case_id"]]["corridas"] if c["brazo"] == variante and c["analysis"])
        item = f"K{i:02}"
        rows.append({"item": item, **_item_text(corrida["analysis"]), **{q: "" for q in preguntas}})
        key[item] = {"case_id": row["case_id"], "variante": variante}
    out.mkdir(parents=True, exist_ok=True)
    form, key_path = out / "formulario.csv", out / "clave.json"
    with form.open("w", newline="", encoding="utf-8") as fh:
        fh.write("# Responde cada pregunta con si o no. "
                 + " ".join(f"{q['id']}: {q['texto']}" for q in protocol["kappa"]["preguntas"]) + "\n")
        w = csv.DictWriter(fh, fieldnames=FIELDS + preguntas)
        w.writeheader()
        w.writerows(rows)
    key_path.write_text(json.dumps({"protocolo": protocol["hash"], "items": key}, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    return form, key_path


def read_ratings(path: str | Path, preguntas: list[str], escala: list[str]) -> dict[str, dict[str, str]]:
    lines = [x for x in Path(path).read_text(encoding="utf-8").splitlines() if not x.startswith("#")]
    out = {}
    for row in csv.DictReader(lines):
        vals = {q: (row.get(q) or "").strip().lower() for q in preguntas}
        bad = {q: v for q, v in vals.items() if v not in escala}
        if bad:
            raise ValueError(f"{path}: respuesta inválida en {row['item']}: {bad}")
        out[row["item"]] = vals
    return out


def cohen_kappa(a: list[str], b: list[str]) -> dict:
    """κ de Cohen con IC 95 % por el error estándar asintótico simple sqrt(po(1-po)/(n(1-pe)^2))."""
    if not a or len(a) != len(b):
        raise ValueError("Se requieren calificaciones pareadas")
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n**2
    if pe == 1:
        return {"n": n, "po": po, "pe": pe, "kappa": 1.0 if po == 1 else 0.0, "ic95": [None, None]}
    k = (po - pe) / (1 - pe)
    se = math.sqrt(po * (1 - po) / (n * (1 - pe) ** 2))
    return {"n": n, "po": po, "pe": pe, "kappa": k, "ic95": [max(-1.0, k - 1.96 * se), min(1.0, k + 1.96 * se)]}


def kappa_from_files(protocol: dict, a: str, b: str, key_path: str | None = None) -> dict:
    preguntas = [q["id"] for q in protocol["kappa"]["preguntas"]]
    escala = protocol["kappa"]["escala"]
    ra, rb = read_ratings(a, preguntas, escala), read_ratings(b, preguntas, escala)
    if set(ra) != set(rb):
        raise ValueError("Las dos planillas no tienen los mismos ítems")
    if key_path:
        key = json.loads(Path(key_path).read_text(encoding="utf-8"))
        if key["protocolo"] != protocol["hash"] or set(key["items"]) != set(ra):
            raise ValueError("La clave no corresponde a estas planillas o a este protocolo")
    items = sorted(ra)
    return {q: cohen_kappa([ra[i][q] for i in items], [rb[i][q] for i in items]) for q in preguntas}


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(prog="eval.pilot.kappa_form")
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--runs", required=True)
    e.add_argument("--out", required=True)
    k = sub.add_parser("kappa")
    k.add_argument("a")
    k.add_argument("b")
    k.add_argument("--key", default=None)
    for p in (e, k):
        p.add_argument("--protocol", default=str(P.PROTOCOL))
    args = parser.parse_args(argv)
    protocol = P.load(args.protocol)
    if args.cmd == "export":
        index, traces = load_runs(args.runs)
        form, key = export(protocol, index, traces, Path(args.out))
        print(f"Formulario: {form}\nClave (no la compartas con los evaluadores): {key}")
    else:
        print(json.dumps(kappa_from_files(protocol, args.a, args.b, args.key), indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
