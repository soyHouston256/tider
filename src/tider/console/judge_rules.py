"""Reglas fijas del Juez (Technical Plan §8 con A06, A07, A21 y A41). Corren antes del Juez LLM.

Las reglas 1 a 4 **rechazan** el diagnóstico con un motivo; la regla 5 **no rechaza**: solo marca el
análisis como `incompleto`.

1. Cada cita existe y es del tipo correcto (`S####` = observación del barrido, clase `evidencia`;
   `D##` = documento del Lake entregado al Investigador, clase `antecedente`). La causa (hipótesis 1)
   tiene al menos una cita de evidencia sobre su propia entidad (el servicio, o un extremo del enlace)
   dentro de la ventana pedida.
2. Cada hipótesis usa una firma CONFIRMADA sobre su misma entidad, y la entidad causa está en `falla`
   (no `sin_datos` ni `sano`): `Nodo.estado` para un servicio, `Arista.estado` para un enlace (A06).
3. Si hay más de una firma CONFIRMADA, `justificacion_orden` de la hipótesis 1 cita un Cambio previo
   sobre su entidad (su id `S####`) o su `t_inicio` (`HH:MM:SS`), y el orden es coherente (A21): si
   cita solo el `t_inicio`, ninguna otra hipótesis empieza antes.
4. Solo si la recomendación es `diagnostico_no_verificado` (A07): no contiene comandos que cambien el
   clúster. La acción de catálogo validada (`kubectl scale` de RB-01) no pasa por esta regla.
5. Cobertura del barrido: si la fracción de servicios de la tienda con lectura completa (sin `truncado`
   ni fuentes fallidas) es menor que `judge_min_coverage` (0,8 por defecto), o falló un conector global
   (registrador, eventos, logs), el análisis se marca `incompleto`.

`comandos_mutantes` usa una lista de **subcomandos permitidos** por herramienta (`kubectl get|describe|
logs|top…`, `gcloud … read|list|describe`, `aws … describe*|list*|get*`), no una lista de verbos
prohibidos: así `ScalingReplicaSet` en un filtro no cuenta y `kubectl exec` o `label` sí.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .evidence.model import Evidencia
from .models import Arista, Hipotesis, Nodo, Recomendacion
from .signatures import VeredictoFirma

KUBECTL_LECTURA = {
    "get", "describe", "logs", "top", "explain", "api-resources", "api-versions", "version", "events",
    "cluster-info",
}
KUBECTL_FLAGS_CON_VALOR = {"-n", "--namespace", "--context", "--kubeconfig", "--cluster", "--user", "-s", "--server"}
GCLOUD_LECTURA = {"read", "list", "describe", "tail"}
HELM_LECTURA = {"list", "ls", "status", "get", "history", "show"}
HERRAMIENTAS = {"kubectl", "gcloud", "aws", "helm"}


def _posicionales(tokens: list[str], con_valor: set[str] = frozenset()) -> list[str]:
    salida, saltar = [], False
    for t in tokens:
        if saltar:
            saltar = False
            continue
        if t.startswith("-"):
            saltar = t in con_valor
            continue
        salida.append(t)
    return salida


def _es_lectura(herramienta: str, resto: list[str]) -> bool:
    if herramienta == "kubectl":
        pos = _posicionales(resto, KUBECTL_FLAGS_CON_VALOR)
        if not pos:
            return True
        sub = pos[0]
        if sub == "rollout":
            return len(pos) > 1 and pos[1] in {"history", "status"}
        if sub == "auth":
            return len(pos) > 1 and pos[1] == "can-i"
        return sub in KUBECTL_LECTURA
    pos = _posicionales(resto)
    if herramienta == "gcloud":
        return any(t in GCLOUD_LECTURA for t in pos[:4])
    if herramienta == "aws":
        return len(pos) > 1 and pos[1].startswith(("describe", "list", "get"))
    if herramienta == "helm":
        return bool(pos) and pos[0] in HELM_LECTURA
    return True


def comandos_mutantes(texto: str) -> list[str]:
    """Segmentos de comando que no son de solo lectura (en líneas sueltas, bloques de código o `inline`)."""
    salida = []
    for linea in (texto or "").splitlines():
        linea = re.split(r"\s#", linea, maxsplit=1)[0]
        if linea.lstrip().startswith("#"):
            continue
        for segmento in re.split(r"\|\||&&|[|;`]|\$\(", linea):
            tokens = segmento.replace("\\", " ").split()
            inicio = next((i for i, t in enumerate(tokens) if t in HERRAMIENTAS), None)
            if inicio is None:
                continue
            if not _es_lectura(tokens[inicio], tokens[inicio + 1 :]):
                salida.append(" ".join(tokens[inicio:]))
    return salida


@dataclass
class ResultadoReglas:
    rechazos: list[str] = field(default_factory=list)
    incompleto: bool = False
    motivo_incompleto: str = ""
    cobertura: float = 1.0

    @property
    def aprobado(self) -> bool:
        return not self.rechazos


def _hhmmss(t) -> str:
    return t.strftime("%H:%M:%S")


def cobertura(nodos: list[Nodo]) -> float:
    tienda = [n for n in nodos if n.tipo == "tienda"]
    if not tienda:
        return 0.0
    completos = [n for n in tienda if not n.truncado and not (n.cobertura or {}).get("fuentes_fallidas")]
    return len(completos) / len(tienda)


def _sobre_entidad(obs, h: Hipotesis) -> bool:
    e = h.entidad
    return obs.servicio in ({e.servicio} if e.tipo == "servicio" else {e.origen, e.destino})


def aplicar(
    hipotesis: list[Hipotesis],
    recomendacion: Recomendacion | None,
    *,
    evidencia: Evidencia,
    antecedentes: set[str],
    nodos: list[Nodo],
    aristas: list[Arista],
    confirmadas: list[VeredictoFirma],
    min_cobertura: float = 0.8,
) -> ResultadoReglas:
    r = ResultadoReglas()
    por_id = evidencia.por_id()
    ventana = evidencia.ventana
    estado_nodo = {n.servicio: n.estado for n in nodos}
    estado_arista = {(a.origen, a.destino): a.estado for a in aristas}

    # Regla 1: citas.
    for h in hipotesis:
        for c in h.citas:
            if c.id.startswith("S") and (c.clase != "evidencia" or c.id not in por_id):
                r.rechazos.append(f"regla 1: la cita {c.id} de la hipótesis {h.orden} no existe en la evidencia")
            elif c.id.startswith("D") and (c.clase != "antecedente" or c.id not in antecedentes):
                r.rechazos.append(f"regla 1: la cita {c.id} de la hipótesis {h.orden} no es un antecedente entregado")
    causa = hipotesis[0] if hipotesis else None
    if causa is not None and causa.razon != "desconocida":
        propias = [
            por_id[c.id]
            for c in causa.citas
            if c.clase == "evidencia" and c.id in por_id
            and _sobre_entidad(por_id[c.id], causa)
            and ventana.inicio <= por_id[c.id].tiempo <= ventana.fin
        ]
        if not propias:
            r.rechazos.append(
                f"regla 1: la causa {causa.entidad.clave} no tiene citas de evidencia sobre su entidad en la ventana"
            )

    # Regla 2: firma CONFIRMADA sobre la misma entidad y entidad causa en falla.
    for h in hipotesis:
        if h.razon == "desconocida":
            if confirmadas:
                r.rechazos.append(f"regla 2: la hipótesis {h.orden} no usa ninguna firma CONFIRMADA")
            continue
        if not any(v.firma_id == h.firma_id and v.entidad == h.entidad for v in confirmadas):
            r.rechazos.append(f"regla 2: {h.firma_id} no está CONFIRMADA sobre {h.entidad.clave}")
    if causa is not None and causa.razon != "desconocida":
        e = causa.entidad
        estado = estado_nodo.get(e.servicio) if e.tipo == "servicio" else estado_arista.get((e.origen, e.destino))
        if estado != "falla":
            r.rechazos.append(f"regla 2: la entidad causa {e.clave} tiene estado {estado or 'desconocido'}, no falla")

    # Regla 3: orden con más de una firma confirmada.
    if causa is not None and len(confirmadas) > 1 and causa.razon != "desconocida":
        texto = causa.justificacion_orden or ""
        cambios = [
            c for c in evidencia.cambios
            if c.servicio == causa.entidad.componente and c.id in texto
            and (causa.t_inicio is None or c.tiempo <= causa.t_inicio)
        ]
        otros = [h.t_inicio for h in hipotesis[1:] if h.t_inicio is not None]
        otros += [v.t_inicio for v in confirmadas if v.entidad != causa.entidad and v.t_inicio is not None]
        cita_t = causa.t_inicio is not None and _hhmmss(causa.t_inicio) in texto
        coherente = cita_t and all(causa.t_inicio <= t for t in otros)
        if not cambios and not coherente:
            r.rechazos.append(
                "regla 3: con varias firmas CONFIRMADAS, la justificación del orden no cita un Cambio previo "
                "sobre la causa ni un t_inicio coherente con el orden"
            )

    # Regla 4: solo el texto no verificado (A07).
    if recomendacion is not None and recomendacion.tipo == "diagnostico_no_verificado":
        mutantes = comandos_mutantes(recomendacion.texto)
        if mutantes:
            r.rechazos.append("regla 4: la sugerencia no verificada contiene comandos de cambio: " + "; ".join(mutantes))

    # Regla 5: marca, no rechaza.
    r.cobertura = round(cobertura(nodos), 3)
    globales = sorted(evidencia.fuentes_fallidas)
    if r.cobertura < min_cobertura or globales:
        r.incompleto = True
        partes = [f"cobertura {r.cobertura:.0%} < {min_cobertura:.0%}"] if r.cobertura < min_cobertura else []
        partes += [f"conector fallido: {f}" for f in globales]
        r.motivo_incompleto = "; ".join(partes)
    return r
