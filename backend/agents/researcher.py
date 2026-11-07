"""Researcher agent (backend/agents/researcher.py). Level 0 (READ)."""
from backend.agents.base import BaseAgent


class ResearcherAgent(BaseAgent):
    def __init__(self, registry, llm):
        super().__init__(
            name="researcher",
            tools=["web_search", "fetch_url", "read_file", "write_file", "list_files"],
            permission_level=0,
            registry=registry,
            llm=llm,
        )

    def run(self, task):
        # Best-effort web search first; network failure is never fatal.
        note = ""
        try:
            res = self.call_tool("web_search", query=task.get("title", ""))
            if isinstance(res, dict) and res.get("ok"):
                results = res.get("results", []) or []
                note = "web_search returned %d result(s)." % len(results)
            else:
                note = "web_search unavailable (offline)."
        except Exception as e:
            note = "web_search unavailable (offline): %s" % e

        outcome = super().run(task)
        findings = "%s\n%s" % (note, outcome.get("output", ""))
        outcome["output"] = self.llm.summarize(findings, max_chars=600) if self.llm else findings[:600]
        return outcome
