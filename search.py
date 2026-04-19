# Copyright (c) 2026 eele14. All Rights Reserved.
import logging

import httpx

logger = logging.getLogger(__name__)


async def duckduckgo_search(query: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, max_redirects=5) as client:
            response = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
                headers={"User-Agent": "Mozilla/5.0 (compatible)"},
            )
            response.raise_for_status()
            data = response.json()

    except httpx.TimeoutException:
        logger.warning("Search timed out for query: %r", query)
        return "search timed out ngl"
    except httpx.HTTPStatusError as e:
        logger.warning("Search HTTP %s for query: %r", e.response.status_code, query)
        return "search failed lol"
    except httpx.RequestError as e:
        logger.error("Search request error for query %r: %s", query, e)
        return "couldn't reach search rn"
    except Exception as e:
        logger.error("Unexpected search error for query %r: %s", query, e)
        return "couldn't find much on that ngl"

    result = data.get("AbstractText", "").strip()
    if not result:
        for topic in data.get("RelatedTopics", []):
            if isinstance(topic, dict) and topic.get("Text"):
                result = topic["Text"]
                break

    return result or "couldn't find much on that ngl"
