"""Adaptador GKE: traduce Cloud Logging, el log de eventos y el registrador al modelo común.

Módulo concreto, sin interfaz nueva (A36). Reutiliza `gcp_signals` y `gcp_events`.

Procedencia de `texto_original`:
* logs: el mensaje que reconstruye `gcp_signals` (campos `error | message | msg` o `textPayload`),
  enmascarado y truncado a 600 caracteres por `providers.redaction.sanitize`;
* eventos: `message` del evento, enmascarado y truncado a 800 caracteres por `event_from_entry`;
* registrador: un resumen JSON compacto de la instantánea (no el objeto completo de Kubernetes).

`sweep_timeout_seconds` se traduce en un único deadline monotónico compartido por todas las lecturas;
cada RPC de `BoundedLoggingClient` usa lo que queda de él.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Callable

from ..providers.cloud_logging import gcp_signals
from ..providers.kubernetes_events import gcp_events
from ..recorder import Instantanea, Recorder
from .model import (
    Cambio,
    CoberturaServicio,
    DireccionServicio,
    Evento,
    Evidencia,
    Instancia,
    Senal,
    Servicio,
    Ventana,
    asignar_ids,
)

_SCALE = re.compile(r"from (?P<antes>\d+) to (?P<despues>\d+)")
_EVENT_TYPES = {
    "Killing": "instancia_terminada",
    "OOMKilling": "instancia_terminada",
    "Evicted": "instancia_terminada",
    "BackOff": "instancia_terminada",
    "FailedScheduling": "sin_capacidad",
    "Unhealthy": "health_check_fallido",
    "ErrImagePull": "imagen_no_disponible",
    "ImagePullBackOff": "imagen_no_disponible",
    "Started": "instancia_iniciada",
    "Created": "instancia_iniciada",
    "Scheduled": "instancia_iniciada",
    "Pulled": "instancia_iniciada",
}


@dataclass(frozen=True)
class Cuotas:
    advertencia: int = 40  # lectura severity>=WARNING por servicio
    info: int = 40  # lectura severity<WARNING por servicio (solo tráfico)
    eventos: int = 500  # eventos del namespace


def _compact(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _evento_tipo(reason: str, message: str) -> str:
    if reason == "Failed" and "image" in message.lower():
        return "imagen_no_disponible"
    return _EVENT_TYPES.get(reason, "otro")


def from_snapshots(snaps: list[Instantanea], namespace: str):
    """Proyecta instantáneas a observaciones. Solo emite cuando cambia el estado de cada objeto."""
    servicios, direcciones, instancias, cambios = [], [], [], []
    last: dict[tuple, str] = {}
    prev_carga: dict[str, object] = {}
    for snap in snaps:
        for carga in snap.cargas:
            estado = {
                "carga": carga.nombre,
                "tipo": carga.tipo,
                "deseadas": carga.deseadas,
                "listas": carga.listas,
                "endpoints_listos": snap.endpoints_listos(carga.nombre),
                "generacion": carga.generacion,
                "hash_spec": carga.hash_spec,
                "direcciones": carga.direcciones,
            }
            texto = _compact(estado)
            if last.get(("svc", carga.nombre)) != texto:
                last[("svc", carga.nombre)] = texto
                servicios.append(
                    Servicio(
                        fuente="recorder",
                        tiempo=snap.tiempo,
                        texto_original=texto,
                        servicio=carga.nombre,
                        tipo_carga=carga.tipo
                        if carga.tipo in {"Deployment", "StatefulSet"}
                        else "Deployment",
                        ubicacion=namespace,
                        instancias_deseadas=carga.deseadas,
                        instancias_listas=carga.listas,
                        endpoints_listos=snap.endpoints_listos(carga.nombre),
                        version_config=f"{carga.generacion}:{carga.hash_spec}",
                        direcciones=carga.direcciones,
                    )
                )
            antes = prev_carga.get(carga.nombre)
            if antes is not None and antes.hash_spec != carga.hash_spec:
                tipo = "imagen_cambiada" if antes.imagenes != carga.imagenes else "config_cambiada"
                diff = {
                    k: [antes.direcciones.get(k), carga.direcciones.get(k)]
                    for k in sorted(set(antes.direcciones) | set(carga.direcciones))
                    if antes.direcciones.get(k) != carga.direcciones.get(k)
                }
                if antes.recursos != carga.recursos:  # límites de CPU/memoria (corroborante de RB-04)
                    diff["recursos"] = [antes.recursos, carga.recursos]
                if tipo == "imagen_cambiada":
                    diff = {
                        k: [antes.imagenes.get(k), carga.imagenes.get(k)]
                        for k in sorted(carga.imagenes)
                        if antes.imagenes.get(k) != carga.imagenes.get(k)
                    }
                cambios.append(
                    Cambio(
                        fuente="recorder",
                        tiempo=snap.tiempo,
                        servicio=carga.nombre,
                        tipo=tipo,
                        antes=f"{antes.generacion}:{antes.hash_spec}",
                        despues=f"{carga.generacion}:{carga.hash_spec}",
                        texto_original=_compact(
                            {
                                "carga": carga.nombre,
                                "cambio": tipo,
                                "diferencias": diff,
                                "generacion": [antes.generacion, carga.generacion],
                            }
                        ),
                    )
                )
            prev_carga[carga.nombre] = carga
        for svc in snap.services:
            texto = _compact({"service": svc.nombre, "cluster_ip": svc.cluster_ip, "puertos": svc.puertos})
            if last.get(("dir", svc.nombre)) != texto:
                last[("dir", svc.nombre)] = texto
                direcciones.append(
                    DireccionServicio(
                        fuente="recorder",
                        tiempo=snap.tiempo,
                        texto_original=texto,
                        servicio=svc.nombre,
                        cluster_ip=svc.cluster_ip,
                        puertos=svc.puertos,
                    )
                )
        for pod in snap.pods:
            app = pod.etiquetas.get("app") or pod.etiquetas.get("app.kubernetes.io/name")
            if not app:
                continue
            term = next((c for c in pod.contenedores if c.terminado_motivo), None)
            estado = {
                "pod": pod.nombre,
                "fase": pod.fase,
                "ip": pod.ip,
                "terminado": [term.terminado_motivo, term.terminado_codigo] if term else None,
            }
            texto = _compact(estado)
            if last.get(("pod", pod.nombre)) != texto:
                last[("pod", pod.nombre)] = texto
                fase = {
                    "Running": "corriendo",
                    "Pending": "arrancando",
                    "Succeeded": "terminada",
                    "Failed": "terminada",
                }.get(pod.fase or "", "desconocido")
                instancias.append(
                    Instancia(
                        fuente="recorder",
                        tiempo=snap.tiempo,
                        texto_original=texto,
                        servicio=app,
                        instancia=pod.nombre,
                        estado=fase,
                        ip=pod.ip,
                        motivo_fin=term.terminado_motivo if term else None,
                        codigo_salida=term.terminado_codigo if term else None,
                    )
                )
    return servicios, direcciones, instancias, cambios


def from_event(event: dict) -> Evento | Cambio | None:
    tiempo = _parse_time(event["timestamp"])
    reason, message = event.get("reason", ""), event.get("message", "")
    texto = f"{event.get('type', '')} {reason} {event.get('object_kind', '')}/{event.get('object_name', '')} {message}"
    texto = texto.strip()
    if reason == "ScalingReplicaSet" and event.get("object_kind") == "Deployment" and event.get("service"):
        match = _SCALE.search(message)
        return Cambio(
            fuente="k8s_events",
            tiempo=tiempo,
            servicio=event["service"],
            tipo="escalado",
            antes=match["antes"] if match else None,
            despues=match["despues"] if match else None,
            texto_original=texto,
        )
    instancia = event.get("object_name") if event.get("object_kind") == "Pod" else None
    return Evento(
        fuente="k8s_events",
        tiempo=tiempo,
        servicio=event.get("service"),
        instancia=instancia,
        tipo=_evento_tipo(reason, message),
        razon=reason,
        asignacion=event.get("mapping", ""),
        texto_original=texto,
    )


class GKEAdapter:
    def __init__(
        self,
        settings,
        *,
        recorder: Recorder | None = None,
        read_logs: Callable = gcp_signals,
        read_events: Callable = gcp_events,
        clock: Callable[[], float] = monotonic,
    ):
        self.settings, self.recorder = settings, recorder
        self.read_logs, self.read_events, self.clock = read_logs, read_events, clock

    def collect(
        self, ventana: Ventana, inventario: list[str] | None = None, cuotas: Cuotas | None = None
    ) -> Evidencia:
        cuotas = cuotas or Cuotas(
            self.settings.sweep_quota_per_service, self.settings.sweep_info_quota_per_service
        )
        deadline = self.clock() + self.settings.sweep_timeout_seconds
        namespace = self.settings.gcp_namespace
        fallidas: dict[str, str] = {}

        # 1. Registrador: única fuente histórica de réplicas, endpoints, Services y spec. Sin volver al estado actual.
        snaps: list[Instantanea] = []
        if self.recorder is None:
            fallidas["recorder"] = "registrador no configurado"
        else:
            try:
                snaps = self.recorder.snapshots(ventana.base_inicio, ventana.fin)
            except Exception as exc:
                fallidas["recorder"] = f"lectura fallida: {type(exc).__name__}"
            if not snaps and "recorder" not in fallidas:
                fallidas["recorder"] = "sin instantáneas válidas en la ventana"
        servicios, direcciones, instancias, cambios = from_snapshots(snaps, namespace)

        # 2. Inventario de la plataforma (Deployments y StatefulSets). Nunca del Lake.
        inventory = sorted({c.nombre for s in snaps for c in s.cargas}) or sorted(set(inventario or ()))
        if not inventory:
            raise ValueError(
                "Sin inventario de la plataforma: el registrador no tiene instantáneas en la ventana."
            )

        # 3. Eventos de todo el namespace, sin filtro de nombres.
        eventos: list[Evento] = []
        try:
            data = self.read_events(
                ventana.base_inicio,
                ventana.fin,
                self.settings,
                None,
                deadline=deadline,
                limit=cuotas.eventos,
                inventory=inventory,
            )
            for raw in data.get("events", []):
                obs = from_event(raw)
                (cambios if isinstance(obs, Cambio) else eventos).append(obs)
            if data.get("incomplete") or data.get("truncated"):
                fallidas["k8s_events"] = "lectura parcial de eventos"
        except Exception as exc:
            fallidas["k8s_events"] = f"lectura fallida: {type(exc).__name__}"

        # 4. Logs: dos lecturas por servicio, cada una con su cuota (A14).
        senales: list[Senal] = []
        cobertura: dict[str, CoberturaServicio] = {}
        for servicio in inventory:
            leidos, truncado, truncado_info, fallas = 0, False, False, []
            for severity, cuota in ((">=WARNING", cuotas.advertencia), ("<WARNING", cuotas.info)):
                try:
                    rows = self.read_logs(
                        servicio,
                        ventana.base_inicio,
                        ventana.fin,
                        self.settings,
                        services=[servicio],
                        max_records=cuota + 1,
                        errors_only=False,
                        deadline=deadline,
                        severity=severity,
                    )
                except Exception:
                    fallas.append("cloud_logging")
                    continue
                if getattr(rows, "incomplete", None):
                    fallas.append("cloud_logging")
                rows = list(rows)
                if len(rows) > cuota:
                    rows = sorted(rows, key=lambda s: s.timestamp)[-cuota:]
                    if severity == ">=WARNING":
                        truncado = True
                    else:
                        truncado_info = True
                leidos += len(rows)
                senales += [
                    Senal(
                        fuente="cloud_logging",
                        tiempo=s.timestamp,
                        servicio=s.service,
                        instancia=getattr(s, "instance", None),
                        severidad=s.severity.upper(),
                        texto_original=s.message,
                    )
                    for s in rows
                    if s.message
                ]
            if "recorder" in fallidas:
                fallas.append("recorder")
            if "k8s_events" in fallidas:
                fallas.append("k8s_events")
            cobertura[servicio] = CoberturaServicio(
                servicio=servicio,
                registros_leidos=leidos,
                truncado=truncado,
                truncado_info=truncado_info,
                fuentes_fallidas=sorted(set(fallas)),
            )

        evidencia = Evidencia(
            ventana=ventana,
            namespace=namespace,
            inventario=inventory,
            servicios=servicios,
            direcciones=direcciones,
            instancias=instancias,
            cambios=cambios,
            eventos=eventos,
            senales=senales,
            cobertura=cobertura,
            fuentes_fallidas=fallidas,
        )
        return asignar_ids(evidencia)
