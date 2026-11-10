"""Estado por servicio (falla / sano / sin datos), estado de las aristas y roles causa/víctima (Fase 2).

Orden de cálculo (A04): barrido (`sweep.py`) → Cartógrafo (`topology.py`) → verificador
(`signatures.py`) → estado (este módulo). El verificador toma sus candidatos de la función de anomalía y
de la tabla del barrido, no del estado, así que no hay circularidad.

* **falla**: alguna firma CONFIRMADA sobre el servicio, o anomalía propia (`predicados.anomalia`, A03);
* **sano**: el predicado "sano confirmado" (P3) sobre la fila del barrido;
* **sin datos**: todo lo demás (truncado, fuentes fallidas, plataforma sin datos, tráfico < K…).

**Roles (A06, P8).** Los asigna este código, no el LLM:
* **causa**: el servicio de la hipótesis principal. Si la entidad es un enlace, la causa es la arista y
  ningún nodo es `causa`; el origen del enlace es la víctima directa (RB-03).
* **víctima**: un nodo aguas arriba de la causa (camino dirigido en el grafo) cuyos errores atribuidos por
  `ClusterIP:puerto` (A01) a la causa, o a otra víctima, empiezan en `t_inicio` o después. Se propaga
  hasta un punto fijo (redis-cart → cartservice → frontend).
* **víctima anidada**: si una víctima registra un error atribuido a un destino que no llama directamente
  (frontend nombra a paymentservice en PM-04), los nodos que están en **todos** los caminos del grafo entre
  ambos son víctimas, citadas con la línea de esa víctima (checkoutservice en PM-04). No se parsean las
  cadenas de error anidadas (diferido): si la víctima también llama directo a la causa (frontend →
  cartservice en PM-01), no se infiere ningún intermedio.
"""

from __future__ import annotations

from datetime import datetime

from .models import Arista, Nodo
from .predicados import Atribucion, atribuir_errores, decidir_sano
from .signatures import VeredictoFirma
from .sweep import Barrido
from .topology import Grafo


def estado_servicio(barrido: Barrido, grafo: Grafo, veredictos: list[VeredictoFirma], k: int) -> dict[str, Nodo]:
    """`estado_servicio(barrido, grafo, veredictos, k) -> dict[str, Nodo]`, un nodo por servicio del inventario."""
    nodos: dict[str, Nodo] = {}
    for fila in barrido.filas:
        s = fila.servicio
        confirmadas = [
            v
            for v in veredictos
            if v.veredicto == "CONFIRMADA" and v.entidad.tipo == "servicio" and v.entidad.servicio == s
        ]
        base = dict(
            servicio=s,
            tipo=grafo.tipo(s),
            cobertura=fila.cobertura.model_dump(mode="json"),
            truncado=fila.cobertura.truncado,
        )
        if confirmadas:
            nodos[s] = Nodo(
                **base,
                estado="falla",
                motivo="firma CONFIRMADA: " + ", ".join(v.firma_id for v in confirmadas),
                ids=list(dict.fromkeys(i for v in confirmadas for i in v.evidencia_ids)),
            )
            continue
        if fila.anomalia.anomala:
            nodos[s] = Nodo(**base, estado="falla", motivo="anomalía propia", ids=list(fila.anomalia.ids))
            continue
        sano = decidir_sano(
            cobertura=fila.cobertura,
            plataforma=fila.plataforma,
            anom=fila.anomalia,
            atribuidos=fila.errores_atribuidos,
            n_trafico=fila.trafico,
            k=k,
        )
        nodos[s] = Nodo(
            **base,
            estado="sano" if sano.sano else "sin_datos",
            motivo=sano.motivo,
            ids=list(fila.plataforma.ids) if sano.sano else [],
        )
    return nodos


