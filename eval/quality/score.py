"""Score captured outputs with exact identifiers. No model, Chroma or network calls."""

from collections import Counter
from datetime import datetime
from math import comb, sqrt
from statistics import NormalDist, mean

from tider.console.causal_evaluation import score_causal

from .data import HERE, digest, read


def proportion(flags):
    n = len(flags)
    hits = sum(flags)
    if not n:
        return {"hits": 0, "n": 0, "rate": None, "wilson95": None}
    z = NormalDist().inv_cdf(.975)
    rate = hits / n
    denom = 1 + z**2 / n
    center = (rate + z**2 / (2 * n)) / denom
    margin = z * sqrt(rate * (1 - rate) / n + z**2 / (4 * n**2)) / denom
    return {"hits": hits, "n": n, "rate": rate,
            "wilson95": [max(0., center - margin), min(1., center + margin)]}


def paired(first, second):
    if not first or len(first) != len(second):
        raise ValueError("Se requieren pares completos")
    wins = sum(a and not b for a, b in zip(first, second, strict=True))
    losses = sum(b and not a for a, b in zip(first, second, strict=True))
    n = wins + losses
    p = min(1., 2 * sum(comb(n, i) for i in range(min(wins, losses) + 1)) / 2**n)
    return {"n": len(first), "first_only": wins, "second_only": losses,
            "difference": (wins - losses) / len(first), "exact_two_sided_p": p}


def score_retrieval(capture, queries, labels, k, methods=("tider", "lexical")):
    if capture["k"] != k or set(capture["rankings"]) != set(queries) or set(labels) != set(queries):
        raise ValueError("Rankings, consultas y etiquetas no corresponden")
    inventory = set(capture["passages"])
    cases = {}
    for key, refs in labels.items():
        if len(set(refs)) != len(refs) or not set(refs) <= inventory:
            raise ValueError(f"Pasaje esperado inválido en {key}")
        row = {"query": queries[key], "expected": refs}
        for method in methods:
            ranked = capture["rankings"][key][method]
            if len(ranked) > k or len(set(ranked)) != len(ranked) or not set(ranked) <= inventory:
                raise ValueError(f"Ranking inválido en {key}/{method}")
            hits = [i for i, ref in enumerate(ranked, 1) if ref in refs]
            row[method] = {"ranked": ranked, "first_rank": hits[0] if hits else None,
                           "recall": len(hits) / len(refs) if refs else None}
        cases[key] = row
    pos = [row for row in cases.values() if row["expected"]]
    neg = [row for row in cases.values() if not row["expected"]]
    summary = {}
    for m in methods:
        summary[m] = {"hit_at_1": proportion([r[m]["first_rank"] == 1 for r in pos]),
                      "hit_at_4": proportion([bool(r[m]["first_rank"]) for r in pos]),
                      "macro_recall_at_4": mean(r[m]["recall"] for r in pos),
                      "mrr_at_4": mean(1 / r[m]["first_rank"] if r[m]["first_rank"] else 0 for r in pos),
                      "empty_on_unanswerable": proportion([not r[m]["ranked"] for r in neg])}
    return {"summary": summary, "paired_hit_at_4": paired(*[
        [bool(r[m]["first_rank"]) for r in pos] for m in methods]), "cases": cases}


def identity(row):
    return (datetime.fromisoformat(row["timestamp"]), row["service"], row["source"], row["message"])


def records_by_query(case, run):
    source = {identity(s): i for i, s in enumerate(case["signals"], 1)}
    signals = {s["id"]: source[identity(s)] for s in run["evidence"]}
    if len(source) != len(case["signals"]) or len(signals) != len(run["evidence"]):
        raise ValueError("Identidad de registro duplicada")
    found = {}
    for obs in run["observations"]:
        key = obs["id"]
        if key in found:
            raise ValueError(f"Consulta duplicada: {key}")
        found[key] = set()
        if obs["tool"] == "search_logs" and obs["kind"] == "log":
            for group in obs["data"]["groups"]:
                for sid in group["signal_ids"]:
                    i = signals[sid]
                    if any(case["signals"][i-1][f] != group[f] for f in ("service", "source", "message")):
                        raise ValueError("Referencia de evidencia no corresponde al registro expuesto")
                    found[key].add(i)
    return found


