"""Estado por servicio (falla / sano / sin datos): interfaz reservada para la Fase 2 (A04).

Orden de cálculo: barrido (`sweep.py`) → Cartógrafo (`topology.py`) → verificador (`signatures.py`) →
estado (este módulo). El verificador toma sus candidatos de la función de anomalía
(`predicados.anomalia`), no del estado, así que no hay circularidad.

Regla que implementará la Fase 2, con las piezas ya disponibles en la Fase 1:
* **falla**: alguna firma CONFIRMADA sobre el servicio, o anomalía propia (`predicados.anomalia`);
* **sano**: `predicados.sano_confirmado(...)` es verdadero;
* **sin datos**: todo lo demás (incluye truncado, fuentes fallidas y tráfico < K).
"""

from __future__ import annotations

from typing import Any


def estado_servicio(barrido, grafo: Any, veredictos: Any, k: int) -> dict:
    """`estado_servicio(barrido, grafo, veredictos, k) -> dict[str, Nodo]` (Fase 2: necesita grafo y firmas)."""
    raise NotImplementedError(
        "estado_servicio se implementa en la Fase 2 (necesita el grafo y los veredictos)."
    )
