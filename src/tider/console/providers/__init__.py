"""Evidence gateway: explicit source selection, no fallback between sources."""

from ..models import AnalyzeRequest, Signal
from ..settings import Settings
from .cloud_logging import gcp_signals
from .mock import mock_signals


class EvidenceProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def load(self, request: AnalyzeRequest) -> list[Signal]:
        if (request.mode or self.settings.evidence_mode) == "mock":
            return mock_signals(request.service, request.start, request.end, request.scenario)
        return gcp_signals(request.service, request.start, request.end, self.settings)
