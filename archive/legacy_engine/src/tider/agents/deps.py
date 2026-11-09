from __future__ import annotations

from dataclasses import dataclass

from ..llm import LLM
from ..safety import Safety
from ..tools.base import ToolRegistry


@dataclass
class Deps:
    llm: LLM
    store: object  # InMemoryStore | PgVectorStore
    tools: ToolRegistry
    policy: dict
    use_judge: bool = True  # para la ablación del eval (con/sin juez)
    use_rag: bool = True  # para la ablación del eval (con/sin context lake)
    judge_llm: LLM | None = (
        None  # otro modelo para el juez (TIDER_JUDGE_MODEL): menos errores correlacionados
    )
    safety: Safety | None = None  # límites con estado; uno por proceso

    def __post_init__(self):
        if self.safety is None:
            self.safety = Safety.from_policy(self.policy)
