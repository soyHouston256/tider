"""Adaptador GKE: traduce Cloud Logging, el log de eventos, el registrador y el observador al modelo común.

Módulo concreto, sin interfaz nueva (A36). Reutiliza `gcp_signals` y `gcp_events`.

Procedencia de `texto_original`:
* logs: el mensaje que reconstruye `gcp_signals` (campos `error | message | msg` o `textPayload`),
  enmascarado y truncado a 600 caracteres por `providers.redaction.sanitize`;
* eventos: `message` del evento, enmascarado y truncado a 800 caracteres por `event_from_entry`;
* registrador: un resumen JSON compacto de la instantánea (no el objeto completo de Kubernetes);
* observador: una frase con la operación medida, el valor y cuántas muestras resume la cubeta.

Métricas: salen del observador de ChaosForge (`AGENT_OBSERVER_URL`), la única fuente de latencia del
laboratorio. Sin observador configurado no hay métricas y las firmas que las exigen quedan SIN_DATOS.
La lectura directa de Cloud Monitoring (CPU de cualquier servicio) no está implementada.

`sweep_timeout_seconds` se traduce en un único deadline monotónico compartido por todas las lecturas;
cada RPC de `BoundedLoggingClient` usa lo que queda de él.
"""

from __future__ import annotations

import json
import math
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Callable

from ..providers.cloud_logging import gcp_signals
from ..providers.error_filter import is_error
from ..providers.kubernetes_events import gcp_events
from ..providers.operational_observer import DEPENDENCY_TARGET, read_samples
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
    errores_info: int = 40  # lectura severity<WARNING filtrada por contenido de error
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


def _finito(valor) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)


