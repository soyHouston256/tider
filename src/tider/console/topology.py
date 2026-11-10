"""Cartógrafo (pipeline v2, Fase 2): grafo de dependencias con nodos de la plataforma.

* **Nodos:** el inventario de la plataforma (Deployments y StatefulSets), nunca el Lake. Cada nodo es
  `tienda` o `auxiliar`: auxiliar si `topologia.yaml` lo lista en `componentes_auxiliares` o con un rol
  distinto de `tienda` (loadgenerator es `generador_de_trafico`, A24), o, si el Lake no lo conoce, si su
  nombre coincide con un patrón de laboratorio u observabilidad.
* **Aristas configuradas:** `aristas` de `topologia.yaml` (o, sin archivo, `providers.catalog.EDGES`).
* **Aristas observadas:** variables `*_ADDR` del spec (instantáneas del registrador) y errores de un
  llamador cuyo `IP:puerto` se resuelve contra la tabla de Services de la ventana (A01).
* **Discrepancias:** nodo solo en el Lake, nodo solo en la plataforma, arista observada sin arista
  configurada, variable que apunta a un componente auxiliar y variable que no se resuelve a ningún Service.

El barrido nunca usa estas aristas para decidir qué leer (riesgo aceptado del inventario): el grafo se
construye después del barrido y solo sirve para nombrar enlaces y separar causa de víctimas.

`neutralizar` (P9, opción A): la redirección a un componente del laboratorio cuenta como evidencia, pero su
nombre (`chaosforge-*`) se reemplaza por `componente-auxiliar` antes de llegar al LLM o a la traza. La Fase 3
lo aplica al serializar la tabla, el grafo y los veredictos.
"""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from .evidence.destinos import TablaServicios
from .evidence.model import Servicio
from .models import Arista
from .predicados import Atribucion

PATRON_AUXILIAR = re.compile(
    r"^(chaosforge|toxiproxy|opentelemetry|otel|prometheus|grafana|jaeger|loadgenerator)", re.I
)
_LAB = re.compile(r"\bchaosforge[-a-z0-9]*", re.I)
NOMBRE_NEUTRO = "componente-auxiliar"


def neutralizar(texto: str) -> str:
    """Reemplaza los nombres de componentes del laboratorio (`chaosforge-proxy`, …) por un nombre neutro."""
    return _LAB.sub(NOMBRE_NEUTRO, texto or "")


def host_corto(host: str) -> str:
    """`redis-cart.boutique.svc.cluster.local` → `redis-cart`."""
    return host.split(".", 1)[0].lower()


def separar_direccion(valor: str) -> tuple[str, int] | None:
    host, sep, puerto = (valor or "").rpartition(":")
    return (host, int(puerto)) if sep and host and puerto.isdigit() else None


# --- Topología del Lake ---------------------------------------------------------------------------


class AristaLake(BaseModel):
    origen: str
    destino: str
    variable: str | None = None
    valor: str | None = None


class TopologiaLake(BaseModel):
    """Lo que el Cartógrafo necesita de `topologia.yaml` (A04: se lee del disco, sin esperar al Lake v3)."""

    servicios: dict[str, str] = Field(default_factory=dict)  # nombre -> rol
    auxiliares: list[str] = Field(default_factory=list)
    aristas: list[AristaLake] = Field(default_factory=list)
    revision: str = ""

    @classmethod
    def desde_yaml(cls, texto: str) -> "TopologiaLake":
        data = yaml.safe_load(texto) or {}
        return cls(
            servicios={s["nombre"]: s.get("rol", "tienda") for s in data.get("servicios", [])},
            auxiliares=[a["nombre"] for a in data.get("componentes_auxiliares", [])],
            aristas=[
                AristaLake(origen=a["from"], destino=a["to"], variable=a.get("variable"), valor=a.get("valor"))
                for a in data.get("aristas", [])
            ],
            revision=str((data.get("meta") or {}).get("revision", "")),
        )

    @classmethod
    def desde_catalogo(cls) -> "TopologiaLake":
        """Respaldo sin archivo del Lake: las 16 aristas de `providers.catalog` (mismas que topologia.yaml rev 1)."""
        from .providers.catalog import EDGES, SERVICES

        return cls(
            servicios={s: ("generador_de_trafico" if s == "loadgenerator" else "tienda") for s in SERVICES},
            aristas=[AristaLake(origen=o, destino=d) for o, d in EDGES],
            revision="catalog.py",
        )

    def valor_configurado(self, origen: str, variable: str) -> str | None:
        return next((a.valor for a in self.aristas if a.origen == origen and a.variable == variable), None)


