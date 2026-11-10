"""Validated public contracts for analysis, evidence and readable decisions."""

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from tider.state import Decision, Hypothesis, Verdict


class Signal(BaseModel):
    id: str = ""
    timestamp: datetime
    service: str
    source: Literal["log", "metric", "trace", "event"]
    message: str
    severity: str = "INFO"
    trace_id: str | None = None
    # Pod que emitió la línea. Solo lo usa el barrido v2 (agrupar trazas multilínea); no se serializa.
    instance: str | None = Field(default=None, exclude=True)


class AnalyzeRequest(BaseModel):
    objective: str = Field(default="Investiga el incidente y determina qué evidencia falta.", max_length=2000)
    incident_id: str = Field(min_length=1, max_length=128)
    scope: Literal["focused", "general"] = "general"
    service: str | None = Field(default=None, min_length=1, max_length=63, pattern=r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
    start: datetime
    end: datetime
    mode: Literal["mock", "gcp"] | None = None
    scenario: Literal["redis_down", "cart_unavailable", "healthy", "missing_telemetry"] = "redis_down"

    @model_validator(mode="after")
    def valid_window(self):
        # Older API clients that explicitly provide a service keep their focused scope.
        # A symptom without a service starts a general investigation.
        if "scope" not in self.model_fields_set:
            self.scope = "focused" if self.service else "general"
        if self.scope == "focused" and not self.service:
            raise ValueError("Selecciona un servicio para el análisis enfocado.")
        if self.scope == "general":
            self.service = None
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Las fechas deben incluir zona horaria.")
        if self.start >= self.end or self.end - self.start > timedelta(hours=2):
            raise ValueError("La ventana debe ser positiva y no superar dos horas.")
        return self


class DecisionStep(BaseModel):
    sequence: int
    stage: str
    title: str
    outcome: str
    reason: str
    status: Literal["completed", "needs_review", "skipped"]
    evidence_ids: list[str] = Field(default_factory=list)


class UnscoredVerdict(BaseModel):
    confidence: None = None
    supported: bool = False
    missing: list[str] = Field(default_factory=list)
    notes: str = ""


class WorkflowResult(BaseModel):
    handler: str = "generic"
    context: list[dict] = Field(default_factory=list)
    hypothesis: Hypothesis | None = None
    verdict: Verdict | UnscoredVerdict | None = None
    decision: Decision | None = None
    execution: dict = Field(default_factory=dict)
    resolved: bool = False
    report: str = ""
    audit: list[dict] = Field(default_factory=list)


class Analysis(BaseModel):
    scope: Literal["focused", "general"] = "focused"
    incident_id: str
    hypothesis: str
    component: str
    confidence: float | None = Field(ge=0, le=1)
    evidence: list[Signal]
    recommendation: str
    status: Literal["hypothesis", "partial", "insufficient_evidence"] = "hypothesis"
    disclaimer: str = "Hipótesis para revisión humana. Sin remediación ejecutada."
    evidence_mode: Literal["mock", "gcp"] = "mock"
    engine: str = "langgraph"
    reasoning_mode: str = "rules"
    namespace: str = "boutique"
    elapsed_ms: float = 0
    run_id: str = ""
    analyzed_at: datetime | None = None
    workflow: WorkflowResult = Field(default_factory=WorkflowResult)
    investigation: dict = Field(default_factory=dict)
    decision_steps: list[DecisionStep] = Field(default_factory=list)


# --- Pipeline v2 (Fase 2): entidad, nodo y arista del contrato (§5). Cita, Hipotesis y Recomendacion
# llegan en la Fase 3 junto con `Analysis` v2.

EstadoEntidad = Literal["falla", "sano", "sin_datos"]


class Entidad(BaseModel):
    """Entidad de una hipótesis o de un veredicto: un servicio del inventario o un enlace del grafo."""

    model_config = {"frozen": True}

    tipo: Literal["servicio", "enlace"]
    servicio: str | None = None
    origen: str | None = None
    destino: str | None = None

    @model_validator(mode="after")
    def _shape(self):
        if self.tipo == "servicio" and (not self.servicio or self.origen or self.destino):
            raise ValueError("Una entidad servicio lleva solo `servicio`.")
        if self.tipo == "enlace" and (self.servicio or not self.origen or not self.destino):
            raise ValueError("Una entidad enlace lleva `origen` y `destino`.")
        return self

    @classmethod
    def de_servicio(cls, nombre: str) -> "Entidad":
        return cls(tipo="servicio", servicio=nombre)

    @classmethod
    def de_enlace(cls, origen: str, destino: str) -> "Entidad":
        return cls(tipo="enlace", origen=origen, destino=destino)

    @property
    def clave(self) -> str:
        return self.servicio if self.tipo == "servicio" else f"{self.origen}->{self.destino}"

    @property
    def componente(self) -> str:
        """Alias `component` de v1: el servicio, o el origen si es un enlace."""
        return self.servicio if self.tipo == "servicio" else self.origen


class Nodo(BaseModel):
    """Estado de un servicio en la ventana y su rol en la hipótesis principal.

    * `estado`: `falla` (firma CONFIRMADA o anomalía propia), `sano` (predicado P3) o `sin_datos`.
    * `rol_en_principal`: `causa`, `victima` o `ninguno`. Lo asigna código (`estado.asignar_roles`, P8),
      no el LLM; por defecto `ninguno` hasta que haya hipótesis principal.
    """

    servicio: str
    tipo: Literal["tienda", "auxiliar"] = "tienda"
    estado: EstadoEntidad = "sin_datos"
    motivo: str = ""
    rol_en_principal: Literal["causa", "victima", "ninguno"] = "ninguno"
    motivo_rol: str = ""
    ids_rol: list[str] = Field(default_factory=list)  # citas que sostienen el rol (S0001…)
    cobertura: dict = Field(default_factory=dict)  # `CoberturaServicio` serializada
    truncado: bool = False
    ids: list[str] = Field(default_factory=list)  # citas que sostienen el estado


class Arista(BaseModel):
    """Enlace `origen→destino` del grafo.

    * `origen_dato`: `configurada` (Lake), `observada` (`*_ADDR` del spec o errores atribuidos) o `ambas`.
    * `estado` (A06): `falla` si hay una firma CONFIRMADA sobre el enlace o errores del origen atribuidos
      al destino en el incidente; `sano` si ambos extremos están sanos; `sin_datos` en otro caso. La regla 2
      del juez sobre un enlace exige `estado == "falla"`.
    """

    origen: str
    destino: str
    origen_dato: Literal["configurada", "observada", "ambas"]
    estado: EstadoEntidad = "sin_datos"
    variable: str | None = None  # variable *_ADDR que la define, si se conoce
    valor: str | None = None  # valor observado en el spec (o el del Lake si solo es configurada)
    ids: list[str] = Field(default_factory=list)  # observaciones que la muestran o la ponen en falla
