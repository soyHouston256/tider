from tider.console.causal_evaluation import score_causal

EXPECTED = {"accepted_components": ["cartservice"], "mechanism": "cpu_limit"}
REVIEW = {"reviewer": "independent_fixture_review", "mechanism_supported": True, "relevant_cites": ["Q2"]}


def test_component_correct_does_not_credit_wrong_mechanism():
    result = score_causal(EXPECTED, {"component": "cartservice", "mechanism": "scale_zero", "mechanism_cites": ["Q2"]}, adjudication=REVIEW)
    assert result["location_correct"] and not result["mechanism_correct"] and not result["causal_correct"]


def test_matching_label_without_independent_support_is_unscored():
    result = score_causal(EXPECTED, {"component": "cartservice", "mechanism": "cpu_limit"})
    assert result["mechanism_correct"] and result["causal_correct"] is None


def test_supported_mechanism_requires_relevant_cites():
    candidate = {"component": "cartservice", "mechanism": "cpu_limit", "mechanism_cites": ["Q2"]}
    assert score_causal(EXPECTED, candidate, adjudication=REVIEW)["causal_correct"]
    candidate["mechanism_cites"] = ["Q1"]
    assert not score_causal(EXPECTED, candidate, adjudication=REVIEW)["causal_correct"]


def test_technical_failure_is_not_valid_abstention():
    result = score_causal(EXPECTED, {}, technical_error=True)
    assert result["technical_error"] and not result["abstained"] and result["causal_correct"] is None


def test_unknown_cause_keeps_location_separate():
    result = score_causal(EXPECTED, {"component": "cartservice"})
    assert result["location_correct"] and result["abstained"] and not result["mechanism_correct"]
