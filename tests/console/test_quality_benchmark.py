"""Regressions for blinded, reproducible evidence scoring."""

from copy import deepcopy

import pytest

from eval.quality.data import HERE, read
from eval.quality.score import paired, proportion, score_retrieval, score_window


def test_wilson_handles_extremes_and_paired_disagreements_are_exact():
    assert proportion([False] * 6)["wilson95"] == pytest.approx([0, .3903343])
    assert proportion([True] * 2)["wilson95"] == pytest.approx([.3423802, 1])
    assert proportion([])["rate"] is None
    assert paired([False] * 7, [True] * 7)["exact_two_sided_p"] == .015625
    assert paired([True, False], [True, False])["exact_two_sided_p"] == 1


def test_retrieval_scores_alternatives_rank_and_negatives_separately():
    rows = {"q": {"tider": ["other", "b"], "lexical": []},
            "n": {"tider": ["other"], "lexical": []}}
    capture = {"rankings": rows, "passages": ["a", "b", "other"], "k": 4}
    expected = {"q": ["a", "b"], "n": []}
    result = score_retrieval(capture, {"q": "x", "n": "y"}, expected, 4)["summary"]["tider"]
    assert result["hit_at_4"]["hits"] == result["hit_at_4"]["n"] == 1
    assert result["macro_recall_at_4"] == result["mrr_at_4"] == .5
    assert result["empty_on_unanswerable"]["hits"] == 0
    rows["q"]["tider"] = ["b", "b"]
    with pytest.raises(ValueError, match="Ranking"):
        score_retrieval(capture, expected, expected, 4)


def test_only_returned_log_groups_in_mechanism_citations_can_ground_a_match():
    case = read(HERE / "windows.json")[1]
    label = read(HERE / "incident_labels.json")[case["id"]]
    saved = read(HERE / "recordings/2026-11-06/I02.json")["result"]
    # Deliberately correct the label in a test copy. Guessing it still lacks two required records.
    run = deepcopy(saved)
    run["candidate"].update(mechanism="wrong_port", mechanism_cites=["Q1"])
    assert score_window(case, label, run)["mechanism_match"]
    assert not score_window(case, label, run)["joint_with_required_evidence"]
    run["observations"].append({"id": "Qextra", "tool": "search_logs", "kind": "log", "args": {},
                                "data": {"groups": []}})
    for i in (3, 4):
        signal = {**case["signals"][i - 1], "id": f"new{i}"}
        run["evidence"].append(signal)
        run["observations"][-1]["data"]["groups"].append({**signal, "signal_ids": [signal["id"]]})
    result = score_window(case, label, run)
    assert result["required_retrieved"] == label["required_records"]
    assert not result["joint_with_required_evidence"]
    run["candidate"]["cites"].append("Qextra")
    run["candidate"]["mechanism_cites"].append("Qextra")
    assert score_window(case, label, run)["joint_with_required_evidence"]
    run["candidate"]["mechanism_cites"].append("Qinventada")
    assert not score_window(case, label, run)["joint_with_required_evidence"]


def test_technical_failure_or_budget_stop_cannot_be_a_correct_abstention():
    case = read(HERE / "windows.json")[3]
    label = read(HERE / "incident_labels.json")[case["id"]]
    run = read(HERE / "recordings/2026-11-06/I04.json")["result"]
    assert score_window(case, label, run)["mechanism_match"]
    run["stop_reason"] = "budget"
    assert not score_window(case, label, run)["mechanism_match"]
    run["stop_reason"] = "model_error"
    score = score_window(case, label, run)
    assert score["technical_error"] and not score["location_match"] and not score["mechanism_match"]


def test_missing_queries_and_unknown_reference_are_rejected():
    capture = {"rankings": {}, "passages": ["a"], "k": 4}
    with pytest.raises(ValueError, match="corresponden"):
        score_retrieval(capture, {"q": "query"}, {"q": []}, 4)
    capture["rankings"]["q"] = {"tider": [], "lexical": []}
    with pytest.raises(ValueError, match="esperado inválido"):
        score_retrieval(capture, {"q": "query"}, {"q": ["missing"]}, 4)