def cargar_topologia(path: str | Path) -> TopologiaLake:
    return TopologiaLake.desde_yaml(Path(path).read_text(encoding="utf-8"))


# --- Grafo ----------------------------------------------------------------------------------------


class NodoGrafo(BaseModel):
    nombre: str
    tipo: Literal["tienda", "auxiliar"]
    en_lake: bool


class Grafo(BaseModel):
    nodos: list[NodoGrafo]
    aristas: list[Arista]
    discrepancias: list[str] = Field(default_factory=list)

    def nodo(self, nombre: str) -> NodoGrafo | None:
        return next((n for n in self.nodos if n.nombre == nombre), None)

    def tipo(self, nombre: str) -> str:
        nodo = self.nodo(nombre)
        return nodo.tipo if nodo else "tienda"

    @property
    def auxiliares(self) -> set[str]:
        return {n.nombre for n in self.nodos if n.tipo == "auxiliar"}

    def arista(self, origen: str, destino: str) -> Arista | None:
        return next((a for a in self.aristas if a.origen == origen and a.destino == destino), None)

    def sucesores(self, nombre: str) -> list[str]:
        return [a.destino for a in self.aristas if a.origen == nombre]

    def aguas_arriba(self, nombre: str) -> set[str]:
        """Todos los nodos con un camino dirigido hasta `nombre` (llamadores directos e indirectos)."""
        vistos, cola = set(), deque([nombre])
        while cola:
            actual = cola.popleft()
            for a in self.aristas:
                if a.destino == actual and a.origen not in vistos and a.origen != nombre:
                    vistos.add(a.origen)
                    cola.append(a.origen)
        return vistos

    def caminos(self, origen: str, destino: str, limite: int = 6) -> list[list[str]]:
        """Caminos simples `origen → … → destino` (el grafo tiene ~20 aristas: la búsqueda es trivial)."""
        salida: list[list[str]] = []

        def visitar(camino: list[str]):
            if len(camino) > limite:
                return
            for siguiente in self.sucesores(camino[-1]):
                if siguiente == destino:
                    salida.append([*camino, siguiente])
                elif siguiente not in camino:
                    visitar([*camino, siguiente])

        visitar([origen])
        return salida

    def estructural(self) -> "Grafo":
        """Solo las aristas del Lake o de variables `*_ADDR` (sin las que salen únicamente de errores)."""
        return self.model_copy(
            update={"aristas": [a for a in self.aristas if a.origen_dato != "observada" or a.variable]}
        )

    def neutralizado(self) -> "Grafo":
        """Copia con los nombres de laboratorio neutralizados (P9), para el LLM y la traza."""
        return Grafo(
            nodos=[n.model_copy(update={"nombre": neutralizar(n.nombre)}) for n in self.nodos],
            aristas=[
                a.model_copy(
                    update={
                        "origen": neutralizar(a.origen),
                        "destino": neutralizar(a.destino),
                        "valor": neutralizar(a.valor) if a.valor else a.valor,
                    }
                )
                for a in self.aristas
            ],
            discrepancias=[neutralizar(d) for d in self.discrepancias],
        )


def _tipo_nodo(nombre: str, lake: TopologiaLake) -> str:
    if nombre in lake.auxiliares:
        return "auxiliar"
    if nombre in lake.servicios:
        return "tienda" if lake.servicios[nombre] == "tienda" else "auxiliar"
    return "auxiliar" if PATRON_AUXILIAR.match(nombre) else "tienda"


