"""
LLM-based report generator for SOMS.

Generates daily, weekly, and monthly usage reports by querying
historical sensor data from PostgreSQL and feeding it to the LLM
via OpenAI-compatible API (works with llama.cpp / Ollama / vLLM).

Reports are stored in events.reports table as structured JSONB
content plus rendered markdown.
"""
import json
import os
import time
import logging
from datetime import datetime, timedelta, timezone

import aiohttp
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from spatial_config import SpatialConfig

logger = logging.getLogger(__name__)

REPORT_GENERATION_TIMEOUT = int(os.getenv("REPORT_GENERATION_TIMEOUT", "600"))
REPORT_MAX_TOKENS_DAILY = int(os.getenv("REPORT_MAX_TOKENS_DAILY", "8192"))
REPORT_MAX_TOKENS_WEEKLY = int(os.getenv("REPORT_MAX_TOKENS_WEEKLY", "12288"))
REPORT_MAX_TOKENS_MONTHLY = int(os.getenv("REPORT_MAX_TOKENS_MONTHLY", "16384"))
REPORT_TEMPERATURE = float(os.getenv("REPORT_TEMPERATURE", "0.2"))
TZ = timezone(timedelta(hours=9))  # Asia/Tokyo


class ReportGenerator:
    """Generates usage reports using a large LLM model."""

    def __init__(
        self,
        engine: AsyncEngine,
        ollama_base_url: str,
        report_model: str,
        spatial_config: SpatialConfig,
        session: aiohttp.ClientSession,
    ):
        self._engine = engine
        # Derive OpenAI-compatible endpoint from base URL
        base = ollama_base_url.rstrip("/")
        self._api_url = base if base.endswith("/v1") else f"{base}/v1"
        self._report_model = report_model
        self._spatial = spatial_config
        self._session = session
        self._generating = False
        self._cancel_requested = False

    @property
    def is_generating(self) -> bool:
        return self._generating

    async def cancel(self):
        """Request cancellation of ongoing report generation."""
        if self._generating:
            self._cancel_requested = True
            logger.info("[ReportGenerator] キャンセル要求")

    # ------------------------------------------------------------------
    # Public: generate reports
    # ------------------------------------------------------------------

    async def generate_daily_report(self, date: datetime) -> dict | None:
        """Generate a daily report for the given date.

        Args:
            date: The date to report on (timezone-aware, Asia/Tokyo).

        Returns:
            The stored report dict, or None on failure/cancellation.
        """
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return await self._generate_report("daily", start, end, REPORT_MAX_TOKENS_DAILY)

    async def generate_weekly_report(self, week_start: datetime) -> dict | None:
        """Generate a weekly report starting from week_start (Monday)."""
        start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        return await self._generate_report("weekly", start, end, REPORT_MAX_TOKENS_WEEKLY)

    async def generate_monthly_report(self, year: int, month: int) -> dict | None:
        """Generate a monthly report for the given year/month."""
        start = datetime(year, month, 1, tzinfo=TZ)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=TZ)
        else:
            end = datetime(year, month + 1, 1, tzinfo=TZ)
        return await self._generate_report("monthly", start, end, REPORT_MAX_TOKENS_MONTHLY)

    # ------------------------------------------------------------------
    # Core generation pipeline
    # ------------------------------------------------------------------

    async def _generate_report(
        self, report_type: str, start: datetime, end: datetime, max_tokens: int,
    ) -> dict | None:
        self._generating = True
        self._cancel_requested = False
        gen_start = time.time()

        try:
            logger.info(
                "[ReportGenerator] %sレポート生成開始: %s ~ %s",
                report_type, start.isoformat(), end.isoformat(),
            )

            # Step 1: Query historical data
            period_data = await self._query_period_data(start, end)
            if self._cancel_requested:
                logger.info("[ReportGenerator] キャンセル: データクエリ後")
                return None

            # Step 2: Build sensor context
            sensor_context = self._build_sensor_context()

            # Step 3: Build prompt
            messages = self._build_report_prompt(
                report_type, period_data, sensor_context, start, end,
            )
            if self._cancel_requested:
                logger.info("[ReportGenerator] キャンセル: プロンプト構築後")
                return None

            # Step 4: Call LLM
            raw_text = await self._call_llm(messages, max_tokens)
            if raw_text is None or self._cancel_requested:
                logger.warning("[ReportGenerator] LLM呼出失敗またはキャンセル")
                return None

            # Step 5: Parse and store
            gen_time = time.time() - gen_start
            content = self._parse_report_sections(raw_text)
            summary = content.get("executive_summary", raw_text[:200])

            report = await self._store_report(
                report_type=report_type,
                period_start=start,
                period_end=end,
                content=content,
                raw_markdown=raw_text,
                summary=summary,
                generation_time=gen_time,
            )

            logger.info(
                "[ReportGenerator] %sレポート生成完了: %.1f秒, %d文字",
                report_type, gen_time, len(raw_text),
            )
            return report

        except Exception as e:
            logger.error("[ReportGenerator] レポート生成エラー: %s", e)
            return None
        finally:
            self._generating = False
            self._cancel_requested = False

    # ------------------------------------------------------------------
    # Data query
    # ------------------------------------------------------------------

    async def _query_period_data(self, start: datetime, end: datetime) -> dict:
        """Query all relevant data for the report period."""
        data: dict = {
            "hourly_stats": [],
            "llm_activity": {},
            "occupancy_heatmap": [],
            "events": [],
        }

        async with self._engine.begin() as conn:
            # Hourly aggregates (sensor stats per zone)
            rows = await conn.execute(
                text("""
                    SELECT period_start, zones, tasks_created, llm_cycles, device_health
                    FROM events.hourly_aggregates
                    WHERE period_start >= :start AND period_start < :end
                    ORDER BY period_start
                """),
                {"start": start, "end": end},
            )
            for row in rows:
                zones = row[1] if isinstance(row[1], dict) else json.loads(row[1]) if row[1] else {}
                dh = row[4] if isinstance(row[4], dict) else json.loads(row[4]) if row[4] else {}
                data["hourly_stats"].append({
                    "hour": row[0].isoformat() if row[0] else None,
                    "zones": zones,
                    "tasks_created": row[2],
                    "llm_cycles": row[3],
                    "total_tool_calls": dh.get("total_tool_calls", 0),
                })

            # LLM decision summary
            llm_row = await conn.execute(
                text("""
                    SELECT COUNT(*) AS cycles,
                           COALESCE(SUM(total_tool_calls), 0) AS tool_calls,
                           COALESCE(AVG(cycle_duration_sec), 0) AS avg_duration
                    FROM events.llm_decisions
                    WHERE timestamp >= :start AND timestamp < :end
                """),
                {"start": start, "end": end},
            )
            lr = llm_row.fetchone()
            data["llm_activity"] = {
                "total_cycles": lr[0] if lr else 0,
                "total_tool_calls": lr[1] if lr else 0,
                "avg_cycle_duration_sec": round(lr[2], 2) if lr else 0,
            }

            # Spatial heatmap (occupancy)
            heatmap_rows = await conn.execute(
                text("""
                    SELECT zone, period_start, person_count_avg
                    FROM events.spatial_heatmap_hourly
                    WHERE period_start >= :start AND period_start < :end
                    ORDER BY period_start
                """),
                {"start": start, "end": end},
            )
            for row in heatmap_rows:
                data["occupancy_heatmap"].append({
                    "zone": row[0],
                    "hour": row[1].isoformat() if row[1] else None,
                    "person_count_avg": round(row[2], 2) if row[2] else 0,
                })

            # Notable events (world_model_* events)
            event_rows = await conn.execute(
                text("""
                    SELECT timestamp, zone, event_type, data
                    FROM events.raw_events
                    WHERE timestamp >= :start AND timestamp < :end
                      AND event_type LIKE 'world_model_%%'
                    ORDER BY timestamp
                    LIMIT 500
                """),
                {"start": start, "end": end},
            )
            for row in event_rows:
                ev_data = row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {}
                data["events"].append({
                    "time": row[0].isoformat() if row[0] else None,
                    "zone": row[1],
                    "type": row[2],
                    "severity": ev_data.get("severity", "info"),
                })

        return data

    # ------------------------------------------------------------------
    # Sensor context
    # ------------------------------------------------------------------

    def _build_sensor_context(self) -> str:
        """Build sensor context section from spatial config."""
        lines = []

        # Zone descriptions
        lines.append("### ゾーン一覧")
        for zone_id, zone in self._spatial.zones.items():
            lines.append(f"- **{zone.display_name}** ({zone_id}): {zone.area_m2}m², "
                         f"フロア{zone.floor}")

        lines.append("")
        lines.append("### センサー配置")
        for dev_id, dev in self._spatial.devices.items():
            zone_name = dev_id
            if dev.zone in self._spatial.zones:
                zone_name = self._spatial.zones[dev.zone].display_name

            line = f"- **{dev.label or dev_id}** ({dev_id}): {zone_name}, "
            line += f"チャネル: {', '.join(dev.channels)}"
            if dev.context:
                line += f"\n  コンテキスト: {dev.context}"
            lines.append(line)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_report_prompt(
        self,
        report_type: str,
        period_data: dict,
        sensor_context: str,
        start: datetime,
        end: datetime,
    ) -> list[dict]:
        """Build the LLM messages for report generation."""
        type_label = {"daily": "日次", "weekly": "週次", "monthly": "月次"}[report_type]
        period_str = f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}"

        system_msg = f"""あなたはオフィス環境分析AIアナリストです。
センサーデータと活動ログを分析し、構造化された{type_label}レポートを日本語で作成してください。

## レポート構成（以下のセクションヘッダーを必ず使用）

### 1. エグゼクティブサマリー
3-5文で全体概要を記述。

### 2. 環境分析
温度・湿度・CO2のトレンド、快適性評価、異常検知。
ゾーンごとの特徴と時間帯による変化パターン。

### 3. 在室・利用分析
ゾーン別利用率、ピーク時間帯、未活用スペースの特定。
人の動きのパターン。

### 4. AI行動履歴
認知サイクル数、ツール実行回数、タスク作成/完了の統計。
AIがどのような判断を行ったか。

### 5. 異常・注意事項
環境異常（CO2スパイク、温度異常等）の詳細。
センサー欠損やデータ品質の問題。

### 6. 改善提案
環境改善の具体的提案。
空間活用の最適化案。

## 注意事項
- 数値は必ずデータに基づいて記述すること
- 推測する場合は「推測」と明記
- ゾーン名は日本語表示名を使用"""

        # Format period data for the prompt
        data_summary = self._format_period_data(period_data, report_type)

        user_msg = f"""## レポート対象期間
{period_str}

## センサー配置コンテキスト
{sensor_context}

## 分析データ
{data_summary}

上記のデータを分析し、{type_label}レポートを作成してください。"""

        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

    def _format_period_data(self, data: dict, report_type: str) -> str:
        """Format period data into a prompt-friendly string."""
        lines = []

        # Hourly stats summary
        hourly = data.get("hourly_stats", [])
        if hourly:
            lines.append("### 時間帯別環境データ")

            # Group by zone, show key channels
            zone_hours: dict[str, list] = {}
            for h in hourly:
                for zone_id, stats in h["zones"].items():
                    if zone_id not in zone_hours:
                        zone_hours[zone_id] = []
                    zone_hours[zone_id].append({
                        "hour": h["hour"],
                        **stats,
                    })

            for zone_id, hours in zone_hours.items():
                zone_name = zone_id
                if zone_id in self._spatial.zones:
                    zone_name = self._spatial.zones[zone_id].display_name
                lines.append(f"\n#### {zone_name}")

                # Summarize key metrics
                temps = [h.get("avg_temperature") for h in hours
                         if h.get("avg_temperature") is not None]
                humids = [h.get("avg_humidity") for h in hours
                          if h.get("avg_humidity") is not None]
                co2s = [h.get("avg_co2") for h in hours
                        if h.get("avg_co2") is not None]

                if temps:
                    lines.append(f"  温度: 平均{sum(temps)/len(temps):.1f}℃ "
                                 f"(最低{min(temps):.1f}, 最高{max(temps):.1f})")
                if humids:
                    lines.append(f"  湿度: 平均{sum(humids)/len(humids):.0f}% "
                                 f"(最低{min(humids):.0f}, 最高{max(humids):.0f})")
                if co2s:
                    lines.append(f"  CO2: 平均{sum(co2s)/len(co2s):.0f}ppm "
                                 f"(最低{min(co2s):.0f}, 最高{max(co2s):.0f})")

                # For daily: show hourly breakdown
                if report_type == "daily" and len(hours) <= 24:
                    lines.append("  時間帯別:")
                    for h in hours:
                        hour_str = h["hour"][:13] if h.get("hour") else "?"
                        parts = []
                        if h.get("avg_temperature") is not None:
                            parts.append(f"{h['avg_temperature']:.1f}℃")
                        if h.get("avg_humidity") is not None:
                            parts.append(f"{h['avg_humidity']:.0f}%")
                        if h.get("avg_co2") is not None:
                            parts.append(f"CO2 {h['avg_co2']:.0f}")
                        if parts:
                            lines.append(f"    {hour_str}: {', '.join(parts)}")

        # LLM activity
        llm = data.get("llm_activity", {})
        if llm.get("total_cycles", 0) > 0:
            lines.append(f"\n### AI活動統計")
            lines.append(f"  認知サイクル数: {llm['total_cycles']}")
            lines.append(f"  ツール実行数: {llm['total_tool_calls']}")
            lines.append(f"  平均サイクル時間: {llm['avg_cycle_duration_sec']:.1f}秒")

        # Task statistics from hourly data
        total_tasks = sum(h.get("tasks_created", 0) for h in hourly)
        if total_tasks > 0:
            lines.append(f"  タスク作成数: {total_tasks}")

        # Occupancy summary
        occ = data.get("occupancy_heatmap", [])
        if occ:
            lines.append("\n### 在室データ")
            zone_occ: dict[str, list[float]] = {}
            for o in occ:
                z = o["zone"]
                if z not in zone_occ:
                    zone_occ[z] = []
                zone_occ[z].append(o["person_count_avg"])

            for zone_id, counts in zone_occ.items():
                zone_name = zone_id
                if zone_id in self._spatial.zones:
                    zone_name = self._spatial.zones[zone_id].display_name
                avg_occ = sum(counts) / len(counts) if counts else 0
                max_occ = max(counts) if counts else 0
                occupied_hours = sum(1 for c in counts if c > 0.1)
                lines.append(
                    f"  {zone_name}: 平均{avg_occ:.1f}人, "
                    f"最大{max_occ:.1f}人, 利用時間{occupied_hours}h"
                )

        # Notable events
        events = data.get("events", [])
        if events:
            lines.append(f"\n### 注目イベント ({len(events)}件)")
            # Group by type
            type_counts: dict[str, int] = {}
            for ev in events:
                t = ev["type"].replace("world_model_", "")
                type_counts[t] = type_counts.get(t, 0) + 1
            for t, count in sorted(type_counts.items(), key=lambda x: -x[1])[:10]:
                lines.append(f"  {t}: {count}件")

        return "\n".join(lines) if lines else "データなし"

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    async def _call_llm(self, messages: list[dict], max_tokens: int) -> str | None:
        """Call the report LLM via OpenAI-compatible /v1/chat/completions."""
        try:
            payload = {
                "model": self._report_model,
                "messages": messages,
                "temperature": REPORT_TEMPERATURE,
                "max_tokens": max_tokens,
            }

            async with self._session.post(
                f"{self._api_url}/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=REPORT_GENERATION_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(
                        "[ReportGenerator] LLM呼出失敗: %d %s", resp.status, body[:300],
                    )
                    return None

                result = await resp.json()
                content = (
                    result.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )

                # Strip thinking blocks (Qwen3.5 may include <think>...</think>)
                import re
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

                return content if content else None

        except TimeoutError:
            logger.error("[ReportGenerator] LLMタイムアウト (%ds)", REPORT_GENERATION_TIMEOUT)
            return None
        except Exception as e:
            logger.error("[ReportGenerator] LLM呼出エラー: %s", e)
            return None

    # ------------------------------------------------------------------
    # Report parsing
    # ------------------------------------------------------------------

    def _parse_report_sections(self, raw_text: str) -> dict:
        """Parse raw markdown report into structured sections.

        Splits on ### headings and maps to known section keys.
        """
        sections: dict[str, str] = {}
        current_key = "preamble"
        current_lines: list[str] = []

        section_map = {
            "エグゼクティブサマリー": "executive_summary",
            "環境分析": "environment_analysis",
            "在室・利用分析": "occupancy_analysis",
            "在室": "occupancy_analysis",
            "利用分析": "occupancy_analysis",
            "ai行動履歴": "ai_activity",
            "行動履歴": "ai_activity",
            "異常・注意事項": "anomalies",
            "異常": "anomalies",
            "注意事項": "anomalies",
            "改善提案": "recommendations",
            "提案": "recommendations",
        }

        for line in raw_text.split("\n"):
            stripped = line.strip().lower()
            if stripped.startswith("###") or stripped.startswith("## "):
                # Save previous section
                if current_lines:
                    text = "\n".join(current_lines).strip()
                    if text:
                        sections[current_key] = text

                # Determine new section key
                heading = stripped.lstrip("#").strip()
                # Remove numbering like "1. " or "1."
                import re
                heading = re.sub(r"^\d+\.?\s*", "", heading)

                current_key = "other"
                for pattern, key in section_map.items():
                    if pattern in heading:
                        current_key = key
                        break
                current_lines = []
            else:
                current_lines.append(line)

        # Save last section
        if current_lines:
            text = "\n".join(current_lines).strip()
            if text:
                sections[current_key] = text

        # Use first section as executive_summary if not found
        if "executive_summary" not in sections and "preamble" in sections:
            sections["executive_summary"] = sections.pop("preamble")

        return sections

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    async def _store_report(
        self,
        report_type: str,
        period_start: datetime,
        period_end: datetime,
        content: dict,
        raw_markdown: str,
        summary: str,
        generation_time: float,
    ) -> dict:
        """Store generated report in events.reports table."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("""
                    INSERT INTO events.reports
                        (report_type, period_start, period_end, model_used,
                         generation_time_sec, status, content, raw_markdown, summary)
                    VALUES
                        (:report_type, :period_start, :period_end, :model_used,
                         :generation_time_sec, 'completed',
                         CAST(:content AS jsonb), :raw_markdown, :summary)
                    ON CONFLICT (report_type, period_start) DO UPDATE SET
                        period_end = EXCLUDED.period_end,
                        model_used = EXCLUDED.model_used,
                        generation_time_sec = EXCLUDED.generation_time_sec,
                        status = EXCLUDED.status,
                        content = EXCLUDED.content,
                        raw_markdown = EXCLUDED.raw_markdown,
                        summary = EXCLUDED.summary,
                        generated_at = now()
                    RETURNING id, generated_at
                """),
                {
                    "report_type": report_type,
                    "period_start": period_start,
                    "period_end": period_end,
                    "model_used": self._report_model,
                    "generation_time_sec": round(generation_time, 2),
                    "content": json.dumps(content, ensure_ascii=False),
                    "raw_markdown": raw_markdown,
                    "summary": summary[:500] if summary else None,
                },
            )
            row = result.fetchone()

        return {
            "id": row[0],
            "report_type": report_type,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "generated_at": row[1].isoformat() if row[1] else None,
            "generation_time_sec": round(generation_time, 2),
            "status": "completed",
        }

    # ------------------------------------------------------------------
    # Utility: check if report already exists
    # ------------------------------------------------------------------

    async def report_exists(self, report_type: str, period_start: datetime) -> bool:
        """Check if a report already exists for the given type and period."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("""
                    SELECT 1 FROM events.reports
                    WHERE report_type = :report_type
                      AND period_start = :period_start
                      AND status = 'completed'
                    LIMIT 1
                """),
                {"report_type": report_type, "period_start": period_start},
            )
            return result.fetchone() is not None
