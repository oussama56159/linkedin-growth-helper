@echo off
echo Starting Chrome with remote debugging...
echo.
echo Chrome will open with a yellow bar at the top.
echo This is normal - it means the bot can connect to it.
echo.
echo IMPORTANT: Log into LinkedIn in this Chrome window!
echo.
"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\ChromeDebug
