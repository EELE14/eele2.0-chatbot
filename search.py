# Copyright (c) 2026 eele14. All Rights Reserved.
import httpx


async def duckduckgo_search(query: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
                headers={"User-Agent": "Mozilla/5.0 (compatible)"},
            )
            data = r.json()

        result = data.get("AbstractText", "").strip()

        if not result:
            for topic in data.get("RelatedTopics", []):
                if isinstance(topic, dict) and topic.get("Text"):
                    result = topic["Text"]
                    break

        return result or "couldn't find much on that ngl"

    except Exception:
        return "search failed lol"
