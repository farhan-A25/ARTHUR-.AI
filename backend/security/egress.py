"""ARTHUR data-egress control.

Rule: agents must NEVER send user/project data to an external service
(email, APIs, webhooks, ...) without explicit owner approval. Any tool
that transmits user/project content externally is registered at
permission LEVEL 2+ so the ToolRegistry gates it behind an approval —
there is no silent path.

Additionally, *outbound sends* (POST/PUT/DELETE/PATCH...) are checked
against an allowlist:

    ARTHUR_EGRESS_ALLOWLIST="host1,host2"   (comma-separated)

Default allowlist: the DuckDuckGo search hosts, the Expo push hosts, and
the operator-configured LLM base-URL host (auto-added). Unknown hosts are
DENIED by default (``EgressBlocked`` is raised).

Inbound GET fetches (``fetch_url`` research reads) are permitted for any
host — fetching public web content does not transmit user data — and are
audit-logged by the ToolRegistry like every other tool call.
"""
from __future__ import annotations

import os
import urllib.parse

_DEFAULT_ALLOWLIST = (
    "html.duckduckgo.com,duckduckgo.com,exp.host,exponent.dev"
)


class EgressBlocked(Exception):
    """Raised when an outbound send targets a non-allowlisted host."""


def get_allowlist() -> set[str]:
    """Configured egress allowlist + the LLM provider host (auto-added)."""
    raw = os.environ.get("ARTHUR_EGRESS_ALLOWLIST", _DEFAULT_ALLOWLIST)
    hosts = {h.strip().lower() for h in raw.split(",") if h.strip()}
    llm_base = os.environ.get("ARTHUR_LLM_BASE_URL", "").strip()
    if llm_base:
        try:
            host = urllib.parse.urlparse(llm_base).hostname
            if host:
                hosts.add(host.lower())
        except Exception:
            pass
    return hosts


def _host_of(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").lower()


def is_outbound_send_allowed(url: str) -> bool:
    """True when ``url``'s host is on the egress allowlist."""
    return _host_of(url) in get_allowlist()


def check_outbound(url: str, method: str = "POST") -> None:
    """Enforce default-DENY on outbound sends.

    Raises :class:`EgressBlocked` for non-GET requests to hosts outside the
    allowlist. GET (inbound fetch) is always permitted.
    """
    if method.upper() == "GET":
        return
    if not is_outbound_send_allowed(url):
        raise EgressBlocked(
            "egress denied: host %r is not on the ARTHUR_EGRESS_ALLOWLIST"
            % (_host_of(url),)
        )


def assert_send_allowed(url: str) -> None:
    """Helper for future external-send tools: allowlist check for user data.

    Call this before transmitting any user/project content externally.
    Such tools MUST additionally be registered at permission level 2+ so
    the owner explicitly approves each use.
    """
    check_outbound(url, method="POST")
