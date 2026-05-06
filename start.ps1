# LinkedIn Growth System - PowerShell Startup Script

Write-Host "========================================"
Write-Host "LinkedIn Growth System - Starting..."
Write-Host "========================================"
Write-Host ""

# Check if Chrome is running
$chromeRunning = Get-Process chrome -ErrorAction SilentlyContinue

if ($chromeRunning) {
    Write-Host "Chrome is already running"
} else {
    Write-Host "Starting Chrome with remote debugging..."
    $chromePath = "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    
    if (Test-Path $chromePath) {
        Start-Process $chromePath -ArgumentList "--remote-debugging-port=9222","--user-data-dir=C:\ChromeDebug"
        Start-Sleep -Seconds 5
    } else {
        Write-Host "Chrome not found at $chromePath"
        Write-Host "Please start Chrome manually with debugging enabled"
    }
}

Write-Host ""
Write-Host "Starting LinkedIn Growth System..."
Write-Host ""
Write-Host "The system will:"
Write-Host "  - Scrape posts every 2-5 hours"
Write-Host "  - Listen for Telegram button presses"
Write-Host "  - Execute approved actions instantly"
Write-Host "  - Auto-restart on crashes"
Write-Host ""
Write-Host "Press Ctrl+C to stop"
Write-Host "========================================"
Write-Host ""

python run_with_restart.py
