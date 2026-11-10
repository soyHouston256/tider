"""Recolector (barrido) determinista del pipeline v2. Corre antes de cualquier llamada al LLM.

Orden de cálculo (A04): **barrido → Cartógrafo → verificador → estado**. Este módulo solo hace el
barrido: inventario de la plataforma, eventos del namespace, dos lecturas de logs por servicio y la
tabla de una fila por servicio con los insumos de los predicados (anomalía, errores atribuidos por
`ClusterIP:puerto`, tráfico, plataforma). El estado final por servicio (falla / sano / sin datos)
necesita el grafo y los veredictos de firmas, y vive en `estado.estado_servicio` (Fase 2).
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field

from .evidence.gke import Cuotas, GKEAdapter
from .evidence.model import CoberturaServicio, Evidencia, Ventana, at_least_warning
from .models import AnalyzeRequest
from .predicados import (
    Anomalia,
    Clausula,
    agrupar_eventos,
    anomalia,
    atribuir_errores,
    clausula_plataforma,
    trafico,
)
from .recorder import Recorder

_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_ADDR = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{1,5}\b")
_HEX = re.compile(r"\b[0-9a-f]{8,}\b", re.I)
_CODE = re.compile(r"\b[A-Z0-9]{10}\b")
_NUM = re.compile(r"\d+")


def plantilla(texto: str) -> str:
    """Plantilla de error: ids, números y códigos se reemplazan; `IP:puerto` se conserva (discrimina)."""
    primera = (texto or "").splitlines()[0] if texto else ""
    guardados: list[str] = []

    def guardar(match):
        guardados.append(match.group(0))
        return f"\x00{'abcdefghijklmnopqrstuvwxyz'[min(len(guardados) - 1, 25)]}\x00"

    t = _ADDR.sub(guardar, primera)
    for pattern, token in ((_UUID, "<id>"), (_HEX, "<hex>"), (_CODE, "<cod>"), (_NUM, "<n>")):
        t = pattern.sub(token, t)
    t = re.sub(r"\x00([a-z])\x00", lambda m: guardados[min(ord(m.group(1)) - 97, len(guardados) - 1)], t)
    return re.sub(r"\s+", " ", t).strip()[:400]


class PlantillaError(BaseModel):
    plantilla: str
    conteo: int
    primera: datetime
    ultima: datetime
    ids: list[str] = Field(default_factory=list)  # hasta 5 ids de ejemplo


class FilaServicio(BaseModel):
    servicio: str
    severidades: dict[str, int] = Field(default_factory=dict)  # líneas del incidente por severidad
    plantillas: list[PlantillaError] = Field(default_factory=list)
    primera: datetime | None = None  # primer error (>= WARNING) del incidente
    ultima: datetime | None = None
    eventos: list[str] = Field(default_factory=list)
    cambios: list[str] = Field(default_factory=list)
    instancias_deseadas_min: int | None = None
    instancias_listas_min: int | None = None
    endpoints_listos_min: int | None = None
    cobertura: CoberturaServicio
    anomalia: Anomalia
    plataforma: Clausula
    errores_atribuidos: list[str] = Field(default_factory=list)
    trafico: int = 0


class Barrido(BaseModel):
    ventana: Ventana
    evidencia: Evidencia
    filas: list[FilaServicio]
    errores_sin_atribuir: list[str] = Field(default_factory=list)

    def fila(self, servicio: str) -> FilaServicio | None:
        return next((f for f in self.filas if f.servicio == servicio), None)


def _fila(servicio: str, evidencia: Evidencia, atribuidos: list[str], settings) -> FilaServicio:
    ventana = evidencia.ventana
    propias = [s for s in evidencia.senales if s.servicio == servicio and ventana.en_incidente(s.tiempo)]
    severidades: dict[str, int] = {}
    for s in propias:
        severidades[s.severidad] = severidades.get(s.severidad, 0) + 1
    errores = [s for s in propias if at_least_warning(s.severidad)]
    plantillas: dict[str, PlantillaError] = {}
    for grupo in agrupar_eventos(errores):
        key = plantilla(grupo.lineas[0])
        p = plantillas.get(key)
        if p is None:
            plantillas[key] = PlantillaError(
                plantilla=key, conteo=1, primera=grupo.inicio, ultima=grupo.inicio, ids=[grupo.ids[0]]
            )
        else:
            p.conteo += 1
            p.ultima = max(p.ultima, grupo.inicio)
            if len(p.ids) < 5:
                p.ids.append(grupo.ids[0])
    estados = [s for s in evidencia.servicios if s.servicio == servicio and s.tiempo <= ventana.fin]
    previas = [s for s in estados if s.tiempo <= ventana.t0][-1:]
    vigentes = previas + [s for s in estados if s.tiempo > ventana.t0]

    def minimo(attr):
        valores = [getattr(s, attr) for s in vigentes if getattr(s, attr) is not None]
        return min(valores) if valores else None

    return FilaServicio(
        servicio=servicio,
        severidades=severidades,
        plantillas=sorted(plantillas.values(), key=lambda p: (-p.conteo, p.primera)),
        primera=min((s.tiempo for s in errores), default=None),
        ultima=max((s.tiempo for s in errores), default=None),
        eventos=[
            e.id for e in evidencia.eventos if e.servicio == servicio and ventana.en_incidente(e.tiempo)
        ],
        cambios=[
            c.id
            for c in evidencia.cambios
            if c.servicio == servicio and ventana.base_inicio <= c.tiempo <= ventana.fin
        ],
        instancias_deseadas_min=minimo("instancias_deseadas"),
        instancias_listas_min=minimo("instancias_listas"),
        endpoints_listos_min=minimo("endpoints_listos"),
        cobertura=evidencia.cobertura.get(servicio)
        or CoberturaServicio(servicio=servicio, fuentes_fallidas=["cloud_logging"]),
        anomalia=anomalia(
            servicio,
            evidencia,
            bucket_seconds=settings.anomaly_bucket_seconds,
            min_eventos=settings.anomaly_min_events,
            gracia_arranque=settings.lifecycle_grace_seconds,
        ),
        plataforma=clausula_plataforma(servicio, evidencia),
        errores_atribuidos=atribuidos,
        trafico=len(trafico(servicio, evidencia)),
    )


def tabla(evidencia: Evidencia, settings) -> Barrido:
    atribucion = atribuir_errores(evidencia)
    filas = [_fila(s, evidencia, atribucion.por_servicio.get(s, []), settings) for s in evidencia.inventario]
    return Barrido(
        ventana=evidencia.ventana,
        evidencia=evidencia,
        filas=filas,
        errores_sin_atribuir=atribucion.sin_atribuir,
    )


def sweep(
    solicitud: AnalyzeRequest,
    settings,
    *,
    t0: datetime | None = None,
    adapter: GKEAdapter | None = None,
    recorder: Recorder | None = None,
    inventario: list[str] | None = None,
) -> Barrido:
    """Barrido del pipeline v2. `t0` es el instante de la inyección en la campaña; si falta, el inicio
    de la ventana pedida. El inventario sale del registrador; `inventario` solo se usa si no hay
    instantáneas (y entonces las columnas de plataforma quedan sin datos)."""
    ventana = Ventana.desde(solicitud.start, solicitud.end, t0)
    if adapter is None:
        if recorder is None and settings.recorder_db_path:
            recorder = Recorder.from_settings(settings)
        adapter = GKEAdapter(settings, recorder=recorder)
    cuotas = Cuotas(settings.sweep_quota_per_service, settings.sweep_info_quota_per_service)
    return tabla(adapter.collect(ventana, inventario, cuotas), settings)
