"""Weather fetcher with cache — wttr.in (no API key required)."""
import logging
import time
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

DEFAULT_LOCATION = "Maebashi"
CACHE_TTL = 1800  # 30 minutes

# wttr.in weatherCode → Japanese description (common codes)
_WEATHER_JA: dict[int, str] = {
    113: "晴れ", 116: "晴れ時々曇り", 119: "曇り", 122: "本曇り",
    143: "霧", 176: "小雨", 179: "小雪", 182: "みぞれ",
    185: "着氷性霧雨", 200: "雷雨の可能性", 227: "吹雪", 230: "猛吹雪",
    248: "霧", 260: "着氷性霧", 263: "霧雨", 266: "霧雨",
    281: "着氷性霧雨", 284: "着氷性大雨", 293: "小雨", 296: "弱い雨",
    299: "雨", 302: "やや強い雨", 305: "強い雨", 308: "大雨",
    311: "着氷性雨", 314: "着氷性大雨", 317: "みぞれ", 320: "強いみぞれ",
    323: "小雪", 326: "弱い雪", 329: "雪", 332: "やや強い雪",
    335: "強い雪", 338: "大雪", 350: "ひょう",
    353: "にわか雨", 356: "強いにわか雨", 359: "激しいにわか雨",
    362: "にわかみぞれ", 365: "強いにわかみぞれ",
    368: "にわか雪", 371: "強いにわか雪",
    374: "にわかひょう", 377: "強いにわかひょう",
    386: "雷を伴う小雨", 389: "雷を伴う大雨",
    392: "雷を伴う小雪", 395: "雷を伴う大雪",
}


class WeatherFetcher:
    """Fetches and caches weather data from wttr.in."""

    def __init__(
        self,
        location: str = DEFAULT_LOCATION,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self._location = location
        self._session = session
        self._cache: Optional[dict] = None
        self._cache_time: float = 0

    async def get_summary(self) -> Optional[str]:
        """Return weather summary for LLM context.  None on total failure."""
        now = time.time()
        if self._cache and now - self._cache_time < CACHE_TTL:
            return self._format(self._cache)

        data = await self._fetch()
        if data:
            self._cache = data
            self._cache_time = now
            return self._format(data)

        # Stale cache better than nothing
        if self._cache:
            return self._format(self._cache)
        return None

    async def _fetch(self) -> Optional[dict]:
        url = f"https://wttr.in/{self._location}?format=j1&lang=ja"
        try:
            session = self._session or aiohttp.ClientSession()
            own_session = self._session is None
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        logger.warning("Weather fetch HTTP %d", resp.status)
                        return None
                    return await resp.json(content_type=None)
            finally:
                if own_session:
                    await session.close()
        except Exception as e:
            logger.warning("Weather fetch error: %s", e)
            return None

    @staticmethod
    def _desc_ja(entry: dict) -> str:
        """Resolve Japanese weather description from weatherCode or fallback."""
        code = int(entry.get("weatherCode", 0))
        if code in _WEATHER_JA:
            return _WEATHER_JA[code]
        return entry.get("weatherDesc", [{}])[0].get("value", "不明")

    def _format(self, data: dict) -> str:
        try:
            cur = data["current_condition"][0]
            temp = cur.get("temp_C", "?")
            feels = cur.get("FeelsLikeC", "?")
            humidity = cur.get("humidity", "?")
            desc = self._desc_ja(cur)

            today = data.get("weather", [{}])[0]
            max_t = today.get("maxtempC", "?")
            min_t = today.get("mintempC", "?")

            # Afternoon outlook
            hourly = today.get("hourly", [])
            afternoon = ""
            if len(hourly) > 4:
                pm_desc = self._desc_ja(hourly[4])
                if pm_desc:
                    afternoon = f", 午後: {pm_desc}"

            lines = [
                f"場所: {self._location}",
                f"現在: {desc} {temp}°C (体感{feels}°C), 湿度{humidity}%",
                f"今日: 最高{max_t}°C / 最低{min_t}°C{afternoon}",
            ]

            # Tomorrow
            weather_days = data.get("weather", [])
            if len(weather_days) > 1:
                tom = weather_days[1]
                tom_h = tom.get("hourly", [])
                tom_desc = self._desc_ja(tom_h[4]) if len(tom_h) > 4 else ""
                lines.append(
                    f"明日: {tom_desc} 最高{tom.get('maxtempC', '?')}°C"
                    f" / 最低{tom.get('mintempC', '?')}°C"
                )

            return "\n".join(lines)
        except (KeyError, IndexError) as e:
            logger.warning("Weather format error: %s", e)
            return f"{self._location}: データ取得済み (解析エラー)"
