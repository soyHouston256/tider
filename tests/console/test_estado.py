"""Orden barrido → Cartógrafo → verificador → estado → roles sobre casos con forma real (PM-04, PM-01, PM-02).

Los logs y eventos son líneas reales recortadas de los exports de los postmortems (Context Lake V3,
`postmortems/datos/PM-0N`), sin líneas con tarjeta o correo. El estado del clúster lo simula
`FakeCluster` con el escalado a cero y la restauración en los tiempos de los eventos reales.
"""

from datetime import timedelta
from pathlib import Path

import pytest

from tider.console.estado import asignar_roles, estado_aristas, estado_servicio
from tider.console.evidence.destinos import TablaServicios
from tider.console.models import AnalyzeRequest
from tider.console.predicados import atribuir_errores
from tider.console.recorder import Recorder
from tider.console.settings import Settings
from tider.console.signatures import cargar_catalogo, evaluate, ordenar_confirmadas
from tider.console.sweep import sweep
from tider.console.topology import build_graph, cargar_topologia

from .pilot_fakes import FakeCluster, install_logging, load, record, ts, utc

LAKE = cargar_topologia(Path(__file__).parent / "fixtures" / "topologia.yaml")
CATALOGO = cargar_catalogo()

# (servicio caído, inicio, t0, fin, escalado a 0, escalado a 1, pod listo, logs, eventos)
CASOS = {
    "PM-04": ("paymentservice", utc(18, 33, 54), utc(18, 38, 54), utc(18, 46, 21), utc(18, 38, 55),
              utc(18, 40, 55), utc(18, 41, 4), ["pm04-logs.json"], "pm04-eventos.json"),
    "PM-01": ("cartservice", utc(22, 36, 4), utc(22, 41, 4), utc(22, 49, 5), utc(22, 41, 6),
              utc(22, 43, 7), utc(22, 43, 12), ["pm01-caso-logs.json"], "pm01-eventos.json"),
    "PM-02": ("productcatalogservice", utc(18, 8, 5), utc(18, 13, 5), utc(18, 21, 20), utc(18, 13, 6),
              utc(18, 15, 7), utc(18, 15, 11), ["pm02-caso-logs.json", "pm02-traza-python.json"],
              "pm02-eventos.json"),
}


def correr(caso, monkeypatch, tmp_path, k=3):
    causa, inicio, t0, fin, abajo, arriba, listo, logs, eventos = CASOS[caso]

    def overrides(t, name):
        if name != causa:
            return {}
        return {"replicas": 0 if abajo <= t < arriba else 1, "ready": 0 if abajo <= t < listo else 1}

    rec = record(Recorder, tmp_path / f"{caso}.db", FakeCluster(overrides=overrides),
                 t0 - (fin - t0) - timedelta(minutes=1), fin, step=timedelta(seconds=10))
    install_logging(monkeypatch, [r for f in logs for r in load(f)], load(eventos))
    barrido = sweep(AnalyzeRequest(incident_id=caso, start=inicio, end=fin), Settings(evidence_mode="gcp"),
                    t0=t0, recorder=rec)
    ev = barrido.evidencia
    atribucion = atribuir_errores(ev)
    grafo = build_graph(ev.inventario, LAKE, ev.servicios, atribucion,
                        tabla=TablaServicios.desde(ev.direcciones, ev.namespace))
    veredictos = evaluate(CATALOGO, barrido, grafo, lake=LAKE)
    nodos = estado_servicio(barrido, grafo, veredictos, k)
    return barrido, grafo, veredictos, nodos, atribucion


@pytest.mark.parametrize("caso", ["PM-04", "PM-01", "PM-02"])
def test_scale_zero_confirms_only_the_scaled_service(caso, monkeypatch, tmp_path):
    causa = CASOS[caso][0]
    barrido, grafo, veredictos, nodos, _ = correr(caso, monkeypatch, tmp_path)
    confirmadas = ordenar_confirmadas(veredictos, barrido.evidencia)
    assert [(v.entidad.clave, v.firma_id) for v in confirmadas] == [(causa, "servicio-sin-instancias")]
    v = confirmadas[0]
    assert v.t_inicio == CASOS[caso][4]  # el ScalingReplicaSet a 0
    assert {"sin_instancias", "sin_endpoints", "escalado_a_cero", "errores_atribuidos"} <= set(v.cumplidos)
    assert nodos[causa].estado == "falla" and nodos[causa].motivo.startswith("firma CONFIRMADA")
    # Ningún veredicto CONFIRMADA con conflicto.
    assert not any(x.veredicto == "CONFIRMADA" and x.conflicto for x in veredictos)


