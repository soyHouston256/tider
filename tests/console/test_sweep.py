"""Barrido v2 y predicados sin grafo, con líneas reales recortadas de PM-04, PM-02 y PM-01."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from tider.console.evidence.model import CoberturaServicio, Evidencia, Senal, Ventana, asignar_ids
from tider.console.models import AnalyzeRequest
from tider.console.predicados import agrupar_eventos, anomalia, atribuir_errores, sano_confirmado
from tider.console.providers.cloud_logging import gcp_signals
from tider.console.providers.kubernetes_events import event_filter, event_from_entry, owner_from_name
from tider.console.recorder import Recorder
from tider.console.settings import Settings
from tider.console.sweep import plantilla, sweep

from .pilot_fakes import PROXY, SERVICES, FakeCluster, install_logging, load, record, ts, utc

# PM-04: ventana exportada 18:33:54–18:46:21; inyección (t0) 18:38:54.
START, T0, END = utc(18, 33, 54), utc(18, 38, 54), utc(18, 46, 21)
STORE = sorted(SERVICES)


def pm04_overrides(t, name):
    if name != "paymentservice":
        return {}
    desired = 0 if utc(18, 38, 55) <= t < utc(18, 40, 55) else 1
    ready = 0 if utc(18, 38, 55) <= t < utc(18, 41, 4) else 1
    return {"replicas": desired, "ready": ready}


def settings(**kw):
    return Settings(evidence_mode="gcp", **kw)


def request():
    return AnalyzeRequest(incident_id="PM-04", start=START, end=END)


@pytest.fixture
def pm04(monkeypatch, tmp_path):
    rec = record(Recorder, tmp_path / "rec.db", FakeCluster(overrides=pm04_overrides), utc(18, 31), END)
    logs, events = install_logging(monkeypatch, load("pm04-logs.json"), load("pm04-eventos.json"))
    return SimpleNamespace(recorder=rec, logs=logs, events=events)


def test_sweep_covers_every_platform_workload_with_empty_lake(pm04):
    barrido = sweep(request(), settings(), t0=T0, recorder=pm04.recorder)
    assert [
        f.servicio for f in barrido.filas
    ] == STORE  # 12 servicios: inventario del registrador, no del Lake
    assert all(f.cobertura.fuentes_fallidas == [] for f in barrido.filas)
    # Dos lecturas por servicio (WARNING+ e INFO), cada una filtrada por servicio y severidad.
    assert len(pm04.logs.filters) == 2 * len(STORE)
    assert any("severity>=WARNING" in f for f in pm04.logs.filters)
    assert any("severity<WARNING" in f for f in pm04.logs.filters)
    # Eventos del namespace sin regex de nombres.
    assert all("involvedObject.name=~" not in f for f in pm04.events.filters)
    assert barrido.evidencia.senales and all(s.instancia for s in barrido.evidencia.senales)
    with pytest.raises(ValueError, match="severidad"):
        gcp_signals(
            "frontend",
            START,
            END,
            settings(),
            services=["frontend"],
            max_records=1,
            errors_only=False,
            deadline=1e12,
            severity="OR 1=1",
        )
    ids = [o.id for o in barrido.evidencia.observaciones()]
    assert len(ids) == len(set(ids)) and all(i.startswith("S") for i in ids)


def test_pm04_caller_errors_are_attributed_to_payment_not_shipping(pm04):
    barrido = sweep(request(), settings(), t0=T0, recorder=pm04.recorder)
    pay, ship, front = (
        barrido.fila("paymentservice"),
        barrido.fila("shippingservice"),
        barrido.fila("frontend"),
    )
    assert len(pay.errores_atribuidos) == 4 and ship.errores_atribuidos == []
    por_id = barrido.evidencia.por_id()
    assert all(
        "dial tcp 10.49.5.115:50051: connect: connection refused" in por_id[i].texto_original
        for i in pay.errores_atribuidos
    )
    assert front.plantillas[0].conteo == 4 and "10.49.5.115:50051" in front.plantillas[0].plantilla
    assert front.primera == ts("2026-11-09T18:39:13.901077497Z")


def test_zero_replicas_never_healthy_and_scaling_recorded(pm04):
    barrido = sweep(request(), settings(), t0=T0, recorder=pm04.recorder)
    pay = barrido.fila("paymentservice")
    assert pay.instancias_deseadas_min == 0 and pay.endpoints_listos_min == 0
    assert pay.plataforma.cumple is False
    escalados = [c for c in barrido.evidencia.cambios if c.tipo == "escalado"]
    assert [(c.servicio, c.antes, c.despues) for c in escalados] == [
        ("paymentservice", "1", "0"),
        ("paymentservice", "0", "1"),
    ]
    resultado = sano_confirmado("paymentservice", barrido.evidencia, k=1)
    assert resultado.sano is False and resultado.motivo.startswith("plataforma")


def test_anomaly_against_baseline_and_lifecycle_noise(pm04):
    barrido = sweep(request(), settings(), t0=T0, recorder=pm04.recorder)
    front, pay = barrido.fila("frontend").anomalia, barrido.fila("paymentservice").anomalia
    assert front.anomala is True and front.eventos_linea_base == 0
    assert front.t_inicio == ts("2026-11-09T18:39:13.901077497Z") and len(front.ids) == 4
    # Los dos ERROR de arranque del pod nuevo (DeprecationWarning) son ruido de ciclo de vida.
    assert pay.anomala is False and pay.ruido_ciclo_vida == 2 and pay.eventos_incidente == 0
    sin_gracia = anomalia("paymentservice", barrido.evidencia, gracia_arranque=0, min_eventos=2)
    assert sin_gracia.ruido_ciclo_vida == 0 and sin_gracia.anomala is True


def test_healthy_requires_traffic_k_otherwise_no_data(pm04):
    barrido = sweep(request(), settings(), t0=T0, recorder=pm04.recorder)
    ev = barrido.evidencia
    assert barrido.fila("shippingservice").trafico == 2
    assert sano_confirmado("shippingservice", ev, k=2).sano is True
    sin_trafico = sano_confirmado("shippingservice", ev, k=3)
    assert sin_trafico.sano is False and "tráfico insuficiente" in sin_trafico.motivo
    # emailservice no recibe compras en la fixture: nunca sano.
    assert sano_confirmado("emailservice", ev, k=1).sano is False
    # frontend tiene anomalía propia; checkoutservice no tiene errores propios ni atribuidos.
    assert sano_confirmado("frontend", ev, k=1).motivo == "anomalía propia"
    assert sano_confirmado("checkoutservice", ev, k=2).sano is True


def test_quota_marks_truncated_and_truncated_is_never_healthy(pm04):
    barrido = sweep(request(), settings(sweep_quota_per_service=2), t0=T0, recorder=pm04.recorder)
    front, ship = barrido.fila("frontend"), barrido.fila("shippingservice")
    assert front.cobertura.truncado is True and front.cobertura.registros_leidos <= 2 + 40
    assert ship.cobertura.truncado is False
    assert sano_confirmado("frontend", barrido.evidencia, k=1).motivo.startswith("lectura truncada")
    info = sweep(request(), settings(sweep_info_quota_per_service=1), t0=T0, recorder=pm04.recorder)
    assert info.fila("shippingservice").cobertura.truncado_info is True


def test_without_recorder_platform_is_no_data_never_current_state(pm04, tmp_path):
    barrido = sweep(request(), settings(), t0=T0, inventario=STORE)
    assert barrido.evidencia.fuentes_fallidas["recorder"] == "registrador no configurado"
    ship = barrido.fila("shippingservice")
    assert ship.plataforma.cumple is None and "recorder" in ship.cobertura.fuentes_fallidas
    assert sano_confirmado("shippingservice", barrido.evidencia, k=1).sano is False
    # Sin Services en la ventana, ningún error se puede atribuir: queda sin atribuir.
    assert barrido.fila("paymentservice").errores_atribuidos == [] and len(barrido.errores_sin_atribuir) == 4
    vacio = Recorder(tmp_path / "vacio.db", "boutique")
    with pytest.raises(ValueError, match="Sin inventario"):
        sweep(request(), settings(), t0=T0, recorder=vacio)


def test_log_source_failure_is_coverage_not_absence_of_errors(pm04, monkeypatch):
    def broken(*args, **kwargs):
        raise TimeoutError("deadline")

    monkeypatch.setattr("tider.console.providers.logging_sdk.BoundedLoggingClient", broken)
    barrido = sweep(request(), settings(), t0=T0, recorder=pm04.recorder)
    fila = barrido.fila("shippingservice")
    assert fila.cobertura.fuentes_fallidas == ["cloud_logging"] and fila.anomalia.anomala is None
    assert sano_confirmado("shippingservice", barrido.evidencia, k=1).sano is False


# --- trazas multilínea (PM-02) y colisión 6379 -------------------------------------------------


def _evidencia(rows, start, end, direcciones=(), servicios=("recommendationservice",)):
    senales = [
        Senal(
            fuente="cloud_logging",
            tiempo=ts(r["timestamp"]),
            servicio=r["labels"]["k8s-pod/app"],
            instancia=r["resource"]["labels"]["pod_name"],
            severidad=r["severity"],
            texto_original=r.get("textPayload")
            or r["jsonPayload"].get("error")
            or r["jsonPayload"]["message"],
        )
        for r in rows
    ]
    cobertura = {s: CoberturaServicio(servicio=s) for s in servicios}
    return asignar_ids(
        Evidencia(
            ventana=Ventana.desde(start, end),
            namespace="boutique",
            inventario=list(servicios),
            senales=senales,
            direcciones=list(direcciones),
            cobertura=cobertura,
        )
    )


def _direcciones(*rows):
    from tider.console.evidence.model import DireccionServicio

    return [
        DireccionServicio(
            fuente="recorder", tiempo=utc(18, 0), texto_original=n, servicio=n, cluster_ip=ip, puertos=[p]
        )
        for n, ip, p in rows
    ]


def test_python_traceback_is_one_event_and_attributed_once():
    rows = load("pm02-traza-python.json")
    ev = _evidencia(
        rows, utc(18, 13), utc(18, 15), _direcciones(("productcatalogservice", "10.49.2.83", 3550))
    )
    assert len(rows) == 15 and len(agrupar_eventos(ev.senales)) == 1
    assert atribuir_errores(ev).por_servicio == {"productcatalogservice": [ev.senales[12].id]}
    assert anomalia("recommendationservice", ev).eventos_incidente == 1


def test_go_cart_errors_resolve_by_clusterip_pm01():
    rows = load("pm01-frontend-cart.json")
    ev = _evidencia(
        rows,
        utc(22, 41),
        utc(22, 43),
        _direcciones(("cartservice", "10.49.8.13", 7070), ("otro", "10.49.8.14", 7070)),
        ("frontend",),
    )
    assert list(atribuir_errores(ev).por_servicio) == ["cartservice"]


def test_6379_proxy_and_wrong_port_never_blame_redis_cart():
    base = {
        "severity": "ERROR",
        "labels": {"k8s-pod/app": "cartservice"},
        "resource": {"labels": {"pod_name": "cartservice-696588d894-nrw4s"}},
    }
    # Formato StackExchange.Redis de cartservice (sintético, mismo formato que RB-02).
    rows = [
        {
            **base,
            "timestamp": "2026-11-09T18:40:00Z",
            "textPayload": "Can't access cart storage. UnableToConnect on 10.49.7.99:6379/Interactive",
        },
        {
            **base,
            "timestamp": "2026-11-09T18:40:05Z",
            "textPayload": "Can't access cart storage. UnableToConnect on redis-cart:6380/Interactive",
        },
    ]
    ev = _evidencia(
        rows,
        utc(18, 39),
        utc(18, 42),
        _direcciones(("redis-cart", "10.49.7.20", 6379), PROXY),
        ("cartservice",),
    )
    atribucion = atribuir_errores(ev)
    assert atribucion.por_servicio == {"chaosforge-proxy": [ev.senales[0].id]}
    assert atribucion.sin_atribuir == [ev.senales[1].id]


# --- eventos sin lista de servicios (A32) --------------------------------------------------------


def test_events_namespace_wide_assign_by_platform_inventory():
    s = Settings(evidence_mode="gcp")
    assert "involvedObject.name=~" not in event_filter(START, END, s)
    assert "involvedObject.name=~" in event_filter(START, END, s, ["paymentservice"])
    inv = {"paymentservice", "redis-cart", "redis"}
    assert owner_from_name("paymentservice-7987f697ff-kzznm", "Pod", inv) == (
        "paymentservice",
        "platform_name_pattern",
    )
    assert owner_from_name("paymentservice-7987f697ff", "ReplicaSet", inv)[0] == "paymentservice"
    assert owner_from_name("redis-cart-0", "Pod", inv)[0] == "redis-cart"
    assert owner_from_name("node-pool-x", "Node", inv) == (None, "")
    raw = load("pm04-eventos.json")[2]
    entry = SimpleNamespace(payload=raw["jsonPayload"], timestamp=ts(raw["timestamp"]))
    event = event_from_entry(entry, None, "boutique", START, END, inventory=inv)
    assert event["service"] == "paymentservice" and event["reason"] == "Killing"
    orphan = event_from_entry(entry, None, "boutique", START, END, inventory=set())
    assert orphan["service"] is None and orphan["mapping"] == "unassigned_namespace_event"
    # La firma v1 sigue igual.
    assert event_from_entry(entry, ["paymentservice"], "boutique", START, END)["service"] == "paymentservice"


def test_plantilla_keeps_address_and_masks_ids():
    a = plantilla(
        "could not retrieve cart: dial tcp 10.49.8.13:7070: connect | user 3bdf7dbf-20bf-4a7b-a029-e268726dcd50"
    )
    assert a == "could not retrieve cart: dial tcp 10.49.8.13:7070: connect | user <id>"
    assert (
        plantilla('failed to convert price of "OLJCESPC7Z" to TRY 12')
        == 'failed to convert price of "<cod>" to TRY <n>'
    )


def test_window_without_t0_uses_request_start():
    ventana = Ventana.desde(START, END)
    assert ventana.t0 == START and ventana.base_inicio == START - (END - START)
    assert timedelta(0) < ventana.duracion


def _redis_case(error_text, redis_ready):
    """Casi iguales (A02): puerto correcto con redis-cart caído / puerto equivocado con redis-cart sano."""
    from tider.console.evidence.model import Servicio

    cart = {
        "severity": "ERROR",
        "labels": {"k8s-pod/app": "cartservice"},
        "resource": {"labels": {"pod_name": "cartservice-696588d894-nrw4s"}},
    }
    redis = {
        "severity": "INFO",
        "labels": {"k8s-pod/app": "redis-cart"},
        "resource": {"labels": {"pod_name": "redis-cart-547cf56b4f-bsfbx"}},
    }
    rows = [
        {**cart, "timestamp": f"2026-11-09T18:40:{i:02}Z", "textPayload": error_text} for i in range(0, 20, 5)
    ]
    if redis_ready:  # líneas reales de redis-cart en PM-04 (BGSAVE)
        rows += [
            {**r, "timestamp": f"2026-11-09T18:40:{30 + i:02}Z"}
            for i, r in enumerate(
                [
                    {
                        **redis,
                        "textPayload": "1:M 09 Nov 2026 18:39:53.136 * 100 changes in 300 seconds. Saving...",
                    },
                    {**redis, "textPayload": "2643:C 09 Nov 2026 18:39:53.171 * DB saved on disk"},
                    {
                        **redis,
                        "textPayload": "1:M 09 Nov 2026 18:39:53.237 * Background saving terminated with success",
                    },
                ]
            )
        ]
    ev = _evidencia(
        rows,
        utc(18, 39, 30),
        utc(18, 41),
        _direcciones(("redis-cart", "10.49.7.20", 6379), PROXY),
        ("cartservice", "redis-cart"),
    )
    n = 1 if redis_ready else 0
    estado = Servicio(
        fuente="recorder",
        tiempo=utc(18, 39),
        texto_original="redis-cart",
        servicio="redis-cart",
        instancias_deseadas=1,
        instancias_listas=n,
        endpoints_listos=n,
    )
    return asignar_ids(ev.model_copy(update={"servicios": [estado]}))


def test_wrong_port_keeps_redis_cart_healthy_correct_port_with_redis_down_does_not():
    wrong = _redis_case("Can't access cart storage. UnableToConnect on redis-cart:6380/Interactive", True)
    assert atribuir_errores(wrong).por_servicio == {}
    assert sano_confirmado("redis-cart", wrong, k=3).sano is True
    down = _redis_case("Can't access cart storage. UnableToConnect on 10.49.7.20:6379/Interactive", False)
    atribuidos = atribuir_errores(down).por_servicio["redis-cart"]
    assert len(atribuidos) == 4
    resultado = sano_confirmado("redis-cart", down, k=3)
    assert resultado.sano is False and resultado.errores_atribuidos == atribuidos
