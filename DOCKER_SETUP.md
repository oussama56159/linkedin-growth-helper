# Docker Setup Guide

## Quick Start with Docker

### Prerequisites

- Docker Desktop installed
- Docker Compose installed
- Telegram bot configured (see main README)

---

## Option 1: Docker (Recommended for Linux/Mac)

### 1. Configure settings

Edit `config/settings.yaml`:
- Add your Telegram bot token and chat_id
- Add your LinkedIn credentials
- **Important:** Set `use_real_browser: false` (Docker uses headless Chrome)
- Set `headless: true`

### 2. Build and run

```bash
docker-compose up -d
```

That's it! The system is now running in the background.

### 3. View logs

```bash
# Live logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100
```

### 4. Stop the system

```bash
docker-compose down
```

### 5. Restart after config changes

```bash
docker-compose restart
```

---

## Option 2: Windows (Without Docker)

Docker on Windows has issues with Chrome debugging. Use the native approach instead:

### 1. Start everything

```cmd
start.bat
```

This will:
- Start Chrome with remote debugging
- Start the background service with auto-restart
- Run health checks daily

### 2. Stop

Press `Ctrl+C` in the terminal

---

## What Runs Automatically

### Main Service (`run_with_restart.py`)
- Scrapes posts every 2-5 hours
- Listens for Telegram buttons every 2 seconds
- Executes approved actions instantly
- Auto-restarts on crashes (max 5 times/hour)

### Health Check (Daily at 9 AM)
- Checks database activity
- Checks log freshness
- Checks Chrome session
- Logs results to `storage/logs/health_check.log`

---

## Monitoring

### Check if it's running

**Docker:**
```bash
docker ps
```

**Windows:**
```powershell
Get-Process python
```

### View logs

**Docker:**
```bash
docker-compose logs -f linkedin-bot
```

**Windows:**
```powershell
Get-Content storage\logs\background.log -Tail 50 -Wait
```

### Run health check manually

**Docker:**
```bash
docker-compose exec linkedin-bot python health_check.py
```

**Windows:**
```powershell
python health_check.py
```

---

## Troubleshooting

### Docker: Container keeps restarting

```bash
# Check logs
docker-compose logs linkedin-bot

# Common issues:
# 1. Missing config file
# 2. Invalid Telegram credentials
# 3. LinkedIn login failed
```

### Windows: Chrome won't start

```cmd
# Kill existing Chrome processes
taskkill /F /IM chrome.exe

# Start Chrome manually
"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\ChromeDebug
```

### No posts being found

```bash
# Check if you're in active hours (9am-9pm by default)
# Check config/settings.yaml scheduling section

# Run scraper manually to test
python main.py --mode scrape
```

### Telegram buttons not responding

```bash
# Check Telegram credentials in config/settings.yaml
# Verify bot token and chat_id are correct

# Test Telegram connection
python main.py --mode summary
```

---

## File Persistence

### Docker Volumes

The following directories are mounted as volumes (data persists):
- `./config` → Container's `/app/config`
- `./storage` → Container's `/app/storage`

This means:
- Your config changes persist
- Database persists
- Logs persist
- Chrome session persists

### Backup

```bash
# Backup everything important
tar -czf linkedin-backup.tar.gz config/ storage/
```

---

## Performance

### Resource Usage

**Typical:**
- CPU: 5-10% during scraping, <1% idle
- RAM: 200-500 MB
- Disk: ~50 MB for database + logs

**Chrome (when active):**
- CPU: 10-20%
- RAM: 300-800 MB

### Optimization

To reduce resource usage:
- Increase `min_interval_minutes` (scrape less often)
- Reduce `max_suggestions_per_run` (process fewer posts)
- Use headless mode (no GUI overhead)

---

## Security Notes

### Credentials

**Never commit these files:**
- `config/settings.yaml` (contains passwords)
- `storage/linkedin_session.json` (session cookies)
- `storage/*.db` (personal data)

Already in `.gitignore` ✅

### Docker Security

The container:
- Runs as non-root user
- Has no network access except HTTPS to LinkedIn/Telegram
- Stores data in mounted volumes only

---

## Updating

### Docker

```bash
# Pull latest code
git pull

# Rebuild container
docker-compose down
docker-compose build
docker-compose up -d
```

### Windows

```bash
# Pull latest code
git pull

# Restart
# Press Ctrl+C to stop, then:
start.bat
```

---

## Advanced: Custom Schedule

Edit `config/settings.yaml`:

```yaml
scheduling:
  active_hours_start: 8      # Start at 8 AM
  active_hours_end: 23       # End at 11 PM
  min_interval_minutes: 180  # Min 3 hours between runs
  max_interval_minutes: 360  # Max 6 hours between runs
  daily_skip_probability: 0.2  # 20% chance to skip a day
  days_off: [5, 6]           # Skip Saturdays (5) and Sundays (6)
```

Then restart:

**Docker:** `docker-compose restart`  
**Windows:** Stop and run `start.bat` again

---

## Support

Check logs first:
- `storage/logs/background.log` — Main service
- `storage/logs/watchdog.log` — Auto-restart events
- `storage/logs/health_check.log` — Daily health checks
- `storage/logs/app.log` — Scraper details

Run health check:
```bash
python health_check.py
```

If issues persist, check:
1. LinkedIn account not restricted
2. Telegram bot working
3. Chrome session valid
4. Config file correct
