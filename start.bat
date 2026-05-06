@echo off
echo ========================================
echo LinkedIn Growth System - Starting...
echo ========================================
echo.

REM Check if Chrome is running
tasklist /FI "IMAGENAME eq chrome.exe" 2>NUL | find /I /N "chrome.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo Chrome is already running
) else (
    echo Starting Chrome with remote debugging...
    start "" "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\ChromeDebug
    timeout /t 5 /nobreak >nul
)

echo.
echo Starting LinkedIn Growth System...
echo.
echo The system will:
echo   - Scrape posts every 2-5 hours
echo   - Listen for Telegram button presses
echo   - Execute approved actions instantly
echo   - Auto-restart on crashes
echo.
echo Press Ctrl+C to stop
echo ========================================
echo.

python run_with_restart.py
