# MTUS Complete Startup Script
# Starts Redis, Dashboard Bridge, Agents, and Dashboard

$ErrorActionPreference = "Continue"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  MTUS Complete System Startup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Start Redis
Write-Host "[1/4] Starting Redis..." -ForegroundColor Yellow
$redisProc = Start-Process -FilePath "D:\Trader\redis\redis-server.exe" `
    -ArgumentList "--port 6379" `
    -NoNewWindow `
    -PassThru
Start-Sleep -Seconds 1

# Check if Redis started
try {
    $null = & "D:\Trader\redis\redis-cli.exe" ping
    Write-Host "  Redis: Running on port 6379" -ForegroundColor Green
} catch {
    Write-Host "  Redis: Already running or failed to start" -ForegroundColor Gray
}

# 2. Start Dashboard Bridge (AGT-11)
Write-Host "[2/4] Starting Dashboard Bridge (AGT-11)..." -ForegroundColor Yellow
$env:PYTHONPATH = "D:\Trader"
$bridgeProc = Start-Process -FilePath "python" `
    -ArgumentList "src\python\agents\dashboard_bridge.py" `
    -WorkingDirectory "D:\Trader" `
    -NoNewWindow `
    -PassThru
Start-Sleep -Seconds 2
Write-Host "  Dashboard Bridge: Started on port 3001" -ForegroundColor Green

# 3. Start Dashboard
Write-Host "[3/4] Starting Dashboard..." -ForegroundColor Yellow
$dashProc = Start-Process -FilePath "cmd" `
    -ArgumentList "/c","npm run start" `
    -WorkingDirectory "D:\Trader\dashboard" `
    -NoNewWindow `
    -PassThru
Start-Sleep -Seconds 3
Write-Host "  Dashboard: Started on http://localhost:3000" -ForegroundColor Green

# 4. Summary
Write-Host ""
Write-Host "[4/4] System Status:" -ForegroundColor Yellow
Write-Host "  Redis:        Running (port 6379)" -ForegroundColor Green
Write-Host "  Dashboard:    http://localhost:3000" -ForegroundColor Green
Write-Host "  WebSocket:    ws://localhost:3001" -ForegroundColor Green
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  MTUS System Started!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "NOTE: Python trading agents require proper Python environment." -ForegroundColor Yellow
Write-Host "      To run agents manually:" -ForegroundColor Gray
Write-Host "        cd D:\Trader" -ForegroundColor Gray
Write-Host "        set PYTHONPATH=D:\Trader" -ForegroundColor Gray
Write-Host "        python src\python\agents\heracles.py" -ForegroundColor Gray

# Open dashboard in browser
Start-Process "http://localhost:3000"