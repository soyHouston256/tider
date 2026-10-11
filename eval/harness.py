"""Arnés de evaluación. Compara variantes sobre los mismos escenarios (telemetría grabada, reproducible):
  direct         = un solo LLM con toda la telemetría pegada (línea base "LLM directo")
  tider_nojudge  = agentes + RAG, sin juez
  tider_norag    = agentes + juez, sin context lake
  tider_full     = agentes + RAG + juez
Uso: python eval/harness.py --repeats 3   (requiere ANTHROPIC_API_KEY)
"""
from __future__ import annotations
import argparse, csv, json, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tider.agents.deps import Deps            # noqa: E402
from tider.decision.policy import load_policy  # noqa: E402
from tider.graph import build_graph, run_alert  # noqa: E402
from tider.lake.ingest import ingest_dir       # noqa: E402
from tider.lake.store import InMemoryStore     # noqa: E402
from tider.llm import AnthropicLLM             # noqa: E402
from tider.tools.base import FixtureRegistry   # noqa: E402

VARIANTS = ["direct", "tider_nojudge", "tider_norag", "tider_full"]


def score(expected: dict, component: str, reason: str, action: str) -> dict:
    c = expected["component"].lower() in (component or "").lower()
    r = any(k in (reason or "").lower() for k in expected["reason_keywords"])
    a = action == expected["action"]
    return {"component": int(c), "reason": int(r), "action": int(a), "all": int(c and r and a)}


def run_direct(llm, sc, fixture: dict) -> tuple[str, str, str]:
    system = ("Eres un SRE. Con la alerta y la telemetría, responde JSON: "
              '{"component":"","reason":"","action":"runbook:rollout-restart|runbook:rollout-undo|runbook:scale|pr:manifests|pr:app|escalate"}')
    out = llm.complete_json("direct", system, f"ALERTA: {sc['alert']}\nTELEMETRÍA: {json.dumps(fixture, ensure_ascii=False)}")
    return out.get("component", ""), out.get("reason", ""), out.get("action", "")


def run_tider(llm, sc, store, variant: str) -> tuple[str, str, str]:
    deps = Deps(llm, store, FixtureRegistry(ROOT / "eval" / sc["fixture"]), load_policy(),
                use_judge=variant != "tider_nojudge", use_rag=variant != "tider_norag")
    final = run_alert(build_graph(deps), sc["alert"])
    h, d = final["hypothesis"], final["decision"]
    action = d["action"] if d["route"] == "escalate" else f"{d['route']}:{d['action']}"
    return h["component"], h["reason"], action


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "out" / "eval.csv"))
    args = ap.parse_args()
    scenarios = yaml.safe_load((ROOT / "eval" / "scenarios.yaml").read_text())
    llm = AnthropicLLM(temperature=0.0)
    rows = []
    for sc in scenarios:
        fixture = json.loads((ROOT / "eval" / sc["fixture"]).read_text())
        for v in VARIANTS:
            for rep in range(args.repeats):
                store = InMemoryStore(); ingest_dir(store, ROOT / "docs")   # lake limpio por corrida
                try:
                    comp, reason, act = run_direct(llm, sc, fixture) if v == "direct" else run_tider(llm, sc, store, v)
                except Exception as e:
                    comp, reason, act = "", f"ERROR {e}", "error"
                rows.append({"scenario": sc["id"], "variant": v, "rep": rep, "action": act,
                             **score(sc["expected"], comp, reason, act)})
    Path(args.out).parent.mkdir(exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    for v in VARIANTS:
        rs = [r for r in rows if r["variant"] == v]
        print(f"{v:15s} componente={sum(r['component'] for r in rs)/len(rs):.2f} "
              f"acción={sum(r['action'] for r in rs)/len(rs):.2f} todo={sum(r['all'] for r in rs)/len(rs):.2f}")


if __name__ == "__main__":
    main()
