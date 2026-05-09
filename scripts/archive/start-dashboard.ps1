# MTUS Dashboard Quick Start Script
# Run this to start the frontend with mock data for testing

Write-Host "Starting MTUS Dashboard..." -ForegroundColor Cyan

# Check if dashboard is built
if (!(Test-Path "D:\Trader\dashboard\.next")) {
    Write-Host "Building dashboard first..." -ForegroundColor Yellow
    cd D:\Trader\dashboard
    npm run build
}

# Start dashboard in production mode (bypasses Turbopack bug)
Write-Host "Starting dashboard on http://localhost:3000" -ForegroundColor Green
Start-Process "npm" -ArgumentList "run","start" -WorkingDirectory "D:\Trader\dashboard" -NoNewWindow

Write-Host ""
Write-Host "Dashboard available at: http://localhost:3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "NOTE: Backend services must be running for live data:" -ForegroundColor Yellow
Write-Host "  - Redis (for data persistence)" -ForegroundColor Gray
Write-Host "  - Dashboard Bridge (AGT-11) on port 3001" -ForegroundColor Gray
Write-Host "  - Python trading agents" -ForegroundColor Gray
Write-Host ""
Write-Host "Without backend, dashboard shows 'Disconnected' status (expected)." -ForegroundColor Gray