$ErrorActionPreference = "SilentlyContinue"
$result = D:\Trader\redis\redis-cli.exe --eval "return redis.call('PUBLISH', 'health_check', 'test-message')", 0
Write-Host "Publish test result: $result"