def score_window(case, label, run):
    required = set(label["required_records"])
    has_cause = label["mechanism"] != "unknown"
    if has_cause != bool(required) or not required <= set(range(1, len(case["signals"]) + 1)):
        raise ValueError("Rúbrica causal incompleta")
    candidate = run["candidate"]
    technical = run["stop_reason"] in {"model_error", "review_error"} or run["review_status"] == "error"
    # A failed attempt to fetch telemetry cannot earn abstention credit as an empty window.
    log_queries = [q for q in run["observations"] if q["tool"] == "search_logs"]
    if run["errors"] and not any(q["kind"] in {"log", "empty"} for q in log_queries):
        technical = True
    supported = run["status"] == "hypothesis" and run["review_status"] == "passed" and not technical
    explicit_unknown = (candidate.get("component") == "desconocido" and
                        candidate.get("mechanism") == "unknown" and run["stop_reason"] == "insufficient"
                        and not technical)
    scorable = supported or explicit_unknown
    component = run["component"]
    mechanism = candidate.get("mechanism")
    matches = score_causal(label, {"component": component, "mechanism": mechanism},
                           technical_error=technical)
    by_query = records_by_query(case, run)
    seen = set().union(*by_query.values())
    cites = candidate.get("mechanism_cites", [])
    cited = set().union(*(by_query.get(q, set()) for q in cites))
    valid_refs = bool(cites) and set(cites) <= set(candidate.get("cites", [])) and all(
        q in by_query and bool(by_query[q] & required) for q in cites)
    location = scorable and bool(matches["location_correct"])
    mechanism_ok = scorable and bool(matches["mechanism_correct"])
    return {"expected_components": label["accepted_components"], "expected_mechanism": label["mechanism"],
            "component": component, "candidate_mechanism": mechanism, "status": run["status"],
            "stop_reason": run["stop_reason"], "technical_error": technical,
            "location_match": location, "mechanism_match": mechanism_ok,
            "required": sorted(required), "required_retrieved": sorted(required & seen),
            "required_cited": sorted(required & cited), "mechanism_cites": cites,
            "joint_with_required_evidence": bool(location and mechanism_ok and valid_refs and required <= cited)
            if has_cause else None,
            "asserted_cause": bool(supported and mechanism not in {None, "unknown"}),
            "queried_documents": any(o["tool"] == "context_search" for o in run["observations"]),
            "log_queries": len(log_queries),
            "errors_only_queries": sum(q["args"].get("errors_only", True) is True for q in log_queries),
            "input_tokens": sum(m.get("input_tokens", 0) for m in run["model_requests"]),
            "output_tokens": sum(m.get("output_tokens", 0) for m in run["model_requests"]),
            "model_calls": run["model_calls"]}


def score_diagnoses(folder):
    meta = read(folder / "run.json")
    if meta["protocol"] != digest(HERE / "manifest.json"):
        raise ValueError("La corrida pertenece a otra versión del protocolo")
    windows = read(HERE / "windows.json")
    labels = read(HERE / "incident_labels.json")
    ids = {c["id"] for c in windows}
    if len(windows) != len(ids) or ids != set(labels) or ids != {p.stem for p in folder.glob("I*.json")}:
        raise ValueError("Se requiere exactamente un resultado por ventana")
    rows = {}
    for case in windows:
        key = case["id"]
        entry = read(folder / f"{key}.json")
        if entry["id"] != key or entry["result"]["model"] != meta["model"]:
            raise ValueError("Identidad o modelo incompatible")
        rows[key] = score_window(case, labels[key], entry["result"])
    pos = [r for r in rows.values() if r["required"]]
    controls = [r for r in rows.values() if not r["required"]]
    return {"model": meta["model"], "windows": len(rows), "summary": {
        "location_including_unknown": proportion([r["location_match"] for r in rows.values()]),
        "location_known": proportion([r["location_match"] for r in rows.values()
                                      if "desconocido" not in r["expected_components"]]),
        "mechanism_on_known": proportion([r["mechanism_match"] for r in pos]),
        "all_required_retrieved": proportion([r["required_retrieved"] == r["required"] for r in pos]),
        "joint_with_required_evidence": proportion([r["joint_with_required_evidence"] for r in pos]),
        "explicit_unknown_on_controls": proportion([r["mechanism_match"] for r in controls]),
        "false_attribution_on_controls": proportion([r["asserted_cause"] for r in controls]),
        "technical_errors": sum(r["technical_error"] for r in rows.values()),
        "outcomes": dict(Counter(r["stop_reason"] for r in rows.values())),
        "windows_with_document_query": sum(r["queried_documents"] for r in rows.values()),
        **{field: sum(r[field] for r in rows.values()) for field in (
            "log_queries", "errors_only_queries", "model_calls", "input_tokens", "output_tokens")}}, "cases": rows}
