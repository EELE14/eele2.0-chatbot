# Copyright (c) 2026 eele14. All Rights Reserved.
import logging
import random

import httpx

logger = logging.getLogger(__name__)


async def search_gif(query: str, api_key: str, limit: int = 10) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                "https://api.giphy.com/v1/gifs/search",
                params={"q": query, "api_key": api_key, "limit": limit, "rating": "pg-13"},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        logger.warning("Giphy search timed out for query: %r", query)
        return None
    except httpx.HTTPStatusError as e:
        logger.warning("Giphy HTTP %s for query: %r", e.response.status_code, query)
        return None
    except Exception as e:
        logger.error("Giphy search error for query %r: %s", query, e)
        return None

    results = data.get("data", [])
    if not results:
        logger.warning("No Giphy results for query: %r", query)
        return None

    pick = random.choice(results)
    images = pick.get("images", {})
    url = (
        images.get("downsized", {}).get("url")
        or images.get("original", {}).get("url")
    )
    if not url:
        logger.warning("No gif URL in Giphy result for query: %r", query)
    return url
