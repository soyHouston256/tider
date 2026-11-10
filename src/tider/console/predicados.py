"""Predicados deterministas que no dependen del grafo ni de las firmas (Fase 1).

* `agrupar_eventos`: una traza multilínea es un solo evento (RB-01: 1937 líneas = pocas trazas, PM-02).
* `ruido_ciclo_vida`: líneas de un pod que termina (después de `Killing`) o que arranca (gracia tras
  `Started`/`Created`/`Scheduled`), como los `DeprecationWarning` de paymentservice en PM-04.
* `anomalia`: función de anomalía de A03 (definición abajo).
* `atribuir_errores`: errores de llamadores atribuidos por `ClusterIP:puerto` exacto (A01).
* `trafico`: líneas de actividad normal (A02).
* `clausula_plataforma` y `sano_confirmado`: el predicado de "sano confirmado" según P3 (aceptada).

**Anomalía (A03).** Para cada servicio:
1. se toman sus logs con severidad >= WARNING (RB-01), se agrupan las trazas multilínea y se descarta
   el ruido de ciclo de vida;
2. la línea base `[t0 - D, t0)` y el incidente `[t0, fin]` (`D = fin - t0`) se dividen en cubetas de
   `anomaly_bucket_seconds`; en la línea base se calcula la media μ y la desviación σ (poblacional) de
   eventos por cubeta;
3. una cubeta del incidente es anómala si su conteo supera `μ + 3σ`;
4. hay anomalía si los eventos de las cubetas anómalas suman al menos `anomaly_min_events` (3).
   `t_inicio` es el primer evento de la primera cubeta anómala. Si la lectura de logs falló, el
   resultado es `None` (sin datos), nunca "sin anomalía".
La deduplicación por plantilla se usa para reportar (tabla del barrido), no para contar: dos errores
iguales son dos eventos.
"""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from .evidence.destinos import TablaServicios, extraer_destinos
from .evidence.model import Cambio, Evento, Evidencia, Senal, Ventana, at_least_warning
from .providers.error_filter import is_error

_CONTINUACION = re.compile(r"^(\s|\^|>|File \"|During handling|The above exception)")
_EXCEPCION = re.compile(r"^[\w.]+(Error|Exception)\b")
_ARRANQUE = {"Started", "Created", "Scheduled"}


@dataclass
class EventoLog:
    servicio: str
    instancia: str | None
    inicio: datetime
    fin: datetime
    severidad: str
    ids: list[str] = field(default_factory=list)
    lineas: list[str] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n".join(self.lineas)


def agrupar_eventos(senales: list[Senal], max_gap: timedelta = timedelta(seconds=1)) -> list[EventoLog]:
    """Agrupa líneas consecutivas del mismo pod que continúan una traza (indentadas, `^`, `>`, `File "…`,
    o la línea de excepción final de un `Traceback`)."""
    eventos: list[EventoLog] = []
    abiertos: dict[str | None, EventoLog] = {}
    for s in sorted(senales, key=lambda s: (s.tiempo, s.id)):
        prev = abiertos.get(s.instancia) if s.instancia else None
        texto = s.texto_original
        traza = prev is not None and prev.lineas[0].startswith("Traceback")
        continua = (
            prev is not None
            and s.tiempo - prev.fin <= max_gap
            and bool(
                _CONTINUACION.match(texto)
                or (traza and (_EXCEPCION.match(texto) or texto.startswith("Traceback")))
            )
        )
        if continua:
            prev.fin = s.tiempo
            prev.ids.append(s.id)
            prev.lineas.append(texto)
            continue
        evento = EventoLog(s.servicio, s.instancia, s.tiempo, s.tiempo, s.severidad, [s.id], [texto])
        eventos.append(evento)
        abiertos[s.instancia] = evento
    return eventos


def ruido_ciclo_vida(eventos: list[Evento], ventana: Ventana, gracia: timedelta) -> dict[str, list[tuple]]:
    """Intervalos por pod en los que sus líneas de error son ruido de arranque o de terminación."""
    intervalos: dict[str, list[tuple]] = {}
    for e in eventos:
        if not e.instancia:
            continue
        if e.razon == "Killing":
            intervalos.setdefault(e.instancia, []).append((e.tiempo, ventana.fin))
        elif e.razon in _ARRANQUE:
            intervalos.setdefault(e.instancia, []).append((e.tiempo, e.tiempo + gracia))
    return intervalos


def _es_ruido(evento: EventoLog, intervalos: dict[str, list[tuple]]) -> bool:
    return any(a <= evento.inicio <= b for a, b in intervalos.get(evento.instancia or "", ()))


