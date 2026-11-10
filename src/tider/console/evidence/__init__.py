"""Modelo común de evidencia (pipeline v2). Sin interfaz `EvidenceAdapter` (A36): `gke.GKEAdapter` es concreto."""

from .destinos import Destino, TablaServicios, extraer_destinos, resolver_destino
from .model import (
    Cambio,
    CoberturaServicio,
    DireccionServicio,
    Evento,
    Evidencia,
    Fuente,
    Instancia,
    Observacion,
    Senal,
    Servicio,
    Ventana,
    asignar_ids,
)

__all__ = [
    "Cambio",
    "CoberturaServicio",
    "Destino",
    "DireccionServicio",
    "Evento",
    "Evidencia",
    "Fuente",
    "Instancia",
    "Observacion",
    "Senal",
    "Servicio",
    "TablaServicios",
    "Ventana",
    "asignar_ids",
    "extraer_destinos",
    "resolver_destino",
]
