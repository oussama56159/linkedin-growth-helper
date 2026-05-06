"""
Unified background service for LinkedIn Growth System.
Runs everything in one process:
  - Scrapes posts at randomized intervals
  - Listens for Telegram button presses continuously
  - Executes approved actions instantly

Usage:
  python run_background.py
"""

import logging
import sys
import time
import random
import yaml
import threading
from pathlib import Path
from datetime import datetime

# Create logs directory
Path("storage/logs").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("storage/logs/background.log", mode="a"),
    ],
)
logger = logging.getLogger("background")


def load_config():
    with open("config/settings.yaml") as f:
        return yaml.safe_load(f)


def is_active_hour(config):
    """Check if current time is within configured active hours."""
    sched = config.get("scheduling", {})
    start = sched.get("active_hours_start", 9)
    end = sched.get("active_hours_end", 21)
    current_hour = datetime.now().hour
    return start <= current_hour < end


def should_skip_today(config):
    """Check if today should be skipped."""
    sched = config.get("scheduling", {})
    skip_probability = sched.get("daily_skip_probability", 0.15)
    days_off = sched.get("days_off", [6])
    
    if datetime.now().weekday() in days_off:
        return True
    
    if random.random() < skip_probability:
        return True
    
    return False


def telegram_listener_thread(config, db, notifier, stop_event):
    """Background thread that listens for Telegram button presses."""
    from scraper.session_manager import SessionManager
    from executor.action_executor import ActionExecutor
    from executor.rate_limiter import RateLimiter
    
    logger.info("Telegram listener thread started")
    
    offset = 0
    offset_file = Path("storage/telegram_offset.txt")
    if offset_file.exists():
        offset = int(offset_file.read_text())
    
    session = None
    rate_limiter = None
    executor = None
    
    try:
        while not stop_event.is_set():
            try:
                updates = notifier.poll_updates(offset)
                
                for update in updates:
                    result = notifier.process_callback(update)
                    
                    if result:
                        sid = result["suggestion_id"]
                        decision = result["decision"]
                        
                        db.update_suggestion_status(sid, decision)
                        logger.info("Suggestion #%d -> %s", sid, decision)
                        
                        suggestion = db.get_suggestion_by_id(sid)
                        if suggestion and suggestion.get("telegram_message_id"):
                            notifier.update_message_status(
                                suggestion["telegram_message_id"], decision, sid
                            )
                        
                        # Execute immediately if approved
                        if decision == "approved":
                            logger.info("Executing suggestion #%d...", sid)
                            
                            # Initialize session if needed
                            if not session:
                                logger.info("Starting Chrome session for execution...")
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
                            
                            success = executor.execute(suggestion)
                            
                            if success:
                                logger.info("Executed successfully!")
                                if suggestion.get("telegram_message_id"):
                                    notifier.update_message_status(
                                        suggestion["telegram_message_id"], "executed", sid
                                    )
                            else:
                                logger.warning("Execution failed")
                    
                    update_id = update.get("update_id", 0)
                    if update_id >= offset:
                        offset = update_id + 1
                
                offset_file.write_text(str(offset))
                
            except Exception as e:
                logger.error("Error in Telegram listener: %s", e)
            
            time.sleep(2)  # Poll every 2 seconds
    
    finally:
        if session:
            session.close()
        logger.info("Telegram listener thread stopped")


