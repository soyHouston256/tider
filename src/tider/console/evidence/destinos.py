"""Resolución `ClusterIP:puerto` → servicio por ventana (A01).

Regla: un error de un llamador se atribuye a un servicio solo si coinciden la IP **y** el puerto con un
Service de la ventana (o el nombre DNS del Service **y** uno de sus puertos). Nunca por el puerto solo:
`paymentservice` y `shippingservice` comparten 50051, y `redis-cart` y `chaosforge-proxy` comparten 6379.
Lo que no se resuelve no se atribuye a nadie (queda `sin_datos`). El respaldo por IP de pod vía
EndpointSlices queda diferido.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import DireccionServicio

_IPV4 = r"(?:\d{1,3}\.){3}\d{1,3}"
_HOST = r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?(?:\.[a-z0-9](?:[-a-z0-9]*[a-z0-9])?)*"

# Formatos observados en el historial (RB-01, PM-01 a PM-05).
DESTINO_PATTERNS = (
    # Go (frontend, checkout): `transport: Error while dialing: dial tcp 10.49.5.115:50051: connect: ...`
    re.compile(rf"\bdial tcp (?P<host>{_IPV4}|{_HOST}):(?P<puerto>\d{{1,5}})\b"),
    # Python gRPC (recommendationservice): `last error: UNKNOWN: ipv4:10.49.2.83:3550: Failed to connect ...`
    re.compile(rf"\bipv4:(?P<host>{_IPV4}):(?P<puerto>\d{{1,5}})\b"),
    # StackExchange.Redis (cartservice): `UnableToConnect on redis-cart:6379/Interactive`
    re.compile(rf"\bUnableToConnect on (?P<host>{_IPV4}|{_HOST}):(?P<puerto>\d{{1,5}})\b"),
)


@dataclass(frozen=True)
class Destino:
    host: str
    puerto: int
    texto: str


def extraer_destinos(mensaje: str) -> list[Destino]:
    vistos, salida = set(), []
    for pattern in DESTINO_PATTERNS:
        for match in pattern.finditer(mensaje or ""):
            key = (match["host"], int(match["puerto"]))
            if key not in vistos:
                vistos.add(key)
                salida.append(Destino(match["host"], key[1], match.group(0)))
    return salida


@dataclass
class TablaServicios:
    """Tabla `IP:puerto → servicio` (y `nombre:puerto → servicio`) de una ventana."""

    por_ip: dict[tuple[str, int], set[str]] = field(default_factory=dict)
    por_nombre: dict[tuple[str, int], set[str]] = field(default_factory=dict)

    @classmethod
    def desde(cls, direcciones: list[DireccionServicio], namespace: str = "") -> "TablaServicios":
        tabla = cls()
        for d in direcciones:
            for puerto in d.puertos:
                if d.cluster_ip and d.cluster_ip not in {"None", ""}:
                    tabla.por_ip.setdefault((d.cluster_ip, puerto), set()).add(d.servicio)
                nombres = {d.servicio}
                if namespace:
                    nombres |= {
                        f"{d.servicio}.{namespace}",
                        f"{d.servicio}.{namespace}.svc",
                        f"{d.servicio}.{namespace}.svc.cluster.local",
                    }
                for nombre in nombres:
                    tabla.por_nombre.setdefault((nombre, puerto), set()).add(d.servicio)
        return tabla

    def resolver_destino(self, host: str, puerto: int) -> str | None:
        """Servicio dueño de `host:puerto`, o None si no hay coincidencia exacta o es ambigua."""
        candidatos = self.por_ip.get((host, puerto)) or self.por_nombre.get((host.lower(), puerto)) or set()
        return next(iter(candidatos)) if len(candidatos) == 1 else None


def resolver_destino(tabla: TablaServicios, host: str, puerto: int) -> str | None:
    return tabla.resolver_destino(host, puerto)
