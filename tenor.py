# Copyright (c) 2026 eele14. All Rights Reserved.
import logging
import random

import httpx

logger = logging.getLogger(__name__)


async def search_gif(query: str, api_key: str, limit: int = 8) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                "https://tenor.googleapis.com/v2/search",
                params={"q": query, "key": api_key, "limit": limit, "media_filter": "gif"},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        logger.warning("Tenor search timed out for query: %r", query)
        return None
    except httpx.HTTPStatusError as e:
        logger.warning("Tenor HTTP %s for query: %r", e.response.status_code, query)
        return None
    except Exception as e:
        logger.error("Tenor search error for query %r: %s", query, e)
        return None

    results = data.get("results", [])
    if not results:
        logger.warning("No Tenor results for query: %r", query)
        return None

    pick = random.choice(results)
    url = pick.get("media_formats", {}).get("gif", {}).get("url")
    if not url:
        logger.warning("No gif URL in Tenor result for query: %r", query)
    return url
