# Quick Start Guide — Safest Configuration

## Phase 1: Installation (5 minutes)

```bash
cd linkedin-growth-system

# Install Python dependencies
pip install -r requirements.txt

# Install Chromium for Playwright
playwright install chromium
```

---

## Phase 2: Real Browser Setup (RECOMMENDED — 5 minutes)

This is the **safest mode** — LinkedIn sees your actual browser.

### Windows:
```bash
# Close all Chrome windows first
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\ChromeDebug
```

### Mac:
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

### Linux:
```bash
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

**Then:**
1. Chrome will open with a yellow bar saying "Chrome is being controlled by automated test software"
2. Log into LinkedIn manually in that Chrome window
3. Keep this Chrome window open while the bot runs

---

## Phase 3: Configure Telegram Bot (5 minutes)

```bash
python main.py --mode setup
```

Follow the prompts:
1. Message @BotFather on Telegram → `/newbot`
2. Copy your bot token
3. Send any message to your new bot
4. Paste token when prompted → script finds your chat_id

---

## Phase 4: Edit config/settings.yaml

```yaml
# Enable real browser mode (SAFEST)
browser:
  use_real_browser: true    # ← Change this to true
  real_browser_port: 9222
  headless: false           # Must be false for real browser

# Your LinkedIn credentials (only needed if use_real_browser=false)
linkedin:
  email: "your_linkedin_email@example.com"
  password: "your_linkedin_password"

# Your Telegram bot (from Phase 3)
telegram:
  bot_token: "YOUR_BOT_TOKEN_HERE"
  chat_id: "YOUR_CHAT_ID_HERE"

# ULTRA-SAFE LIMITS (start here)
limits:
  max_likes_per_day: 5          # Start very low
  max_comments_per_day: 0       # Disable comments initially
  max_reposts_per_day: 0        # Disable reposts initially
  max_connections_per_day: 0    # DISABLE connections (highest risk)
  max_suggestions_per_run: 5

# Your targeting (customize these)
targeting:
  keywords:
    - "your niche keyword 1"
    - "your niche keyword 2"
  hashtags:
    - "#YourNiche"
    - "#YourIndustry"
```

---

## Phase 5: Test Run (Discovery Only)

```bash
# Run once manually to test
python main.py --mode scrape
```

**What happens:**
1. Connects to your Chrome (or logs in if real browser disabled)
2. Visits your hashtag feeds
3. Discovers posts
4. Sends suggestions to Telegram
5. **Does NOT execute anything** — waits for your approval

Check Telegram — you should see suggestions with ✅/❌ buttons.

---

## Phase 6: Approve & Execute

In Telegram, tap ✅ on 2-3 suggestions you genuinely like.

Then run:
```bash
python main.py --mode execute
```

Watch the terminal — it will like those posts with human-like delays.

---

## Phase 7: Go Continuous (Optional)

Once you're comfortable:

```bash
python scheduler.py
```

This runs continuously with randomized 2-5 hour intervals.

**To stop it:** Press Ctrl+C

---

## Safety Checklist Before Going Live

- [ ] Real browser mode enabled (`use_real_browser: true`)
- [ ] Chrome is running with `--remote-debugging-port=9222`
- [ ] You're logged into LinkedIn in that Chrome window
- [ ] Connection requests disabled (`max_connections_per_day: 0`)
- [ ] Comments disabled initially (`max_comments_per_day: 0`)
- [ ] Daily limits set to 5 or less for first week
- [ ] You've tested with `--mode scrape` and received Telegram notifications
- [ ] You've manually approved 2-3 suggestions and tested `--mode execute`

---

## Gradual Ramp-Up Strategy

**Week 1:** 5 likes/day, no comments, no connects
**Week 2:** 8 likes/day, 2 comments/day (only if they sound natural)
**Week 3:** 10 likes/day, 3 comments/day
**Week 4+:** Consider 2-3 connects/day (only to highly relevant profiles)

**Never exceed:**
- 15 likes/day
- 5 comments/day
- 5 connects/day

---

## Red Flags to Watch For

**Stop immediately if you see:**
- LinkedIn asks you to verify your identity
- Actions fail silently (like button clicked but count doesn't increase)
- You get a message about "unusual activity"
- Connection requests get auto-rejected

**If this happens:**
1. Stop the scheduler
2. Don't use the tool for 7-14 days
3. Use LinkedIn normally from your regular browser
4. When resuming, cut limits in half

---

## FAQ

**Q: Can I run this on a VPS/cloud server?**
A: Not recommended. LinkedIn will see a different IP than your normal usage. Run it on your personal computer.

**Q: What if I have 2FA enabled?**
A: Real browser mode handles this automatically (you're already logged in). If using headless mode, you'll need to complete 2FA manually the first time.

**Q: Can I run this while using LinkedIn normally?**
A: Not if using real browser mode (it controls your Chrome). Use headless mode instead, but that's riskier.

**Q: How do I know if it's working?**
A: Check `storage/logs/app.log` and `storage/logs/scheduler.log` for detailed activity.

**Q: Should I use this on my main LinkedIn account?**
A: Only if you're comfortable with the risk. Consider testing on a secondary account first.