def estado_aristas(
    grafo: Grafo,
    nodos: dict[str, Nodo],
    veredictos: list[VeredictoFirma],
    atribucion: Atribucion,
) -> list[Arista]:
    """`falla` si hay firma CONFIRMADA sobre el enlace o errores del origen atribuidos al destino;
    `sano` si ambos extremos están sanos; `sin_datos` en otro caso."""
    salida = []
    for a in grafo.aristas:
        confirmadas = [
            v
            for v in veredictos
            if v.veredicto == "CONFIRMADA"
            and v.entidad.tipo == "enlace"
            and (v.entidad.origen, v.entidad.destino) == (a.origen, a.destino)
        ]
        errores = atribucion.por_arista.get((a.origen, a.destino), [])
        if confirmadas or errores:
            ids = [i for v in confirmadas for i in v.evidencia_ids] + errores
            salida.append(a.model_copy(update={"estado": "falla", "ids": list(dict.fromkeys([*a.ids, *ids]))}))
        elif all(nodos.get(n) and nodos[n].estado == "sano" for n in (a.origen, a.destino)):
            salida.append(a.model_copy(update={"estado": "sano"}))
        else:
            salida.append(a.model_copy(update={"estado": "sin_datos"}))
    return salida


def _desde(ids: list[str], por_id: dict, t_inicio: datetime | None) -> list[str]:
    return [i for i in ids if t_inicio is None or por_id[i].tiempo >= t_inicio]


def asignar_roles(
    causa: VeredictoFirma,
    grafo: Grafo,
    nodos: dict[str, Nodo],
    barrido: Barrido,
    atribucion: Atribucion | None = None,
) -> dict[str, Nodo]:
    """Roles de cada nodo respecto de la hipótesis principal `causa` (un veredicto CONFIRMADO)."""
    atribucion = atribucion or atribuir_errores(barrido.evidencia)
    por_id = barrido.evidencia.por_id()
    t_inicio = causa.t_inicio
    roles: dict[str, tuple[str, str, list[str]]] = {}
    entidad = causa.entidad
    if entidad.tipo == "servicio":
        raiz = entidad.servicio
        roles[raiz] = ("causa", f"{causa.firma_id} CONFIRMADA", list(causa.evidencia_ids))
        afectados = {raiz}
    else:
        raiz = entidad.origen
        roles[raiz] = ("victima", f"origen del enlace causa {entidad.clave}", list(causa.evidencia_ids))
        afectados = {raiz}
    arriba = grafo.aguas_arriba(raiz)

    cambiado = True
    while cambiado:  # punto fijo: una víctima nueva puede explicar los errores de otro llamador
        cambiado = False
        for nodo in sorted(arriba - set(roles)):
            if nodo in roles:  # asignado como intermedio en esta misma pasada
                continue
            for destino in sorted(afectados):
                ids = _desde(atribucion.por_arista.get((nodo, destino), []), por_id, t_inicio)
                if not ids:
                    continue
                roles[nodo] = ("victima", f"errores atribuidos a {destino}", ids)
                afectados.add(nodo)
                cambiado = True
                for intermedio in _intermedios(grafo, nodo, destino):
                    if intermedio not in roles:
                        roles[intermedio] = ("victima", f"anidada en el error de {nodo} hacia {destino}", ids)
                        afectados.add(intermedio)
                break

    salida = {}
    for nombre, nodo in nodos.items():
        rol, motivo, ids = roles.get(nombre, ("ninguno", "", []))
        salida[nombre] = nodo.model_copy(update={"rol_en_principal": rol, "motivo_rol": motivo, "ids_rol": ids})
    return salida


def _intermedios(grafo: Grafo, origen: str, destino: str) -> list[str]:
    """Nodos presentes en todos los caminos `origen → destino`, si `origen` no llama directo a `destino`.

    Solo cuentan las aristas estructurales (Lake o `*_ADDR`): la arista que crea el propio error anidado
    (frontend→paymentservice) no es una llamada directa."""
    estructural = grafo.estructural()
    if estructural.arista(origen, destino):
        return []
    caminos = estructural.caminos(origen, destino)
    if not caminos:
        return []
    comunes = set(caminos[0][1:-1])
    for camino in caminos[1:]:
        comunes &= set(camino[1:-1])
    return sorted(comunes)