def build_graph(
    inventario: list[str],
    lake_topology: TopologiaLake | None,
    spec_snapshots: list[Servicio],
    errores: Atribucion | None = None,
    *,
    tabla: TablaServicios | None = None,
) -> Grafo:
    """Grafo de la ventana. `spec_snapshots` son las observaciones `Servicio` del registrador (traen las
    variables `*_ADDR`); `errores` es la atribución de errores por `ClusterIP:puerto` del barrido; `tabla`
    resuelve `nombre:puerto` contra los Services de la ventana (sin tabla, solo se compara el nombre)."""
    lake = lake_topology or TopologiaLake()
    plataforma = set(inventario)
    nodos = [NodoGrafo(nombre=n, tipo=_tipo_nodo(n, lake), en_lake=n in lake.servicios) for n in sorted(plataforma)]
    auxiliares = {n.nombre for n in nodos if n.tipo == "auxiliar"}
    discrepancias: set[str] = set()
    for nombre in sorted(set(lake.servicios) - plataforma):
        discrepancias.add(f"nodo solo en el Lake: {nombre}")
    for n in nodos:
        if not n.en_lake and n.nombre not in lake.auxiliares:
            discrepancias.add(f"nodo solo en la plataforma: {n.nombre} ({n.tipo})")

    configuradas = {(a.origen, a.destino): a for a in lake.aristas if {a.origen, a.destino} <= plataforma}
    observadas: dict[tuple[str, str], dict] = {}

    # Variables *_ADDR del spec, en todas las instantáneas de la ventana (un cambio deja las dos aristas).
    for s in sorted(spec_snapshots, key=lambda s: s.tiempo):
        for variable, valor in sorted(s.direcciones.items()):
            partes = separar_direccion(valor)
            if partes is None:
                continue
            host, puerto = partes
            destino = tabla.resolver_destino(host, puerto) if tabla else None
            if destino is None:
                corto = host_corto(host)
                if corto not in plataforma:
                    discrepancias.add(f"variable sin destino en la plataforma: {s.servicio} {variable}={valor}")
                    continue
                destino = corto
                if tabla is not None:
                    discrepancias.add(
                        f"variable que no se resuelve a ningún Service: {s.servicio} {variable}={valor}"
                    )
            if destino in auxiliares:
                discrepancias.add(f"variable que apunta a un componente auxiliar: {s.servicio} {variable}={valor}")
            esperado = lake.valor_configurado(s.servicio, variable)
            if esperado and esperado != valor:
                discrepancias.add(f"valor distinto del Lake: {s.servicio} {variable}={valor} (Lake: {esperado})")
            obs = observadas.setdefault((s.servicio, destino), {"variable": variable, "valor": valor, "ids": []})
            obs["valor"] = valor
            if s.id and s.id not in obs["ids"]:
                obs["ids"].append(s.id)

    # Errores de llamadores atribuidos por ClusterIP:puerto.
    for (origen, destino), ids in sorted((errores.por_arista if errores else {}).items()):
        obs = observadas.setdefault((origen, destino), {"variable": None, "valor": None, "ids": []})
        obs["ids"] += [i for i in ids if i not in obs["ids"]]

    aristas = []
    for clave in sorted(set(configuradas) | set(observadas)):
        conf, obs = configuradas.get(clave), observadas.get(clave)
        if obs and not conf:
            por = f"variable {obs['variable']}" if obs.get("variable") else "errores atribuidos"
            discrepancias.add(f"arista observada sin arista configurada: {clave[0]}→{clave[1]} ({por})")
        aristas.append(
            Arista(
                origen=clave[0],
                destino=clave[1],
                origen_dato="ambas" if conf and obs else ("configurada" if conf else "observada"),
                variable=(obs or {}).get("variable") or (conf.variable if conf else None),
                valor=(obs or {}).get("valor") or (conf.valor if conf else None),
                ids=list((obs or {}).get("ids", [])),
            )
        )
    return Grafo(nodos=nodos, aristas=aristas, discrepancias=sorted(discrepancias))
