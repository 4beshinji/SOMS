"""News fetcher with cache — Hacker News API (no key required)."""
import logging
import time
from typing import List, Optional

import aiohttp

logger = logging.getLogger(__name__)

HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"
CACHE_TTL = 3600  # 1 hour
MAX_STORIES = 5


class NewsFetcher:
    """Fetches and caches top Hacker News stories."""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._cache: Optional[List[dict]] = None
        self._cache_time: float = 0

    async def get_summary(self) -> Optional[str]:
        """Return news summary for LLM context.  None on total failure."""
        now = time.time()
        if self._cache and now - self._cache_time < CACHE_TTL:
            return self._format(self._cache)

        stories = await self._fetch()
        if stories:
            self._cache = stories
            self._cache_time = now
            return self._format(stories)

        if self._cache:
            return self._format(self._cache)
        return None

    async def _fetch(self) -> Optional[List[dict]]:
        try:
            session = self._session or aiohttp.ClientSession()
            own_session = self._session is None
            try:
                # Get top story IDs
                async with session.get(
                    HN_TOP_URL, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        logger.warning("HN top stories HTTP %d", resp.status)
                        return None
                    ids = await resp.json(content_type=None)

                # Fetch first N stories in parallel
                stories: List[dict] = []
                top_ids = ids[: MAX_STORIES * 2]  # fetch extra in case some fail

                async def _get_story(story_id: int) -> Optional[dict]:
                    url = HN_ITEM_URL.format(story_id)
                    try:
                        async with session.get(
                            url, timeout=aiohttp.ClientTimeout(total=5)
                        ) as r:
                            if r.status == 200:
                                return await r.json(content_type=None)
                    except Exception:
                        pass
                    return None

                import asyncio

                results = await asyncio.gather(
                    *[_get_story(sid) for sid in top_ids]
                )
                for item in results:
                    if item and item.get("title"):
                        stories.append(
                            {
                                "title": item["title"],
                                "score": item.get("score", 0),
                                "url": item.get("url", ""),
                            }
                        )
                    if len(stories) >= MAX_STORIES:
                        break

                return stories if stories else None
            finally:
                if own_session:
                    await session.close()
        except Exception as e:
            logger.warning("HN fetch error: %s", e)
            return None

    def _format(self, stories: List[dict]) -> str:
        if not stories:
            return "ニュースを取得できませんでした"
        lines = [f"Hacker News トップ {len(stories)} 件:"]
        for s in stories:
            score = s.get("score", 0)
            lines.append(f"- {s['title']} ({score}pts)")
        return "\n".join(lines)
