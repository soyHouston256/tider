"""Capture one arm on the fixed follow-up cases, or score both saved arms offline."""
import argparse
from pathlib import Path

from eval.quality.data import HERE, digest, passage, read, runbooks, save, verify
from eval.quality.score import paired, proportion, score_retrieval, score_window

DATA = HERE / "followup"


def check_inputs():
    verify()
    for name, expected in read(DATA / "manifest.json").items():
        if digest(DATA / name) != expected:
            raise ValueError(f"Entrada modificada: {name}")


def rank(out):
    from inspect import getfile

    from tider.console.context_lake import ContextLake

    if out.exists():
        raise FileExistsError(out)
    lake = ContextLake()
    for path in [*runbooks(), *sorted((HERE / "corpus").iterdir())]:
        lake.add(path.name, path.read_text())
    queries = read(DATA / "queries.json")
    result = {k: [passage(r) for r in lake.search(q, k=4)] for k, q in queries.items()}
    save(out, {"protocol": digest(DATA / "manifest.json"), "code": digest(Path(getfile(ContextLake))),
               "passages": sorted(passage(r) for r in lake.snapshot_documents()), "rankings": result})


def summarize():
    inputs = digest(DATA / "manifest.json")
    before, after = [read(DATA / f"{arm}-ranks.json") for arm in ("before", "after")]
    if before["passages"] != after["passages"] or any(a["protocol"] != inputs for a in (before, after)):
        raise ValueError("Protocolos o corpus de búsqueda distintos")
    queries = read(DATA / "queries.json")
    gold = read(DATA / "passage_labels.json")
    if any(set(queries) != set(a["rankings"]) for a in (before, after)):
        raise ValueError("Faltan rankings")
    joined = {k: {"before": before["rankings"][k], "after": after["rankings"][k]} for k in queries}
    scores = score_retrieval({"rankings": joined, "passages": before["passages"], "k": 4},
                             queries, gold, 4, methods=("after", "before"))
    retrieval = {**scores["summary"], "paired_after_vs_before": scores["paired_hit_at_4"]}
    windows, labels = read(DATA / "windows.json"), read(DATA / "incident_labels.json")
    cases = {}
    meta = {}
    for arm in ("before", "after"):
        folder = DATA / arm
        meta[arm] = read(folder / "run.json")
        if meta[arm]["protocol"] != inputs or {p.stem for p in folder.glob("H*.json")} != set(labels):
            raise ValueError("Corrida incompleta o de otro protocolo")
        results = {}
        for window in windows:
            cid = window["id"]
            entry = read(folder / f"{cid}.json")
            if entry["id"] != cid or entry["result"]["model"] != meta[arm]["model"]:
                raise ValueError("Ventana/modelo incompatible")
            results[cid] = score_window(window, labels[cid], entry["result"])
        cases[arm] = results
    if any(meta["before"][k] != meta["after"][k] for k in ("model", "effort", "steps", "timeout_seconds", "log_budget")):
        raise ValueError("Modelo o presupuesto distintos")
    groups = {"all_required_retrieved": [k for k in labels if labels[k]["required_records"]],
              "joint_with_required_evidence": [k for k in labels if labels[k]["required_records"]],
              "mechanism_match": [k for k in labels if labels[k]["required_records"]],
              "location_match": [k for k in labels if "desconocido" not in labels[k]["accepted_components"]],
              "asserted_cause": [k for k in labels if not labels[k]["required_records"]],
              "explicit_unknown": [k for k in labels if not labels[k]["required_records"]]}
    diagnosis = {}
    for metric, ids in groups.items():
        flags = {}
        for arm, rows in cases.items():
            if metric == "all_required_retrieved":
                flags[arm] = [rows[k]["required"] == rows[k]["required_retrieved"] for k in ids]
            else:
                key = "mechanism_match" if metric == "explicit_unknown" else metric
                flags[arm] = [rows[k][key] for k in ids]
        diagnosis[metric] = {arm: proportion(vals) for arm, vals in flags.items()}
        diagnosis[metric]["paired_after_vs_before"] = paired(flags["after"], flags["before"])
    paths = [DATA / "before-ranks.json", DATA / "after-ranks.json",
             *sorted((DATA / "before").glob("*.json")), *sorted((DATA / "after").glob("*.json"))]
    usage = {arm: {field: sum(r[field] for r in rows.values()) for field in (
        "model_calls", "input_tokens", "output_tokens", "technical_error", "log_queries", "errors_only_queries")}
        for arm, rows in cases.items()}
    return {"protocol": inputs, "artifacts_sha256": {str(p.relative_to(DATA)): digest(p) for p in paths},
            "retrieval": retrieval, "diagnosis": diagnosis, "usage": usage, "cases": cases}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["rank", "live", "score"])
    parser.add_argument("--arm", choices=["before", "after"])
    args = parser.parse_args()
    check_inputs()
    if args.stage == "score":
        save(DATA / "summary.json", summarize())
    elif not args.arm:
        parser.error("Indica la versión con --arm.")
    elif args.stage == "rank":
        rank(DATA / f"{args.arm}-ranks.json")
    else:
        from eval.quality.live import main

        main(DATA / args.arm, cases_path=DATA / "windows.json", protocol=DATA / "manifest.json",
             reverse=args.arm == "after", expand_activity=args.arm == "after")