class Anomalia(BaseModel):
    servicio: str
    anomala: bool | None  # None = sin datos
    eventos_incidente: int = 0
    eventos_linea_base: int = 0
    ruido_ciclo_vida: int = 0
    media: float = 0
    sigma: float = 0
    umbral: float = 0
    t_inicio: datetime | None = None
    ids: list[str] = Field(default_factory=list)
    motivo: str = ""


def _cubetas(desde: datetime, hasta: datetime, ancho: timedelta) -> int:
    return max(1, math.ceil((hasta - desde) / ancho))


def anomalia(
    servicio: str,
    evidencia: Evidencia,
    *,
    bucket_seconds: int = 30,
    min_eventos: int = 3,
    gracia_arranque: int = 15,
) -> Anomalia:
    ventana = evidencia.ventana
    cobertura = evidencia.cobertura.get(servicio)
    if cobertura is None or "cloud_logging" in cobertura.fuentes_fallidas:
        return Anomalia(servicio=servicio, anomala=None, motivo="lectura de logs fallida o ausente")
    ancho = timedelta(seconds=bucket_seconds)
    errores = [
        s
        for s in evidencia.senales
        if s.servicio == servicio and s.clase == "log" and at_least_warning(s.severidad)
    ]
    intervalos = ruido_ciclo_vida(evidencia.eventos, ventana, timedelta(seconds=gracia_arranque))
    grupos = agrupar_eventos(errores)
    ruido = [g for g in grupos if _es_ruido(g, intervalos)]
    utiles = [g for g in grupos if not _es_ruido(g, intervalos)]
    base = [g for g in utiles if ventana.en_linea_base(g.inicio)]
    incidente = [g for g in utiles if ventana.en_incidente(g.inicio)]

    n_base = _cubetas(ventana.base_inicio, ventana.t0, ancho)
    conteo_base = [0] * n_base
    for g in base:
        conteo_base[min(n_base - 1, int((g.inicio - ventana.base_inicio) / ancho))] += 1
    media = statistics.fmean(conteo_base)
    sigma = statistics.pstdev(conteo_base)
    umbral = media + 3 * sigma

    n_inc = _cubetas(ventana.t0, ventana.fin, ancho)
    cubetas: list[list[EventoLog]] = [[] for _ in range(n_inc)]
    for g in incidente:
        cubetas[min(n_inc - 1, int((g.inicio - ventana.t0) / ancho))].append(g)
    anomalas = [c for c in cubetas if len(c) > umbral]
    en_anomalas = [g for c in anomalas for g in c]
    es_anomala = len(en_anomalas) >= min_eventos
    t_inicio = min((g.inicio for g in en_anomalas), default=None) if es_anomala else None
    motivo = "truncado: la línea base es un mínimo" if cobertura.truncado else ""
    return Anomalia(
        servicio=servicio,
        anomala=es_anomala,
        eventos_incidente=len(incidente),
        eventos_linea_base=len(base),
        ruido_ciclo_vida=len(ruido),
        media=round(media, 4),
        sigma=round(sigma, 4),
        umbral=round(umbral, 4),
        t_inicio=t_inicio,
        ids=[g.ids[0] for g in en_anomalas] if es_anomala else [],
        motivo=motivo,
    )


@dataclass
class Atribucion:
    por_servicio: dict[str, list[str]] = field(default_factory=dict)  # destino -> ids de la primera línea
    sin_atribuir: list[str] = field(default_factory=list)  # ids con destino no resuelto


def atribuir_errores(evidencia: Evidencia) -> Atribucion:
    """Errores (>= WARNING) del incidente cuyo `IP:puerto` (o `nombre:puerto`) se resuelve a un Service.

    Se atribuye por evento agrupado (una traza cuenta una vez por destino). Nunca solo por puerto.
    """
    tabla = TablaServicios.desde(evidencia.direcciones, evidencia.namespace)
    resultado = Atribucion()
    errores = [
        s
        for s in evidencia.senales
        if s.clase == "log" and at_least_warning(s.severidad) and evidencia.ventana.en_incidente(s.tiempo)
    ]
    por_id = {s.id: s for s in errores}
    for grupo in agrupar_eventos(errores):
        vistos = set()
        for sid in grupo.ids:
            for destino in extraer_destinos(por_id[sid].texto_original):
                servicio = tabla.resolver_destino(destino.host, destino.puerto)
                key = servicio or f"?{destino.host}:{destino.puerto}"
                if key in vistos:
                    continue
                vistos.add(key)
                if servicio is None:
                    resultado.sin_atribuir.append(sid)
                elif servicio != grupo.servicio:
                    resultado.por_servicio.setdefault(servicio, []).append(sid)
    return resultado


