"""Use case shared by HTTP and tests; owns each application's bounded history."""

from collections import deque
from datetime import datetime, timezone
from threading import Lock
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from .models import Analysis, AnalyzeRequest, Signal
from .settings import Settings


class EvidenceSource(Protocol):
    def load(self, request: AnalyzeRequest) -> list[Signal]: ...


class DiagnosticEngine(Protocol):
    def analyze(self, request: AnalyzeRequest, evidence: list[Signal]) -> Analysis: ...


class EvidenceUnavailable(RuntimeError):
    pass


class AnalysisUnavailable(RuntimeError):
    pass


class AnalysisService:
    def __init__(self, settings: Settings, provider: EvidenceSource, engine: DiagnosticEngine):
        self.settings = settings
        self.provider = provider
        self.engine = engine
        self._history: deque[Analysis] = deque(maxlen=settings.history_limit)
        self._lock = Lock()

    def history(self) -> list[Analysis]:
        with self._lock:
            return [result.model_copy(deep=True) for result in reversed(self._history)]

    def analyze(self, request: AnalyzeRequest) -> Analysis:
        started = perf_counter()
        try:
            evidence = self.provider.load(request)
        except ValueError:
            raise
        except Exception as exc:
            raise EvidenceUnavailable("No se pudo consultar la fuente de evidencia.") from exc
        evidence = [
            signal.model_copy(update={"id": f"S{index:02}"}) for index, signal in enumerate(evidence, 1)
        ]
        try:
            result = self.engine.analyze(request, evidence)
        except ValueError:
            raise
        except Exception as exc:
            raise AnalysisUnavailable("No se pudo completar el análisis.") from exc
        result.evidence_mode = request.mode or self.settings.evidence_mode
        result.run_id = uuid4().hex
        result.elapsed_ms = round((perf_counter() - started) * 1000, 2)
        result.analyzed_at = datetime.now(timezone.utc)
        with self._lock:
            self._history.append(result.model_copy(deep=True))
        return result
