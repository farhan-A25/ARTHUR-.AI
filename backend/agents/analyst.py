"""Analyst agent stub — Phase 4 (analyst) — not implemented in MVP."""
from backend.agents.base import BaseAgent


class AnalystAgent(BaseAgent):
    """Phase 4 (analyst) — not implemented in MVP."""

    def __init__(self, registry, llm):
        super().__init__(name="analyst", tools=[], permission_level=1,
                         registry=registry, llm=llm)

    def run(self, task):
        return {"ok": False, "error": "Phase 4 (analyst) \u2014 not implemented in MVP"}
