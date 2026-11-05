param([string]$Project='smartseat-ai-9059',[string]$Scope='rohiths-projects-5e14931b')
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    npm.cmd run build --prefix web
    if($LASTEXITCODE -ne 0){throw 'Frontend build failed.'}
    $smartseatStage=Join-Path $PSScriptRoot 'local/public-site'
    New-Item -ItemType Directory -Path $smartseatStage -Force | Out-Null
    Copy-Item -Path 'web/dist/*' -Destination $smartseatStage -Recurse -Force
    foreach($smartseatFile in @('api','lib','vercel.json','package.json','package-lock.json')) {
        Copy-Item -LiteralPath (Join-Path 'deployment' $smartseatFile) -Destination $smartseatStage -Recurse -Force
    }
    Copy-Item -LiteralPath 'deployment/.vercelignore' -Destination (Join-Path $smartseatStage '.vercelignore') -Force
    vercel.cmd link --yes --project $Project --scope $Scope --cwd $smartseatStage
    if($LASTEXITCODE -ne 0){throw 'Vercel project linking failed.'}
    vercel.cmd deploy --prod --yes --scope $Scope --cwd $smartseatStage
    if($LASTEXITCODE -ne 0){throw 'Vercel deployment failed.'}
} finally {Pop-Location}
