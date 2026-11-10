"""Modelo común de evidencia (decisión 22, `recomend/modelo_comun.md`).

Las firmas se escriben una sola vez contra estos tipos. Cada observación conserva su `fuente`, su
`texto_original` y su `tiempo`, y recibe un id citable `S0001…` estable por corrida (A29).

El enum `Fuente` nombra las fuentes del adaptador GKE y se extiende por adaptador (A36); no hay
interfaz `EvidenceAdapter` ni campo `proveedor`. `terminaciones_en_ventana` se eliminó (alcance MVP).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Fuente = Literal["cloud_logging", "k8s_events", "recorder", "observer", "monitoring"]
Severidad = Literal[
    "DEFAULT", "DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY"
]
SEVERITY_RANK = {s: i for i, s in enumerate(Severidad.__args__)}  # type: ignore[attr-defined]
ID_PATTERN = r"^S\d{4,}$"


def severity_rank(value: str | None) -> int:
    return SEVERITY_RANK.get((value or "DEFAULT").upper(), SEVERITY_RANK["DEFAULT"])


def at_least_warning(value: str | None) -> bool:
    return severity_rank(value) >= SEVERITY_RANK["WARNING"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Observacion(_Strict):
    """Base de toda pieza citable. Sin `fuente` o sin texto original, no hay observación."""

    id: str = Field(default="", pattern=r"^$|" + ID_PATTERN)
    fuente: Fuente
    tiempo: datetime
    texto_original: str = Field(min_length=1, max_length=4000)
    servicio: str | None = None

    @field_validator("tiempo")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("El tiempo de una observación debe incluir zona horaria.")
        return value


class Servicio(Observacion):
    """Estado de un Deployment/StatefulSet en una instantánea del registrador."""

    servicio: str
    tipo_carga: Literal["Deployment", "StatefulSet"] = "Deployment"
    ubicacion: str = ""  # clúster/namespace
    instancias_deseadas: int | None = Field(default=None, ge=0)
    instancias_listas: int | None = Field(default=None, ge=0)
    endpoints_listos: int | None = Field(default=None, ge=0)
    version_config: str | None = None  # generación + hash del spec
    direcciones: dict[str, str] = Field(default_factory=dict)  # variables *_ADDR literales


class DireccionServicio(Observacion):
    """ClusterIP y puertos de un Service en una instantánea (A01)."""

    servicio: str
    cluster_ip: str | None = None
    puertos: list[int] = Field(default_factory=list)


class Instancia(Observacion):
    servicio: str
    instancia: str
    estado: Literal["arrancando", "corriendo", "terminada", "desconocido"] = "desconocido"
    ip: str | None = None
    motivo_fin: str | None = None
    codigo_salida: int | None = None
    limites: dict[str, dict[str, str]] = Field(default_factory=dict)


class Cambio(Observacion):
    servicio: str
    tipo: Literal["escalado", "config_cambiada", "imagen_cambiada"]
    antes: str | None = None
    despues: str | None = None


class Evento(Observacion):
    instancia: str | None = None
    tipo: Literal[
        "instancia_terminada",
        "sin_capacidad",
        "health_check_fallido",
        "imagen_no_disponible",
        "instancia_iniciada",
        "otro",
    ]
    razon: str = ""  # reason original de la plataforma
    asignacion: str = ""  # cómo se asignó el servicio (nombre exacto o patrón de pod)


class Senal(Observacion):
    """Log o métrica. Un log lleva severidad y mensaje; una métrica, nombre y valor."""

    servicio: str
    clase: Literal["log", "metrica"] = "log"
    instancia: str | None = None
    severidad: str = "DEFAULT"
    nombre: (
        Literal["latencia_p95", "latencia_dependencia_p95", "tasa_error", "cpu_throttling", "memoria_uso"]
        | None
    ) = None
    destino: str | None = None
    valor: float | None = None

    @model_validator(mode="after")
    def _shape(self):
        if self.clase == "metrica":
            if self.nombre is None or self.valor is None:
                raise ValueError("Una métrica necesita nombre y valor.")
            if self.nombre == "latencia_dependencia_p95" and not self.destino:
                raise ValueError("latencia_dependencia_p95 necesita el destino.")
        return self

    @property
    def mensaje(self) -> str:
        return self.texto_original


class CoberturaServicio(_Strict):
    servicio: str
    registros_leidos: int = Field(default=0, ge=0)
    truncado: bool = False  # la lectura WARNING+ llenó su cuota: nunca puede quedar sano
    truncado_info: bool = False  # la lectura de tráfico llenó su cuota (no impide el sano)
    fuentes_fallidas: list[Fuente] = Field(default_factory=list)


class Ventana(_Strict):
    """`t0` y las dos ventanas que se comparan (A03).

    * En la campaña, `t0` es el instante de la inyección. En uso real, es el inicio de la ventana que
      pide el operador (`inicio`).
    * Incidente: `[t0, fin]`. Línea base: `[t0 - (fin - t0), t0)`, de la misma duración.
    """

    inicio: datetime
    fin: datetime
    t0: datetime

    @model_validator(mode="after")
    def _valid(self):
        for value in (self.inicio, self.fin, self.t0):
            if value.tzinfo is None:
                raise ValueError("La ventana debe incluir zona horaria.")
        if not self.inicio <= self.t0 < self.fin:
            raise ValueError("t0 debe estar dentro de la ventana [inicio, fin).")
        return self

    @classmethod
    def desde(cls, inicio: datetime, fin: datetime, t0: datetime | None = None) -> "Ventana":
        return cls(inicio=inicio, fin=fin, t0=t0 or inicio)

    @property
    def duracion(self) -> timedelta:
        return self.fin - self.t0

    @property
    def base_inicio(self) -> datetime:
        return self.t0 - self.duracion

    def en_incidente(self, t: datetime) -> bool:
        return self.t0 <= t <= self.fin

    def en_linea_base(self, t: datetime) -> bool:
        return self.base_inicio <= t < self.t0


class Evidencia(_Strict):
    """Todo lo que recogió el barrido, en el modelo común, con ids asignados."""

    ventana: Ventana
    namespace: str
    inventario: list[str]
    servicios: list[Servicio] = Field(default_factory=list)
    direcciones: list[DireccionServicio] = Field(default_factory=list)
    instancias: list[Instancia] = Field(default_factory=list)
    cambios: list[Cambio] = Field(default_factory=list)
    eventos: list[Evento] = Field(default_factory=list)
    senales: list[Senal] = Field(default_factory=list)
    cobertura: dict[str, CoberturaServicio] = Field(default_factory=dict)
    fuentes_fallidas: dict[str, str] = Field(default_factory=dict)  # fuente -> motivo

    def observaciones(self) -> list[Observacion]:
        return [
            *self.servicios,
            *self.direcciones,
            *self.instancias,
            *self.cambios,
            *self.eventos,
            *self.senales,
        ]

    def por_id(self) -> dict[str, Observacion]:
        return {o.id: o for o in self.observaciones() if o.id}


_ORDEN_LISTAS = ("servicios", "direcciones", "instancias", "cambios", "eventos", "senales")


def asignar_ids(evidencia: Evidencia) -> Evidencia:
    """Ids `S0001…` deterministas: mismo contenido, mismos ids, también en el replay (A29)."""
    rows = []
    for lista in _ORDEN_LISTAS:
        for index, obs in enumerate(getattr(evidencia, lista)):
            key = (obs.tiempo, obs.fuente, obs.servicio or "", lista, obs.texto_original, index)
            rows.append((key, lista, index))
    rows.sort(key=lambda row: row[0])
    nuevos: dict[str, list] = {lista: list(getattr(evidencia, lista)) for lista in _ORDEN_LISTAS}
    for n, (_, lista, index) in enumerate(rows, 1):
        nuevos[lista][index] = nuevos[lista][index].model_copy(update={"id": f"S{n:04}"})
    return evidencia.model_copy(update=nuevos)
