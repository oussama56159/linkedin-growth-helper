"""
LinkedIn Growth System — Main Orchestrator
Runs the full pipeline: scrape → analyze → suggest → notify → (await approval) → execute

Usage:
  python main.py --mode scrape      # Discover posts/profiles and send suggestions
  python main.py --mode execute     # Execute all approved suggestions
  python main.py --mode poll        # Poll Telegram for approve/reject decisions
  python main.py --mode full        # Run scrape + poll + execute in sequence
  python main.py --mode summary     # Send daily summary to Telegram
  python main.py --mode setup       # First-time setup helper
"""

import argparse
import logging
import sys
import time
import random
import yaml
from pathlib import Path

# ── Logging setup ──────────────────────────────────────────────────────────────
# Create logs directory if it doesn't exist
Path("storage/logs").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("storage/logs/app.log", mode="a"),
    ],
)
logger = logging.getLogger("main")


def load_config() -> dict:
    config_path = Path("config/settings.yaml")
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


def run_scrape(config: dict):
    """Scrape LinkedIn, analyze content, create suggestions, send to Telegram."""
    from storage.database import Database
    from scraper.session_manager import SessionManager
    from scraper.linkedin_scraper import LinkedInScraper
    from analyzer.post_scorer import rank_posts, suggest_action
    from analyzer.profile_scorer import rank_profiles, build_connection_reason
    from analyzer.comment_generator import generate_comment_draft
    from notifier.telegram_bot import TelegramNotifier

    db = Database(config["storage"]["db_path"])
    notifier = TelegramNotifier(config, db)

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
            logger.error("LinkedIn login failed. Check credentials or handle 2FA manually.")
            return

        scraper = LinkedInScraper(session, config)

        # ── Scrape posts ───────────────────────────────────────────────────
        logger.info("Starting post scraping...")
        raw_posts = scraper.scrape_posts()

        # Filter already-seen posts
        new_posts = []
        for post in raw_posts:
            url = post.get("post_url", "")
            if url and not db.is_seen(url):
                db.mark_seen(url)
                db.save_post(post)
                new_posts.append(post)

        logger.info("%d new posts discovered", len(new_posts))

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
                f"Comments: {post.get('comments_count', 0)} | "
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

        # ── Scrape profiles ────────────────────────────────────────────────
        logger.info("Starting profile scraping...")
        raw_profiles = scraper.scrape_profiles()

        new_profiles = []
        for profile in raw_profiles:
            url = profile.get("profile_url", "")
            if url and not db.is_seen(url):
                db.mark_seen(url)
                db.save_profile(profile)
                new_profiles.append(profile)

        logger.info("%d new profiles discovered", len(new_profiles))

        ranked_profiles = rank_profiles(new_profiles, config)
        profile_suggestions = []

        max_connections = config["limits"].get("max_connection_suggestions_per_run", 5)
        max_follows = config["limits"].get("max_follow_suggestions_per_run", 3)
        connection_profiles = [
            p for p in ranked_profiles if p.get("suggestion_type", "connect") != "follow"
        ][:max_connections]
        follow_profiles = [
            p for p in ranked_profiles if p.get("suggestion_type", "connect") == "follow"
        ][:max_follows]

        for profile in connection_profiles + follow_profiles:
            reason = build_connection_reason(profile, config)
            suggestion_type = profile.get("suggestion_type", "connect")
            summary = (
                f"{profile.get('full_name', 'Unknown')} — "
                f"{profile.get('headline', 'No headline')}"
            )
            sid = db.create_suggestion({
                "suggestion_type": suggestion_type,
                "target_url": profile["profile_url"],
                "target_summary": summary,
                "reason": reason,
                "relevance_score": profile.get("final_score", 0),
            })
            suggestion = db.get_suggestion_by_id(sid)
            profile_suggestions.append(suggestion)

        # ── Send to Telegram ───────────────────────────────────────────────
        logger.info(
            "Sending %d post + %d profile suggestions to Telegram",
            len(post_suggestions),
            len(profile_suggestions),
        )
        notifier.send_batch_suggestions(post_suggestions, profile_suggestions)

    finally:
        session.close()


