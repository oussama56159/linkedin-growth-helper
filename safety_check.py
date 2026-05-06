"""
Safety checker — validates your configuration before running.
Warns about risky settings and suggests improvements.

Usage: python safety_check.py
"""

import yaml
import sys
from pathlib import Path


def load_config():
    config_path = Path("config/settings.yaml")
    if not config_path.exists():
        print("❌ config/settings.yaml not found")
        print("   Copy config/settings.SAFE.yaml to config/settings.yaml first")
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


def check_config(config):
    issues = []
    warnings = []
    good = []

    # Browser mode
    browser = config.get("browser", {})
    if browser.get("use_real_browser"):
        good.append("✅ Real browser mode enabled (safest option)")
    else:
        warnings.append(
            "⚠️  Real browser mode disabled — higher detection risk\n"
            "   Recommendation: Set browser.use_real_browser = true"
        )

    # Daily limits
    limits = config.get("limits", {})
    likes = limits.get("max_likes_per_day", 0)
    comments = limits.get("max_comments_per_day", 0)
    reposts = limits.get("max_reposts_per_day", 0)
    connects = limits.get("max_connections_per_day", 0)

    if likes <= 10:
        good.append(f"✅ Likes per day: {likes} (safe)")
    elif likes <= 20:
        warnings.append(f"⚠️  Likes per day: {likes} (moderate — consider lowering to 10)")
    else:
        issues.append(f"❌ Likes per day: {likes} (HIGH RISK — reduce to 10 or less)")

    if comments == 0:
        good.append("✅ Comments disabled (safest for starting)")
    elif comments <= 5:
        warnings.append(
            f"⚠️  Comments per day: {comments}\n"
            "   Comments are risky if they sound template-generated"
        )
    else:
        issues.append(f"❌ Comments per day: {comments} (too high — max 5)")

    if connects == 0:
        good.append("✅ Connection requests disabled (HIGHLY RECOMMENDED)")
    elif connects <= 5:
        warnings.append(
            f"⚠️  Connections per day: {connects}\n"
            "   Connection requests are the HIGHEST RISK action\n"
            "   Only enable after weeks of safe usage"
        )
    else:
        issues.append(
            f"❌ Connections per day: {connects} (VERY HIGH RISK)\n"
            "   Reduce to 0 initially, max 5 after proven safe"
        )

    # Scheduling
    sched = config.get("scheduling", {})
    min_interval = sched.get("min_interval_minutes", 0)
    if min_interval >= 120:
        good.append(f"✅ Minimum interval: {min_interval} minutes (good)")
    else:
        warnings.append(
            f"⚠️  Minimum interval: {min_interval} minutes\n"
            "   Recommendation: At least 120 minutes (2 hours)"
        )

    skip_prob = sched.get("daily_skip_probability", 0)
    if skip_prob >= 0.15:
        good.append(f"✅ Daily skip probability: {skip_prob:.0%} (good)")
    else:
        warnings.append(
            f"⚠️  Daily skip probability: {skip_prob:.0%}\n"
            "   Recommendation: At least 15% to avoid predictable patterns"
        )

    # Credentials
    telegram = config.get("telegram", {})
    if telegram.get("bot_token") == "YOUR_TELEGRAM_BOT_TOKEN":
        issues.append(
            "❌ Telegram bot not configured\n"
            "   Run: python main.py --mode setup"
        )
    else:
        good.append("✅ Telegram bot configured")

    linkedin = config.get("linkedin", {})
    if not browser.get("use_real_browser"):
        if linkedin.get("email") == "your_linkedin_email@example.com":
            issues.append(
                "❌ LinkedIn credentials not configured\n"
                "   Update linkedin.email and linkedin.password in settings.yaml"
            )

    return issues, warnings, good


def print_report(issues, warnings, good):
    print("\n" + "=" * 70)
    print("  LINKEDIN GROWTH SYSTEM — SAFETY CHECK")
    print("=" * 70 + "\n")

    if good:
        print("✅ GOOD CONFIGURATION:\n")
        for item in good:
            print(f"   {item}")
        print()

    if warnings:
        print("⚠️  WARNINGS (consider addressing):\n")
        for item in warnings:
            print(f"   {item}\n")

    if issues:
        print("❌ CRITICAL ISSUES (must fix before running):\n")
        for item in issues:
            print(f"   {item}\n")

    print("=" * 70)

    if issues:
        print("\n❌ Configuration has CRITICAL ISSUES — fix before running\n")
        return False
    elif warnings:
        print(
            "\n⚠️  Configuration is functional but has warnings\n"
            "   You can proceed, but consider the recommendations above\n"
        )
        return True
    else:
        print("\n✅ Configuration looks safe — ready to run\n")
        return True


def main():
    try:
        config = load_config()
        issues, warnings, good = check_config(config)
        is_safe = print_report(issues, warnings, good)

        if is_safe:
            print("Next steps:")
            print("  1. Start Chrome with debugging: see QUICKSTART.md")
            print("  2. Test discovery: python main.py --mode scrape")
            print("  3. Approve suggestions in Telegram")
            print("  4. Execute: python main.py --mode execute")
            print("  5. Go continuous: python scheduler.py\n")
        else:
            print("Fix the issues above, then run this check again.\n")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error reading config: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