def _dict(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def _lista(valor) -> list[dict]:
    return [x for x in valor if isinstance(x, dict)] if isinstance(valor, list) else []


def from_observer(samples: list[dict], ventana: Ventana, cubeta_s: int) -> list[Senal]:
    """Proyecta las muestras del observador a métricas por cubeta de `cubeta_s` segundos.

    Las cubetas se alinean a `t0`, así ninguna mezcla línea base e incidente. Por servicio y cubeta:

    * `latencia_dependencia_p95`: latencia del PING a Redis, solo de las muestras en que respondió. Un
      destino que no responde no tiene latencia: ese caso lo cubren las firmas de conexión;
    * `latencia_p95`: latencia de `GET /cart`, solo de las respuestas 200;
    * `cpu_throttling`: el máximo, entre pods y muestras, de la fracción de periodos limitados, cuando
      el observador la trae completa.

    **El valor de las dos latencias es la mediana de la cubeta, no un p95.** El observador toma una
    muestra cada ~3 s: con unas 9 muestras por cubeta, el p95 es el máximo. En el laboratorio, cerca
    del 3 % de las muestras sin falla son picos aislados de 150 a 700 ms, y con el máximo esos picos
    cumplían solos la persistencia de 60 s de las firmas. La mediana ignora los picos y conserva la
    inyección, que sube todas las muestras. Los nombres son los del modelo común; el texto de cada
    señal dice qué se calculó.
    """
    ancho = timedelta(seconds=cubeta_s)
    grupos: dict[tuple[str, str, int], list[float]] = {}
    destinos: dict[tuple[str, int], str] = {}
    for row in samples:
        if not isinstance(row, dict):
            continue
        servicio, at = row.get("service"), row.get("at")
        if not isinstance(servicio, str) or not servicio or not _finito(at):
            continue
        try:
            t = datetime.fromtimestamp(at, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            continue
        if not ventana.base_inicio <= t <= ventana.fin:
            continue
        k = math.floor((t - ventana.t0) / ancho)
        dependencia = _dict(row.get("dependency"))
        if (
            servicio in DEPENDENCY_TARGET
            and dependencia.get("success") is True
            and _finito(dependencia.get("elapsed_ms"))
        ):
            grupos.setdefault((servicio, "latencia_dependencia_p95", k), []).append(dependencia["elapsed_ms"])
            direccion = _dict(row.get("configuration")).get("redis_address")
            if isinstance(direccion, str) and direccion:
                destinos[(servicio, k)] = direccion
        for sonda in _lista(row.get("http")):
            if (
                sonda.get("path") == "/cart"
                and sonda.get("status") == 200
                and _finito(sonda.get("elapsed_ms"))
            ):
                grupos.setdefault((servicio, "latencia_p95", k), []).append(sonda["elapsed_ms"])
        cpu = _dict(row.get("cpu_throttling"))
        if cpu.get("coverage") == "complete":
            fracciones = [x.get("ratio") for x in _lista(cpu.get("series"))]
            fracciones = [x for x in fracciones if _finito(x) and 0 <= x <= 1]
            if fracciones:
                grupos.setdefault((servicio, "cpu_throttling", k), []).append(max(fracciones))

    senales = []
    for (servicio, nombre, k), valores in sorted(grupos.items()):
        tiempo = max(ventana.t0 + k * ancho, ventana.base_inicio)
        n = len(valores)
        if nombre == "cpu_throttling":
            valor = round(max(valores), 4)
            texto = (
                f"Observador (Managed Prometheus): fracción de periodos de CPU limitados {valor:.2f}, "
                f"máximo entre pods en {n} muestras de {cubeta_s} s"
            )
        elif nombre == "latencia_dependencia_p95":
            valor = round(statistics.median(valores), 2)
            direccion = destinos.get((servicio, k), "destino no informado")
            texto = (
                f"Observador: PING a Redis por el destino configurado ({direccion}); "
                f"mediana {valor:.1f} ms en {n} muestras de {cubeta_s} s"
            )
        else:
            valor = round(statistics.median(valores), 2)
            texto = f"Observador: GET /cart; mediana {valor:.1f} ms en {n} respuestas 200 de {cubeta_s} s"
        senales.append(
            Senal(
                fuente="observer",
                clase="metrica",
                tiempo=tiempo,
                servicio=servicio,
                nombre=nombre,
                destino=DEPENDENCY_TARGET[servicio] if nombre == "latencia_dependencia_p95" else None,
                valor=valor,
                texto_original=texto,
            )
        )
    return senales


MARGEN_REINTENTO_S = 20  # presupuesto mínimo restante para reintentar una lectura fallida
TIEMPO_OBSERVADOR_S = 10  # tope de una lectura al observador (túnel local)


class GKEAdapter:
    def __init__(
        self,
        settings,
        *,
        recorder: Recorder | None = None,
        read_logs: Callable = gcp_signals,
        read_events: Callable = gcp_events,
        read_observer: Callable = read_samples,
        clock: Callable[[], float] = monotonic,
    ):
        self.settings, self.recorder = settings, recorder
        self.read_logs, self.read_events, self.clock = read_logs, read_events, clock
        self.read_observer = read_observer

    def collect(
        self, ventana: Ventana, inventario: list[str] | None = None, cuotas: Cuotas | None = None
    ) -> Evidencia:
        cuotas = cuotas or Cuotas(
            self.settings.sweep_quota_per_service,
            self.settings.sweep_info_quota_per_service,
            self.settings.sweep_error_info_quota_per_service,
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

        # 3b. Métricas del observador, si está configurado: latencia de la dependencia, latencia de la
        #     operación y CPU. Una fuente configurada que no entrega datos se informa como fallida.
        metricas: list[Senal] = []
        if self.settings.agent_observer_url:
            try:
                data = self.read_observer(
                    self.settings.agent_observer_url,
                    ventana.base_inicio,
                    ventana.fin,
                    max(1.0, min(TIEMPO_OBSERVADOR_S, deadline - self.clock())),
                )
                muestras = data.get("samples") or []
                metricas = from_observer(muestras, ventana, self.settings.anomaly_bucket_seconds)
                if data.get("truncated"):
                    fallidas["observer"] = "lectura parcial del observador"
                elif not muestras:
                    fallidas["observer"] = "sin observaciones en la ventana"
            except Exception as exc:
                fallidas["observer"] = f"lectura fallida: {type(exc).__name__}"

        # 4. Logs: tres lecturas por servicio, cada una con su cuota (A14). La tercera recoge los
        #    fallos que la aplicación escribe por debajo de WARNING (cartservice registra sus
        #    excepciones como INFO): sin ella, la cuota de tráfico solo retiene las últimas líneas
        #    de la ventana y los errores del incidente quedan fuera. Las lecturas son independientes
        #    y se lanzan en paralelo; en serie no caben en el presupuesto compartido del barrido.
        lecturas = (
            (">=WARNING", cuotas.advertencia, False),
            ("<WARNING", cuotas.errores_info, True),
            ("<WARNING", cuotas.info, False),
        )

        def leer(tarea):
            """Una lectura con un reintento. Devuelve las filas o la excepción del último intento.

            Un fallo transitorio (una RPC que agota su tiempo) no debe dejar al servicio sin logs: se
            reintenta una vez mientras quede presupuesto del barrido para otra lectura completa.
            """
            servicio, (severity, cuota, solo_errores) = tarea
            resultado = None
            for intento in (1, 2):
                if intento == 2 and deadline - self.clock() < MARGEN_REINTENTO_S:
                    break
                try:
                    resultado = self.read_logs(
                        servicio,
                        ventana.base_inicio,
                        ventana.fin,
                        self.settings,
                        services=[servicio],
                        max_records=cuota + 1,
                        errors_only=solo_errores,
                        deadline=deadline,
                        severity=severity,
                    )
                except Exception as exc:  # una lectura fallida no detiene a las demás
                    resultado = exc
                    continue
                if not getattr(resultado, "incomplete", None):
                    break  # lectura completa; una parcial se reintenta y, si no mejora, se conserva
            return resultado

        tareas = [(servicio, lectura) for servicio in inventory for lectura in lecturas]
        hilos = max(1, min(self.settings.sweep_parallel_reads, len(tareas)))
        if hilos == 1:
            resultados = [leer(t) for t in tareas]
        else:
            with ThreadPoolExecutor(max_workers=hilos, thread_name_prefix="barrido") as pool:
                resultados = list(pool.map(leer, tareas))  # conserva el orden de las tareas
        leido = dict(zip(tareas, resultados))

        senales: list[Senal] = []
        cobertura: dict[str, CoberturaServicio] = {}
        for servicio in inventory:
            leidos, truncado, truncado_info, fallas = 0, False, False, []
            motivos: list[str] = []
            vistas: set[tuple] = set()
            for lectura in lecturas:
                severity, cuota, solo_errores = lectura
                rows = leido[(servicio, lectura)]
                tipo = "errores_info" if solo_errores else ("trafico" if severity == "<WARNING" else "warning")
                if isinstance(rows, Exception):
                    fallas.append("cloud_logging")
                    motivos.append(f"{tipo}: {type(rows).__name__}")
                    continue
                if getattr(rows, "incomplete", None):
                    fallas.append("cloud_logging")
                    motivos.append(f"{tipo}: lectura parcial")
                rows = list(rows)
                if len(rows) > cuota:
                    rows = sorted(rows, key=lambda s: s.timestamp)[-cuota:]
                    if severity == ">=WARNING" or solo_errores:
                        truncado = True
                    else:
                        truncado_info = True
                for s in rows:
                    if not s.message:
                        continue
                    # La misma línea puede llegar por la lectura de errores y por la de tráfico.
                    clave = (s.timestamp, getattr(s, "instance", None), s.message)
                    if clave in vistas:
                        continue
                    vistas.add(clave)
                    leidos += 1
                    senales.append(
                        Senal(
                            fuente="cloud_logging",
                            tiempo=s.timestamp,
                            servicio=s.service,
                            instancia=getattr(s, "instance", None),
                            severidad=s.severity.upper(),
                            texto_original=s.message,
                            # Se comprueba también aquí: la marca no depende solo del filtro del servidor.
                            error_por_contenido=solo_errores and is_error(s.message, s.severity.upper()),
                        )
                    )
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
                motivos_fallo=motivos,
            )

        senales.extend(m for m in metricas if m.servicio in inventory)

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
