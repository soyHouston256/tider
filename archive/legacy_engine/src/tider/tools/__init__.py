from .base import FixtureRegistry, Tool, ToolRegistry

__all__ = ["FixtureRegistry", "Tool", "ToolRegistry", "default_registry"]


def default_registry() -> ToolRegistry:
    from . import kube, observability

    return ToolRegistry(kube.tools() + observability.tools())
