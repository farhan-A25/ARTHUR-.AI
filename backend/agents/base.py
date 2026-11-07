"""Base agent (backend/agents/base.py).

Step-execution + checkpoint protocol every agent follows:
  - run(task) executes task["steps"] = [{tool, args}] in order
  - steps with index < checkpoint["step_index"] are skipped (crash resume)
  - save_checkpoint(task_id, i+1, {"last_output": str}) after each step
  - WaitingForApproval is re-raised (never swallowed); other exceptions
    produce {ok: False, error, output: partial, artifacts}
"""
from backend.tasks.queue import save_checkpoint
from backend.tools.registry import WaitingForApproval


class BaseAgent:
    def __init__(self, name, tools, permission_level, registry, llm):
        self.name = name
        self.tools = list(tools)
        self.permission_level = permission_level
        self.registry = registry
        self.llm = llm

    def call_tool(self, tool_name, **kwargs):
        return self.registry.call(self, tool_name, **kwargs)

    def run(self, task):
        """Execute task steps. Returns {ok, output, artifacts, error?}."""
        steps = task.get("steps", []) or []
        checkpoint = task.get("checkpoint", {}) or {}
        start = checkpoint.get("step_index", 0) or 0

        outputs = []
        artifacts = []
        executed = 0

        for i, step in enumerate(steps):
            if i < start:
                continue
            tool = step["tool"]
            args = step.get("args", {}) or {}
            try:
                result = self.call_tool(tool, **args)
            except WaitingForApproval:
                raise
            except Exception as e:
                return {
                    "ok": False,
                    "error": "step %d (%s) failed: %s" % (i, tool, e),
                    "output": self._summarize(outputs, executed, len(steps)),
                    "artifacts": artifacts,
                }
            # A tool reporting ok=False is a step failure (not a success):
            # propagate it so the worker's retry/supervision machinery engages.
            if isinstance(result, dict) and result.get("ok") is False:
                return {
                    "ok": False,
                    "error": "step %d (%s) failed: %s" % (
                        i, tool, result.get("error") or "tool returned ok=False"),
                    "output": self._summarize(outputs, executed, len(steps)),
                    "artifacts": artifacts,
                }
            outputs.append(result)
            executed += 1
            if tool == "write_file" and isinstance(result, dict) and result.get("ok"):
                artifacts.append(result.get("path"))
            save_checkpoint(task.get("id"), i + 1, {"last_output": str(result)})

        return {
            "ok": True,
            "output": self._summarize(outputs, executed, len(steps)),
            "artifacts": artifacts,
        }

    @staticmethod
    def _summarize(outputs, executed, total):
        lines = ["Executed %d/%d steps." % (executed, total)]
        for r in outputs[-3:]:
            lines.append(str(r)[:500])
        return "\n".join(lines)
