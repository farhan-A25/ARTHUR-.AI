"""LLM client (llm/client.py).

OpenAI-compatible chat client with a deterministic rule-based demo fallback.
DEMO_MODE defaults to "true": no API key or network is required at import
or runtime.
"""
import json
import os
import urllib.request

DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() == "true"


class LLMClient:
    def __init__(self):
        self.demo_mode = os.environ.get("DEMO_MODE", "true").lower() == "true"
        self.base_url = os.environ.get("ARTHUR_LLM_BASE_URL", "").rstrip("/")
        self.api_key = os.environ.get("ARTHUR_LLM_API_KEY", "")
        self.model = os.environ.get("ARTHUR_LLM_MODEL", "gpt-4o-mini")

    def chat(self, messages, system=None):
        """Chat completion -> str. Falls back to deterministic demo reply on any failure."""
        if self.demo_mode or not self.api_key:
            return self._demo_reply(messages)
        try:
            return self._remote_chat(messages, system)
        except Exception:
            return self._demo_reply(messages)

    def _remote_chat(self, messages, system=None):
        msgs = ([{"role": "system", "content": system}] if system else []) + list(messages or [])
        # Egress control: the LLM provider host is auto-added to the
        # allowlist (operator-configured); anything else is denied.
        from backend.security.egress import check_outbound

        check_outbound(self.base_url + "/chat/completions", method="POST")
        payload = json.dumps({"model": self.model, "messages": msgs}).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]

    def _demo_reply(self, messages):
        """Deterministic rule-based demo reply (no network, no key needed)."""
        last_user = ""
        for m in reversed(messages or []):
            if isinstance(m, dict) and m.get("role") == "user":
                last_user = str(m.get("content", ""))
                break
        low = last_user.lower()
        if "plan" in low or "tasks" in low:
            return (
                "Demo plan:\n"
                "1. Research the goal and write findings to a file.\n"
                "2. Implement the change in small, tested steps.\n"
                "3. Run verification and report results."
            )
        if "summar" in low:
            return (last_user[:200] + "\u2026") if len(last_user) > 200 else last_user + "\u2026"
        return "Acknowledged (demo mode). I will proceed with the requested steps."

    def summarize(self, text, max_chars=300):
        """Short summary of text; deterministic truncation in demo mode."""
        text = str(text)
        if self.demo_mode or not self.api_key:
            return (text[:max_chars] + "\u2026") if len(text) > max_chars else text
        try:
            out = self.chat([{"role": "user", "content": "Summarize concisely:\n\n" + text}])
            out = str(out)
            return (out[:max_chars] + "\u2026") if len(out) > max_chars else out
        except Exception:
            return (text[:max_chars] + "\u2026") if len(text) > max_chars else text
