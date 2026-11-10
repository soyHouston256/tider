"""Verificador de firmas: catálogo, tabla de verdad de las 4 firmas y latencia frente a configuración.

Fixtures construidas a mano con el modelo común (ítem 14). Las métricas de latencia y CPU son
**SINTÉTICAS**: las corridas de historial (PM-01 a PM-05) no traen observador ni Monitoring.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tider.console.evidence.model import (
    Cambio,
    CoberturaServicio,
    DireccionServicio,
    Evidencia,
    Senal,
    Servicio,
    Ventana,
    asignar_ids,
)
from tider.console.models import Entidad
from tider.console.predicados import atribuir_errores
from tider.console.settings import Settings
from tider.console.signatures import (
    Catalogo,
    Predicado,
    ResultadoPredicado,
    baseline,
    cargar_catalogo,
    evaluate,
    ordenar_confirmadas,
    tabla_de_verdad,
)
from tider.console.sweep import tabla
from tider.console.topology import build_graph, cargar_topologia

FIXTURES = Path(__file__).parent / "fixtures"
LAKE = cargar_topologia(FIXTURES / "topologia.yaml")
CATALOGO = cargar_catalogo()
START = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
T0, FIN = START + timedelta(minutes=5), START + timedelta(minutes=10)
IPS = {
    "cartservice": ("10.49.8.13", 7070),
    "redis-cart": ("10.49.7.20", 6379),
    "frontend": ("10.49.0.80", 80),
    "chaosforge-proxy": ("10.49.7.99", 6379),  # inventada; comparte puerto con redis-cart
}
CART, REDIS = Entidad.de_servicio("cartservice"), Entidad.de_servicio("redis-cart")
ENLACE = Entidad.de_enlace("cartservice", "redis-cart")


def at(minutos: float) -> datetime:
    return START + timedelta(minutes=minutos)


def estado(servicio, t, deseadas=1, listas=1, endpoints=1, **direcciones):
    return Servicio(
        fuente="recorder",
        tiempo=t,
        texto_original=f"{servicio} {deseadas}/{listas}/{endpoints} {direcciones}",
        servicio=servicio,
        instancias_deseadas=deseadas,
        instancias_listas=listas,
        endpoints_listos=endpoints,
        direcciones=direcciones,
    )


def log(servicio, t, texto, severidad="ERROR"):
    return Senal(fuente="cloud_logging", tiempo=t, servicio=servicio, severidad=severidad, texto_original=texto,
                 instancia=f"{servicio}-pod")


def metrica(servicio, nombre, t, valor, destino=None):
    """Métrica SINTÉTICA (observador de ChaosForge / Managed Prometheus)."""
    return Senal(fuente="observer" if "latencia" in nombre else "monitoring", clase="metrica", tiempo=t,
                 servicio=servicio, nombre=nombre, valor=valor, destino=destino,
                 texto_original=f"{nombre}={valor} {servicio}->{destino or ''}")


def serie(servicio, nombre, base, incidente, destino=None, cada=10):
    puntos = []
    t = START
    while t <= FIN:
        puntos.append(metrica(servicio, nombre, t, base if t < T0 else incidente, destino))
        t += timedelta(seconds=cada)
    return puntos


def cambio(servicio, t, tipo="config_cambiada", **diferencias):
    texto = json.dumps({"carga": servicio, "cambio": tipo, "diferencias": diferencias, "generacion": [1, 2]})
    return Cambio(fuente="recorder" if tipo != "escalado" else "k8s_events", tiempo=t, servicio=servicio,
                  tipo=tipo, texto_original=texto)


def escalado(servicio, t, antes, despues):
    return Cambio(fuente="k8s_events", tiempo=t, servicio=servicio, tipo="escalado", antes=antes, despues=despues,
                  texto_original=f"Normal ScalingReplicaSet Deployment/{servicio} from {antes} to {despues}")


def escenario(servicios=(), cambios=(), senales=(), fallidas=None, inventario=None):
    inventario = inventario or ["cartservice", "chaosforge-proxy", "frontend", "redis-cart"]
    direcciones = [
        DireccionServicio(fuente="recorder", tiempo=START - timedelta(minutes=10), texto_original=n,
                          servicio=n, cluster_ip=ip, puertos=[p])
        for n, (ip, p) in IPS.items()
        if n in inventario
    ]
    fallidas = fallidas or {}
    cobertura = {
        s: CoberturaServicio(servicio=s, fuentes_fallidas=sorted(f for f in fallidas if f != "k8s_events"))
        for s in inventario
    }
    ev = asignar_ids(
        Evidencia(
            ventana=Ventana.desde(START, FIN, T0),
            namespace="boutique",
            inventario=inventario,
            servicios=list(servicios),
            direcciones=direcciones,
            cambios=list(cambios),
            senales=list(senales),
            cobertura=cobertura,
            fuentes_fallidas=fallidas,
        )
    )
    barrido = tabla(ev, Settings())
    grafo = build_graph(inventario, LAKE, ev.servicios, atribuir_errores(ev))
    return barrido, grafo


def veredicto(barrido, grafo, firma_id, entidad):
    catalogo = Catalogo(version=1, firmas=[CATALOGO.firma(firma_id)])
    (v,) = evaluate(catalogo, barrido, grafo, lake=LAKE, entidades=[entidad])
    return v


def sanos(*nombres, **direcciones):
    return [estado(n, START - timedelta(minutes=1), **(direcciones if n == "cartservice" else {})) for n in nombres]


# --- catálogo y tabla de verdad -------------------------------------------------------------------


def test_catalog_has_four_signatures_to_validate_and_two_declared():
    assert [f.id for f in CATALOGO.firmas] == [
        "servicio-sin-instancias",
        "configuracion-incorrecta",
        "dependencia-lenta",
        "saturacion-cpu",
    ]
    assert [f.runbook_id for f in CATALOGO.firmas] == ["RB-01", "RB-02", "RB-03", "RB-04"]
    assert all(f.validado is False for f in CATALOGO.firmas)  # pasan a true solo tras la Fase 6
    assert {d.id: d.runbook_id for d in CATALOGO.declaradas_no_validadas} == {
        "se-cae-al-arrancar": "RB-05",
        "sin-memoria": "RB-06",
    }
    assert all(d.estado_validacion == "declarada, no validada" for d in CATALOGO.declaradas_no_validadas)
    assert len(CATALOGO.hash) == 64
    with pytest.raises(ValueError, match="Campo desconocido"):
        Predicado(id="x", campo="terminaciones_en_ventana", operador="existe")
    with pytest.raises(ValueError, match="hoja"):
        Predicado(id="x", campo="servicio.instancias_deseadas", operador="==", umbral=0, todos=[])


def _r(cumple):
    return ResultadoPredicado(id="p", cumple=cumple)


@pytest.mark.parametrize(
    "obl, des, cor, esperado",
    [
        ([None, True], [True], [True], ("SIN_DATOS", False)),  # SIN_DATOS precede a todo
        ([True, True], [True], [True], ("DESCARTADA", True)),  # confirma y descarta: conflicto
        ([True, False], [True], [True], ("DESCARTADA", False)),
        ([True, True], [None], [True], ("CONFIRMADA", False)),  # descarte sin datos no descarta
        ([True, True], [False], [None, False], ("DESCARTADA", False)),  # sin corroborante
        ([True, False], [False], [True], ("DESCARTADA", False)),
    ],
)
def test_truth_table_precedence(obl, des, cor, esperado):
    v, conflicto, _ = tabla_de_verdad([_r(x) for x in obl], [_r(x) for x in des], [_r(x) for x in cor])
    assert (v, conflicto) == esperado
    assert not (v == "CONFIRMADA" and conflicto)


# --- servicio-sin-instancias (RB-01) ----------------------------------------------------------------

_CAIDO = "could not retrieve cart: rpc error: code = Unavailable desc = connection error: desc = \"transport: Error while dialing: dial tcp 10.49.8.13:7070: connect: connection refused\""  # noqa: E501


def _sin_instancias(**kw):
    servicios = [*sanos("frontend", "redis-cart"), estado("cartservice", START), *kw.get("cart", [])]
    cambios = kw.get("cambios", [])
    senales = [log("frontend", at(5.3 + i / 10), _CAIDO) for i in range(4)]
    return escenario(servicios, cambios, senales, fallidas=kw.get("fallidas"))


def test_sin_instancias_confirm():
    b, g = _sin_instancias(
        cart=[estado("cartservice", at(5.2), 0, 0, 0), estado("cartservice", at(7.2))],
        cambios=[escalado("cartservice", at(5.1), "1", "0")],
    )
    v = veredicto(b, g, "servicio-sin-instancias", CART)
    assert v.veredicto == "CONFIRMADA" and not v.conflicto
    assert v.t_inicio == at(5.1)  # el escalado es el primer punto
    assert {"sin_instancias", "sin_endpoints", "escalado_a_cero", "errores_atribuidos"} <= set(v.cumplidos)


def test_sin_instancias_discard_and_near_negative():
    b, g = _sin_instancias()
    v = veredicto(b, g, "servicio-sin-instancias", CART)
    assert v.veredicto == "DESCARTADA" and v.motivo.startswith("descarte: siempre_listo")
    # Negativo cercano: 0 réplicas durante 10 s (menos que la persistencia de 20 s).
    b, g = _sin_instancias(cart=[estado("cartservice", at(5.2), 0, 0, 0), estado("cartservice", at(5.2 + 1 / 6))])
    assert veredicto(b, g, "servicio-sin-instancias", CART).veredicto == "DESCARTADA"


def test_sin_instancias_without_recorder_is_no_data():
    b, g = escenario([], [], [log("frontend", at(5.3), _CAIDO)], fallidas={"recorder": "registrador no configurado"})
    v = veredicto(b, g, "servicio-sin-instancias", CART)
    assert v.veredicto == "SIN_DATOS" and "sin_instancias" in v.motivo


def test_sin_instancias_contradictory_evidence_never_confirms():
    # Contradictorio: 0 deseadas pero pods listos y endpoints (ReplicaSet viejo aún sirviendo).
    # Los obligatorios piden endpoints == 0, así que no se cumplen a la vez que el descarte: sin conflicto.
    b, g = _sin_instancias(cart=[estado("cartservice", at(5.2), 0, 1, 1)])
    v = veredicto(b, g, "servicio-sin-instancias", CART)
    assert v.veredicto == "DESCARTADA" and v.conflicto is False


# --- configuracion-incorrecta (RB-02) y dependencia-lenta (RB-03) ---------------------------------

_WRONG = "Can't access cart storage. StackExchange.Redis.RedisConnectionException: It was not possible to connect to the redis server(s). UnableToConnect on redis-cart:6380/Interactive"  # noqa: E501
_TIMEOUT = "Can't access cart storage. StackExchange.Redis.RedisTimeoutException: Timeout performing HGET (5000ms), inst: 0, qu: 0, qs: 1, serverEndpoint: chaosforge-proxy:6379, mgr: 10 of 10 available"  # noqa: E501


def _wrong_port(errores=True, fallidas=None):
    servicios = [
        *sanos("frontend", "redis-cart", "chaosforge-proxy", "cartservice", REDIS_ADDR="redis-cart:6379"),
        estado("cartservice", at(5), REDIS_ADDR="redis-cart:6380"),
    ]
    cambios = [cambio("cartservice", at(5), REDIS_ADDR=["redis-cart:6379", "redis-cart:6380"])]
    senales = [log("cartservice", at(5.25 + i / 10), _WRONG) for i in range(4)] if errores else []
    return escenario(servicios, cambios, senales, fallidas=fallidas)


def _latencia(con_timeouts=True, cpu_origen=0.01, observador=True):
    """Inyección de latencia: el laboratorio redirige REDIS_ADDR al proxy (Cambio previo) y el proxy demora."""
    servicios = [
        *sanos("frontend", "redis-cart", "chaosforge-proxy", "cartservice", REDIS_ADDR="redis-cart:6379"),
        estado("cartservice", at(4), REDIS_ADDR="chaosforge-proxy:6379"),
    ]
    cambios = [cambio("cartservice", at(4), REDIS_ADDR=["redis-cart:6379", "chaosforge-proxy:6379"])]
    senales = [log("cartservice", at(5.5 + i / 10), _TIMEOUT, "WARNING") for i in range(3)] if con_timeouts else []
    if observador:
        senales += serie("cartservice", "latencia_dependencia_p95", 2.0, 900.0, destino="redis-cart")
        senales += serie("cartservice", "latencia_p95", 30.0, 1200.0)
        senales += serie("cartservice", "cpu_throttling", 0.01, cpu_origen)
        senales += serie("redis-cart", "cpu_throttling", 0.0, 0.0)
    return escenario(servicios, cambios, senales)


def test_config_confirm_wrong_port():
    b, g = _wrong_port()
    v = veredicto(b, g, "configuracion-incorrecta", CART)
    assert v.veredicto == "CONFIRMADA" and not v.conflicto
    assert v.t_inicio == at(5)
    assert {"cambio_previo", "errores_hacia_valor_nuevo", "destino_original_sano", "sigue_vivo"} <= set(v.cumplidos)
    responde = next(r for r in v.descartes if r.id == "destino_nuevo_responde")
    assert responde.cumple is False  # redis-cart:6380 no se resuelve a ningún Service (nombre y puerto)
    assert next(r for r in v.descartes if r.id == "igual_al_lake").cumple is False
    # redis-cart no es candidato a causa: sin errores atribuidos (6380 no es suyo).
    assert b.fila("redis-cart").errores_atribuidos == []


def test_config_discard_without_change_and_without_errors():
    b, g = escenario(sanos("frontend", "redis-cart", "cartservice", REDIS_ADDR="redis-cart:6379"))
    v = veredicto(b, g, "configuracion-incorrecta", CART)
    assert v.veredicto == "DESCARTADA" and "igual_al_lake" in v.motivo
    b, g = _wrong_port(errores=False)  # cambio sin síntoma que lo explique
    v = veredicto(b, g, "configuracion-incorrecta", CART)
    assert v.veredicto == "DESCARTADA" and v.faltantes == ["errores_hacia_valor_nuevo"]


def test_config_without_recorder_is_no_data():
    b, g = _wrong_port(fallidas={"recorder": "registrador no configurado"})
    assert veredicto(b, g, "configuracion-incorrecta", CART).veredicto == "SIN_DATOS"


def test_config_conflict_when_redirected_to_responding_proxy():
    b, g = _latencia()
    v = veredicto(b, g, "configuracion-incorrecta", CART)
    # Cambio previo + timeouts hacia el valor nuevo: los obligatorios se cumplen; el proxy responde: descarte.
    assert v.veredicto == "DESCARTADA" and v.conflicto is True
    assert "destino_nuevo_responde" in v.motivo


def test_latency_vs_config_disambiguation():
    lat_b, lat_g = _latencia()
    wp_b, wp_g = _wrong_port()
    lat = {v.firma_id: v for v in evaluate(CATALOGO, lat_b, lat_g, lake=LAKE, entidades=[CART, ENLACE])}
    wp = {v.firma_id: v for v in evaluate(CATALOGO, wp_b, wp_g, lake=LAKE, entidades=[CART, ENLACE])}
    assert lat["dependencia-lenta"].veredicto == "CONFIRMADA"
    assert lat["configuracion-incorrecta"].veredicto == "DESCARTADA"
    assert lat["saturacion-cpu"].veredicto == "DESCARTADA"
    assert wp["configuracion-incorrecta"].veredicto == "CONFIRMADA"
    assert wp["dependencia-lenta"].veredicto == "SIN_DATOS"  # sin observador no hay latencia medida
    # Una sola firma confirmada en cada caso: el orden no depende del LLM.
    assert [v.firma_id for v in ordenar_confirmadas(list(lat.values()), lat_b.evidencia)] == ["dependencia-lenta"]
    assert [v.firma_id for v in ordenar_confirmadas(list(wp.values()), wp_b.evidencia)] == [
        "configuracion-incorrecta"
    ]
    # El Cartógrafo reporta la redirección, y el nombre del laboratorio se neutraliza para el LLM (P9).
    assert any("componente auxiliar: cartservice REDIS_ADDR=chaosforge-proxy:6379" in d for d in lat_g.discrepancias)
    assert all("chaosforge" not in d for d in lat_g.neutralizado().discrepancias)


def test_dependencia_lenta_truth_table():
    v = veredicto(*_latencia(), "dependencia-lenta", ENLACE)
    assert v.veredicto == "CONFIRMADA" and v.t_inicio == T0
    assert next(r for r in v.obligatorios if r.id == "sin_errores_conexion").cumple is True  # timeouts, no rechazo
    # Descarte: sin aumento de latencia.
    b, g = escenario(
        sanos("cartservice", "redis-cart"),
        senales=serie("cartservice", "latencia_dependencia_p95", 2.0, 2.5, destino="redis-cart"),
    )
    v = veredicto(b, g, "dependencia-lenta", ENLACE)
    assert v.veredicto == "DESCARTADA" and v.faltantes == ["latencia_alta"]
    # Sin datos: ninguna medida de latencia para el enlace (fuera del laboratorio).
    assert veredicto(*_latencia(observador=False), "dependencia-lenta", ENLACE).veredicto == "SIN_DATOS"
    # Conflicto: latencia alta, pero la CPU propia del llamador está saturada (RB-04).
    v = veredicto(*_latencia(cpu_origen=0.5), "dependencia-lenta", ENLACE)
    assert v.veredicto == "DESCARTADA" and v.conflicto is True


def test_dependencia_lenta_connection_refused_goes_to_rb01_rb02():
    b, g = _latencia()
    senales = [*b.evidencia.senales, *(log("cartservice", at(6 + i / 10), _WRONG) for i in range(3))]
    servicios = list(b.evidencia.servicios)
    b2, g2 = escenario(servicios, b.evidencia.cambios, senales)
    v = veredicto(b2, g2, "dependencia-lenta", ENLACE)
    assert v.veredicto == "DESCARTADA" and v.faltantes == ["sin_errores_conexion"]


# --- saturacion-cpu (RB-04) -------------------------------------------------------------------------


def _cpu(throttling=0.4, limites=True, metricas=True, saliente=False):
    servicios = sanos("cartservice", "redis-cart", "frontend")
    cambios = (
        [cambio("cartservice", at(5), recursos=[{"server": {"limits": {"cpu": "300m"}}},
                                                 {"server": {"limits": {"cpu": "100m"}}}])]
        if limites
        else []
    )
    senales = []
    if metricas:
        senales += serie("cartservice", "cpu_throttling", 0.01, throttling)
        senales += serie("cartservice", "latencia_p95", 20.0, 400.0)
    if saliente:
        senales += serie("cartservice", "latencia_dependencia_p95", 2.0, 900.0, destino="redis-cart")
    return escenario(servicios, cambios, senales)


def test_saturacion_cpu_truth_table():
    v = veredicto(*_cpu(), "saturacion-cpu", CART)
    assert v.veredicto == "CONFIRMADA" and "limites_cambiados" in v.cumplidos and v.t_inicio == at(5)
    v = veredicto(*_cpu(throttling=0.02), "saturacion-cpu", CART)
    assert v.veredicto == "DESCARTADA" and "throttling_bajo" in v.motivo and not v.conflicto
    assert veredicto(*_cpu(metricas=False), "saturacion-cpu", CART).veredicto == "SIN_DATOS"
    v = veredicto(*_cpu(saliente=True), "saturacion-cpu", CART)
    assert v.veredicto == "DESCARTADA" and v.conflicto is True and "dependencia_saliente_lenta" in v.motivo
    v = veredicto(*_cpu(limites=False), "saturacion-cpu", CART)
    assert v.veredicto == "DESCARTADA" and "sin ningún corroborante" in v.motivo


def test_baseline_without_llm_orders_confirmed_and_reports_none():
    b, g = _wrong_port()
    veredictos = evaluate(CATALOGO, b, g, lake=LAKE)
    analysis = baseline("C-1", veredictos, b)
    assert analysis.component == "cartservice" and analysis.reasoning_mode == "rules"
    assert "configuracion-incorrecta" in analysis.hypothesis and analysis.evidence
    assert "no verificada" in analysis.recommendation
    vacio = baseline("C-2", [v for v in veredictos if v.veredicto != "CONFIRMADA"], b)
    assert vacio.status == "insufficient_evidence" and vacio.evidence == []
