"""Proponente (pipeline v2, P1 aceptada): determinista, sin LLM y sin filtro de verbos propio.

* Hipótesis 1 con firma CONFIRMADA y runbook `validado: true` en `catalog_v1.yaml` → la sección
  "Acción de reparación sugerida" del runbook (`tipo = catalogo`, `validada = True`). Es texto para la
  persona: Tider no la ejecuta.
* En otro caso → la sección "Pasos de verificación (SOLO LECTURA)" del runbook de la razón, con el
  servicio, el `CLUSTER_IP:puerto` y la ventana rellenados desde la evidencia, y la etiqueta
  "sugerencia no verificada" (`tipo = diagnostico_no_verificado`).
* Sin hipótesis, con `razon = desconocida` o sin el runbook en el Lake → un paso genérico de lectura
  del namespace.

La regla 4 del Juez (A07) revisa que el texto `diagnostico_no_verificado` no tenga comandos que cambien
el clúster; la acción de catálogo validada (por ejemplo `kubectl scale` de RB-01) no pasa por esa regla.
"""

from __future__ import annotations

import re
from typing import Callable

from .evidence.model import Evidencia
from .models import Hipotesis, Recomendacion
from .signatures import Catalogo, VeredictoFirma

SECCION_ACCION = "Acción de reparación sugerida"
SECCION_PASOS = "Pasos de verificación"
ETIQUETA = "Sugerencia no verificada (solo lectura)."


def seccion(markdown: str, titulo: str) -> str | None:
    """Cuerpo de la sección `## <titulo>…` hasta el próximo `## ` fuera de un bloque de código."""
    lineas, dentro, cerco = [], False, False
    for linea in (markdown or "").splitlines():
        if linea.lstrip().startswith("```"):
            cerco = not cerco
        if not cerco and linea.startswith("## "):
            if dentro:
                break
            dentro = linea[3:].strip().lower().startswith(titulo.lower())
            continue
        if dentro:
            lineas.append(linea)
    texto = "\n".join(lineas).strip()
    return texto or None


def _iso(t) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def rellenar(texto: str, servicio: str, evidencia: Evidencia | None, namespace: str) -> str:
    """Sustituye los parámetros del runbook (`<servicio>`, `<CLUSTER_IP>:<puerto>`, `<T0>`, `<T1>`)."""
    texto = re.sub(r"\bNS=\S+", f"NS={namespace}", texto)
    texto = texto.replace("<servicio>", servicio)
    if evidencia is not None:
        direccion = next(
            (d for d in reversed(evidencia.direcciones) if d.servicio == servicio and d.cluster_ip and d.puertos),
            None,
        )
        if direccion:
            texto = texto.replace("<CLUSTER_IP>:<puerto>", f"{direccion.cluster_ip}:{direccion.puertos[0]}")
        texto = texto.replace("<T0>", _iso(evidencia.ventana.t0)).replace("<T1>", _iso(evidencia.ventana.fin))
    return texto


def paso_generico(namespace: str) -> str:
    return (
        f"{ETIQUETA}\n"
        f"kubectl -n {namespace} get deploy,statefulset,pods,endpointslices -o wide\n"
        f"kubectl -n {namespace} get events --sort-by=.lastTimestamp"
    )


def propose(
    hipotesis: list[Hipotesis],
    veredictos: list[VeredictoFirma],
    catalogo: Catalogo,
    runbooks: Callable[[str], str | None],
    *,
    evidencia: Evidencia | None = None,
    namespace: str = "boutique",
) -> Recomendacion:
    """`runbooks(runbook_id)` devuelve el Markdown del runbook (vía por clave del Lake) o None."""
    principal = hipotesis[0] if hipotesis else None
    if principal is None or principal.razon == "desconocida" or principal.firma_id is None:
        return Recomendacion(tipo="diagnostico_no_verificado", texto=paso_generico(namespace))
    firma = catalogo.firma(principal.firma_id)
    confirmada = any(
        v.veredicto == "CONFIRMADA" and v.firma_id == principal.firma_id and v.entidad == principal.entidad
        for v in veredictos
    )
    if firma is None:
        return Recomendacion(tipo="diagnostico_no_verificado", texto=paso_generico(namespace))
    documento = runbooks(firma.runbook_id) or ""
    servicio = principal.entidad.componente
    if confirmada and firma.validado:
        accion = seccion(documento, SECCION_ACCION)
        if accion:
            return Recomendacion(
                tipo="catalogo",
                runbook_id=firma.runbook_id,
                texto=rellenar(accion, servicio, evidencia, namespace),
                validada=True,
            )
    pasos = seccion(documento, SECCION_PASOS)
    if not pasos:
        return Recomendacion(
            tipo="diagnostico_no_verificado", runbook_id=firma.runbook_id, texto=paso_generico(namespace)
        )
    return Recomendacion(
        tipo="diagnostico_no_verificado",
        runbook_id=firma.runbook_id,
        texto=f"{ETIQUETA} {firma.runbook_id}\n{rellenar(pasos, servicio, evidencia, namespace)}",
    )
