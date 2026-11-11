$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    if(-not (Test-Path 'deployment/node_modules/@supabase/ssr/package.json')){npm.cmd ci --prefix deployment;if($LASTEXITCODE -ne 0){throw 'Gateway dependencies could not be installed.'}}
    if(-not (Test-Path 'web/node_modules/vite/package.json')){npm.cmd ci --prefix web;if($LASTEXITCODE -ne 0){throw 'Web dependencies could not be installed.'}}
    $env:VITE_SMARTSEAT_GATEWAY='1'
    try {npm.cmd run build --prefix web -- --base=/smartseat/ --outDir=../local/public-runtime;if($LASTEXITCODE -ne 0){throw 'Public application build failed.'}}
    finally {Remove-Item Env:VITE_SMARTSEAT_GATEWAY -ErrorAction SilentlyContinue}
    if((Get-Content 'local/public-runtime/index.html' -Raw) -notmatch '/smartseat/assets/'){throw 'The web build has the wrong public base path.'}
} finally {Pop-Location}