EXPECTED_VICTIMS = {
    "PM-04": {"frontend", "checkoutservice"},  # checkout: anidada en la línea de frontend
    "PM-01": {"frontend"},
    "PM-02": {"frontend", "recommendationservice"},
}


@pytest.mark.parametrize("caso", ["PM-04", "PM-01", "PM-02"])
def test_victims_are_derived_by_code_from_graph_and_attribution(caso, monkeypatch, tmp_path):
    causa = CASOS[caso][0]
    barrido, grafo, veredictos, nodos, atribucion = correr(caso, monkeypatch, tmp_path)
    principal = ordenar_confirmadas(veredictos, barrido.evidencia)[0]
    roles = asignar_roles(principal, grafo, nodos, barrido, atribucion)
    assert roles[causa].rol_en_principal == "causa"
    victimas = {n for n, nodo in roles.items() if nodo.rol_en_principal == "victima"}
    assert victimas == EXPECTED_VICTIMS[caso]
    por_id = barrido.evidencia.por_id()
    front = roles["frontend"]
    assert front.ids_rol and all(por_id[i].servicio == "frontend" for i in front.ids_rol)
    assert all(por_id[i].tiempo >= principal.t_inicio for i in front.ids_rol)
    # checkoutservice nunca escribe errores propios (RB-01): no es causa y, si es víctima, se cita con
    # la línea de frontend.
    checkout = barrido.fila("checkoutservice")
    assert checkout.plantillas == [] and checkout.errores_atribuidos == []
    if "checkoutservice" in victimas:
        assert roles["checkoutservice"].ids_rol == front.ids_rol
        assert "anidada" in roles["checkoutservice"].motivo_rol
    else:
        assert roles["checkoutservice"].rol_en_principal == "ninguno"
    # Los servicios sin relación no reciben rol.
    assert roles["adservice"].rol_en_principal == "ninguno"


def test_pm04_estado_servicio_three_values_and_edges(monkeypatch, tmp_path):
    barrido, grafo, veredictos, nodos, atribucion = correr("PM-04", monkeypatch, tmp_path, k=2)
    assert set(nodos) == set(barrido.evidencia.inventario)
    assert nodos["paymentservice"].estado == "falla"
    assert nodos["frontend"].estado == "falla" and nodos["frontend"].motivo == "anomalía propia"
    assert nodos["checkoutservice"].estado == "sano"  # tráfico propio, sin errores propios ni atribuidos
    assert nodos["emailservice"].estado == "sin_datos"  # sin compras que le lleguen: nunca sano
    assert nodos["loadgenerator"].tipo == "auxiliar" and nodos["frontend"].tipo == "tienda"
    k3 = estado_servicio(barrido, grafo, veredictos, 3)
    assert k3["checkoutservice"].estado == "sin_datos" and "tráfico insuficiente" in k3["checkoutservice"].motivo
    aristas = {(a.origen, a.destino): a for a in estado_aristas(grafo, nodos, veredictos, atribucion)}
    assert aristas[("frontend", "paymentservice")].estado == "falla"
    assert aristas[("checkoutservice", "paymentservice")].estado == "sin_datos"
    assert aristas[("frontend", "checkoutservice")].estado == "sin_datos"  # frontend en falla
    assert {a.estado for a in aristas.values()} <= {"falla", "sano", "sin_datos"}


def test_pm02_python_trace_victim_counts_once(monkeypatch, tmp_path):
    barrido, grafo, _, _, atribucion = correr("PM-02", monkeypatch, tmp_path)
    ids = atribucion.por_arista[("recommendationservice", "productcatalogservice")]
    assert len(ids) == 1  # 15 líneas, una traza
    assert barrido.evidencia.por_id()[ids[0]].tiempo >= ts("2026-11-09T18:13:06Z")
    assert grafo.arista("recommendationservice", "productcatalogservice").origen_dato == "ambas"
