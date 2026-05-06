# Complete Setup Guide — Follow These Steps Exactly

## ✅ Step 1: Install Dependencies (DONE if no errors)

```bash
cd linkedin-growth-system
pip install -r requirements.txt
playwright install chromium
```

---

## ✅ Step 2: Setup Telegram Bot (DONE — you should have these)

- Bot token: `_____________________` (write it here)
- Chat ID: `_____________________` (write it here)

If you don't have these yet:
```bash
python main.py --mode setup
```

---

## ✅ Step 3: Edit config/settings.yaml

Open `config/settings.yaml` in your text editor and make these changes:

### 3a. Add your Telegram credentials:

Find this section:
```yaml
telegram:
  bot_token: "PASTE_YOUR_BOT_TOKEN_HERE"
  chat_id: "PASTE_YOUR_CHAT_ID_HERE"
```

Replace with your actual values from Step 2.

### 3b. Customize your targeting (IMPORTANT):

Find this section:
```yaml
targeting:
  keywords:
    - "agentic AI"
    - "AI agents"
    # ... more keywords
```

**Replace these with YOUR professional interests.** Examples:
- If you're in marketing: "digital marketing", "content strategy", "SEO"
- If you're in finance: "fintech", "blockchain", "investment"
- If you're in design: "UI/UX", "product design", "figma"

Same for hashtags — use ones relevant to YOUR niche.

### 3c. Make it ULTRA-SAFE for first week:

Find this section:
```yaml
limits:
  max_likes_per_day: 10
  max_comments_per_day: 4
  max_reposts_per_day: 2
  max_connections_per_day: 5
```

**Change to:**
```yaml
limits:
  max_likes_per_day: 5      # Start very low
  max_comments_per_day: 0   # Disable for week 1
  max_reposts_per_day: 0    # Disable for week 1
  max_connections_per_day: 0  # Disable (highest risk)
```

### 3d. Enable real browser mode:

Find this section:
```yaml
browser:
  use_real_browser: false
```

**Change to:**
```yaml
browser:
  use_real_browser: true    # CRITICAL for safety
```

**Save the file.**

---

## ✅ Step 4: Verify Configuration

Run the safety checker:

```bash
python safety_check.py
```

**Expected output:** Should show ✅ marks and no critical errors.

If you see ❌ errors, fix them in `config/settings.yaml` and run the check again.

---

## ✅ Step 5: Start Chrome with Remote Debugging (CRITICAL)

This is the most important step for safety. You need Chrome running in a special mode.

### Windows:

1. **Close ALL Chrome windows** (important!)
2. Open Command Prompt or PowerShell
3. Run this command:

```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\ChromeDebug
```

**Note:** If Chrome is installed elsewhere, adjust the path. Common locations:
- `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`
- `%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe`

### Mac:

1. **Close ALL Chrome windows**
2. Open Terminal
3. Run:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

### Linux:

1. **Close ALL Chrome windows**
2. Open Terminal
3. Run:

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

### What you should see:

- Chrome opens with a **yellow bar at the top** saying "Chrome is being controlled by automated test software"
- This is normal and expected!

### Now log into LinkedIn:

1. In this special Chrome window, go to linkedin.com
2. Log in with your credentials
3. Complete 2FA if you have it enabled
4. Browse around to make sure you're fully logged in
5. **Keep this Chrome window open** — don't close it!

---

## ✅ Step 6: Test Discovery (No Actions Yet)

Open a **NEW terminal/command prompt** (keep Chrome running in the other one).

Navigate to the project:
```bash
cd linkedin-growth-system
```

Run the discovery test:
```bash
python main.py --mode scrape
```

### What should happen:

1. Terminal shows: `Connected to real Chrome successfully`
2. You'll see: `Scraping hashtag: #...` messages
3. After 2-5 minutes, it finishes
4. **Check Telegram** — you should receive a message with post suggestions
5. Each suggestion has ✅ Approve and ❌ Reject buttons

### If you see errors:

**"Could not connect to Chrome on port 9222"**
→ Chrome with debugging isn't running. Go back to Step 5.

**"Not logged in"**
→ Log into LinkedIn in the Chrome debugging window.

**"No new suggestions this run"**
→ Normal if your hashtags don't have recent posts. Try different hashtags.

---

## ✅ Step 7: Test Approval & Execution

### 7a. Approve some suggestions:

