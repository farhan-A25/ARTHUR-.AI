"""Browser agent stub — Phase 8 (browser) — not implemented in MVP."""
from backend.agents.base import BaseAgent


class BrowserAgent(BaseAgent):
    """Phase 8 (browser) — not implemented in MVP."""

    def __init__(self, registry, llm):
        super().__init__(name="browser", tools=[], permission_level=1,
                         registry=registry, llm=llm)

    def run(self, task):
        return {"ok": False, "error": "Phase 8 (browser) \u2014 not implemented in MVP"}
