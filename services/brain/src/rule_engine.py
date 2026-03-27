"""
Rule-based fallback engine for SOMS Brain.

Used when GPU load is high, LLM is unavailable, or office is in
inactive mode. Evaluates simple threshold rules and returns tool
call actions that can be executed without LLM involvement.
"""
import os
import subprocess
import time
import logging

logger = logging.getLogger(__name__)

# Environment thresholds (matching system_prompt.py constants)
CO2_HIGH = float(os.getenv("THRESHOLD_CO2_HIGH", "1000"))
CO2_CRITICAL = float(os.getenv("THRESHOLD_CO2_CRITICAL", "1500"))
TEMP_HIGH = float(os.getenv("THRESHOLD_TEMP_HIGH", "26"))
TEMP_LOW = float(os.getenv("THRESHOLD_TEMP_LOW", "18"))
TEMP_CRITICAL_HIGH = float(os.getenv("THRESHOLD_TEMP_CRITICAL_HIGH", "35"))
TEMP_CRITICAL_LOW = float(os.getenv("THRESHOLD_TEMP_CRITICAL_LOW", "10"))
HUMIDITY_HIGH = float(os.getenv("THRESHOLD_HUMIDITY_HIGH", "60"))
HUMIDITY_LOW = float(os.getenv("THRESHOLD_HUMIDITY_LOW", "30"))

GPU_TYPE = os.getenv("GPU_TYPE", "none")  # amd | nvidia | none
GPU_HIGH_LOAD_THRESHOLD = int(os.getenv("GPU_HIGH_LOAD_THRESHOLD", "80"))


def _get_gpu_utilization() -> float | None:
    """Query GPU utilization percentage. Returns None if unavailable."""
    try:
        if GPU_TYPE == "nvidia":
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                timeout=5, text=True,
            )
            return float(out.strip().split("\n")[0])
        elif GPU_TYPE == "amd":
            out = subprocess.check_output(
                ["rocm-smi", "--showuse", "--csv"],
                timeout=5, text=True,
            )
            for line in out.strip().split("\n"):
                if "," in line and not line.startswith("device"):
                    parts = line.split(",")
                    if len(parts) >= 2:
                        try:
                            return float(parts[1].strip().replace("%", ""))
                        except ValueError:
                            pass
    except (FileNotFoundError, subprocess.TimeoutExpired,
            subprocess.CalledProcessError, ValueError) as e:
        logger.debug("GPU query failed: %s", e)
    return None


