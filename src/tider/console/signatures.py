"""Verificador de firmas (pipeline v2, Fase 2). Determinista: también es el baseline del modo sin LLM.

Las firmas son datos (`resources/catalog_v1.yaml`, esquema en su cabecera). Este módulo define:

* los **campos**: medidas del modelo común por entidad (`CAMPOS`), cada una con su fuente. Sin la fuente
  (lectura fallida o ausente), el campo devuelve `None` y la hoja queda "sin datos";
* la evaluación de predicados (operador, umbral, persistencia en segundos, modo `siempre`, grupos OR/AND);
* la **tabla de verdad** (A05): obligatorio sin datos → SIN_DATOS; descarte verdadero → DESCARTADA (con
  `conflicto` si los obligatorios también se cumplen); obligatorios + algún corroborante → CONFIRMADA; en
  otro caso → DESCARTADA. Nunca se emite CONFIRMADA con `conflicto` (decisión 27.4);
* los **candidatos**: el verificador no lee el estado (A04, sin circularidad). Un servicio es candidato si
  tiene anomalía propia (A03), errores atribuidos, plataforma perturbada, un Cambio en la ventana o
  métricas propias. Un servicio escalado a cero no escribe logs: por eso la anomalía sola no alcanza. Un
  enlace es candidato si tiene medida de latencia o si sus dos extremos son candidatos.

Orden del modo sin LLM (`baseline`, P4): entre las firmas CONFIRMADAS, primero las que tienen un Cambio
previo sobre su entidad; luego el `t_inicio` más temprano; luego el id de la entidad.

**Latencia frente a configuración (A20).** Preparar la latencia cambia `REDIS_ADDR` a
`chaosforge-proxy:6379`, un Cambio previo a los síntomas. "configuración incorrecta" lo descarta con
`destino_cambiado.responde`: el valor nuevo se resuelve (nombre **y** puerto) a un Service con endpoints
listos y los errores hacia él no son de conexión rechazada (un timeout es un destino lento, no ausente).
`wrong_port` (`redis-cart:6380`) no se resuelve a ningún Service: no responde y la firma se confirma.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Callable, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from .evidence.destinos import TablaServicios, extraer_destinos
from .evidence.model import Cambio, Evidencia, Senal, at_least_warning
from .models import Analysis, Entidad, Signal
from .predicados import Atribucion, EventoLog, agrupar_eventos, atribuir_errores
from .sweep import Barrido
from .topology import Grafo, TopologiaLake, host_corto, separar_direccion

CATALOGO_V1 = Path(__file__).parent / "resources" / "catalog_v1.yaml"
Veredicto = Literal["CONFIRMADA", "DESCARTADA", "SIN_DATOS"]
Operador = Literal["==", "!=", ">", ">=", "<", "<=", "existe", "no_existe"]

# Errores de conexión rechazada o destino inexistente (no un timeout).
RECHAZO = re.compile(
    r"connection refused|UnableToConnect|Failed to connect|no such host|Name or service not known"
    r"|could not resolve|No connection could be made",
    re.I,
)


# --- Catálogo -------------------------------------------------------------------------------------


class Predicado(BaseModel):
    id: str = ""
    campo: str | None = None
    operador: Operador | None = None
    umbral: float | bool | dict | None = None
    persistencia_s: float = Field(default=0, ge=0)
    modo: Literal["alguna_vez", "siempre"] = "alguna_vez"
    cualquiera: list[Predicado] | None = None
    todos: list[Predicado] | None = None

    @model_validator(mode="after")
    def _shape(self):
        formas = [self.campo is not None, self.cualquiera is not None, self.todos is not None]
        if sum(formas) != 1:
            raise ValueError("Un predicado es una hoja (campo) o un grupo (cualquiera | todos).")
        if self.campo is not None:
            if self.campo not in CAMPOS:
                raise ValueError(f"Campo desconocido: {self.campo}")
            if self.operador is None:
                raise ValueError(f"La hoja {self.campo} necesita operador.")
            if self.operador not in {"existe", "no_existe"} and self.umbral is None:
                raise ValueError(f"La hoja {self.campo} necesita umbral.")
            if isinstance(self.umbral, dict) and set(self.umbral) != {"linea_base"}:
                raise ValueError("Un umbral relativo se escribe {linea_base: {factor, margen}}.")
        return self

    @property
    def nombre(self) -> str:
        return self.id or self.campo or ("cualquiera" if self.cualquiera is not None else "todos")


class Firma(BaseModel):
    id: str
    runbook_id: str
    entidad: Literal["servicio", "enlace"]
    validado: bool = False
    resumen: str
    obligatorios: list[Predicado] = Field(min_length=1)
    descartes: list[Predicado] = Field(default_factory=list)
    corroborantes: list[Predicado] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ids(self):
        for p in [*self.obligatorios, *self.descartes, *self.corroborantes]:
            if not p.id:
                raise ValueError(f"{self.id}: cada predicado de primer nivel necesita id.")
        return self

    def campos(self) -> set[str]:
        def visitar(p: Predicado):
            if p.campo:
                yield p.campo
            for hijo in (p.cualquiera or []) + (p.todos or []):
                yield from visitar(hijo)

        return {c for p in [*self.obligatorios, *self.descartes, *self.corroborantes] for c in visitar(p)}


class RazonDeclarada(BaseModel):
    id: str
    runbook_id: str
    estado_validacion: str


class Catalogo(BaseModel):
    version: int
    firmas: list[Firma]
    declaradas_no_validadas: list[RazonDeclarada] = Field(default_factory=list)
    hash: str = ""  # sha256 del archivo, para la traza

    def firma(self, firma_id: str) -> Firma | None:
        return next((f for f in self.firmas if f.id == firma_id), None)


def cargar_catalogo(path: str | Path | None = None) -> Catalogo:
    texto = Path(path or CATALOGO_V1).read_text(encoding="utf-8")
    data = yaml.safe_load(texto)
    return Catalogo(**data, hash=hashlib.sha256(texto.encode()).hexdigest())


# --- Medidas --------------------------------------------------------------------------------------


@dataclass
class Punto:
    t: datetime
    valor: float | bool
    ids: list[str] = field(default_factory=list)


@dataclass
class Medida:
    puntos: list[Punto]
    escalonada: bool = False  # True: el valor rige hasta el próximo punto o el fin del incidente
    linea_base: float | None = None


@dataclass
class Contexto:
    evidencia: Evidencia
    grafo: Grafo
    lake: TopologiaLake | None
    atribucion: Atribucion

    @property
    def ventana(self):
        return self.evidencia.ventana

    @cached_property
    def tabla(self) -> TablaServicios:
        return TablaServicios.desde(self.evidencia.direcciones, self.evidencia.namespace)

    @cached_property
    def por_id(self):
        return self.evidencia.por_id()

    def fuente_fallida(self, fuente: str) -> bool:
        return fuente in self.evidencia.fuentes_fallidas

    def logs_ok(self, servicio: str) -> bool:
        cobertura = self.evidencia.cobertura.get(servicio)
        return cobertura is not None and "cloud_logging" not in cobertura.fuentes_fallidas

    def errores_propios(self, servicio: str) -> list[EventoLog]:
        senales = [
            s
            for s in self.evidencia.senales
            if s.servicio == servicio
            and s.clase == "log"
            and at_least_warning(s.severidad)
            and self.ventana.en_incidente(s.tiempo)
        ]
        return agrupar_eventos(senales)

    def primer_sintoma(self, servicio: str) -> datetime | None:
        return min((e.inicio for e in self.errores_propios(servicio)), default=None)


def _serie_estado(ctx: Contexto, servicio: str, valor: Callable) -> Medida | None:
    """Estado vigente en t0 (última instantánea previa) y cada cambio posterior hasta el fin."""
    ventana = ctx.ventana
    obs = sorted((s for s in ctx.evidencia.servicios if s.servicio == servicio), key=lambda s: s.tiempo)
    relevantes = [s for s in obs if s.tiempo <= ventana.t0][-1:] + [
        s for s in obs if ventana.t0 < s.tiempo <= ventana.fin
    ]
    puntos = []
    for s in relevantes:
        v = valor(s)
        if v is not None:
            puntos.append(Punto(max(s.tiempo, ventana.t0), v, [s.id]))
    return Medida(puntos, escalonada=True) if puntos else None


def _atributo(nombre: str):
    return lambda ctx, e: _serie_estado(ctx, e.servicio, lambda s: getattr(s, nombre))


def _metrica(ctx: Contexto, servicio: str, nombre: str, destino: str | None = None) -> Medida | None:
    ventana = ctx.ventana
    serie = sorted(
        (
            s
            for s in ctx.evidencia.senales
            if s.clase == "metrica"
            and s.nombre == nombre
            and s.servicio == servicio
            and (destino is None or s.destino == destino)
        ),
        key=lambda s: s.tiempo,
    )
    base = [s.valor for s in serie if ventana.en_linea_base(s.tiempo)]
    incidente = [Punto(s.tiempo, s.valor, [s.id]) for s in serie if ventana.en_incidente(s.tiempo)]
    if not incidente:
        return None
    return Medida(incidente, linea_base=statistics.fmean(base) if base else None)


def _ocurrencias(obs) -> Medida:
    return Medida([Punto(o.tiempo, True, [o.id]) for o in sorted(obs, key=lambda o: o.tiempo)])


def _cambios_config(ctx: Contexto, servicio: str) -> list[Cambio]:
    v = ctx.ventana
    return [
        c
        for c in ctx.evidencia.cambios
        if c.servicio == servicio
        and c.tipo in {"config_cambiada", "imagen_cambiada"}
        and v.base_inicio <= c.tiempo <= v.fin
    ]


def _diferencias(cambio: Cambio) -> dict:
    try:
        return json.loads(cambio.texto_original).get("diferencias", {}) or {}
    except (ValueError, AttributeError):
        return {}


def _cambios_direccion(ctx: Contexto, servicio: str) -> list[tuple[Cambio, str, str | None, str | None]]:
    salida = []
    for c in _cambios_config(ctx, servicio):
        for variable, valores in _diferencias(c).items():
            if variable.endswith("_ADDR") and isinstance(valores, list) and len(valores) == 2:
                salida.append((c, variable, valores[0], valores[1]))
    return salida


def _nombra(ctx: Contexto, host: str, puerto: int, valor: str | None) -> bool:
    """¿El destino `host:puerto` de un error es el valor `host:puerto` de una variable?"""
    partes = separar_direccion(valor or "")
    if partes is None:
        return False
    vhost, vpuerto = partes
    if puerto == vpuerto and host_corto(host) == host_corto(vhost):
        return True
    resuelto = ctx.tabla.resolver_destino(host, puerto)
    return resuelto is not None and resuelto == ctx.tabla.resolver_destino(vhost, vpuerto)


def _errores_hacia(ctx: Contexto, servicio: str, valor: str | None, solo_rechazo: bool = False):
    salida = []
    for e in ctx.errores_propios(servicio):
        if solo_rechazo and not RECHAZO.search(e.texto):
            continue
        if any(_nombra(ctx, d.host, d.puerto, valor) for d in extraer_destinos(e.texto)):
            salida.append(e)
    return salida


def _siempre_listo(ctx: Contexto, servicio: str) -> bool | None:
    medida = _serie_estado(
        ctx,
        servicio,
        lambda s: None
        if s.endpoints_listos is None
        else bool((s.instancias_listas or 0) >= 1 and s.endpoints_listos >= 1),
    )
    return None if medida is None else all(p.valor for p in medida.puntos)


# Campos de servicio ---------------------------------------------------------------------------------


def _sin_programar(ctx: Contexto, e: Entidad) -> Medida | None:
    if ctx.fuente_fallida("k8s_events"):
        return None
    v = ctx.ventana
    sin_capacidad = any(
        ev.servicio == e.servicio and ev.tipo == "sin_capacidad" and v.base_inicio <= ev.tiempo <= v.fin
        for ev in ctx.evidencia.eventos
    )
    return _serie_estado(
        ctx,
        e.servicio,
        lambda s: bool(sin_capacidad and (s.instancias_deseadas or 0) > 0 and (s.instancias_listas or 0) == 0),
    )


def _escalado_a_cero(ctx: Contexto, e: Entidad) -> Medida | None:
    if ctx.fuente_fallida("k8s_events"):
        return None
    v = ctx.ventana
    return _ocurrencias(
        c
        for c in ctx.evidencia.cambios
        if c.servicio == e.servicio and c.tipo == "escalado" and c.despues == "0" and v.base_inicio <= c.tiempo <= v.fin
    )


def _errores_atribuidos(ctx: Contexto, e: Entidad) -> Medida | None:
    if not any(ctx.logs_ok(s) for s in ctx.evidencia.inventario):
        return None
    return _ocurrencias(ctx.por_id[i] for i in ctx.atribucion.por_servicio.get(e.servicio, []))


def _config_antes_del_sintoma(ctx: Contexto, e: Entidad) -> Medida | None:
    if ctx.fuente_fallida("recorder"):
        return None
    limite = ctx.primer_sintoma(e.servicio) or ctx.ventana.fin
    return _ocurrencias(c for c in _cambios_config(ctx, e.servicio) if c.tiempo <= limite)


def _hacia_destino_cambiado(ctx: Contexto, e: Entidad) -> Medida | None:
    if not ctx.logs_ok(e.servicio):
        return None
    puntos = []
    for cambio, _, _, nuevo in _cambios_direccion(ctx, e.servicio):
        puntos += [Punto(ev.inicio, True, [ev.ids[0]]) for ev in _errores_hacia(ctx, e.servicio, nuevo)]
    v = ctx.ventana
    puntos += [
        Punto(ev.tiempo, True, [ev.id])
        for ev in ctx.evidencia.eventos
        if ev.servicio == e.servicio
        and v.en_incidente(ev.tiempo)
        and (ev.tipo == "imagen_no_disponible" or ev.razon == "CreateContainerConfigError")
    ]
    return Medida(sorted(puntos, key=lambda p: p.t))


def _destino_original_sano(ctx: Contexto, e: Entidad) -> Medida | None:
    puntos = []
    for cambio, _, antes, _ in _cambios_direccion(ctx, e.servicio):
        partes = separar_direccion(antes or "")
        destino = ctx.tabla.resolver_destino(*partes) if partes else None
        listo = _siempre_listo(ctx, destino) if destino else None
        if listo is not None:
            puntos.append(Punto(cambio.tiempo, listo, [cambio.id]))
    return Medida(puntos) if puntos else None


def _destino_cambiado_responde(ctx: Contexto, e: Entidad) -> Medida | None:
    cambios = _cambios_direccion(ctx, e.servicio)
    if not cambios or not ctx.evidencia.direcciones:
        return None  # sin cambio de dirección o sin tabla de Services: no se puede decir
    puntos = []
    for cambio, _, _, nuevo in cambios:
        partes = separar_direccion(nuevo or "")
        destino = ctx.tabla.resolver_destino(*partes) if partes else None
        if destino is None:
            puntos.append(Punto(cambio.tiempo, False, [cambio.id]))
            continue
        listo = _siempre_listo(ctx, destino)
        if listo is None:
            continue
        rechazos = _errores_hacia(ctx, e.servicio, nuevo, solo_rechazo=True)
        puntos.append(Punto(cambio.tiempo, bool(listo and not rechazos), [cambio.id]))
    return Medida(puntos) if puntos else None


def _coincide_con_lake(ctx: Contexto, e: Entidad) -> Medida | None:
    if ctx.lake is None:
        return None
    esperados = {a.variable: a.valor for a in ctx.lake.aristas if a.origen == e.servicio and a.variable}
    if not esperados:
        return None

    def valor(s):
        comunes = [v for v in esperados if v in s.direcciones]
        return all(s.direcciones[v] == esperados[v] for v in comunes) if comunes else None

    return _serie_estado(ctx, e.servicio, valor)


def _salientes_lentas(ctx: Contexto, e: Entidad) -> Medida | None:
    destinos = sorted(
        {
            s.destino
            for s in ctx.evidencia.senales
            if s.clase == "metrica" and s.nombre == "latencia_dependencia_p95" and s.servicio == e.servicio
        }
    )
    medidas = [m for d in destinos if (m := _metrica(ctx, e.servicio, "latencia_dependencia_p95", d))]
    con_base = [m for m in medidas if m.linea_base]
    if not con_base:
        return medidas[0] if medidas else None
    return max(con_base, key=lambda m: max(p.valor for p in m.puntos) / m.linea_base)


def _limites_antes_del_sintoma(ctx: Contexto, e: Entidad) -> Medida | None:
    if ctx.fuente_fallida("recorder"):
        return None
    cpu = _metrica(ctx, e.servicio, "cpu_throttling")
    limite = min((p.t for p in cpu.puntos if p.valor >= 0.10), default=ctx.ventana.fin) if cpu else ctx.ventana.fin
    return _ocurrencias(
        c for c in _cambios_config(ctx, e.servicio) if "recursos" in _diferencias(c) and c.tiempo <= limite
    )


# Campos de enlace -----------------------------------------------------------------------------------


def _errores_conexion(ctx: Contexto, e: Entidad) -> Medida | None:
    """Errores de conexión rechazada del origen hacia el destino, hacia un auxiliar interpuesto o hacia
    el host del destino con otro puerto (`redis-cart:6380`)."""
    if not ctx.logs_ok(e.origen):
        return None
    auxiliares = ctx.grafo.auxiliares
    ids = []
    for ev in ctx.errores_propios(e.origen):
        if not RECHAZO.search(ev.texto):
            continue
        for d in extraer_destinos(ev.texto):
            resuelto = ctx.tabla.resolver_destino(d.host, d.puerto)
            if resuelto == e.destino or resuelto in auxiliares or host_corto(d.host) == e.destino:
                ids.append(ev.ids[0])
                break
    return Medida([Punto(ctx.ventana.t0, len(ids), ids)])


def _metrica_de(extremo: str, nombre: str, destino: bool = False):
    def campo(ctx: Contexto, e: Entidad) -> Medida | None:
        servicio = getattr(e, extremo) if e.tipo == "enlace" else e.servicio
        return _metrica(ctx, servicio, nombre, e.destino if destino else None)

    return campo


CAMPOS: dict[str, tuple[str, Callable[[Contexto, Entidad], Medida | None]]] = {
    "servicio.instancias_deseadas": ("servicio", _atributo("instancias_deseadas")),
    "servicio.instancias_listas": ("servicio", _atributo("instancias_listas")),
    "servicio.endpoints_listos": ("servicio", _atributo("endpoints_listos")),
    "servicio.sin_programar": ("servicio", _sin_programar),
    "servicio.cpu_throttling": ("servicio", _metrica_de("servicio", "cpu_throttling")),
    "servicio.latencia_p95": ("servicio", _metrica_de("servicio", "latencia_p95")),
    "cambio.escalado_a_cero": ("servicio", _escalado_a_cero),
    "cambio.config_antes_del_sintoma": ("servicio", _config_antes_del_sintoma),
    "cambio.limites_antes_del_sintoma": ("servicio", _limites_antes_del_sintoma),
    "llamadores.errores_atribuidos": ("servicio", _errores_atribuidos),
    "errores.hacia_destino_cambiado": ("servicio", _hacia_destino_cambiado),
    "destino_original.sano": ("servicio", _destino_original_sano),
    "destino_cambiado.responde": ("servicio", _destino_cambiado_responde),
    "config.coincide_con_lake": ("servicio", _coincide_con_lake),
    "salientes.latencia_dependencia_p95": ("servicio", _salientes_lentas),
    "enlace.latencia_dependencia_p95": ("enlace", _metrica_de("origen", "latencia_dependencia_p95", True)),
    "enlace.errores_conexion": ("enlace", _errores_conexion),
    "origen.cpu_throttling": ("enlace", _metrica_de("origen", "cpu_throttling")),
    "destino.cpu_throttling": ("enlace", _metrica_de("destino", "cpu_throttling")),
    "origen.latencia_p95": ("enlace", _metrica_de("origen", "latencia_p95")),
}


# --- Evaluación -----------------------------------------------------------------------------------


class ResultadoPredicado(BaseModel):
    id: str
    cumple: bool | None  # None = sin datos
    ids: list[str] = Field(default_factory=list)
    t: datetime | None = None


class VeredictoFirma(BaseModel):
    entidad: Entidad
    firma_id: str
    runbook_id: str
    veredicto: Veredicto
    conflicto: bool = False
    motivo: str = ""
    t_inicio: datetime | None = None  # primer punto anómalo (solo CONFIRMADA)
    evidencia_ids: list[str] = Field(default_factory=list)
    obligatorios: list[ResultadoPredicado] = Field(default_factory=list)
    descartes: list[ResultadoPredicado] = Field(default_factory=list)
    corroborantes: list[ResultadoPredicado] = Field(default_factory=list)

    @property
    def cumplidos(self) -> list[str]:
        return [r.id for r in [*self.obligatorios, *self.corroborantes] if r.cumple]

    @property
    def faltantes(self) -> list[str]:
        return [r.id for r in self.obligatorios if r.cumple is not True]


def _comparar(operador: str, valor, umbral) -> bool:
    return {
        "==": lambda: valor == umbral,
        "!=": lambda: valor != umbral,
        ">": lambda: valor > umbral,
        ">=": lambda: valor >= umbral,
        "<": lambda: valor < umbral,
        "<=": lambda: valor <= umbral,
    }[operador]()


def _paso(puntos: list[Punto]) -> timedelta:
    difs = [b.t - a.t for a, b in zip(puntos, puntos[1:])]
    return statistics.median(difs) if difs else timedelta(0)


def evaluar_hoja(p: Predicado, medida: Medida | None, fin: datetime) -> ResultadoPredicado:
    nombre = p.nombre
    if medida is None:
        return ResultadoPredicado(id=nombre, cumple=None)
    puntos = medida.puntos
    if p.operador == "existe":
        return ResultadoPredicado(
            id=nombre, cumple=bool(puntos), ids=[i for x in puntos for i in x.ids], t=puntos[0].t if puntos else None
        )
    if p.operador == "no_existe":
        return ResultadoPredicado(id=nombre, cumple=not puntos)
    umbral = p.umbral
    if isinstance(umbral, dict):
        if medida.linea_base is None:
            return ResultadoPredicado(id=nombre, cumple=None)
        rel = umbral["linea_base"]
        base = medida.linea_base
        umbral = max(base * rel.get("factor", 1), base + rel.get("margen", 0))
    if not puntos:
        return ResultadoPredicado(id=nombre, cumple=None)
    ok = [_comparar(p.operador, x.valor, umbral) for x in puntos]
    if p.modo == "siempre":
        if all(ok):
            return ResultadoPredicado(id=nombre, cumple=True, ids=[i for x in puntos for i in x.ids], t=puntos[0].t)
        malo = puntos[ok.index(False)]
        return ResultadoPredicado(id=nombre, cumple=False, ids=list(malo.ids))
    persistencia = timedelta(seconds=p.persistencia_s)
    paso = _paso(puntos)
    i = 0
    while i < len(puntos):
        if not ok[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(puntos) and ok[j + 1]:
            j += 1
        if j + 1 < len(puntos):
            hasta = puntos[j + 1].t
        else:
            hasta = fin if medida.escalonada else puntos[j].t + paso
        if hasta - puntos[i].t >= persistencia:
            return ResultadoPredicado(
                id=nombre, cumple=True, ids=[x for pt in puntos[i : j + 1] for x in pt.ids], t=puntos[i].t
            )
        i = j + 1
    return ResultadoPredicado(id=nombre, cumple=False)


def evaluar_predicado(p: Predicado, entidad: Entidad, ctx: Contexto) -> ResultadoPredicado:
    if p.campo:
        tipo, campo = CAMPOS[p.campo]
        if tipo != entidad.tipo:
            raise ValueError(f"El campo {p.campo} es de {tipo}, no de {entidad.tipo}.")
        return evaluar_hoja(p, campo(ctx, entidad), ctx.ventana.fin)
    hijos = [evaluar_predicado(h, entidad, ctx) for h in (p.cualquiera or p.todos or [])]
    verdaderos = [h for h in hijos if h.cumple]
    if p.cualquiera is not None:
        if verdaderos:
            return ResultadoPredicado(
                id=p.nombre,
                cumple=True,
                ids=[i for h in verdaderos for i in h.ids],
                t=min(h.t for h in verdaderos if h.t) if any(h.t for h in verdaderos) else None,
            )
        return ResultadoPredicado(id=p.nombre, cumple=None if any(h.cumple is None for h in hijos) else False)
    if any(h.cumple is False for h in hijos):
        return ResultadoPredicado(id=p.nombre, cumple=False)
    if any(h.cumple is None for h in hijos):
        return ResultadoPredicado(id=p.nombre, cumple=None)
    tiempos = [h.t for h in hijos if h.t]
    return ResultadoPredicado(
        id=p.nombre, cumple=True, ids=[i for h in hijos for i in h.ids], t=min(tiempos) if tiempos else None
    )


def tabla_de_verdad(
    obligatorios: list[ResultadoPredicado],
    descartes: list[ResultadoPredicado],
    corroborantes: list[ResultadoPredicado],
) -> tuple[Veredicto, bool, str]:
    """(veredicto, conflicto, motivo) según A05. Precedencia SIN_DATOS > DESCARTADA > CONFIRMADA."""
    sin_datos = [r.id for r in obligatorios if r.cumple is None]
    if sin_datos:
        return "SIN_DATOS", False, "obligatorio sin datos: " + ", ".join(sin_datos)
    todos = all(r.cumple for r in obligatorios)
    descarte = [r.id for r in descartes if r.cumple]
    if descarte:
        motivo = "descarte: " + ", ".join(descarte)
        return "DESCARTADA", todos, (motivo + " (conflicto: los obligatorios también se cumplen)") if todos else motivo
    if todos and any(r.cumple for r in corroborantes):
        return "CONFIRMADA", False, "obligatorios y corroborante"
    if todos:
        return "DESCARTADA", False, "obligatorios cumplidos sin ningún corroborante"
    return "DESCARTADA", False, "obligatorio falso: " + ", ".join(r.id for r in obligatorios if not r.cumple)


def evaluar_firma(firma: Firma, entidad: Entidad, ctx: Contexto) -> VeredictoFirma:
    obl = [evaluar_predicado(p, entidad, ctx) for p in firma.obligatorios]
    des = [evaluar_predicado(p, entidad, ctx) for p in firma.descartes]
    cor = [evaluar_predicado(p, entidad, ctx) for p in firma.corroborantes]
    veredicto, conflicto, motivo = tabla_de_verdad(obl, des, cor)
    if veredicto == "CONFIRMADA":
        sosten = [r for r in [*obl, *cor] if r.cumple]
    elif veredicto == "DESCARTADA":
        sosten = [r for r in des if r.cumple] or [r for r in obl if r.cumple is False]
    else:
        sosten = []
    tiempos = [r.t for r in sosten if r.t]
    return VeredictoFirma(
        entidad=entidad,
        firma_id=firma.id,
        runbook_id=firma.runbook_id,
        veredicto=veredicto,
        conflicto=conflicto,
        motivo=motivo,
        t_inicio=min(tiempos) if veredicto == "CONFIRMADA" and tiempos else None,
        evidencia_ids=list(dict.fromkeys(i for r in sosten for i in r.ids)),
        obligatorios=obl,
        descartes=des,
        corroborantes=cor,
    )


def candidatos(barrido: Barrido, grafo: Grafo) -> list[Entidad]:
    metricas = {(s.servicio, s.destino) for s in barrido.evidencia.senales if s.clase == "metrica"}
    con_metrica = {servicio for servicio, _ in metricas}
    servicios = [
        f.servicio
        for f in barrido.filas
        if f.anomalia.anomala
        or f.errores_atribuidos
        or f.plataforma.cumple is False
        or f.cambios
        or f.servicio in con_metrica
    ]
    elegidos = set(servicios)
    enlaces = [
        a
        for a in grafo.aristas
        if (a.origen, a.destino) in metricas or (a.origen in elegidos and a.destino in elegidos)
    ]
    return [Entidad.de_servicio(s) for s in servicios] + [Entidad.de_enlace(a.origen, a.destino) for a in enlaces]


def evaluate(
    catalogo: Catalogo,
    barrido: Barrido,
    grafo: Grafo,
    *,
    lake: TopologiaLake | None = None,
    entidades: list[Entidad] | None = None,
) -> list[VeredictoFirma]:
    """Cada firma sobre cada entidad candidata de su tipo. `entidades` fuerza el conjunto (pruebas, matriz)."""
    ctx = Contexto(barrido.evidencia, grafo, lake, atribuir_errores(barrido.evidencia))
    objetivos = entidades if entidades is not None else candidatos(barrido, grafo)
    return [
        evaluar_firma(firma, entidad, ctx)
        for firma in catalogo.firmas
        for entidad in objetivos
        if entidad.tipo == firma.entidad
    ]


# --- Modo sin LLM ---------------------------------------------------------------------------------


def ordenar_confirmadas(veredictos: list[VeredictoFirma], evidencia: Evidencia) -> list[VeredictoFirma]:
    """Regla fija del modo sin LLM (P4): Cambio previo sobre la entidad; si no, `t_inicio` más temprano."""

    def cambio_previo(v: VeredictoFirma) -> bool:
        return any(
            c.servicio == v.entidad.componente and v.t_inicio is not None and c.tiempo <= v.t_inicio
            for c in evidencia.cambios
        )

    confirmadas = [v for v in veredictos if v.veredicto == "CONFIRMADA"]
    lejano = datetime.max.replace(tzinfo=evidencia.ventana.fin.tzinfo)
    return sorted(confirmadas, key=lambda v: (not cambio_previo(v), v.t_inicio or lejano, v.entidad.clave))


def _signal(obs) -> Signal:
    fuente = "log" if isinstance(obs, Senal) and obs.clase == "log" else "metric" if isinstance(obs, Senal) else "event"
    return Signal(
        id=obs.id,
        timestamp=obs.tiempo,
        service=obs.servicio or "",
        source=fuente,
        message=obs.texto_original,
        severity=getattr(obs, "severidad", "INFO"),
    )


def baseline(incident_id: str, veredictos: list[VeredictoFirma], barrido: Barrido) -> Analysis:
    """`Analysis` v1 del modo sin LLM a partir de los veredictos (reemplaza a `baseline.diagnose` en v2)."""
    evidencia = barrido.evidencia
    orden = ordenar_confirmadas(veredictos, evidencia)
    if not orden:
        return Analysis(
            incident_id=incident_id,
            hypothesis="Ninguna firma del catálogo quedó CONFIRMADA en la ventana.",
            component="desconocida",
            confidence=None,
            evidence=[],
            recommendation="Sugerencia no verificada: ampliar la ventana o revisar las fuentes sin datos.",
            status="insufficient_evidence",
            evidence_mode="gcp",
            engine="signatures-v2",
            reasoning_mode="rules",
            namespace=evidencia.namespace,
        )
    principal = orden[0]
    por_id = evidencia.por_id()
    return Analysis(
        incident_id=incident_id,
        hypothesis=f"{principal.firma_id} en {principal.entidad.clave} (firma CONFIRMADA).",
        component=principal.entidad.componente,
        confidence=None,
        evidence=[_signal(por_id[i]) for i in principal.evidencia_ids if i in por_id],
        recommendation=(
            f"Sugerencia no verificada: seguir los pasos de verificación (solo lectura) de {principal.runbook_id}."
        ),
        evidence_mode="gcp",
        engine="signatures-v2",
        reasoning_mode="rules",
        namespace=evidencia.namespace,
        investigation={"firmas_confirmadas": [v.model_dump(mode="json") for v in orden]},
    )
