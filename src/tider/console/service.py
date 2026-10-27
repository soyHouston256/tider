"""Use case shared by HTTP and tests; owns each application's bounded history."""

import sqlite3
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
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
        self._history_path = settings.investigation_history_path
        if self._history_path:
            path = Path(self._history_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._history_path = str(path)
            with sqlite3.connect(self._history_path) as db:
                db.execute("CREATE TABLE IF NOT EXISTS investigations (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
                rows = db.execute("SELECT payload FROM investigations ORDER BY id DESC LIMIT ?", (settings.history_limit,)).fetchall()
                self._history.extend(Analysis.model_validate_json(row[0]) for row in reversed(rows))

    def history(self) -> list[Analysis]:
        with self._lock:
            return [result.model_copy(deep=True) for result in reversed(self._history)]

    def analyze(self, request: AnalyzeRequest, emit=None) -> Analysis:
        started = perf_counter()
        if self.settings.llm_provider != "none" and hasattr(self.engine, "analyze_live"):
            try:
                result = self.engine.analyze_live(request, emit=emit)
            except ValueError:
                raise
            except Exception as exc:
                raise AnalysisUnavailable("No se pudo completar la investigación.") from exc
        else:
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
        result.scope = request.scope
        result.evidence_mode = request.mode or self.settings.evidence_mode
        result.run_id = uuid4().hex
        result.elapsed_ms = round((perf_counter() - started) * 1000, 2)
        result.analyzed_at = datetime.now(timezone.utc)
        with self._lock:
            if self._history_path:
                with sqlite3.connect(self._history_path) as db:
                    db.execute("INSERT INTO investigations(payload) VALUES (?)", (result.model_dump_json(),))
                    db.execute("DELETE FROM investigations WHERE id NOT IN (SELECT id FROM investigations ORDER BY id DESC LIMIT ?)",
                               (self.settings.history_limit,))
            self._history.append(result.model_copy(deep=True))
        return result