class RuleEngine:
    """Threshold-based decision engine — no LLM required.

    Returns lists of action dicts: {"tool": str, "args": dict}
    that can be fed directly to ToolExecutor.execute().
    """

    COOLDOWN_SECONDS = 300  # 5 minutes

    def __init__(self):
        self._cooldowns: dict[str, float] = {}

    def should_use_rules(self) -> bool:
        """Check if we should use rule-based mode instead of LLM.

        Returns True when GPU utilization exceeds threshold.
        """
        if GPU_TYPE == "none":
            return False
        util = _get_gpu_utilization()
        if util is not None and util > GPU_HIGH_LOAD_THRESHOLD:
            logger.info("[RuleEngine] GPU負荷 %.0f%% > %d%% — ルールベースモード",
                        util, GPU_HIGH_LOAD_THRESHOLD)
            return True
        return False

    def evaluate_critical(self, world_model) -> list[dict]:
        """Safety-critical rules that always execute regardless of mode.

        These handle situations requiring immediate response even
        without LLM involvement.
        """
        actions = []
        now = time.time()

        for zone_id, zone in world_model.zones.items():
            zone_name = zone.metadata.display_name or zone_id
            env = zone.environment

            # Fall detection — check recent events
            for event in zone.events[-10:]:
                if (event.get("type") == "world_model_fall_detected"
                        and event.get("timestamp", 0) > now - 60):
                    key = f"fall_{zone_id}"
                    if self._check_cooldown(key, now):
                        actions.append({
                            "tool": "create_task",
                            "args": {
                                "title": f"転倒検知: {zone_name}で転倒の可能性",
                                "description": f"{zone_name}で転倒が検知されました。速やかに確認してください。",
                                "bounty": 5000,
                                "urgency": 4,
                                "zone": zone_id,
                            },
                        })

            # Critical CO2
            if env.co2 is not None and env.co2 > CO2_CRITICAL:
                key = f"co2_critical_{zone_id}"
                if self._check_cooldown(key, now):
                    actions.append({
                        "tool": "create_task",
                        "args": {
                            "title": f"CO2危険: {zone_name} ({env.co2:.0f}ppm)",
                            "description": f"{zone_name}のCO2濃度が{env.co2:.0f}ppmで危険水準です。直ちに換気してください。",
                            "bounty": 3000,
                            "urgency": 3,
                            "zone": zone_id,
                        },
                    })

            # Critical temperature
            if env.temperature is not None:
                if env.temperature > TEMP_CRITICAL_HIGH:
                    key = f"temp_critical_high_{zone_id}"
                    if self._check_cooldown(key, now):
                        actions.append({
                            "tool": "create_task",
                            "args": {
                                "title": f"高温警報: {zone_name} ({env.temperature:.1f}℃)",
                                "description": f"{zone_name}の温度が{env.temperature:.1f}℃で危険です。冷房を確認してください。",
                                "bounty": 3000,
                                "urgency": 3,
                                "zone": zone_id,
                            },
                        })
                elif env.temperature < TEMP_CRITICAL_LOW:
                    key = f"temp_critical_low_{zone_id}"
                    if self._check_cooldown(key, now):
                        actions.append({
                            "tool": "create_task",
                            "args": {
                                "title": f"低温警報: {zone_name} ({env.temperature:.1f}℃)",
                                "description": f"{zone_name}の温度が{env.temperature:.1f}℃で危険です。暖房を確認してください。",
                                "bounty": 3000,
                                "urgency": 3,
                                "zone": zone_id,
                            },
                        })

            # Water leak
            extra = zone.extra_sensors
            if extra.get("water_leak", 0) > 0:
                key = f"water_leak_{zone_id}"
                if self._check_cooldown(key, now):
                    actions.append({
                        "tool": "create_task",
                        "args": {
                            "title": f"漏水検知: {zone_name}",
                            "description": f"{zone_name}で漏水が検知されました。速やかに確認してください。",
                            "bounty": 5000,
                            "urgency": 4,
                            "zone": zone_id,
                        },
                    })

        return actions

    def evaluate(self, world_model) -> list[dict]:
        """Normal threshold rules (with cooldown).

        Returns actions for non-critical but noteworthy conditions.
        """
        actions = []
        now = time.time()

        for zone_id, zone in world_model.zones.items():
            zone_name = zone.metadata.display_name or zone_id
            env = zone.environment

            # High CO2 (non-critical)
            if env.co2 is not None and CO2_HIGH < env.co2 <= CO2_CRITICAL:
                key = f"co2_high_{zone_id}"
                if self._check_cooldown(key, now):
                    actions.append({
                        "tool": "create_task",
                        "args": {
                            "title": f"換気推奨: {zone_name} CO2 {env.co2:.0f}ppm",
                            "description": f"{zone_name}のCO2濃度が{env.co2:.0f}ppmです。換気をお願いします。",
                            "bounty": 500,
                            "urgency": 1,
                            "zone": zone_id,
                        },
                    })

            # Temperature out of comfort range (non-critical)
            if env.temperature is not None:
                if TEMP_HIGH < env.temperature <= TEMP_CRITICAL_HIGH:
                    key = f"temp_high_{zone_id}"
                    if self._check_cooldown(key, now):
                        actions.append({
                            "tool": "create_task",
                            "args": {
                                "title": f"室温高め: {zone_name} ({env.temperature:.1f}℃)",
                                "description": f"{zone_name}の温度が{env.temperature:.1f}℃で快適範囲を超えています。",
                                "bounty": 500,
                                "urgency": 1,
                                "zone": zone_id,
                            },
                        })
                elif TEMP_CRITICAL_LOW < env.temperature < TEMP_LOW:
                    key = f"temp_low_{zone_id}"
                    if self._check_cooldown(key, now):
                        actions.append({
                            "tool": "create_task",
                            "args": {
                                "title": f"室温低め: {zone_name} ({env.temperature:.1f}℃)",
                                "description": f"{zone_name}の温度が{env.temperature:.1f}℃で快適範囲を下回っています。",
                                "bounty": 500,
                                "urgency": 1,
                                "zone": zone_id,
                            },
                        })

            # Humidity out of range
            if env.humidity is not None:
                if env.humidity > HUMIDITY_HIGH:
                    key = f"humidity_high_{zone_id}"
                    if self._check_cooldown(key, now):
                        actions.append({
                            "tool": "create_task",
                            "args": {
                                "title": f"湿度高: {zone_name} ({env.humidity:.0f}%)",
                                "description": f"{zone_name}の湿度が{env.humidity:.0f}%です。除湿をお願いします。",
                                "bounty": 500,
                                "urgency": 1,
                                "zone": zone_id,
                            },
                        })
                elif env.humidity < HUMIDITY_LOW:
                    key = f"humidity_low_{zone_id}"
                    if self._check_cooldown(key, now):
                        actions.append({
                            "tool": "create_task",
                            "args": {
                                "title": f"湿度低: {zone_name} ({env.humidity:.0f}%)",
                                "description": f"{zone_name}の湿度が{env.humidity:.0f}%です。加湿をお願いします。",
                                "bounty": 500,
                                "urgency": 1,
                                "zone": zone_id,
                            },
                        })

        return actions

    def _check_cooldown(self, key: str, now: float) -> bool:
        """Return True if the cooldown for this key has expired, and reset it."""
        last = self._cooldowns.get(key, 0)
        if now - last < self.COOLDOWN_SECONDS:
            return False
        self._cooldowns[key] = now
        return True
