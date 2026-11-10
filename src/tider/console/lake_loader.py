"""Carga del Context Lake v3 en el ContextLake de la consola (Fase 4, A11 y A33).

El índice de `ContextLake` es un `chromadb.EphemeralClient`: vive en la memoria del proceso. Por eso
no hay un comando `tider-lake-load` aparte (indexaría en su propia memoria y terminaría). La consola
llama a `load_v3` al iniciar cuando `LAKE_V3_PATH` apunta a la carpeta.

Qué entra y qué no:
- `topologia.yaml`: grafo estructurado para el Cartógrafo; no entra al índice vectorial.
- `fichas/*.md` y `runbooks/*.md`: un fragmento por documento, accesibles por clave (`get`).
- `postmortems/PM-*.md`: historial, un fragmento por documento (el corte por `##` queda diferido, P6),
  marcados como antecedente; solo por búsqueda.
- Se omiten `README.md`, `postmortems/PLANTILLA.md`, `postmortems/PENDIENTES.md`, `postmortems/datos/**`
  (exportaciones crudas), `correr_corridas.sh` y `corridas.log`.
"""

import re
from pathlib import Path

import yaml

from .context_lake import ContextLake, front_matter, sha256_text

# (patrón relativo a la carpeta, tipo_doc esperado). Los patrones no son recursivos.
INCLUDE = (("fichas/*.md", "ficha"), ("runbooks/*.md", "runbook"), ("postmortems/PM-*.md", "postmortem"))
SKIP = {"PLANTILLA.md", "PENDIENTES.md"}
REVISION = re.compile(r"^Revisi[oó]n\s+(\d+)\b", re.M)


def lake_files(folder: Path) -> list[tuple[Path, str]]:
    """Archivos que se indexan, en orden estable, con el tipo que su carpeta exige."""
    selected = []
    for pattern, tipo in INCLUDE:
        selected += [(path, tipo) for path in sorted(folder.glob(pattern))
                     if path.is_file() and path.name not in SKIP]
    return selected


def lake_revision(folder: Path) -> int | None:
    readme = folder / "README.md"
    if not readme.is_file():
        return None
    match = REVISION.search(readme.read_text(encoding="utf-8"))
    return int(match[1]) if match else None


def load_v3(folder: str | Path, lake: ContextLake) -> dict:
    """Carga el Lake v3 en `lake` y devuelve su manifiesto congelado. Falla si el paquete está mal formado."""
    folder = Path(folder).expanduser()
    topology_path = folder / "topologia.yaml"
    if not topology_path.is_file():
        raise ValueError(f"El Lake v3 no tiene topologia.yaml: {folder}")
    files = lake_files(folder)
    if not files:
        raise ValueError(f"El Lake v3 no tiene fichas, runbooks ni postmortems: {folder}")
    loaded = []
    for path, expected in files:
        content = path.read_text(encoding="utf-8")
        tipo = front_matter(content)[0].get("tipo_doc")
        if tipo != expected:
            raise ValueError(f"{path.relative_to(folder)}: tipo_doc {tipo!r}, se esperaba {expected!r}.")
        loaded.append((path, content))
    raw_topology = topology_path.read_text(encoding="utf-8")
    topology = yaml.safe_load(raw_topology)
    if not isinstance(topology, dict):
        raise ValueError("topologia.yaml no es un mapa YAML.")
    for path, content in loaded:
        lake.add(path.name, content)
    lake.set_topology(topology, sha256_text(raw_topology),
                      {"carpeta": str(folder), "revision": lake_revision(folder)})
    return lake.manifest()
