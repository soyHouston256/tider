"""Protocolo prerregistrado: carga, hash canónico, plan de casos y etiquetas esperadas.

El plan es determinista (semilla del protocolo). Las etiquetas salen del protocolo, no de ChaosForge:
el ground truth de ChaosForge solo se usa para admitir o excluir un caso (inyección acreditada).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "protocol.yaml"
_HASH_LINE = re.compile(r"^hash: *[0-9a-f]*$", re.M)


class ProtocolError(ValueError):
    pass


def _canonical(data: dict) -> str:
    body = {k: v for k, v in data.items() if k != "hash"}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)


def compute_hash(data: dict) -> str:
    return hashlib.sha256(_canonical(data).encode("utf-8")).hexdigest()


def load(path: str | Path = PROTOCOL, *, verify: bool = True) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if verify and data.get("hash") != compute_hash(data):
        raise ProtocolError(
            f"El hash de {Path(path).name} no corresponde a su contenido: el protocolo cambió después de "
            "registrarse. Si todavía no hubo ninguna corrida, recalcúlalo con --rehash.")
    return data


def rehash(path: str | Path = PROTOCOL) -> str:
    """Reescribe solo la línea `hash:` (conserva los comentarios)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    digest = compute_hash(yaml.safe_load(text))
    if not _HASH_LINE.search(text):
        raise ProtocolError("El protocolo no tiene una línea `hash:` de primer nivel.")
    path.write_text(_HASH_LINE.sub(f"hash: {digest}", text, count=1), encoding="utf-8")
    return digest


# --- Etiquetas ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Etiqueta:
    tipo: str  # servicio | enlace | ninguna
    servicio: str | None = None
    origen: str | None = None
    destino: str | None = None
    razon: str | None = None
    impacto: str | None = None

    @property
    def clave(self) -> str:
        if self.tipo == "servicio":
            return self.servicio
        if self.tipo == "enlace":
            return f"{self.origen}->{self.destino}"
        return "ninguna"


def etiqueta(protocol: dict, servicio: str | None, mecanismo: str | None) -> Etiqueta:
    if mecanismo is None:
        return Etiqueta(tipo="ninguna")
    m = protocol["mecanismos"][mecanismo]
    if m["entidad"] == "enlace":
        return Etiqueta(tipo="enlace", origen=m["enlace"]["origen"], destino=m["enlace"]["destino"], razon=m["razon"])
    impacto = None
    ctrl = protocol["conjuntos"]["control"]["loadgenerator"]
    if servicio == ctrl["servicio"]:
        impacto = ctrl["etiqueta"]["impacto"]
    return Etiqueta(tipo="servicio", servicio=servicio, razon=m["razon"], impacto=impacto)


# --- Plan ---------------------------------------------------------------------------------------------


@dataclass
class Caso:
    case_id: str
    conjunto: str  # evaluacion | control | validacion
    estrato: str
    servicio: str | None
    mecanismo: str | None  # None = sin falla
    duracion: int
    parametros: dict = field(default_factory=dict)

    def etiqueta(self, protocol: dict) -> Etiqueta:
        return etiqueta(protocol, self.servicio, self.mecanismo)

    def to_dict(self) -> dict:
        return asdict(self)


def historial_pairs(protocol: dict) -> set[tuple[str, str]]:
    return {(p["servicio"], p["mecanismo"]) for p in protocol["conjuntos"]["historial"]["pares"]}


def prohibited_ids(protocol: dict) -> list[str]:
    return [str(i).lower() for i in protocol["conjuntos"]["historial"]["experimentos_prohibidos"]]


def is_prohibited(experiment_id: str, protocol: dict) -> bool:
    """Un id prohibido completo, o un id que empieza por un prefijo prohibido (o al revés)."""
    ident = (experiment_id or "").lower()
    return any(ident.startswith(p) or p.startswith(ident) for p in prohibited_ids(protocol) if ident)


def _parametros(protocol: dict, mecanismo: str | None) -> dict:
    return dict(protocol["mecanismos"][mecanismo].get("parametros") or {}) if mecanismo else {}


