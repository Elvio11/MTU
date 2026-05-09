$ErrorActionPreference = "Continue"

Write-Host "Starting MTUS System..." -ForegroundColor Cyan

# Start Redis
Write-Host "Starting Redis..." -ForegroundColor Yellow
Start-Process -FilePath "D:\Trader\redis\redis-server.exe" -ArgumentList "--port 6379" -NoNewWindow

# Start Dashboard Bridge
Write-Host "Starting Dashboard Bridge..." -ForegroundColor Yellow
$env:PYTHONPATH = "D:\Trader"
Start-Process -FilePath "python" -ArgumentList "src\python\agents\dashboard_bridge.py" -WorkingDirectory "D:\Trader" -NoNewWindow

# Start Dashboard
Write-Host "Starting Dashboard..." -ForegroundColor Yellow
Start-Process -FilePath "cmd" -ArgumentList "/c","npm run start" -WorkingDirectory "D:\Trader\dashboard" -NoNewWindow

Start-Sleep -Seconds 3
Write-Host "All services started!" -ForegroundColor Green