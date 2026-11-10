from .base import FixtureRegistry, Tool, ToolRegistry

__all__ = ["ARCHIVED", "FixtureRegistry", "Tool", "ToolRegistry", "default_registry"]

ARCHIVED = (
    "archivado: ver docs/archive/remediacion. El registro por defecto usaba las herramientas "
    "kube/Prometheus del dominio OTel (archive/legacy_engine/src/tider/tools/)."
)


def default_registry() -> ToolRegistry:
    """Archivada con el grafo antiguo; la implementación original está en
    archive/legacy_engine/src/tider/tools/__init__.py. La consola usa console/investigation_tools.py."""
    raise RuntimeError(ARCHIVED)