def trafico(servicio: str, evidencia: Evidencia) -> list[str]:
    """Ids de actividad normal en el incidente: líneas < WARNING del servicio que no parecen error, o de un
    llamador cuyo destino se resuelve al servicio (definición genérica de A02)."""
    tabla = TablaServicios.desde(evidencia.direcciones, evidencia.namespace)
    ids = []
    for s in evidencia.senales:
        if s.clase != "log" or at_least_warning(s.severidad) or not evidencia.ventana.en_incidente(s.tiempo):
            continue
        if is_error(s.texto_original, s.severidad):
            continue
        if s.servicio == servicio or any(
            tabla.resolver_destino(d.host, d.puerto) == servicio for d in extraer_destinos(s.texto_original)
        ):
            ids.append(s.id)
    return ids


class Clausula(BaseModel):
    cumple: bool | None  # None = sin datos
    motivo: str = ""
    ids: list[str] = Field(default_factory=list)


def clausula_plataforma(servicio: str, evidencia: Evidencia) -> Clausula:
    """Réplicas listas = deseadas > 0, endpoints listos > 0 y ningún evento de terminación o escalado
    en el incidente. Se evalúa sobre el estado vigente en t0 y cada cambio posterior."""
    ventana = evidencia.ventana
    obs = sorted((s for s in evidencia.servicios if s.servicio == servicio), key=lambda s: s.tiempo)
    previas = [s for s in obs if s.tiempo <= ventana.t0]
    relevantes = previas[-1:] + [s for s in obs if ventana.t0 < s.tiempo <= ventana.fin]
    if not relevantes:
        return Clausula(cumple=None, motivo="sin instantáneas del registrador")
    for s in relevantes:
        if not s.instancias_deseadas or (s.instancias_listas or 0) < s.instancias_deseadas:
            return Clausula(
                cumple=False, motivo="réplicas listas distintas de las deseadas o cero", ids=[s.id]
            )
        if s.endpoints_listos == 0:
            return Clausula(cumple=False, motivo="sin endpoints listos", ids=[s.id])
    perturbaciones = [
        o
        for o in [*evidencia.eventos, *evidencia.cambios]
        if o.servicio == servicio
        and ventana.en_incidente(o.tiempo)
        and (
            (isinstance(o, Evento) and o.tipo == "instancia_terminada")
            or (isinstance(o, Cambio) and o.tipo == "escalado")
        )
    ]
    if perturbaciones:
        return Clausula(
            cumple=False, motivo="terminación o escalado en el incidente", ids=[o.id for o in perturbaciones]
        )
    if any(s.endpoints_listos is None for s in relevantes):
        return Clausula(cumple=None, motivo="sin EndpointSlice para el servicio")
    return Clausula(cumple=True, ids=[s.id for s in relevantes])


class SanoConfirmado(BaseModel):
    sano: bool
    motivo: str
    plataforma: Clausula
    anomalia: Anomalia
    errores_atribuidos: list[str] = Field(default_factory=list)
    trafico: int = 0


def sano_confirmado(
    servicio: str,
    evidencia: Evidencia,
    *,
    k: int = 3,
    atribucion: Atribucion | None = None,
    **anomalia_kwargs,
) -> SanoConfirmado:
    """Predicado "sano confirmado" (P3): plataforma OK, sin anomalía propia respecto de la línea base y
    ningún error atribuido (IP y puerto) al servicio, y tráfico >= K. `False` no significa falla: el
    estado final (falla / sano / sin datos) lo decide `estado.estado_servicio` en la Fase 2."""
    atribucion = atribucion or atribuir_errores(evidencia)
    plataforma = clausula_plataforma(servicio, evidencia)
    anom = anomalia(servicio, evidencia, **anomalia_kwargs)
    atribuidos = atribucion.por_servicio.get(servicio, [])
    n_trafico = len(trafico(servicio, evidencia))
    cobertura = evidencia.cobertura.get(servicio)

    def resultado(sano: bool, motivo: str) -> SanoConfirmado:
        return SanoConfirmado(
            sano=sano,
            motivo=motivo,
            plataforma=plataforma,
            anomalia=anom,
            errores_atribuidos=atribuidos,
            trafico=n_trafico,
        )

    if cobertura is None or cobertura.truncado:
        return resultado(False, "lectura truncada o ausente: nunca sano")
    if cobertura.fuentes_fallidas:
        return resultado(False, "fuentes fallidas: " + ", ".join(cobertura.fuentes_fallidas))
    if plataforma.cumple is not True:
        return resultado(False, "plataforma: " + (plataforma.motivo or "sin datos"))
    if anom.anomala is not False:
        return resultado(False, "anomalía propia" if anom.anomala else "anomalía sin datos")
    if atribuidos:
        return resultado(False, "errores de llamadores atribuidos al servicio")
    if n_trafico < k:
        return resultado(False, f"tráfico insuficiente ({n_trafico} < {k})")
    return resultado(True, "plataforma, errores y tráfico")
