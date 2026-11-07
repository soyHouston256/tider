"""Offline scoring: location, mechanism and independent evidence review are separate.

No model calls. The ground truth and adjudication belong to the evaluator, never
to the investigation input. A missing independent review remains unscored.
"""


def score_causal(expected, candidate, *, adjudication=None, technical_error=False):
    if technical_error:
        return {"location_correct": None, "mechanism_correct": None, "causal_correct": None,
                "abstained": False, "technical_error": True, "evidence_supported": None}
    component = candidate.get("component", "desconocido")
    mechanism = candidate.get("mechanism", "unknown")
    abstained = component == "desconocido" or mechanism == "unknown"
    location = component in expected["accepted_components"]
    mechanism_correct = mechanism == expected["mechanism"]
    support = None
    if adjudication is not None:
        if (not adjudication.get("reviewer") or type(adjudication.get("mechanism_supported")) is not bool
                or not isinstance(adjudication.get("relevant_cites"), list)):
            raise ValueError("Se requiere revisión independiente identificada y citas pertinentes.")
        cites = set(candidate.get("mechanism_cites", []))
        support = adjudication["mechanism_supported"] and bool(cites) and cites <= set(adjudication["relevant_cites"])
    return {"location_correct": location, "mechanism_correct": mechanism_correct,
            "causal_correct": (location and mechanism_correct and support) if support is not None else None,
            "abstained": abstained, "technical_error": False, "evidence_supported": support}
