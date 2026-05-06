"""
Rate limiter to enforce daily action limits and human-like random delays.
Prevents LinkedIn from detecting automation patterns.

Delay strategy:
  - Uses Gaussian (normal) distribution centered on a mean value.
  - Real human reaction times cluster around a mean, not flat random.
  - Occasionally injects a longer "distraction" pause (reading, thinking).
  - Tracks a velocity budget: if too many actions happen in a short window,
    forces a longer cooldown before continuing.
"""

import time
import random
import logging
from datetime import date, datetime
from collections import deque
from typing import Dict, Any, Deque

logger = logging.getLogger(__name__)

# Map action types to their config keys and DB column names
ACTION_MAP = {
    "like": ("max_likes_per_day", "likes"),
    "comment": ("max_comments_per_day", "comments"),
    "repost": ("max_reposts_per_day", "reposts"),
    "connect": ("max_connections_per_day", "connections"),
    "follow": ("max_follows_per_day", "connections"),
}


class RateLimiter:
    def __init__(self, config: Dict[str, Any], db):
        self.config = config
        self.db = db
        self.limits_cfg = config.get("limits", {})
        self.delays_cfg = config.get("delays", {})
        # Sliding window: timestamps of recent actions (last 60 minutes)
        self._recent_actions: Deque[datetime] = deque()

    def can_perform(self, action_type: str) -> bool:
        """Check if the daily limit for this action type has been reached."""
        if action_type not in ACTION_MAP:
            logger.warning("Unknown action type: %s", action_type)
            return False

        config_key, db_col = ACTION_MAP[action_type]
        limit = self.limits_cfg.get(config_key, 10)

        today_counts = self.db.get_today_counts()
        current = today_counts.get(f"{db_col}_count", 0)

        if current >= limit:
            logger.info(
                "Daily limit reached for %s: %d/%d", action_type, current, limit
            )
            return False

        return True

    def record_action(self, action_type: str):
        """Increment the daily counter for this action type."""
        if action_type not in ACTION_MAP:
            return
        _, db_col = ACTION_MAP[action_type]
        self.db.increment_action_count(db_col)

    def wait_between_actions(self):
        """
        Sleep for a human-like Gaussian delay between actions.
        Occasionally injects a longer 'distraction' pause.
        Also enforces a velocity check — if too many actions happened
        recently, forces a longer cooldown.
        """
        self._enforce_velocity_limit()

        min_d = self.delays_cfg.get("min_action_delay", 8)
        max_d = self.delays_cfg.get("max_action_delay", 25)
        mean = (min_d + max_d) / 2
        std = (max_d - min_d) / 4  # 95% of values fall within min–max

        delay = random.gauss(mean, std)
        delay = max(min_d, min(delay, max_d * 1.5))  # Clamp with slight upper headroom

        # ~12% chance of a longer "distraction" pause (30–90 seconds)
        if random.random() < 0.12:
            distraction = random.uniform(30, 90)
            logger.info(
                "Simulating distraction pause: %.0fs + %.0fs base delay",
                distraction, delay,
            )
            time.sleep(distraction)

        logger.debug("Action delay: %.1fs", delay)
        time.sleep(delay)

        # Record this action timestamp
        self._recent_actions.append(datetime.now())

    def _enforce_velocity_limit(self):
        """
        If more than 5 actions happened in the last 10 minutes,
        force a 3–8 minute cooldown to mimic natural pacing.
        """
        now = datetime.now()
        cutoff_minutes = 10
        max_actions_per_window = 5

        # Purge old entries
        while self._recent_actions and \
              (now - self._recent_actions[0]).seconds > cutoff_minutes * 60:
            self._recent_actions.popleft()

        if len(self._recent_actions) >= max_actions_per_window:
            cooldown = random.uniform(180, 480)  # 3–8 minutes
            logger.info(
                "Velocity limit hit (%d actions in %d min). "
                "Cooling down for %.0f seconds...",
                len(self._recent_actions), cutoff_minutes, cooldown,
            )
            time.sleep(cooldown)
            self._recent_actions.clear()

    def wait_between_pages(self):
        """Gaussian delay between page navigations."""
        min_d = self.delays_cfg.get("min_page_delay", 3)
        max_d = self.delays_cfg.get("max_page_delay", 8)
        mean = (min_d + max_d) / 2
        std = (max_d - min_d) / 4
        delay = max(min_d, random.gauss(mean, std))
        time.sleep(delay)

    def get_remaining(self, action_type: str) -> int:
        """Return how many more actions of this type can be done today."""
        if action_type not in ACTION_MAP:
            return 0
        config_key, db_col = ACTION_MAP[action_type]
        limit = self.limits_cfg.get(config_key, 10)
        today_counts = self.db.get_today_counts()
        current = today_counts.get(f"{db_col}_count", 0)
        return max(0, limit - current)

    def get_all_remaining(self) -> Dict[str, int]:
        """Return remaining counts for all action types."""
        return {atype: self.get_remaining(atype) for atype in ACTION_MAP}
