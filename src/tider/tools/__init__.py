from .base import FixtureRegistry, Tool, ToolRegistry


def default_registry() -> ToolRegistry:
    from . import kube, observability
    return ToolRegistry(kube.tools() + observability.tools())
