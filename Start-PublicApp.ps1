$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    $smartseatPython=Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    $smartseatConfig=Get-Content 'local/public-connection.json' -Raw | ConvertFrom-Json
    & $smartseatPython 'operations/watchdog.py' --check-database | Out-Null
    if($LASTEXITCODE -ne 0){throw 'The restaurant database is missing or unrecognized. Restore a verified backup before starting; no new database was created.'}
    $smartseatShell=(Get-Process -Id $PID).Path
    $smartseatEngine=$null
    try {$smartseatEngine=Invoke-RestMethod 'http://127.0.0.1:8766/api/health' -TimeoutSec 3}catch{}
    if($smartseatEngine -and $smartseatEngine.app -ne 'smartseat'){throw 'Port 8766 belongs to another app. It was left unchanged.'}
    if(-not $smartseatEngine){
        Start-Process -FilePath $smartseatShell -ArgumentList @('-NoProfile','-File',"`"$PSScriptRoot/Start-PublicEngine.ps1`"") -WindowStyle Hidden -RedirectStandardOutput "$PSScriptRoot/local/server-dedicated.log" -RedirectStandardError "$PSScriptRoot/local/server-dedicated-error.log" | Out-Null
        for($smartseatAttempt=0;$smartseatAttempt -lt 20;$smartseatAttempt++){
            Start-Sleep -Milliseconds 500
            try {$smartseatEngine=Invoke-RestMethod 'http://127.0.0.1:8766/api/health' -TimeoutSec 2;if($smartseatEngine.app -eq 'smartseat'){break}}catch{}
        }
    }
    if($smartseatEngine.app -ne 'smartseat'){throw 'The restaurant engine did not start. Check local/server-dedicated-error.log.'}
    $smartseatRouter=$null
    try {$smartseatRouter=Invoke-RestMethod 'http://127.0.0.1:8767/smartseat-engine/api/health' -TimeoutSec 3}catch{}
    if($smartseatRouter.app -ne 'smartseat'){
        Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList @("`"$PSScriptRoot/connector/router.cjs`"") -WindowStyle Hidden -RedirectStandardOutput "$PSScriptRoot/local/connector-router.log" -RedirectStandardError "$PSScriptRoot/local/connector-router-error.log" | Out-Null
        Start-Sleep -Milliseconds 700
    }
    try {$null=Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 3}
    catch {
        $smartseatConfig=Get-Content 'local/public-connection.json' -Raw | ConvertFrom-Json
        $smartseatDomain=([Uri]$smartseatConfig.engine_origin).Host
        Start-Process -FilePath (Get-Command ngrok.exe).Source -ArgumentList @('http','http://127.0.0.1:8767',"--url=https://$smartseatDomain") -WindowStyle Hidden -RedirectStandardOutput "$PSScriptRoot/local/ngrok-smartseat.log" -RedirectStandardError "$PSScriptRoot/local/ngrok-smartseat-error.log" | Out-Null
        Start-Sleep -Seconds 2
    }
    & $smartseatPython 'connector/ensure_connection.py'
    if($LASTEXITCODE -ne 0){throw 'The public connector could not be verified.'}
    if($smartseatConfig.public_app_origin){& "$PSScriptRoot/Start-PublicGateway.ps1";Write-Host "SmartSeat public application: $($smartseatConfig.public_app_origin)/smartseat/"}
    else {Write-Host 'SmartSeat engine is running locally at http://127.0.0.1:8766/.'}
} finally {Pop-Location}
