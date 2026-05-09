$env:PYTHONPATH = "D:\Trader"
Start-Process -FilePath "python" -ArgumentList "src\python\agents\nofx.py" -WorkingDirectory "D:\Trader" -NoNewWindow -PassThru
Start-Process -FilePath "python" -ArgumentList "src\python\agents\hermes.py" -WorkingDirectory "D:\Trader" -NoNewWindow -PassThru
Write-Host "nofx and hermes agents started"