"""Cartógrafo: nodos de la plataforma, aristas configuradas y observadas, discrepancias y neutralización."""

from pathlib import Path

from tider.console.evidence.destinos import TablaServicios
from tider.console.predicados import atribuir_errores
from tider.console.providers.catalog import EDGES
from tider.console.recorder import Recorder
from tider.console.settings import Settings
from tider.console.sweep import tabla
from tider.console.topology import (
    NOMBRE_NEUTRO,
    TopologiaLake,
    build_graph,
    cargar_topologia,
    neutralizar,
)

from .pilot_fakes import SERVICES, FakeCluster, install_logging, load, record, utc

LAKE = cargar_topologia(Path(__file__).parent / "fixtures" / "topologia.yaml")  # copia de Context Lake V3 rev 1
STORE = sorted(SERVICES)


def test_lake_topology_loads_16_edges_and_auxiliaries():
    assert len(LAKE.aristas) == 16
    assert {(a.origen, a.destino) for a in LAKE.aristas} == set(EDGES)
    assert LAKE.auxiliares == ["chaosforge-proxy", "opentelemetrycollector"]
    assert LAKE.servicios["loadgenerator"] == "generador_de_trafico"
    assert LAKE.valor_configurado("cartservice", "REDIS_ADDR") == "redis-cart:6379"
    assert {(a.origen, a.destino) for a in TopologiaLake.desde_catalogo().aristas} == set(EDGES)


def test_nodes_come_from_platform_and_lake_only_nodes_are_discrepancies():
    inventario = [s for s in STORE if s != "adservice"] + ["chaosforge-proxy", "debug-tools"]
    g = build_graph(inventario, LAKE, [])
    assert [n.nombre for n in g.nodos] == sorted(inventario)  # nunca un nodo que solo está en el Lake
    assert g.tipo("loadgenerator") == "auxiliar" and g.tipo("chaosforge-proxy") == "auxiliar"
    assert g.tipo("frontend") == "tienda" and g.tipo("debug-tools") == "tienda"
    assert "nodo solo en el Lake: adservice" in g.discrepancias
    assert "nodo solo en la plataforma: debug-tools (tienda)" in g.discrepancias
    assert not any("chaosforge-proxy" in d for d in g.discrepancias)  # auxiliar declarado en el Lake
    assert g.arista("frontend", "adservice") is None  # sin nodo no hay arista
    assert all(a.origen_dato == "configurada" for a in g.aristas) and len(g.aristas) == 15


def _cart_env(t, name):
    if name != "cartservice":
        return {}
    valor = "chaosforge-proxy:6379" if t >= utc(18, 39) else "redis-cart:6379"
    return {"env": [{"name": "REDIS_ADDR", "value": valor}], "generation": 2 if t >= utc(18, 39) else 1}


def test_observed_edges_from_addr_and_attributed_errors_with_proxy_discrepancy(monkeypatch, tmp_path):
    cluster = FakeCluster(proxy=True, overrides=_cart_env)
    rec = record(Recorder, tmp_path / "rec.db", cluster, utc(18, 30), utc(18, 46))
    install_logging(monkeypatch, load("pm04-logs.json"), load("pm04-eventos.json"))
    from tider.console.evidence.gke import GKEAdapter
    from tider.console.evidence.model import Ventana

    ventana = Ventana.desde(utc(18, 33, 54), utc(18, 46, 21), utc(18, 38, 54))
    ev = GKEAdapter(Settings(evidence_mode="gcp"), recorder=rec).collect(ventana)
    barrido = tabla(ev, Settings())
    tabla_svc = TablaServicios.desde(ev.direcciones, ev.namespace)
    g = build_graph(ev.inventario, LAKE, ev.servicios, atribuir_errores(ev), tabla=tabla_svc)

    redis = g.arista("cartservice", "redis-cart")
    assert redis.origen_dato == "ambas" and redis.variable == "REDIS_ADDR"
    proxy = g.arista("cartservice", "chaosforge-proxy")
    assert proxy.origen_dato == "observada" and proxy.valor == "chaosforge-proxy:6379" and proxy.ids
    assert "variable que apunta a un componente auxiliar: cartservice REDIS_ADDR=chaosforge-proxy:6379" in g.discrepancias
    assert "arista observada sin arista configurada: cartservice→chaosforge-proxy (variable REDIS_ADDR)" in g.discrepancias
    assert any(d.startswith("valor distinto del Lake: cartservice REDIS_ADDR=chaosforge-proxy:6379") for d in g.discrepancias)
    # Error anidado de frontend que nombra a paymentservice: arista observada solo por errores.
    pago = g.arista("frontend", "paymentservice")
    assert pago.origen_dato == "observada" and pago.variable is None and len(pago.ids) == 4
    assert "arista observada sin arista configurada: frontend→paymentservice (errores atribuidos)" in g.discrepancias
    assert g.estructural().arista("frontend", "paymentservice") is None
    assert g.caminos("frontend", "paymentservice") and g.estructural().caminos("frontend", "paymentservice") == [
        ["frontend", "checkoutservice", "paymentservice"]
    ]
    assert {"frontend", "checkoutservice", "loadgenerator"} <= g.aguas_arriba("paymentservice")
    # El recorder registró el cambio de configuración (base del verificador).
    assert any(c.tipo == "config_cambiada" and c.servicio == "cartservice" for c in barrido.evidencia.cambios)


def test_wrong_port_value_is_unresolved_discrepancy_but_keeps_edge():
    from tider.console.evidence.model import DireccionServicio, Servicio

    t = utc(18, 40)
    dirs = [
        DireccionServicio(fuente="recorder", tiempo=t, texto_original="r", servicio="redis-cart",
                          cluster_ip="10.49.7.20", puertos=[6379])
    ]
    spec = [Servicio(fuente="recorder", tiempo=t, texto_original="c", servicio="cartservice",
                     direcciones={"REDIS_ADDR": "redis-cart:6380"})]
    g = build_graph(["cartservice", "redis-cart"], LAKE, spec, tabla=TablaServicios.desde(dirs, "boutique"))
    assert g.arista("cartservice", "redis-cart").origen_dato == "ambas"
    assert "variable que no se resuelve a ningún Service: cartservice REDIS_ADDR=redis-cart:6380" in g.discrepancias


def test_neutralize_lab_names_for_llm():
    assert neutralizar("REDIS_ADDR=chaosforge-proxy:6379") == f"REDIS_ADDR={NOMBRE_NEUTRO}:6379"
    g = build_graph(["cartservice", "chaosforge-proxy"], LAKE, [])
    assert [n.nombre for n in g.neutralizado().nodos] == ["cartservice", NOMBRE_NEUTRO]
