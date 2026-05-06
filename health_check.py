"""
Health check script - run this periodically to verify the system is working.

Usage:
  python health_check.py
"""

import yaml
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def load_config():
    with open("config/settings.yaml") as f:
        return yaml.safe_load(f)


def check_database():
    """Check if database is accessible and has recent activity."""
    config = load_config()
    db_path = config["storage"]["db_path"]
    
    if not Path(db_path).exists():
        return False, "Database file not found"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check for recent posts
        cursor.execute(
            "SELECT COUNT(*) FROM posts WHERE discovered_at > datetime('now', '-24 hours')"
        )
        recent_posts = cursor.fetchone()[0]
        
        # Check for recent actions
        cursor.execute(
            "SELECT COUNT(*) FROM actions_log WHERE executed_at > datetime('now', '-24 hours')"
        )
        recent_actions = cursor.fetchone()[0]
        
        conn.close()
        
        return True, f"Recent posts: {recent_posts}, Recent actions: {recent_actions}"
    
    except Exception as e:
        return False, f"Database error: {e}"


def check_logs():
    """Check if logs are being written recently."""
    log_file = Path("storage/logs/background.log")
    
    if not log_file.exists():
        return False, "Log file not found"
    
    try:
        modified = datetime.fromtimestamp(log_file.stat().st_mtime)
        age = datetime.now() - modified
        
        if age > timedelta(hours=6):
            return False, f"Logs not updated in {age.total_seconds() / 3600:.1f} hours"
        
        return True, f"Logs updated {age.total_seconds() / 60:.0f} minutes ago"
    
    except Exception as e:
        return False, f"Log check error: {e}"


def check_chrome_session():
    """Check if Chrome debugging session file exists."""
    config = load_config()
    session_file = Path(config["linkedin"]["session_file"])
    
    if not session_file.exists():
        return False, "Chrome session file not found"
    
    return True, "Chrome session file exists"


def main():
    print("\n" + "=" * 60)
    print("LinkedIn Growth System - Health Check")
    print("=" * 60 + "\n")
    
    checks = [
        ("Database", check_database),
        ("Logs", check_logs),
        ("Chrome Session", check_chrome_session),
    ]
    
    all_healthy = True
    
    for name, check_func in checks:
        status, message = check_func()
        icon = "✅" if status else "❌"
        print(f"{icon} {name}: {message}")
        if not status:
            all_healthy = False
    
    print("\n" + "=" * 60)
    if all_healthy:
        print("✅ System is healthy")
    else:
        print("⚠️  System has issues - check logs for details")
    print("=" * 60 + "\n")
    
    return 0 if all_healthy else 1


if __name__ == "__main__":
    exit(main())
