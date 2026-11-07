"""QA agent (backend/agents/qa.py). Level 1 (LOW RISK).

Runs the default BaseAgent step execution, then verifies the task's
success_criteria: if a criterion is set and neither the step output nor the
artifacts contain it (the manager encodes the expected marker in the steps),
the task is reported as failed.
"""
from backend.agents.base import BaseAgent


class QAAgent(BaseAgent):
    def __init__(self, registry, llm):
        super().__init__(
            name="qa",
            tools=["read_file", "write_file", "list_files", "run_shell", "run_python"],
            permission_level=1,
            registry=registry,
            llm=llm,
        )

    def run(self, task):
        res = super().run(task)
        criteria = (task.get("success_criteria", "") or "").strip()
        if res.get("ok") and criteria:
            blob = (str(res.get("output", "")) + "\n" + str(res.get("artifacts", ""))).lower()
            if criteria.lower() not in blob:
                res = dict(res)
                res["ok"] = False
                res["error"] = (
                    "QA verification failed: success criteria %r not found "
                    "in step output or artifacts." % criteria
                )
        return res
