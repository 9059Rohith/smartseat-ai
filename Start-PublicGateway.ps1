$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    if(-not (Test-Path 'local/public-runtime/index.html')){throw 'Run Build-PublicApp.ps1 first.'}
    $smartseatGateway=$null
    try {$smartseatGateway=Invoke-RestMethod 'http://127.0.0.1:8768/smartseat/gateway-health' -TimeoutSec 3}catch{}
    if($smartseatGateway.app -eq 'smartseat-gateway'){return}
    if(Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue){throw 'Port 8768 is occupied by an unexpected service. It was left unchanged.'}
    Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList @("`"$PSScriptRoot/connector/public-app.cjs`"") -WindowStyle Hidden -WorkingDirectory $PSScriptRoot -RedirectStandardOutput "$PSScriptRoot/local/public-gateway.log" -RedirectStandardError "$PSScriptRoot/local/public-gateway-error.log" | Out-Null
    for($smartseatAttempt=0;$smartseatAttempt -lt 20;$smartseatAttempt++){
        Start-Sleep -Milliseconds 300
        try {$smartseatGateway=Invoke-RestMethod 'http://127.0.0.1:8768/smartseat/gateway-health' -TimeoutSec 2;if($smartseatGateway.app -eq 'smartseat-gateway'){return}}catch{}
    }
    throw 'Public gateway did not start. Check local/public-gateway-error.log.'
} finally {Pop-Location}
