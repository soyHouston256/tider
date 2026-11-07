"""Recalculate retrieval and diagnosis statistics from saved outputs, offline."""

import argparse
import json
from pathlib import Path

from .data import HERE, digest, read, save, verify
from .log_control import collect_log_control
from .score import score_diagnoses, score_retrieval


def evaluate(retrieval, runs):
    manifest = verify()
    capture = read(retrieval)
    if capture["protocol"] != digest(HERE / "manifest.json"):
        raise ValueError("Los rankings pertenecen a otro protocolo")
    return {"protocol_sha256": capture["protocol"],
            "recordings_sha256": {"retrieval": digest(retrieval),
                                  **{p.name: digest(p) for p in sorted(runs.glob("*.json"))}},
            "retrieval": score_retrieval(capture, read(HERE / "queries.json"),
                                         read(HERE / "passage_labels.json"), manifest["k"]),
            "diagnosis": score_diagnoses(runs), "log_filter_control": collect_log_control()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval", type=Path, default=HERE / "recordings/retrieval-v1.json")
    parser.add_argument("--runs", type=Path, default=HERE / "recordings/2026-11-06")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify", action="store_true", help="Contrastar con el informe de referencia publicado")
    args = parser.parse_args()
    report = evaluate(args.retrieval, args.runs)
    if args.verify and report != read(HERE / "recordings/summary-v1.json"):
        parser.exit(1, "El informe difiere de la referencia. Revisa las diferencias por caso.\n")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        save(args.out, report)
    print(json.dumps({k: report[k]["summary"] for k in ("retrieval", "diagnosis")}, indent=2))
