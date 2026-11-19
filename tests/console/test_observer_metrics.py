"""Métricas del observador en el barrido v2: lectura por tramos, cubetas alineadas a t0 y firmas de
latencia y CPU de punta a punta, con el observador, kubectl y Cloud Logging simulados."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from tider.console.evidence.destinos import TablaServicios
from tider.console.evidence.gke import GKEAdapter, from_observer
from tider.console.evidence.model import Ventana
from tider.console.models import AnalyzeRequest
from tider.console.pipeline_v2 import PipelineV2
from tider.console.predicados import atribuir_errores
from tider.console.providers import operational_observer
from tider.console.providers.operational_observer import MAX_PAGES, read_samples
from tider.console.recorder import Recorder
from tider.console.settings import Settings
from tider.console.signatures import cargar_catalogo, evaluate
from tider.console.sweep import sweep
from tider.console.topology import build_graph, cargar_topologia

from .pilot_fakes import FakeCluster, install_logging, record, utc
from .test_pipeline_v2 import FakeLake

LAKE = cargar_topologia(Path(__file__).parent / "fixtures" / "topologia.yaml")
CATALOGO = cargar_catalogo()
URL = "http://127.0.0.1:8092"
# Caso de 120 s del piloto: solicitud [t0 - 300, restauración + 300]; la falla va de t0 a t0 + 120.
T0 = utc(15, 0, 0)
INICIO, FIN = T0 - timedelta(seconds=300), T0 + timedelta(seconds=430)
FALLA_FIN = T0 + timedelta(seconds=120)
VENTANA = Ventana.desde(INICIO, FIN, T0)
ENLACE = "cartservice->redis-cart"
PROXY_ADDR = "chaosforge-proxy:6379"
# Muestras reales del observador en el laboratorio, con una inyección manual de 300 ms en el medio.
REAL = json.loads(
    (Path(__file__).parent / "fixtures" / "observador" / "latencia-manual.json").read_text(encoding="utf-8")
)


def muestra(t, *, servicio="cartservice", dep_ms=3.0, dep_ok=True, cart_ms=40.0, cart_status=200, cpu=None):
    """Una observación con la forma que entrega `/api/observations` (ChaosForge `observations.capture`)."""
    row = {
        "at": t.timestamp(),
        "service": servicio,
        "coverage": "complete",
        "synthetic": False,
        "configuration": {"redis_address": PROXY_ADDR},
        "http": [
            {"path": "/", "status": 200, "elapsed_ms": 25.0},
            {"path": "/cart", "status": cart_status, "elapsed_ms": cart_ms},
        ],
        "dependency": {
            "operation": "Redis PING via configured destination",
            "success": dep_ok,
            "elapsed_ms": dep_ms,
        },
    }
    if cpu is not None:
        row["cpu_throttling"] = (
            cpu
            if isinstance(cpu, dict)
            else {
                "coverage": "complete",
                "series": [
                    {"pod": "cartservice-a", "ratio": cpu / 2},
                    {"pod": "cartservice-b", "ratio": cpu},
                ],
            }
        )
    return row


def serie(durante=None, **base):
    """Una muestra cada 3 s desde el inicio de la línea base hasta el fin; `durante` rige en la falla."""
    out, t = [], VENTANA.base_inicio
    while t <= FIN:
        out.append(muestra(t, **{**base, **(durante if durante and T0 <= t < FALLA_FIN else {})}))
        t += timedelta(seconds=3)
    return out


LATENCIA = {"dep_ms": 320.0, "cart_ms": 380.0}


# --- Lectura del observador -------------------------------------------------------------------------


def _fake_get(monkeypatch, responder):
    calls = []

    def get(url, params, timeout, follow_redirects):
        calls.append((url, params["start"], params["end"]))
        data = responder(params["start"], params["end"], len(calls))
        return SimpleNamespace(content=b"{}", raise_for_status=lambda: None, json=lambda: data)

    monkeypatch.setattr(operational_observer.httpx, "get", get)
    return calls


def _dt(segundos):
    return datetime.fromtimestamp(segundos, tz=timezone.utc)


def test_read_samples_follows_truncated_pages(monkeypatch):
    filas = [{"at": float(a), "service": "cartservice"} for a in (100, 101, 102, 103, 104)]

    def responder(start, end, n):
        dentro = [r for r in filas if start <= r["at"] <= end]
        return {"observations": dentro[:3], "truncated": len(dentro) > 3}

    calls = _fake_get(monkeypatch, responder)
    data = read_samples(URL, _dt(100), _dt(200), 5)
    assert [r["at"] for r in data["samples"]] == [100, 101, 102, 103, 104] and data["truncated"] is False
    assert len(calls) == 2 and calls[0][0] == URL + "/api/observations"
    assert calls[1][1] > 102 and calls[1][2] == 200  # sigue después de la última muestra recibida


def test_read_samples_splits_long_windows_and_reports_unread_tail(monkeypatch):
    calls = _fake_get(
        monkeypatch, lambda start, end, n: {"observations": [{"at": start}], "truncated": False}
    )
    data = read_samples(URL, _dt(0), _dt(7300), 5)
    assert [(c[1], c[2]) for c in calls] == [(0, 3600), (3600, 7200), (7200, 7300)]  # máximo una hora
    assert [r["at"] for r in data["samples"]] == [0, 3600, 7200] and data["truncated"] is False

    # Si el observador sigue truncando, se deja de leer y se informa la cola sin leer.
    calls = _fake_get(
        monkeypatch, lambda start, end, n: {"observations": [{"at": start + 1}], "truncated": True}
    )
    data = read_samples(URL, _dt(0), _dt(1000), 5)
    assert len(calls) == MAX_PAGES and data["truncated"] is True


def test_read_samples_only_accepts_the_local_tunnel():
    with pytest.raises(ValueError, match="túnel local"):
        read_samples("http://observador.example.com", _dt(0), _dt(10), 5)


# --- Proyección a métricas --------------------------------------------------------------------------


def test_from_observer_buckets_are_aligned_to_t0():
    senales = from_observer(serie(LATENCIA), VENTANA, 30)
    assert {s.nombre for s in senales} == {"latencia_dependencia_p95", "latencia_p95"}
    assert all(
        s.fuente == "observer" and s.clase == "metrica" and s.servicio == "cartservice" for s in senales
    )
    dep = sorted((s for s in senales if s.nombre == "latencia_dependencia_p95"), key=lambda s: s.tiempo)
    assert all(s.destino == "redis-cart" for s in dep)  # el almacén, no el proxy por el que pasa la ruta
    assert all(s.destino is None for s in senales if s.nombre == "latencia_p95")
    # Ninguna cubeta mezcla línea base e incidente: los valores cambian exactamente en t0 y en t0 + 120.
    assert [s.valor for s in dep if s.tiempo < T0] == [3.0] * len([s for s in dep if s.tiempo < T0])
    assert [s.valor for s in dep if T0 <= s.tiempo < FALLA_FIN] == [320.0] * 4
    assert {s.valor for s in dep if s.tiempo >= FALLA_FIN} == {3.0}
    assert all(VENTANA.base_inicio <= s.tiempo <= FIN for s in senales)
    alineadas = [s for s in senales if s.tiempo > VENTANA.base_inicio]
    assert all((s.tiempo - T0).total_seconds() % 30 == 0 for s in alineadas)
    assert PROXY_ADDR in dep[0].texto_original and "mediana 3.0 ms" in dep[0].texto_original


def test_from_observer_latency_is_the_bucket_median_and_cpu_the_worst_pod():
    filas = [muestra(T0 + timedelta(seconds=3 * i), dep_ms=3.0, cart_ms=40.0, cpu=0.4) for i in range(10)]
    filas[2]["dependency"]["elapsed_ms"] = 697.5  # picos aislados, como los del laboratorio
    filas[7]["http"][1]["elapsed_ms"] = 461.7
    filas[3]["cpu_throttling"] = {"coverage": "incomplete", "series": []}
    senales = {s.nombre: s for s in from_observer(filas, VENTANA, 30)}
    assert senales["latencia_dependencia_p95"].valor == 3.0 and senales["latencia_p95"].valor == 40.0
    assert senales["cpu_throttling"].valor == 0.4  # el pod más limitado
    assert "9 muestras" in senales["cpu_throttling"].texto_original  # la lectura incompleta no cuenta


def test_from_observer_ignores_failed_probes_and_unknown_dependencies():
    caida = from_observer(serie({"dep_ok": False, "dep_ms": 1000.0, "cart_status": 500}), VENTANA, 30)
    en_falla = [s for s in caida if T0 <= s.tiempo < FALLA_FIN]
    assert en_falla == []  # un destino que no responde no tiene latencia; un 500 tampoco
    otro = from_observer([muestra(T0, servicio="frontend")], VENTANA, 30)
    assert [s.nombre for s in otro] == ["latencia_p95"]  # el observador solo mide una dependencia
    # Filas mal formadas o fuera de la ventana se ignoran sin tumbar la lectura.
    rota = {
        "at": T0.timestamp(),
        "service": "cartservice",
        "http": "x",
        "dependency": [1],
        "cpu_throttling": 3,
    }
    basura = [None, {"at": "ayer"}, {"service": "cartservice"}, {"at": 1e30, "service": "cartservice"}, rota]
    assert from_observer([*basura, muestra(FIN + timedelta(1))], VENTANA, 30) == []


# --- Barrido y firmas de punta a punta ---------------------------------------------------------------


def correr(monkeypatch, tmp_path, lector, *, url=URL, recursos=None, ventana=VENTANA):
    def overrides(t, name):
        if name != "cartservice":
            return {}
        o = {"env": [{"name": "REDIS_ADDR", "value": PROXY_ADDR}]}
        if recursos:
            o["resources"] = recursos(t)
        return o

    rec = record(
        Recorder,
        tmp_path / "rec.db",
        FakeCluster(proxy=True, overrides=overrides),
        ventana.base_inicio - timedelta(minutes=1),
        ventana.fin,
        step=timedelta(seconds=10),
    )
    install_logging(monkeypatch, [], [])
    cfg = Settings(evidence_mode="gcp", pipeline="v2", healthy_traffic_min_lines=2, agent_observer_url=url)
    lecturas = []

    def read_observer(u, inicio, fin, timeout):
        lecturas.append((u, inicio, fin))
        return lector() if callable(lector) else {"samples": lector, "truncated": False}

    solicitud = AnalyzeRequest(
        incident_id="V3",
        start=ventana.inicio,
        end=ventana.fin,
        mode="gcp",
        objective="La tienda va lenta, investiga",
    )
    adapter = GKEAdapter(cfg, recorder=rec, read_observer=read_observer)
    barrido = sweep(solicitud, cfg, t0=ventana.t0, adapter=adapter)
    ev = barrido.evidencia
    grafo = build_graph(
        ev.inventario,
        LAKE,
        ev.servicios,
        atribuir_errores(ev),
        tabla=TablaServicios.desde(ev.direcciones, ev.namespace),
    )
    veredictos = {(v.entidad.clave, v.firma_id): v for v in evaluate(CATALOGO, barrido, grafo, lake=LAKE)}
    return SimpleNamespace(
        barrido=barrido, veredictos=veredictos, lecturas=lecturas, cfg=cfg, solicitud=solicitud
    )


def confirmadas(r):
    return sorted(k for k, v in r.veredictos.items() if v.veredicto == "CONFIRMADA")


def test_latency_confirms_slow_dependency_on_the_link(monkeypatch, tmp_path):
    r = correr(monkeypatch, tmp_path, serie(LATENCIA))
    assert r.lecturas == [(URL, VENTANA.base_inicio, FIN)]  # línea base e incidente en una lectura
    assert confirmadas(r) == [(ENLACE, "dependencia-lenta")]
    v = r.veredictos[(ENLACE, "dependencia-lenta")]
    assert v.t_inicio == T0 and {"latencia_alta", "sin_errores_conexion", "llamador_lento"} <= set(
        v.cumplidos
    )
    por_id = r.barrido.evidencia.por_id()
    assert v.evidencia_ids and all(por_id[i].fuente == "observer" for i in v.evidencia_ids)
    # Sin CPU medida, la firma de CPU no afirma ni descarta.
    assert r.veredictos[("cartservice", "saturacion-cpu")].veredicto == "SIN_DATOS"
    assert r.barrido.evidencia.fuentes_fallidas == {}
    # La tabla del barrido cuenta líneas de log, no métricas.
    assert r.barrido.fila("cartservice").severidades == {}


def test_latency_case_runs_through_the_whole_pipeline(monkeypatch, tmp_path):
    r = correr(monkeypatch, tmp_path, serie(LATENCIA))
    result = PipelineV2(r.cfg, FakeLake(), sweeper=lambda request: r.barrido).run(r.solicitud)
    h = result.hipotesis[0]
    assert (h.entidad.tipo, h.entidad.origen, h.entidad.destino) == ("enlace", "cartservice", "redis-cart")
    assert (h.firma_id, h.rol, h.t_inicio) == ("dependencia-lenta", "causa", T0)
    assert {n.servicio for n in result.nodos if n.rol_en_principal == "victima"} == {"cartservice"}
    assert not any(n.rol_en_principal == "causa" for n in result.nodos)  # la causa es la arista
    arista = next(a for a in result.aristas if (a.origen, a.destino) == ("cartservice", "redis-cart"))
    assert arista.estado == "falla"
    assert result.status == "hypothesis" and not result.investigation["reglas_juez"]["rechazos"]
    assert result.incompleto is False and result.recomendacion_estructurada.runbook_id == "RB-03"
    assert any(s.source == "metric" for s in result.evidence)
    assert "chaosforge" not in result.model_dump_json().lower()  # P9: también en el texto de las métricas


def test_no_fault_and_refused_connection_do_not_confirm_latency(monkeypatch, tmp_path):
    sano = correr(monkeypatch, tmp_path / "a", serie())
    assert confirmadas(sano) == []
    v = sano.veredictos[(ENLACE, "dependencia-lenta")]
    assert v.veredicto == "DESCARTADA" and v.faltantes == ["latencia_alta"]
    # Destino que no responde (puerto incorrecto): durante la falla no hay latencia que medir, y la que
    # se mide al volver es la normal. La firma de latencia no se confirma.
    caida = correr(monkeypatch, tmp_path / "b", serie({"dep_ok": False, "dep_ms": 1.2, "cart_status": 500}))
    v = caida.veredictos[(ENLACE, "dependencia-lenta")]
    assert v.veredicto == "DESCARTADA" and v.faltantes == ["latencia_alta"]
    assert confirmadas(caida) == []


def test_cpu_limit_confirms_saturation_on_the_service(monkeypatch, tmp_path):
    def recursos(t):
        cpu = "50m" if T0 <= t < FALLA_FIN else "300m"
        return {"requests": {"cpu": cpu}, "limits": {"cpu": cpu}}

    r = correr(monkeypatch, tmp_path, serie({"cpu": 0.45, "cart_ms": 400.0}, cpu=0.01), recursos=recursos)
    assert confirmadas(r) == [("cartservice", "saturacion-cpu")]
    v = r.veredictos[("cartservice", "saturacion-cpu")]
    assert {"throttling_alto", "latencia_propia_alta", "limites_cambiados"} <= set(v.cumplidos)
    # La dependencia no se volvió lenta: la firma de latencia no compite.
    assert r.veredictos[(ENLACE, "dependencia-lenta")].veredicto == "DESCARTADA"


def test_observer_failures_are_reported_and_never_invent_metrics(monkeypatch, tmp_path):
    def caido():
        raise httpx.ConnectError("connection refused")

    r = correr(monkeypatch, tmp_path / "a", caido)
    assert r.barrido.evidencia.fuentes_fallidas == {"observer": "lectura fallida: ConnectError"}
    assert not any(s.clase == "metrica" for s in r.barrido.evidencia.senales) and confirmadas(r) == []
    vacio = correr(monkeypatch, tmp_path / "b", [])
    assert vacio.barrido.evidencia.fuentes_fallidas == {"observer": "sin observaciones en la ventana"}
    parcial = correr(monkeypatch, tmp_path / "c", lambda: {"samples": serie(), "truncated": True})
    assert parcial.barrido.evidencia.fuentes_fallidas == {"observer": "lectura parcial del observador"}
    # Sin observador configurado no se lee nada y no es una falla: las firmas quedan sin datos.
    sin = correr(monkeypatch, tmp_path / "d", serie(LATENCIA), url="")
    assert sin.lecturas == [] and sin.barrido.evidencia.fuentes_fallidas == {}
    assert (ENLACE, "dependencia-lenta") not in sin.veredictos


# --- Muestras reales del laboratorio ------------------------------------------------------------------


def reales():
    return [muestra(_dt(at), cart_ms=cart, dep_ms=dependencia) for at, cart, dependencia in REAL["muestras"]]


def test_real_lab_latency_injection_confirms_the_link(monkeypatch, tmp_path):
    """La ventana que arma el piloto: [t0 - 300, restauración + 300], con t0 en el inicio de la inyección."""
    t0, restaurada = _dt(REAL["inyeccion"]["inicio"]), _dt(REAL["inyeccion"]["restaurada"])
    ventana = Ventana.desde(t0 - timedelta(seconds=300), restaurada + timedelta(seconds=300), t0)
    r = correr(monkeypatch, tmp_path, reales(), ventana=ventana)
    assert confirmadas(r) == [(ENLACE, "dependencia-lenta")]
    v = r.veredictos[(ENLACE, "dependencia-lenta")]
    assert v.t_inicio == t0 and {"latencia_alta", "llamador_lento"} <= set(v.cumplidos)


def test_real_lab_noise_without_fault_confirms_nothing(monkeypatch, tmp_path):
    """Los 13 minutos previos a la inyección: sin falla, pero con picos aislados de cientos de ms."""
    inyeccion = _dt(REAL["inyeccion"]["inicio"])
    t0 = inyeccion - timedelta(seconds=420)
    ventana = Ventana.desde(t0 - timedelta(seconds=300), t0 + timedelta(seconds=400), t0)
    limpias = [
        m for m in REAL["muestras"] if ventana.base_inicio.timestamp() <= m[0] <= ventana.fin.timestamp()
    ]
    assert max(m[2] for m in limpias) > 300 and max(m[1] for m in limpias) > 300  # el ruido está en los datos
    r = correr(monkeypatch, tmp_path, reales(), ventana=ventana)
    assert confirmadas(r) == []
    v = r.veredictos[(ENLACE, "dependencia-lenta")]
    assert v.veredicto == "DESCARTADA" and v.faltantes == ["latencia_alta"]
    llamador = next(c for c in v.corroborantes if c.id == "llamador_lento")
    assert llamador.cumple is False
