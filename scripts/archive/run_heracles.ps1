$env:PYTHONPATH = "D:\Trader"
Start-Process -FilePath "python" -ArgumentList "src\python\agents\heracles.py" -WorkingDirectory "D:\Trader" -NoNewWindow -PassThru
Write-Host "Heracles agent started"