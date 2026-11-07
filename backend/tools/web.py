"""Web tools: DuckDuckGo search + URL fetching.

No external services are required at import time; every network call is
wrapped in try/except and returns {ok: False, error: ...} on failure.
"""
from __future__ import annotations

import re
import urllib.parse
from html import unescape

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

_USER_AGENT = "Mozilla/5.0 (compatible; ARTHUR/1.0; +https://localhost)"
_SEARCH_URL = "https://html.duckduckgo.com/html/"


def _strip_tags(html):
    """Crude tag stripper."""
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _ddg_target(href):
    """Resolve a DuckDuckGo redirect href to its real target URL."""
    parsed = urllib.parse.urlparse(href)
    qs = urllib.parse.parse_qs(parsed.query)
    if "uddg" in qs:
        return qs["uddg"][0]
    if href.startswith("//"):
        return "https:" + href
    return href


def web_search(query, max_results=5):
    """Search the web via DuckDuckGo HTML.

    Returns {ok: True, results: [{title, url, snippet}]} or
    {ok: False, error: ...}. Never raises.
    """
    try:
        if requests is None:
            return {"ok": False, "error": "requests library not installed"}
        resp = requests.get(
            _SEARCH_URL,
            params={"q": query},
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        html = resp.text
        results = []
        # Each result has: <a rel="nofollow" class="result__a" href="...">title</a>
        # followed later by: <a class="result__snippet" ...>snippet</a>
        links = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            flags=re.S,
        )
        snippets = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</a>',
            html,
            flags=re.S,
        )
        for i, (href, title_html) in enumerate(links[:max_results]):
            title = _strip_tags(title_html)
            snippet = _strip_tags(snippets[i]) if i < len(snippets) else ""
            results.append(
                {
                    "title": title,
                    "url": _ddg_target(href),
                    "snippet": snippet,
                }
            )
        return {"ok": True, "results": results}
    except Exception as exc:  # network may be unavailable
        return {"ok": False, "error": str(exc)}


def fetch_url(url):
    """Fetch ``url`` and return its text (tags stripped, first 4000 chars)."""
    try:
        if requests is None:
            return {"ok": False, "error": "requests library not installed"}
        resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=10)
        resp.raise_for_status()
        return {"ok": True, "url": url, "text": _strip_tags(resp.text)[:4000]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