def check_case(caso: Caso, protocol: dict) -> None:
    """Rechaza un caso que viola el reparto congelado o los límites de ChaosForge."""
    if caso.mecanismo is not None:
        permitidas = protocol["mecanismos"][caso.mecanismo]["duraciones_permitidas"]
        if caso.duracion not in permitidas:
            raise ProtocolError(f"{caso.case_id}: duración {caso.duracion} no permitida para {caso.mecanismo}.")
    if caso.conjunto in {"evaluacion", "control"} and (caso.servicio, caso.mecanismo) in historial_pairs(protocol):
        raise ProtocolError(f"{caso.case_id}: el par {caso.servicio}×{caso.mecanismo} es de historial.")


def campaign_plan(protocol: dict) -> list[Caso]:
    """Evaluación (estratos) + control, intercalados con la semilla para no confundir con la hora del día."""
    evaluacion = []
    for estrato, cfg in protocol["conjuntos"]["evaluacion"]["estratos"].items():
        for servicio in cfg["servicios"]:
            duraciones = cfg["duraciones"]
            for i in range(cfg["casos_por_servicio"]):
                evaluacion.append(("evaluacion", estrato, servicio, cfg["mecanismo"], duraciones[i % len(duraciones)]))
    ctrl = protocol["conjuntos"]["control"]
    control = [("control", "loadgenerator", ctrl["loadgenerator"]["servicio"], ctrl["loadgenerator"]["mecanismo"], d)
               for d in ctrl["loadgenerator"]["duraciones"] for _ in range(ctrl["loadgenerator"]["casos_por_duracion"])]
    control += [("control", "sin_falla", None, None, ctrl["sin_falla"]["duracion_s"])
                for _ in range(ctrl["sin_falla"]["casos"])]
    rng = random.Random(protocol["semilla"])
    rng.shuffle(evaluacion)
    rng.shuffle(control)
    # Un control cada ~9 casos de evaluación.
    filas, paso = [], max(1, len(evaluacion) // max(1, len(control)))
    ce = cc = 0
    for i, fila in enumerate(evaluacion):
        filas.append(fila)
        if (i + 1) % paso == 0 and control:
            filas.append(control.pop(0))
    filas += control
    casos = []
    for conjunto, estrato, servicio, mecanismo, duracion in filas:
        if conjunto == "evaluacion":
            ce += 1
            cid = f"E{ce:02}"
        else:
            cc += 1
            cid = f"C{cc:02}"
        caso = Caso(cid, conjunto, estrato, servicio, mecanismo, duracion, _parametros(protocol, mecanismo))
        check_case(caso, protocol)
        casos.append(caso)
    planned = sum(c.conjunto == "evaluacion" for c in casos)
    if planned != protocol["conjuntos"]["evaluacion"]["n_planificado"]:
        raise ProtocolError(f"El plan tiene {planned} casos de evaluación y el protocolo declara "
                            f"{protocol['conjuntos']['evaluacion']['n_planificado']}.")
    return casos


def validation_plan(protocol: dict) -> list[Caso]:
    casos = []
    for i, c in enumerate(protocol["validacion_firmas"]["corridas"], 1):
        mecanismo = None if c.get("sin_falla") else c["mecanismo"]
        caso = Caso(f"V{i}", "validacion", mecanismo or "sin_falla", c.get("servicio"), mecanismo, c["duracion"],
                    _parametros(protocol, mecanismo))
        check_case(caso, protocol)
        casos.append(caso)
    return casos


def estimated_seconds(caso: Caso, protocol: dict, tider_seconds: int = 180) -> int:
    """Tiempo de pared estimado del caso: falla + recuperación + espera de ingesta + Tider + separación."""
    v = protocol["ventana"]
    rec = v["recuperacion_estimada_s"]["scale_zero" if caso.mecanismo in {None, "scale_zero"} else "otros"]
    espera = v["margen_posterior_s"] + v["espera_ingesta_s"]
    separacion = max(0, caso.duracion + rec + v["margen_posterior_s"] - (espera + tider_seconds))
    return caso.duracion + rec + espera + tider_seconds + separacion
