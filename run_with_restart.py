"""
Auto-restart wrapper for the background service.
If it crashes, automatically restarts it.
"""

import subprocess
import time
import logging
import sys
from pathlib import Path

Path("storage/logs").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("storage/logs/watchdog.log", mode="a"),
    ],
)
logger = logging.getLogger("watchdog")


def main():
    logger.info("Watchdog started - will auto-restart on crashes")
    restart_count = 0
    max_restarts_per_hour = 5
    restart_times = []
    
    while True:
        try:
            logger.info("Starting background service...")
            process = subprocess.Popen(
                [sys.executable, "run_background.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Stream output
            for line in process.stdout:
                print(line, end='')
            
            process.wait()
            
            # Check if it was a clean exit
            if process.returncode == 0:
                logger.info("Service stopped cleanly")
                break
            
            # Track restart frequency
            now = time.time()
            restart_times = [t for t in restart_times if now - t < 3600]  # Last hour
            restart_times.append(now)
            restart_count += 1
            
            if len(restart_times) >= max_restarts_per_hour:
                logger.error(
                    "Too many restarts (%d in last hour). Stopping watchdog.",
                    len(restart_times)
                )
                break
            
            logger.warning(
                "Service crashed (exit code %d). Restarting in 30 seconds... (restart #%d)",
                process.returncode, restart_count
            )
            time.sleep(30)
            
        except KeyboardInterrupt:
            logger.info("Watchdog stopped by user")
            if process:
                process.terminate()
            break
        except Exception as e:
            logger.error("Watchdog error: %s", e)
            time.sleep(60)


if __name__ == "__main__":
    main()
