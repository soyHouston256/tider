from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from tider.console.evidence import (
    DireccionServicio,
    Evidencia,
    Senal,
    TablaServicios,
    Ventana,
    asignar_ids,
    extraer_destinos,
)
from tider.console.settings import Settings

T = datetime(2026, 11, 9, 18, 39, 13, tzinfo=timezone.utc)
# Línea real de PM-04 (frontend, logs-warning-o-mas.json).
PM04_PAYMENT = (
    "failed to complete the order: rpc error: code = Internal desc = failed to charge card: could not "
    'charge the card: rpc error: code = Unavailable desc = connection error: desc = "transport: Error '
    'while dialing: dial tcp 10.49.5.115:50051: connect: connection refused" | request error'
)
# Línea real de PM-02 (recommendationservice, cliente Python).
PM02_PYTHON = (
    '\tdetails = "failed to connect to all addresses; last error: UNKNOWN: ipv4:10.49.2.83:3550: '
    'Failed to connect to remote host: Connection refused"'
)


def tabla(*extra):
    rows = [
        ("paymentservice", "10.49.5.115", 50051),
        ("shippingservice", "10.49.6.40", 50051),
        ("redis-cart", "10.49.7.20", 6379),
        ("chaosforge-proxy", "10.49.7.99", 6379),
        *extra,
    ]
    return TablaServicios.desde(
        [
            DireccionServicio(
                fuente="recorder", tiempo=T, texto_original="svc", servicio=n, cluster_ip=ip, puertos=[p]
            )
            for n, ip, p in rows
        ],
        "boutique",
    )


def test_observation_requires_source_aware_time_and_original_text():
    with pytest.raises(ValidationError):
        Senal(tiempo=T, servicio="frontend", texto_original="x")  # sin fuente
    with pytest.raises(ValidationError):
        Senal(fuente="lake", tiempo=T, servicio="frontend", texto_original="x")  # fuente fuera del enum
    with pytest.raises(ValidationError):
        Senal(fuente="cloud_logging", tiempo=T.replace(tzinfo=None), servicio="frontend", texto_original="x")
    with pytest.raises(ValidationError):
        Senal(fuente="cloud_logging", tiempo=T, servicio="frontend", texto_original="")


def test_dependency_latency_metric_needs_destination():
    with pytest.raises(ValidationError):
        Senal(
            fuente="observer",
            tiempo=T,
            servicio="cartservice",
            texto_original="p95=900ms",
            clase="metrica",
            nombre="latencia_dependencia_p95",
            valor=900,
        )
    ok = Senal(
        fuente="observer",
        tiempo=T,
        servicio="cartservice",
        texto_original="p95=900ms",
        clase="metrica",
        nombre="latencia_dependencia_p95",
        valor=900,
        destino="redis-cart",
    )
    assert ok.destino == "redis-cart"


def test_window_baseline_has_same_duration_before_t0():
    v = Ventana.desde(T, T + timedelta(minutes=5))
    assert v.t0 == v.inicio and v.base_inicio == T - timedelta(minutes=5)
    campaign = Ventana.desde(T - timedelta(minutes=5), T + timedelta(minutes=2), t0=T)
    assert campaign.duracion == timedelta(minutes=2) and campaign.en_linea_base(T - timedelta(seconds=1))
    assert not campaign.en_linea_base(T) and campaign.en_incidente(T)
    with pytest.raises(ValidationError):
        Ventana.desde(T, T + timedelta(minutes=1), t0=T + timedelta(minutes=2))


def test_ids_are_deterministic_and_stable_across_replays():
    ventana = Ventana.desde(T, T + timedelta(minutes=5))
    rows = [
        Senal(
            fuente="cloud_logging",
            tiempo=T + timedelta(seconds=i),
            servicio="frontend",
            texto_original=f"l{i}",
        )
        for i in (3, 1, 2)
    ]
    a = asignar_ids(Evidencia(ventana=ventana, namespace="boutique", inventario=["frontend"], senales=rows))
    b = asignar_ids(
        Evidencia(ventana=ventana, namespace="boutique", inventario=["frontend"], senales=rows[::-1])
    )
    assert sorted((s.id, s.texto_original) for s in a.senales) == [
        ("S0001", "l1"),
        ("S0002", "l2"),
        ("S0003", "l3"),
    ]
    assert sorted((s.id, s.texto_original) for s in a.senales) == sorted(
        (s.id, s.texto_original) for s in b.senales
    )
    assert set(a.por_id()) == {"S0001", "S0002", "S0003"}


def test_destination_regexes_for_go_python_and_redis_formats():
    assert [(d.host, d.puerto) for d in extraer_destinos(PM04_PAYMENT)] == [("10.49.5.115", 50051)]
    assert [(d.host, d.puerto) for d in extraer_destinos(PM02_PYTHON)] == [("10.49.2.83", 3550)]
    redis = "Can't access cart storage. UnableToConnect on redis-cart:6379/Interactive"
    assert [(d.host, d.puerto) for d in extraer_destinos(redis)] == [("redis-cart", 6379)]
    # Sonda de readiness: no es un error de llamador y no tiene formato de dial.
    assert (
        extraer_destinos('Readiness probe failed: failed to connect service "10.48.1.171:50051" within 1s')
        == []
    )


def test_port_50051_collision_payment_vs_shipping_needs_ip_and_port():
    t = tabla()
    (destino,) = extraer_destinos(PM04_PAYMENT)
    assert t.resolver_destino(destino.host, destino.puerto) == "paymentservice"
    assert t.resolver_destino("10.49.6.40", 50051) == "shippingservice"
    # La IP correcta con otro puerto o un puerto compartido con otra IP no se resuelven.
    assert t.resolver_destino("10.49.5.115", 50052) is None
    assert t.resolver_destino("10.49.99.99", 50051) is None


def test_port_6379_collision_redis_cart_vs_chaosforge_proxy():
    t = tabla()
    assert t.resolver_destino("10.49.7.20", 6379) == "redis-cart"
    assert t.resolver_destino("10.49.7.99", 6379) == "chaosforge-proxy"
    assert t.resolver_destino("chaosforge-proxy", 6379) == "chaosforge-proxy"
    assert t.resolver_destino("redis-cart.boutique.svc.cluster.local", 6379) == "redis-cart"
    # wrong_port: el nombre coincide pero el puerto no -> no se atribuye a redis-cart.
    assert t.resolver_destino("redis-cart", 6380) is None


def test_pod_ip_and_ambiguous_entries_are_unresolved():
    assert tabla().resolver_destino("10.48.1.171", 50051) is None  # IP de pod: respaldo diferido
    ambigua = tabla(("otro", "10.49.5.115", 50051))
    assert ambigua.resolver_destino("10.49.5.115", 50051) is None


def test_pipeline_defaults_to_v1_and_reads_tider_pipeline(monkeypatch):
    assert Settings().pipeline == "v1"
    monkeypatch.setenv("TIDER_PIPELINE", "v2")
    assert Settings().pipeline == "v2"
    with pytest.raises(ValidationError):
        Settings(pipeline="v3")
