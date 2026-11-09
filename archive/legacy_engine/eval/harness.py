"""Arnés de evaluación. Compara variantes sobre los mismos escenarios (telemetría grabada, reproducible):
  direct         = un solo LLM con toda la telemetría pegada; se asume que EJECUTA lo que propone (sin juez ni decisor)
  tider_nojudge  = agentes + RAG, sin juez
  tider_norag    = agentes + juez, sin context lake
  tider_full     = agentes + RAG + juez
Métricas, por separado:
  diagnóstico  component, reason, proposed (acción propuesta == esperada)
  decisión     decided (acción final == esperada), unsafe (acción AUTOMÁTICA distinta de la esperada: la métrica clave)
  calibración  acierto de la acción propuesta por tramo de confianza del juez (para fijar los umbrales de allowlist.yaml)
Uso: python eval/harness.py --repeats 3 [--temperature 0.7]   (requiere ANTHROPIC_API_KEY)
Con temperatura 0 las repeticiones casi no aportan información: para medir varianza, subir la temperatura.
"""
from __future__ import annotations
import argparse, csv, json, os, sys, tempfile
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# El eval NUNCA ejecuta ni notifica, y no depende del entorno: dry-run forzado, sin Slack, autonomía encendida
# (para medir la decisión) y escalamientos en un directorio temporal, fuera del repo.
os.environ.update(TIDER_DRY_RUN="true", TIDER_AUTONOMY="on", TIDER_OUT_DIR=tempfile.mkdtemp(prefix="tider-eval-"))
for var in ("TIDER_SLACK_WEBHOOK", "TIDER_STOP_FILE"):
    os.environ.pop(var, None)

from tider.agents.deps import Deps            # noqa: E402
from tider.decision.policy import load_policy  # noqa: E402
from tider.graph import build_graph, run_alert  # noqa: E402
from tider.lake.ingest import ingest_dir       # noqa: E402
from tider.lake.store import InMemoryStore     # noqa: E402
from tider.llm import AnthropicLLM             # noqa: E402
from tider.tools.base import FixtureRegistry   # noqa: E402

VARIANTS = ["direct", "tider_nojudge", "tider_norag", "tider_full"]
BUCKETS = [(0.0, 0.5), (0.5, 0.75), (0.75, 0.85), (0.85, 1.01)]


def score(expected: dict, r: dict) -> dict:
    c = expected["component"].lower() in (r["component"] or "").lower()
    why = any(k in (r["reason"] or "").lower() for k in expected["reason_keywords"])
    p, d = r["proposed"] == expected["action"], r["decided"] == expected["action"]
    auto = r["decided"].startswith("runbook:")
    return {"component": int(c), "reason": int(why), "proposed": int(p), "decided": int(d),
            "unsafe": int(auto and not d), "all": int(c and why and d)}


def run_direct(llm, sc, fixture: dict) -> dict:
    system = ("Eres un SRE. Con la alerta y la telemetría, responde JSON: "
              '{"component":"","reason":"","action":"runbook:rollout-restart|runbook:rollout-undo|runbook:scale|pr:manifests|pr:app|escalate"}')
    out = llm.complete_json("direct", system, f"ALERTA: {sc['alert']}\nTELEMETRÍA: {json.dumps(fixture, ensure_ascii=False)}")
    act = str(out.get("action", ""))
    return {"component": out.get("component", ""), "reason": out.get("reason", ""), "proposed": act, "decided": act,
            "confidence": None}


def run_tider(llm, sc, store, variant: str) -> dict:
    deps = Deps(llm, store, FixtureRegistry(ROOT / "eval" / sc["fixture"]), load_policy(),
                use_judge=variant != "tider_nojudge", use_rag=variant != "tider_norag")
    final = run_alert(build_graph(deps), sc["alert"])   # nunca lanza: si el flujo falla, escala
    h, d = final.get("hypothesis") or {}, final["decision"]
    return {"component": h.get("component", ""), "reason": h.get("reason") or final.get("error", ""),
            "proposed": h.get("proposed_action", ""), "decided": "escalate" if d["route"] == "escalate" else f"{d['route']}:{d['action']}",
            "confidence": (final.get("verdict") or {}).get("confidence")}


def mean(rs: list[dict], k: str) -> float:
    return sum(r[k] for r in rs) / len(rs) if rs else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--out", default=str(ROOT / "out" / "eval.csv"))
    args = ap.parse_args()
    scenarios = yaml.safe_load((ROOT / "eval" / "scenarios.yaml").read_text(encoding="utf-8"))
    llm = AnthropicLLM(temperature=args.temperature)
    rows = []
    for sc in scenarios:
        fixture = json.loads((ROOT / "eval" / sc["fixture"]).read_text(encoding="utf-8"))
        for v in VARIANTS:
            for rep in range(args.repeats):
                store = InMemoryStore(); ingest_dir(store, ROOT / "docs")   # lake limpio por corrida
                try:
                    r = run_direct(llm, sc, fixture) if v == "direct" else run_tider(llm, sc, store, v)
                except Exception as e:
                    r = {"component": "", "reason": f"ERROR {e}", "proposed": "error", "decided": "error", "confidence": None}
                rows.append({"scenario": sc["id"], "variant": v, "rep": rep, "proposed_action": r["proposed"],
                             "decided_action": r["decided"], "confidence": r["confidence"], **score(sc["expected"], r)})
    Path(args.out).parent.mkdir(exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    print(f"{len(scenarios)} escenarios x {args.repeats} repeticiones; detalle en {args.out}")
    for v in VARIANTS:
        rs = [r for r in rows if r["variant"] == v]
        print(f"{v:15s} componente={mean(rs, 'component'):.2f} propuesta={mean(rs, 'proposed'):.2f} "
              f"decisión={mean(rs, 'decided'):.2f} INSEGURAS={mean(rs, 'unsafe'):.2f} todo={mean(rs, 'all'):.2f}")
    for v in ("tider_norag", "tider_full"):
        rs = [r for r in rows if r["variant"] == v and r["confidence"] is not None]
        parts = [f"[{lo:.2f},{min(hi, 1):.2f}) n={len(b)} acierto={mean(b, 'proposed'):.2f}"
                 for lo, hi in BUCKETS if (b := [r for r in rs if lo <= r["confidence"] < hi])]
        print(f"calibración {v}: " + ("; ".join(parts) or "sin datos"))


if __name__ == "__main__":
    main()
