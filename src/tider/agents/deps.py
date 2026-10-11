from __future__ import annotations
from dataclasses import dataclass, field
from ..llm import LLM
from ..tools.base import ToolRegistry


@dataclass
class Deps:
    llm: LLM
    store: object            # InMemoryStore | PgVectorStore
    tools: ToolRegistry
    policy: dict
    use_judge: bool = True   # para la ablación del eval (con/sin juez)
    use_rag: bool = True     # para la ablación del eval (con/sin context lake)
