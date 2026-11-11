param([int]$Port=0)
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    & '.\.venv\Scripts\python.exe' 'operations/watchdog.py' --check-database | Out-Null
    if($LASTEXITCODE -ne 0){throw 'The restaurant database is missing or unrecognized. No replacement database was created.'}
    $smartseatConfig=Get-Content -LiteralPath 'local/public-connection.json' -Raw | ConvertFrom-Json
    $smartseatOrigin=[Uri]$smartseatConfig.engine_origin
    if($Port -eq 0){$Port=if($smartseatConfig.engine_port){[int]$smartseatConfig.engine_port}else{8766}}
    if($smartseatOrigin.Scheme -ne 'https'){throw 'The public engine connector must use HTTPS.'}
    $env:SMARTSEAT_PUBLIC_HOSTS=$smartseatOrigin.Host
    $env:SMARTSEAT_PUBLIC_ORIGINS=(@($smartseatConfig.public_origin,$smartseatConfig.public_app_origin)|Where-Object {$_}|Select-Object -Unique)-join ','
    Write-Host "Starting the restaurant engine for $($smartseatConfig.public_origin). Keep this computer online."
    & '.\.venv\Scripts\python.exe' app.py --webcam --port $Port
} finally {Pop-Location}
