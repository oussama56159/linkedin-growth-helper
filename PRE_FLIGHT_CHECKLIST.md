# Pre-Flight Checklist

Run through this checklist before starting the system for the first time.

---

## ✅ Installation

- [ ] Python 3.8+ installed
- [ ] Ran `pip install -r requirements.txt`
- [ ] Ran `playwright install chromium`
- [ ] No errors during installation

---

## ✅ Configuration

- [ ] Copied `config/settings.SAFE.yaml` to `config/settings.yaml`
- [ ] Created Telegram bot via @BotFather
- [ ] Ran `python main.py --mode setup` and got bot token + chat_id
- [ ] Updated `telegram.bot_token` in settings.yaml
- [ ] Updated `telegram.chat_id` in settings.yaml
- [ ] Customized `targeting.keywords` for your niche
- [ ] Customized `targeting.hashtags` for your niche
- [ ] Set `browser.use_real_browser: true`
- [ ] Ran `python safety_check.py` with no critical errors

---

## ✅ Real Browser Setup (CRITICAL)

### Windows:
- [ ] Closed all Chrome windows
- [ ] Ran: `"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\ChromeDebug`
- [ ] Chrome opened with yellow "automated test software" bar
- [ ] Logged into LinkedIn in that Chrome window
- [ ] Verified you can browse LinkedIn normally in that window

### Mac:
- [ ] Closed all Chrome windows
- [ ] Ran: `/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug`
- [ ] Chrome opened with yellow "automated test software" bar
- [ ] Logged into LinkedIn in that Chrome window
- [ ] Verified you can browse LinkedIn normally in that window

### Linux:
- [ ] Closed all Chrome windows
- [ ] Ran: `google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug`
- [ ] Chrome opened with yellow "automated test software" bar
- [ ] Logged into LinkedIn in that Chrome window
- [ ] Verified you can browse LinkedIn normally in that window

---

## ✅ Safety Settings

- [ ] `max_likes_per_day` ≤ 5 (for first week)
- [ ] `max_comments_per_day` = 0 (disabled initially)
- [ ] `max_reposts_per_day` = 0 (disabled initially)
- [ ] `max_connections_per_day` = 0 (disabled — highest risk)
- [ ] `min_interval_minutes` ≥ 120 (at least 2 hours between runs)
- [ ] `daily_skip_probability` ≥ 0.15 (at least 15%)
- [ ] `days_off` includes at least one weekend day

---

## ✅ Test Run

- [ ] Chrome with debugging is still running and logged into LinkedIn
- [ ] Ran `python main.py --mode scrape` in a separate terminal
- [ ] Saw "Connected to real Chrome successfully" in logs
- [ ] Saw "Scraping hashtag: #..." messages
- [ ] Received Telegram message with suggestions
- [ ] Suggestions have ✅ Approve and ❌ Reject buttons
- [ ] No errors in terminal output

---

## ✅ Approval Test

- [ ] Tapped ✅ on 2-3 suggestions in Telegram
- [ ] Ran `python main.py --mode poll`
- [ ] Saw "Telegram decision: suggestion #X → approved" in logs
- [ ] Ran `python main.py --mode execute`
- [ ] Saw actions being executed with delays
- [ ] Verified actions completed on LinkedIn (check your activity)
- [ ] No errors or warnings from LinkedIn

---

## ✅ Monitoring Setup

- [ ] Know where logs are: `storage/logs/app.log` and `storage/logs/scheduler.log`
- [ ] Can tail logs: `tail -f storage/logs/app.log` (Mac/Linux) or open in text editor (Windows)
- [ ] Understand how to stop the scheduler: Ctrl+C
- [ ] Know how to check database: `sqlite3 storage/linkedin_growth.db "SELECT * FROM daily_limits;"`

---

## ✅ Emergency Procedures

- [ ] Know how to stop everything: Ctrl+C in scheduler terminal
- [ ] Know where to disable actions: set all `max_*_per_day` to 0 in settings.yaml
- [ ] Understand the warning signs:
  - LinkedIn asks for identity verification
  - Actions fail silently (button clicked but nothing happens)
  - "Unusual activity" message from LinkedIn
  - Connection requests auto-rejected
- [ ] Know the recovery plan:
  - Stop scheduler immediately
  - Don't use tool for 7-14 days
  - Use LinkedIn normally from regular browser
  - When resuming, cut all limits in half

---

## ✅ Ready to Go Live

If all boxes above are checked:

```bash
# Start the continuous scheduler
python scheduler.py
```

**Keep the Chrome debugging window open** — the scheduler needs it.

**Monitor for the first 24 hours:**
- Check logs every few hours
- Verify actions are completing successfully
- Watch for any LinkedIn warnings
- Confirm Telegram notifications are arriving

**After 1 week of safe operation:**
- Consider increasing likes to 8/day
- Consider enabling 2 comments/day (only if they sound natural)
- Keep connections disabled for at least 2-3 weeks

---

## 🚨 If Something Goes Wrong

**Stop immediately and:**
1. Press Ctrl+C to stop scheduler
2. Check `storage/logs/app.log` for errors
3. Check LinkedIn for any warnings/restrictions
4. Wait 7-14 days before resuming
5. When resuming, use even more conservative limits

**Common issues:**

**"Could not connect to Chrome on port 9222"**
→ Chrome with debugging isn't running. Restart it with the command above.

**"Login may have failed"**
→ You're not logged into LinkedIn in the Chrome debugging window. Log in manually.

**"Daily limit reached"**
→ Normal — the system is protecting you. It will resume tomorrow.

**Actions not executing**
→ Check that you approved suggestions in Telegram first (`python main.py --mode poll`)

**Telegram not receiving messages**
→ Verify bot_token and chat_id in settings.yaml. Test with `python main.py --mode summary`

---

## 📊 Success Metrics

After 1 week, you should see:
- 5-7 likes executed per day (with random off days)
- 0 errors in logs
- 0 warnings from LinkedIn
- Telegram notifications arriving consistently
- Database growing: `sqlite3 storage/linkedin_growth.db "SELECT COUNT(*) FROM posts;"`

If you see this, you're ready to gradually ramp up limits.
