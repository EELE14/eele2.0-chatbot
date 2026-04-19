# Copyright (c) 2026 eele14. All Rights Reserved.
import logging
from html.parser import HTMLParser

import httpx

logger = logging.getLogger(__name__)

_MAX_RESULTS = 4
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_ERROR_RESPONSES = {
    "timeout": "search timed out ngl",
    "http":    "search failed lol",
    "request": "couldn't reach search rn",
    "other":   "couldn't find much on that ngl",
}

_ERROR_STRINGS: frozenset[str] = frozenset(_ERROR_RESPONSES.values())


def is_search_error(result: str) -> bool:
    return result in _ERROR_STRINGS


class _SnippetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.snippets: list[str] = []
        self._capturing = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a" and any("result__snippet" in (v or "") for _, v in attrs):
            self._capturing = True
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capturing:
            self._capturing = False
            text = "".join(self._buf).strip()
            if text:
                self.snippets.append(text)

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._buf.append(data)


async def duckduckgo_search(query: str, max_results: int = _MAX_RESULTS) -> str:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, max_redirects=5) as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers=_HEADERS,
            )
            response.raise_for_status()
            html = response.text

    except httpx.TimeoutException:
        logger.warning("Search timed out for query: %r", query)
        return _ERROR_RESPONSES["timeout"]
    except httpx.HTTPStatusError as e:
        logger.warning("Search HTTP %s for query: %r", e.response.status_code, query)
        return _ERROR_RESPONSES["http"]
    except httpx.RequestError as e:
        logger.error("Search request error for query %r: %s", query, e)
        return _ERROR_RESPONSES["request"]
    except Exception as e:
        logger.error("Unexpected search error for query %r: %s", query, e)
        return _ERROR_RESPONSES["other"]

    if "captcha" in html.lower():
        logger.warning("DDG returned a CAPTCHA page for query: %r", query)
        return _ERROR_RESPONSES["other"]

    parser = _SnippetParser()
    parser.feed(html)
    snippets = parser.snippets[:max_results]

    if not snippets:
        logger.warning("No snippets parsed for query: %r", query)
        return _ERROR_RESPONSES["other"]

    logger.info("Search returned %d snippet(s) for query: %r", len(snippets), query)

    if len(snippets) == 1:
        return snippets[0]

    return "\n".join(f"{i + 1}. {s}" for i, s in enumerate(snippets))