def scraper_thread(config, db, notifier, stop_event):
    """Background thread that scrapes posts at randomized intervals."""
    from storage.database import Database
    from scraper.session_manager import SessionManager
    from scraper.linkedin_scraper import LinkedInScraper
    from analyzer.post_scorer import rank_posts, suggest_action
    from analyzer.comment_generator import generate_comment_draft
    
    logger.info("Scraper thread started")
    
    run_count = 0
    
    while not stop_event.is_set():
        try:
            config = load_config()  # Reload config
            
            # Check if we should skip today
            if should_skip_today(config):
                logger.info("Skipping today (random day off)")
                time.sleep(12 * 3600)  # Sleep 12 hours
                continue
            
            # Check if we're in active hours
            if not is_active_hour(config):
                logger.info("Outside active hours, sleeping...")
                time.sleep(30 * 60)  # Sleep 30 minutes, then check again
                continue
            
            run_count += 1
            logger.info("=== Scraper run #%d ===", run_count)
            
            # Run the scraper
            session = SessionManager(
                config["linkedin"]["session_file"],
                headless=config.get("browser", {}).get("headless", True),
                use_real_browser=config.get("browser", {}).get("use_real_browser", False),
                real_browser_port=config.get("browser", {}).get("real_browser_port", 9222),
            )
            
            try:
                page = session.start()
                logged_in = session.login(
                    config["linkedin"]["email"],
                    config["linkedin"]["password"],
                )
                
                if not logged_in:
                    logger.error("LinkedIn login failed")
                    continue
                
                scraper = LinkedInScraper(session, config)
                
                # Scrape posts
                logger.info("Scraping posts...")
                raw_posts = scraper.scrape_posts()
                
                new_posts = []
                for post in raw_posts:
                    url = post.get("post_url", "")
                    if url and not db.is_seen(url):
                        db.mark_seen(url)
                        db.save_post(post)
                        new_posts.append(post)
                
                logger.info("Found %d new posts", len(new_posts))
                
                # Rank and create suggestions
                ranked_posts = rank_posts(new_posts, config)
                max_suggestions = config["limits"]["max_suggestions_per_run"]
                post_suggestions = []
                
                for post in ranked_posts[:max_suggestions]:
                    action = suggest_action(post)
                    comment_draft = None
                    if action == "comment":
                        comment_draft = generate_comment_draft(post)
                    
                    content_preview = (post.get("content") or "")[:200]
                    reason = (
                        f"Score: {post.get('final_score', 0):.1f} | "
                        f"Likes: {post.get('likes_count', 0)} | "
                        f"Relevance: {post.get('relevance_score', 0):.0%}"
                    )
                    
                    sid = db.create_suggestion({
                        "suggestion_type": action,
                        "target_url": post["post_url"],
                        "target_summary": f"By {post.get('author_name', 'Unknown')}: {content_preview}",
                        "reason": reason,
                        "comment_draft": comment_draft,
                        "relevance_score": post.get("final_score", 0),
                    })
                    suggestion = db.get_suggestion_by_id(sid)
                    post_suggestions.append(suggestion)
                
                # Send to Telegram
                if post_suggestions:
                    logger.info("Sending %d suggestions to Telegram", len(post_suggestions))
                    notifier.send_batch_suggestions(post_suggestions, [])
                else:
                    logger.info("No suggestions to send")
                
            finally:
                session.close()
            
            # Random interval until next run
            sched = config.get("scheduling", {})
            min_interval = sched.get("min_interval_minutes", 120)
            max_interval = sched.get("max_interval_minutes", 300)
            interval_minutes = random.uniform(min_interval, max_interval)
            
            logger.info("Next scrape in %.0f minutes", interval_minutes)
            
            # Sleep in small chunks so we can stop quickly
            sleep_seconds = interval_minutes * 60
            for _ in range(int(sleep_seconds / 10)):
                if stop_event.is_set():
                    break
                time.sleep(10)
        
        except Exception as e:
            logger.error("Error in scraper thread: %s", e)
            time.sleep(60)  # Wait a minute before retrying


def main():
    from storage.database import Database
    from notifier.telegram_bot import TelegramNotifier
    
    logger.info("=" * 70)
    logger.info("LinkedIn Growth System - Background Service")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Starting unified background service...")
    logger.info("  • Scraper: runs every 2-5 hours during active hours")
    logger.info("  • Telegram listener: checks every 2 seconds for button presses")
    logger.info("  • Executor: runs instantly when you approve suggestions")
    logger.info("")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 70)
    logger.info("")
    
    config = load_config()
    db = Database(config["storage"]["db_path"])
    notifier = TelegramNotifier(config, db)
    
    stop_event = threading.Event()
    
    # Start both threads
    telegram_thread = threading.Thread(
        target=telegram_listener_thread,
        args=(config, db, notifier, stop_event),
        daemon=True
    )
    
    scraper_thread_obj = threading.Thread(
        target=scraper_thread,
        args=(config, db, notifier, stop_event),
        daemon=True
    )
    
    telegram_thread.start()
    scraper_thread_obj.start()
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n" + "=" * 70)
        logger.info("Stopping background service...")
        logger.info("=" * 70)
        stop_event.set()
        telegram_thread.join(timeout=5)
        scraper_thread_obj.join(timeout=5)
        logger.info("Background service stopped")


if __name__ == "__main__":
    main()
