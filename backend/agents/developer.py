"""Developer agent (backend/agents/developer.py). Level 1 (LOW RISK).

Uses the default BaseAgent step execution as-is.
"""
from backend.agents.base import BaseAgent


class DeveloperAgent(BaseAgent):
    def __init__(self, registry, llm):
        super().__init__(
            name="developer",
            tools=["read_file", "write_file", "edit_file", "list_files", "run_shell", "run_python"],
            permission_level=1,
            registry=registry,
            llm=llm,
        )
