"""
Real-time Telegram bot listener.
Responds instantly to button presses and executes approved actions immediately.

Usage:
  python telegram_listener.py
"""

import logging
import sys
import time
import yaml
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TELEGRAM] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("storage/logs/telegram_listener.log", mode="a"),
    ],
)
logger = logging.getLogger("telegram_listener")


def load_config():
    with open("config/settings.yaml") as f:
        return yaml.safe_load(f)


def main():
    Path("storage/logs").mkdir(parents=True, exist_ok=True)
    
    from storage.database import Database
    from notifier.telegram_bot import TelegramNotifier
    from scraper.session_manager import SessionManager
    from executor.action_executor import ActionExecutor
    from executor.rate_limiter import RateLimiter

    config = load_config()
    db = Database(config["storage"]["db_path"])
    notifier = TelegramNotifier(config, db)

    logger.info("Telegram listener started - waiting for button presses...")
    logger.info("Press Ctrl+C to stop")

    offset = 0
    offset_file = Path("storage/telegram_offset.txt")
    if offset_file.exists():
        offset = int(offset_file.read_text())

    # Keep Chrome session open for instant execution
    session = None
    rate_limiter = None
    executor = None

    try:
        while True:
            # Poll for updates every 2 seconds (very responsive)
            updates = notifier.poll_updates(offset)

            for update in updates:
                result = notifier.process_callback(update)
                
                if result:
                    sid = result["suggestion_id"]
                    decision = result["decision"]
                    
                    # Update database
                    db.update_suggestion_status(sid, decision)
                    logger.info("✅ Suggestion #%d marked as %s", sid, decision)

                    # Update the Telegram message
                    suggestion = db.get_suggestion_by_id(sid)
                    if suggestion and suggestion.get("telegram_message_id"):
                        notifier.update_message_status(
                            suggestion["telegram_message_id"], decision, sid
                        )

                    # If approved, execute immediately!
                    if decision == "approved":
                        logger.info("🚀 Executing suggestion #%d immediately...", sid)
                        
                        # Initialize session if not already open
                        if not session:
                            logger.info("Starting Chrome session...")
                            session = SessionManager(
                                config["linkedin"]["session_file"],
                                headless=config.get("browser", {}).get("headless", True),
                                use_real_browser=config.get("browser", {}).get("use_real_browser", False),
                                real_browser_port=config.get("browser", {}).get("real_browser_port", 9222),
                            )
                            page = session.start()
                            logged_in = session.login(
                                config["linkedin"]["email"],
                                config["linkedin"]["password"],
                            )
                            
                            if not logged_in:
                                logger.error("LinkedIn login failed")
                                continue
                            
                            rate_limiter = RateLimiter(config, db)
                            executor = ActionExecutor(page, rate_limiter, db)
                        
                        # Execute the action
                        success = executor.execute(suggestion)
                        
                        if success:
                            logger.info("✅ Action executed successfully!")
                            # Update Telegram message to show it's done
                            if suggestion.get("telegram_message_id"):
                                notifier.update_message_status(
                                    suggestion["telegram_message_id"], "executed", sid
                                )
                        else:
                            logger.warning("❌ Action execution failed")

                # Advance offset
                update_id = update.get("update_id", 0)
                if update_id >= offset:
                    offset = update_id + 1

            # Save offset
            offset_file.write_text(str(offset))

            # Short sleep before next poll
            time.sleep(2)

    except KeyboardInterrupt:
        logger.info("\nStopping Telegram listener...")
    finally:
        if session:
            session.close()
        logger.info("Telegram listener stopped")


if __name__ == "__main__":
    main()
