param(
    [switch]$Demo,
    [switch]$Setup,
    [ValidateRange(1024,65535)][int]$Port = 8765,
    [ValidateRange(1,3600)][int]$GreetingSeconds
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $smartseatPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $smartseatStamp = Join-Path $PSScriptRoot '.venv\requirements-installed.sha256'
    $smartseatRequirements = (Get-FileHash -LiteralPath 'requirements.txt' -Algorithm SHA256).Hash
    $smartseatInstalled = if (Test-Path -LiteralPath $smartseatStamp) {
        (Get-Content -LiteralPath $smartseatStamp -Raw).Trim()
    }
    if ($Setup -or $smartseatInstalled -ne $smartseatRequirements -or -not (Test-Path -LiteralPath $smartseatPython)) {
        if (-not (Test-Path -LiteralPath $smartseatPython)) {
            python -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 and try again.' }
        }
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            uv pip install --python $smartseatPython -r requirements.txt
        } else {
            & $smartseatPython -m pip install -r requirements.txt
        }
        if ($LASTEXITCODE -ne 0) { throw 'Python dependencies could not be installed.' }
        Set-Content -LiteralPath $smartseatStamp -Value $smartseatRequirements -Encoding ascii
    }
    $smartseatVisionHash = (Get-FileHash -LiteralPath 'requirements-vision.txt' -Algorithm SHA256).Hash
    $smartseatVisionStamp = Join-Path $PSScriptRoot '.venv\vision-installed.sha256'
    $smartseatVisionInstalled = if (Test-Path -LiteralPath $smartseatVisionStamp) { (Get-Content -LiteralPath $smartseatVisionStamp -Raw).Trim() }
    if ($Setup -or $smartseatVisionInstalled -ne $smartseatVisionHash) {
        $env:UV_HTTP_TIMEOUT = '300'
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            uv pip install --python $smartseatPython --index-strategy unsafe-best-match -r requirements-vision.txt
        } else { & $smartseatPython -m pip install -r requirements-vision.txt }
        if ($LASTEXITCODE -ne 0) { throw 'The local table model dependencies could not be installed.' }
        Set-Content -LiteralPath $smartseatVisionStamp -Value $smartseatVisionHash -Encoding ascii
    }
    if (-not (Test-Path -LiteralPath 'models/grounding-dino-tiny/model.safetensors')) {
        & $smartseatPython download_table_model.py
        if ($LASTEXITCODE -ne 0) { throw 'The public table model could not be downloaded.' }
    }
    if ($Setup -or -not (Test-Path -LiteralPath 'web/dist/index.html')) {
        Push-Location web
        try {
            npm.cmd ci
            if ($LASTEXITCODE -ne 0) { throw 'The web dependencies could not be installed.' }
            npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw 'The web application could not be built.' }
        } finally { Pop-Location }
    }
    $smartseatArgs = @('app.py', '--port', $Port)
    if ($Demo) { $smartseatArgs += '--demo' }
    else { $smartseatArgs += '--webcam' }
    if ($GreetingSeconds) { $smartseatArgs += @('--greeting-seconds', $GreetingSeconds) }
    Write-Host "Open http://127.0.0.1:$Port/ after startup. Ctrl+C stops SmartSeat."
    & $smartseatPython @smartseatArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally { Pop-Location }