1. Open Telegram
2. Look at the suggestions you received
3. **Tap ✅ on 2-3 posts you genuinely like** (important: only approve content you'd actually engage with)

### 7b. Poll for decisions:

```bash
python main.py --mode poll
```

**Expected output:** `Telegram decision: suggestion #X → approved`

### 7c. Execute approved actions:

```bash
python main.py --mode execute
```

### What should happen:

1. Terminal shows: `Executing X approved suggestions...`
2. You'll see delays between actions (15-45 seconds)
3. Messages like: `Executing like on https://linkedin.com/...`
4. Finally: `✅ like executed successfully`

### 7d. Verify on LinkedIn:

1. Go to your LinkedIn profile
2. Click "Activity" or check your notifications
3. You should see the likes you just made

**If actions executed successfully, you're ready for continuous mode!**

---

## ✅ Step 8: Go Continuous (Automated)

If Steps 6 and 7 worked perfectly, you can now run the scheduler.

**Make sure:**
- Chrome with debugging is still running (from Step 5)
- You're still logged into LinkedIn in that Chrome

Then run:
```bash
python scheduler.py
```

### What happens:

- Runs every 2-5 hours (randomized)
- Discovers posts → sends to Telegram → waits for your approval → executes
- Automatically skips some days (20% chance)
- Skips Sundays by default
- Respects daily limits (5 likes/day to start)

### To monitor:

Open another terminal and watch the logs:

**Mac/Linux:**
```bash
tail -f storage/logs/scheduler.log
```

**Windows:**
Open `storage/logs/scheduler.log` in Notepad and refresh it periodically.

### To stop:

Press **Ctrl+C** in the terminal running the scheduler.

---

## ✅ Step 9: Monitor for First 24 Hours

**Check every few hours:**

1. **Telegram:** Are suggestions arriving?
2. **Logs:** Any errors in `storage/logs/app.log`?
3. **LinkedIn:** Are actions completing successfully?
4. **LinkedIn warnings:** Any messages about "unusual activity"?

**If everything looks good after 24 hours, you're golden!**

---

## ✅ Step 10: Gradual Ramp-Up (After 1 Week)

If you've run for 1 week with no issues:

Edit `config/settings.yaml`:

```yaml
limits:
  max_likes_per_day: 8      # Increase from 5
  max_comments_per_day: 2   # Enable comments (carefully)
  max_reposts_per_day: 0    # Keep disabled
  max_connections_per_day: 0  # Keep disabled
```

Restart the scheduler:
```bash
# Stop with Ctrl+C, then:
python scheduler.py
```

**After 3 weeks of safe operation:**
```yaml
limits:
  max_likes_per_day: 10
  max_comments_per_day: 3
  max_reposts_per_day: 2
  max_connections_per_day: 0  # Still keep disabled
```

**After 4+ weeks:**
Consider enabling 2-3 connections/day, but only to highly relevant profiles.

**Never exceed:** 15 likes, 5 comments, 5 connects per day.

---

## 🚨 Warning Signs — Stop Immediately If You See:

- LinkedIn asks you to verify your identity
- Actions fail silently (button clicked but nothing happens)
- "Unusual activity" message from LinkedIn
- Connection requests get auto-rejected
- Your account gets restricted

**If this happens:**
1. Stop the scheduler (Ctrl+C)
2. Don't use the tool for 7-14 days
3. Use LinkedIn normally from your regular browser
4. When resuming, cut all limits in half

---

## 📊 Success Checklist (After 1 Week)

- [ ] 5-7 likes executed per day (with random off days)
- [ ] 0 errors in logs
- [ ] 0 warnings from LinkedIn
- [ ] Telegram notifications arriving consistently
- [ ] Actions completing successfully
- [ ] No unusual activity detected

**If all checked, you're ready to ramp up gradually!**

---

## 🆘 Common Issues

### "ModuleNotFoundError: No module named 'playwright'"
→ Run: `pip install -r requirements.txt`

### "Playwright executable not found"
→ Run: `playwright install chromium`

### "Could not connect to Chrome"
→ Chrome with debugging isn't running. See Step 5.

### "Telegram not receiving messages"
→ Check bot_token and chat_id in settings.yaml. Test with:
```bash
python main.py --mode summary
```

### "Actions not executing"
→ Did you approve suggestions in Telegram first? Run:
```bash
python main.py --mode poll
```

### Chrome closes when I close the terminal
→ Normal. Keep the terminal open, or run Chrome in the background.

---

## 🎯 Quick Reference Commands

```bash
# Test discovery only
python main.py --mode scrape

# Check for approvals
python main.py --mode poll

# Execute approved actions
python main.py --mode execute

# Full pipeline (all three)
python main.py --mode full

# Send daily summary
python main.py --mode summary

# Check configuration safety
python safety_check.py

# Run continuously
python scheduler.py
```

---

## ✅ You're All Set!

Follow these steps in order, and you'll have a safe, working LinkedIn growth system.

**Remember:** Start conservative, monitor closely, ramp up gradually.
