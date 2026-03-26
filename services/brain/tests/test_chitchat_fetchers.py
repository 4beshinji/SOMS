"""Tests for chitchat weather and news fetchers."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from chitchat.weather import WeatherFetcher, _WEATHER_JA
from chitchat.news import NewsFetcher


# ── Weather ──────────────────────────────────────────────────────────

SAMPLE_WEATHER = {
    "current_condition": [{
        "temp_C": "22",
        "FeelsLikeC": "20",
        "humidity": "55",
        "weatherCode": "116",
        "weatherDesc": [{"value": "Partly cloudy"}],
    }],
    "weather": [
        {
            "maxtempC": "28",
            "mintempC": "15",
            "hourly": [
                {}, {}, {}, {},
                {"weatherCode": "113", "weatherDesc": [{"value": "Sunny"}]},
            ],
        },
        {
            "maxtempC": "30",
            "mintempC": "18",
            "hourly": [
                {}, {}, {}, {},
                {"weatherCode": "176", "weatherDesc": [{"value": "Patchy rain nearby"}]},
            ],
        },
    ],
}


class TestWeatherFetcher:
    def test_desc_ja_known_code(self):
        assert WeatherFetcher._desc_ja({"weatherCode": "113"}) == "晴れ"
        assert WeatherFetcher._desc_ja({"weatherCode": "176"}) == "小雨"
        assert WeatherFetcher._desc_ja({"weatherCode": "200"}) == "雷雨の可能性"

    def test_desc_ja_unknown_code_fallback(self):
        entry = {"weatherCode": "9999", "weatherDesc": [{"value": "Alien rain"}]}
        assert WeatherFetcher._desc_ja(entry) == "Alien rain"

    def test_format_full(self):
        f = WeatherFetcher("Maebashi")
        result = f._format(SAMPLE_WEATHER)
        assert "Maebashi" in result
        assert "晴れ時々曇り" in result  # code 116
        assert "22°C" in result
        assert "体感20°C" in result
        assert "湿度55%" in result
        assert "最高28°C" in result
        assert "午後: 晴れ" in result
        assert "明日:" in result
        assert "小雨" in result  # code 176

    @pytest.mark.asyncio
    async def test_get_summary_caches(self):
        f = WeatherFetcher("Maebashi")
        f._cache = SAMPLE_WEATHER
        f._cache_time = 9999999999  # far future
        result = await f.get_summary()
        assert "Maebashi" in result

    @pytest.mark.asyncio
    async def test_get_summary_stale_cache_on_failure(self):
        f = WeatherFetcher("Maebashi")
        f._cache = SAMPLE_WEATHER
        f._cache_time = 0  # expired
        with patch.object(f, "_fetch", return_value=None):
            result = await f.get_summary()
        assert result is not None
        assert "Maebashi" in result

    @pytest.mark.asyncio
    async def test_get_summary_none_on_total_failure(self):
        f = WeatherFetcher("Maebashi")
        with patch.object(f, "_fetch", return_value=None):
            result = await f.get_summary()
        assert result is None


# ── News ─────────────────────────────────────────────────────────────

SAMPLE_STORIES = [
    {"title": "Show HN: My Cool Project", "score": 100, "url": "https://example.com"},
    {"title": "Rust is Awesome", "score": 250, "url": "https://rust.org"},
]


class TestNewsFetcher:
    def test_format(self):
        f = NewsFetcher()
        result = f._format(SAMPLE_STORIES)
        assert "Hacker News" in result
        assert "Show HN: My Cool Project" in result
        assert "100pts" in result
        assert "Rust is Awesome" in result

    def test_format_empty(self):
        f = NewsFetcher()
        assert "取得できません" in f._format([])

    @pytest.mark.asyncio
    async def test_get_summary_caches(self):
        f = NewsFetcher()
        f._cache = SAMPLE_STORIES
        f._cache_time = 9999999999
        result = await f.get_summary()
        assert "Hacker News" in result

    @pytest.mark.asyncio
    async def test_get_summary_stale_cache_on_failure(self):
        f = NewsFetcher()
        f._cache = SAMPLE_STORIES
        f._cache_time = 0
        with patch.object(f, "_fetch", return_value=None):
            result = await f.get_summary()
        assert "Hacker News" in result

    @pytest.mark.asyncio
    async def test_get_summary_none_on_total_failure(self):
        f = NewsFetcher()
        with patch.object(f, "_fetch", return_value=None):
            result = await f.get_summary()
        assert result is None