def run_poll(config: dict):
    """Poll Telegram for approve/reject decisions and update DB."""
    from storage.database import Database
    from notifier.telegram_bot import TelegramNotifier

    db = Database(config["storage"]["db_path"])
    notifier = TelegramNotifier(config, db)

    # Load last known update offset
    offset_file = Path("storage/telegram_offset.txt")
    offset = int(offset_file.read_text()) if offset_file.exists() else 0

    logger.info("Polling Telegram for decisions (offset=%d)...", offset)
    updates = notifier.poll_updates(offset)

    for update in updates:
        result = notifier.process_callback(update)
        if result:
            sid = result["suggestion_id"]
            decision = result["decision"]
            db.update_suggestion_status(sid, decision)
            logger.info("Suggestion #%d marked as %s", sid, decision)

            # Update the Telegram message to reflect the decision
            suggestion = db.get_suggestion_by_id(sid)
            if suggestion and suggestion.get("telegram_message_id"):
                notifier.update_message_status(
                    suggestion["telegram_message_id"], decision, sid
                )

        # Advance offset
        update_id = update.get("update_id", 0)
        if update_id >= offset:
            offset = update_id + 1

    # Save offset
    offset_file.write_text(str(offset))
    logger.info("Processed %d Telegram updates", len(updates))


def run_execute(config: dict):
    """Execute all approved suggestions."""
    from storage.database import Database
    from scraper.session_manager import SessionManager
    from executor.action_executor import ActionExecutor
    from executor.rate_limiter import RateLimiter

    db = Database(config["storage"]["db_path"])
    approved = db.get_approved_suggestions()

    if not approved:
        logger.info("No approved suggestions to execute.")
        return

    logger.info("Executing %d approved suggestions...", len(approved))

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
            logger.error("LinkedIn login failed.")
            return

        rate_limiter = RateLimiter(config, db)
        executor = ActionExecutor(page, rate_limiter, db)
        results = executor.execute_batch(approved)

        logger.info("Execution results: %s", results)

    finally:
        session.close()


def run_summary(config: dict):
    """Send a daily summary to Telegram."""
    from storage.database import Database
    from notifier.telegram_bot import TelegramNotifier

    db = Database(config["storage"]["db_path"])
    notifier = TelegramNotifier(config, db)

    counts = db.get_today_counts()
    pending = len(db.get_pending_suggestions())
    approved = len(db.get_approved_suggestions())

    stats = {
        "likes": counts.get("likes_count", 0),
        "comments": counts.get("comments_count", 0),
        "reposts": counts.get("reposts_count", 0),
        "connections": counts.get("connections_count", 0),
        "pending": pending,
        "executed": approved,
    }
    notifier.send_daily_summary(stats)
    logger.info("Daily summary sent.")


def run_setup():
    """Interactive first-time setup helper."""
    print("\n🚀 LinkedIn Growth System — Setup\n")
    print("Step 1: Create a Telegram bot")
    print("  → Message @BotFather on Telegram")
    print("  → Send /newbot and follow instructions")
    print("  → Copy your bot token\n")

    token = input("Paste your Telegram bot token: ").strip()
    if token:
        from notifier.telegram_bot import get_chat_id
        print("\nStep 2: Send any message to your new bot, then press Enter...")
        input("Press Enter when done...")
        chat_id = get_chat_id(token)
        if chat_id:
            print(f"\n✅ Your chat_id: {chat_id}")
            print("\nStep 3: Update config/settings.yaml with:")
            print(f"  telegram.bot_token: {token}")
            print(f"  telegram.chat_id: {chat_id}")

    print("\nStep 4: Add your LinkedIn credentials to config/settings.yaml")
    print("  linkedin.email: your@email.com")
    print("  linkedin.password: yourpassword")
    print("\nStep 5: Run the system:")
    print("  python main.py --mode full")
    print("\n✅ Setup complete!\n")


def main():
    Path("storage/logs").mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(description="LinkedIn Growth System")
    parser.add_argument(
        "--mode",
        choices=["scrape", "execute", "poll", "full", "summary", "setup"],
        default="full",
        help="Operation mode",
    )
    args = parser.parse_args()

    if args.mode == "setup":
        run_setup()
        return

    config = load_config()

    if args.mode == "scrape":
        run_scrape(config)
    elif args.mode == "poll":
        run_poll(config)
    elif args.mode == "execute":
        run_execute(config)
    elif args.mode == "summary":
        run_summary(config)
    elif args.mode == "full":
        logger.info("=== Full pipeline run ===")
        run_scrape(config)
        # Brief pause before polling
        time.sleep(random.uniform(5, 15))
        run_poll(config)
        # Execute anything already approved
        run_execute(config)
        logger.info("=== Full pipeline complete ===")


if __name__ == "__main__":
    main()
