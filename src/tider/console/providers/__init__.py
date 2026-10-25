"""Evidence gateway: explicit source selection, no fallback between sources."""

from ..models import AnalyzeRequest, Signal
from ..settings import Settings
from .cloud_logging import gcp_signals
from .mock import mock_signals


class EvidenceProvider:
    def __init__(self, settings: Settings, context_lake=None):
        self.settings = settings
        self.context_lake = context_lake

    def load(self, request: AnalyzeRequest) -> list[Signal]:
        if (request.mode or self.settings.evidence_mode) == "mock":
            return mock_signals(request.service, request.start, request.end, request.scenario)
        if request.scope == "general":
            catalog = self.context_lake.catalog() if self.context_lake else None
            if not catalog or catalog["status"] != "confirmed":
                raise ValueError("Confirma un catálogo para realizar un análisis general.")
            services = sorted({s["name"] for s in catalog["confirmed"]["services"]})
            if not services:
                raise ValueError("El catálogo confirmado no contiene servicios.")
            return gcp_signals("general", request.start, request.end, self.settings, services=services)
        scope = self.context_lake.query_scope(request.service) if self.context_lake else None
        if scope is None:
            return gcp_signals(request.service, request.start, request.end, self.settings)
        return gcp_signals(request.service, request.start, request.end, self.settings, services=scope)
