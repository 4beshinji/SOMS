"""
Activity mode manager for SOMS Brain.

Reduces cognitive loop frequency and LLM API usage when the office
is unoccupied, freeing GPU VRAM for report generation or other
batch tasks.

Modes:
  normal   — 30s cycle, full LLM + rules
  inactive — 5min cycle, rule-based only (VRAM available for reports)

LLM escalation policy in inactive mode:
  - Critical rules  → execute immediately, no LLM needed
  - Normal rules    → if anything fires AND LLM budget allows, escalate to LLM
                      if LLM is on cooldown, execute rule actions directly
  - Nothing fires   → skip LLM entirely

Transitions:
  normal   → inactive : all zones person_count=0 for INACTIVE_CONFIRM_SECONDS
  inactive → normal   : any zone person_count > 0
"""
import os
import time
import logging

logger = logging.getLogger(__name__)

INACTIVE_CYCLE_INTERVAL = int(os.getenv("INACTIVE_CYCLE_INTERVAL", "300"))       # 5 min
INACTIVE_MIN_CYCLE_INTERVAL = int(os.getenv("INACTIVE_MIN_CYCLE_INTERVAL", "60"))  # 1 min
INACTIVE_LLM_COOLDOWN = int(os.getenv("INACTIVE_LLM_COOLDOWN", "1800"))           # 30 min
INACTIVE_CONFIRM_SECONDS = int(os.getenv("INACTIVE_CONFIRM_SECONDS", "300"))       # 5 min


class ActivityMode:
    NORMAL = "normal"
    INACTIVE = "inactive"


class ActivityModeManager:
    """Tracks and transitions the office activity mode based on occupancy.

    Instantiate once in Brain.__init__ and call evaluate() at the start of
    each cognitive cycle.

    LLM call policy (inactive mode only):
      allow_llm_call()  — True if enough time since last LLM call
      record_llm_call() — update timestamp after deciding to call LLM
    """

    def __init__(self):
        self._mode: str = ActivityMode.NORMAL
        self._reason: str = ""
        self._entered_at: float = 0.0
        self._empty_since: float | None = None
        self._last_llm_call: float = 0.0

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_inactive(self) -> bool:
        return self._mode == ActivityMode.INACTIVE

    @property
    def cycle_interval(self) -> int:
        """Maximum seconds to wait for an MQTT event before forcing a cycle."""
        if self._mode == ActivityMode.INACTIVE:
            return INACTIVE_CYCLE_INTERVAL
        return 30

    @property
    def min_cycle_interval(self) -> int:
        """Minimum seconds between successive cognitive cycles."""
        if self._mode == ActivityMode.INACTIVE:
            return INACTIVE_MIN_CYCLE_INTERVAL
        return 25

    # ------------------------------------------------------------------
    # LLM call throttling
    # ------------------------------------------------------------------

    def allow_llm_call(self, now: float | None = None) -> bool:
        """Return True if an LLM call is permitted under the current rate limit.

        In normal mode this always returns True.
        In inactive mode the call is allowed only if at least
        INACTIVE_LLM_COOLDOWN seconds have elapsed since the last call.
        """
        if not self.is_inactive:
            return True
        return (now or time.time()) - self._last_llm_call >= INACTIVE_LLM_COOLDOWN

    def record_llm_call(self, now: float | None = None):
        """Record that an LLM call is being made now."""
        self._last_llm_call = now or time.time()

    def seconds_until_llm_allowed(self, now: float | None = None) -> int:
        """Return seconds remaining until next LLM call is allowed (0 if now)."""
        remaining = INACTIVE_LLM_COOLDOWN - ((now or time.time()) - self._last_llm_call)
        return max(0, int(remaining))

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    def evaluate(self, world_model) -> bool:
        """Check occupancy state and transition mode if needed.

        Should be called at the start of each cognitive cycle.
        Returns True if the mode changed this call.
        """
        now = time.time()

        # --- Exit condition: someone appeared ---
        if self._mode == ActivityMode.INACTIVE:
            for zone in world_model.zones.values():
                if zone.occupancy.person_count > 0:
                    return self._transition(
                        ActivityMode.NORMAL, "在室検出（復帰）", now
                    )
            return False

        # --- Entry condition: all zones empty ---
        if world_model.zones:
            all_empty = all(
                z.occupancy.person_count == 0 for z in world_model.zones.values()
            )
            any_fresh = any(
                z.last_update > 0 for z in world_model.zones.values()
            )
            if all_empty and any_fresh:
                if self._empty_since is None:
                    self._empty_since = now
                    logger.debug(
                        "[ActivityMode] 全ゾーン無人を検出 — %d秒後にINACTIVEへ移行",
                        INACTIVE_CONFIRM_SECONDS,
                    )
                elif now - self._empty_since >= INACTIVE_CONFIRM_SECONDS:
                    return self._transition(
                        ActivityMode.INACTIVE, "全ゾーン無人（確認済）", now
                    )
            else:
                if self._empty_since is not None:
                    logger.debug("[ActivityMode] 在室確認 — INACTIVE移行キャンセル")
                self._empty_since = None

        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _transition(self, new_mode: str, reason: str, now: float) -> bool:
        if new_mode == self._mode:
            return False
        logger.info(
            "[ActivityMode] モード変更: %s → %s (%s)",
            self._mode, new_mode, reason,
        )
        self._mode = new_mode
        self._reason = reason
        self._entered_at = now
        if new_mode == ActivityMode.NORMAL:
            self._empty_since = None
        return True

    def get_status(self) -> dict:
        """Return current activity mode status (for logging/dashboard)."""
        return {
            "mode": self._mode,
            "reason": self._reason,
            "entered_at": self._entered_at,
            "cycle_interval_sec": self.cycle_interval,
            "llm_cooldown_remaining_sec": self.seconds_until_llm_allowed(),
        }
