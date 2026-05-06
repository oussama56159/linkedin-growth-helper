"""
Randomized scheduler that runs the LinkedIn Growth System at human-like intervals.
Runs as a background process — keeps the system active without fixed cron patterns.

Usage:
  python scheduler.py
"""

import subprocess
import time
import random
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml

# Create logs directory if it doesn't exist
Path("storage/logs").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SCHEDULER] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("storage/logs/scheduler.log", mode="a"),
    ],
)
logger = logging.getLogger("scheduler")


def load_config() -> dict:
    with open("config/settings.yaml") as f:
        return yaml.safe_load(f)


def should_skip_today(config: dict) -> bool:
    """
    Randomly skip entire days to mimic human behavior (weekends off,
    sick days, busy days). Configurable skip probability.
    """
    sched = config.get("scheduling", {})
    skip_probability = sched.get("daily_skip_probability", 0.15)  # 15% chance to skip a day

    # Always skip on configured days off (0=Mon, 6=Sun)
    days_off = sched.get("days_off", [6])  # Default: skip Sundays
    if datetime.now().weekday() in days_off:
        logger.info("Today is a configured day off. Skipping.")
        return True

    if random.random() < skip_probability:
        logger.info("Random day off (%.0f%% chance). Skipping today.", skip_probability * 100)
        return True

    return False


def is_active_hour(config: dict) -> bool:
    """Check if current time is within configured active hours."""
    sched = config.get("scheduling", {})
    start = sched.get("active_hours_start", 8)
    end = sched.get("active_hours_end", 22)
    current_hour = datetime.now().hour
    return start <= current_hour < end


def run_pipeline():
    """Run the main pipeline as a subprocess."""
    logger.info("▶ Starting pipeline run...")
    result = subprocess.run(
        [sys.executable, "main.py", "--mode", "full"],
        capture_output=False,
    )
    if result.returncode == 0:
        logger.info("✅ Pipeline completed successfully")
    else:
        logger.warning("⚠️ Pipeline exited with code %d", result.returncode)


def run_poll_only():
    """Poll for Telegram decisions between full runs."""
    subprocess.run([sys.executable, "main.py", "--mode", "poll"], capture_output=False)


def main():
    Path("storage/logs").mkdir(parents=True, exist_ok=True)
    logger.info("LinkedIn Growth System Scheduler started")

    config = load_config()
    sched = config.get("scheduling", {})
    min_interval = sched.get("min_interval_minutes", 90)
    max_interval = sched.get("max_interval_minutes", 240)

    run_count = 0

    while True:
        config = load_config()  # Reload config each cycle

        if should_skip_today(config):
            # Sleep until tomorrow 8am-ish
            sleep_until_tomorrow = random.uniform(12 * 3600, 16 * 3600)
            logger.info("Sleeping for ~%.0f hours (day off)", sleep_until_tomorrow / 3600)
            time.sleep(sleep_until_tomorrow)
            continue

        if is_active_hour(config):
            run_count += 1
            logger.info("=== Scheduled run #%d ===", run_count)
            run_pipeline()

            # Send daily summary once per day (on run #1 after 8am)
            if run_count == 1:
                subprocess.run(
                    [sys.executable, "main.py", "--mode", "summary"],
                    capture_output=False,
                )
        else:
            logger.info(
                "Outside active hours (%d–%d), sleeping...",
                sched.get("active_hours_start", 8),
                sched.get("active_hours_end", 22),
            )

        # Random interval until next run
        interval_minutes = random.uniform(min_interval, max_interval)

        # Poll Telegram every 5 minutes in between full runs
        poll_interval = 5 * 60  # 5 minutes in seconds
        total_sleep = interval_minutes * 60
        elapsed = 0

        logger.info("Next full run in %.0f minutes", interval_minutes)

        while elapsed < total_sleep:
            sleep_chunk = min(poll_interval, total_sleep - elapsed)
            time.sleep(sleep_chunk)
            elapsed += sleep_chunk

            # Poll for decisions while waiting
            if is_active_hour(config) and elapsed < total_sleep:
                run_poll_only()


if __name__ == "__main__":
    main()
