[CmdletBinding()]
param(
    [ValidateSet('Install','Status','Enable','Disable','Run','Remove')]
    [string]$Mode = 'Status',
    [switch]$Disabled
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$watchdogPath = Join-Path $PSScriptRoot 'watchdog.py'
$taskName = 'SmartSeat Health Monitor'
$shellPath = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$startupFolder = [Environment]::GetFolderPath('Startup')
$startupFile = Join-Path $startupFolder 'SmartSeat Health Monitor.vbs'
$disabledFile = $startupFile + '.disabled'
$arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Mode Run'
$monitorExecutable = $null
if (Test-Path -LiteralPath $pythonPath -PathType Leaf) {
    # Watchdog uses only stdlib. Run the actual interpreter directly so the task
    # owns the monitor rather than a PowerShell/venv launcher with orphan children.
    $monitorExecutable = (& $pythonPath -c "import pathlib,sys; print(pathlib.Path(sys._base_executable).with_name('pythonw.exe'))").Trim()
}
$monitorArguments = '"' + $watchdogPath + '"'
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value

function Get-AccountSid([string]$account) {
    if ($account -match '^S-1-') { return $account }
    return ([System.Security.Principal.NTAccount]::new($account)).Translate([System.Security.Principal.SecurityIdentifier]).Value
}

function Test-AccessDenied($failure) {
    $exception = $failure.Exception
    while ($exception) {
        if ($exception.HResult -eq -2147024891 -or
            ($exception.PSObject.Properties['NativeErrorCode'] -and $exception.NativeErrorCode -eq 5)) { return $true }
        $exception = $exception.InnerException
    }
    return ($failure.FullyQualifiedErrorId -match '0x80070005|HRESULT 0x80070005')
}

if ($Mode -eq 'Run') {
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $watchdogPath -PathType Leaf)) {
        throw 'SmartSeat monitor runtime is unavailable.'
    }
    Push-Location $projectRoot
    try { & $pythonPath $watchdogPath; exit $LASTEXITCODE }
    finally { Pop-Location }
}

if ($Mode -eq 'Remove') {
    $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existingTask) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
    foreach ($candidate in @($startupFile, $disabledFile)) {
        if (Test-Path -LiteralPath $candidate) { Remove-Item -LiteralPath $candidate }
    }
    Write-Output 'SmartSeat logon startup removed. An already-running monitor is unchanged.'
    exit 0
}

if ($Mode -eq 'Install') {
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $watchdogPath -PathType Leaf)) {
        throw 'SmartSeat monitor runtime is unavailable.'
    }
    try {
        if (-not $monitorExecutable -or -not (Test-Path -LiteralPath $monitorExecutable -PathType Leaf)) {
            throw 'SmartSeat hidden monitor interpreter is unavailable.'
        }
        $action = New-ScheduledTaskAction -Execute $monitorExecutable -Argument $monitorArguments -WorkingDirectory $projectRoot
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
        $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
            -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        if ($Disabled) { $settings.Enabled = $false }
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
            -Principal $principal -Settings $settings -Description 'Per-user aggregate SmartSeat health monitor; guarded recovery; requires signed-in awake computer.' -Force | Out-Null
        $registered = Get-ScheduledTask -TaskName $taskName
        if ($registered.Actions[0].Execute -ne $monitorExecutable -or
            $registered.Actions[0].Arguments -ne $monitorArguments -or
            [string]$registered.Principal.RunLevel -ne 'Limited' -or
            [string]$registered.Principal.LogonType -ne 'Interactive' -or
            (Get-AccountSid $registered.Principal.UserId) -ne $userSid -or
            $registered.Triggers.Count -ne 1 -or
            $registered.Triggers[0].CimClass.CimClassName -ne 'MSFT_TaskLogonTrigger' -or
            (Get-AccountSid $registered.Triggers[0].UserId) -ne $userSid -or
            [bool]$registered.Settings.Enabled -eq [bool]$Disabled) {
            throw 'SmartSeat monitor task verification failed.'
        }
    } catch {
        if (-not (Test-AccessDenied $_)) { throw }
        # Only a real access-denied result permits the per-user Startup fallback.
        $command = '"' + $shellPath + '" ' + $arguments
        $vbs = 'CreateObject("WScript.Shell").Run "' + $command.Replace('"','""') + '", 0, False' + "`r`n"
        $destination = if ($Disabled) { $disabledFile } else { $startupFile }
        [IO.File]::WriteAllText($destination, $vbs, [Text.Encoding]::Unicode)
        if ([IO.File]::ReadAllText($destination) -ne $vbs) { throw 'SmartSeat Startup fallback verification failed.' }
    }
}

if ($Mode -in @('Enable','Disable')) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        if ($Mode -eq 'Enable') { Enable-ScheduledTask -TaskName $taskName | Out-Null }
        else { Disable-ScheduledTask -TaskName $taskName | Out-Null }
    } elseif ($Mode -eq 'Enable' -and (Test-Path -LiteralPath $disabledFile)) {
        Move-Item -LiteralPath $disabledFile -Destination $startupFile
    } elseif ($Mode -eq 'Disable' -and (Test-Path -LiteralPath $startupFile)) {
        Move-Item -LiteralPath $startupFile -Destination $disabledFile
    } else { throw 'SmartSeat monitor startup is not installed.' }
}

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    [pscustomobject]@{
        installed=$true; mechanism='scheduled_task'; enabled=[bool]$task.Settings.Enabled
        state=[string]$task.State; logon_type=[string]$task.Principal.LogonType
        run_level=[string]$task.Principal.RunLevel; logon_triggers=$task.Triggers.Count
        action_verified=($task.Actions[0].Execute -eq $monitorExecutable -and $task.Actions[0].Arguments -eq $monitorArguments)
        user_verified=((Get-AccountSid $task.Principal.UserId) -eq $userSid -and (Get-AccountSid $task.Triggers[0].UserId) -eq $userSid)
        wake_to_run=[bool]$task.Settings.WakeToRun
    } | ConvertTo-Json
} else {
    [pscustomobject]@{
        installed=((Test-Path -LiteralPath $startupFile) -or (Test-Path -LiteralPath $disabledFile))
        mechanism='startup_folder'; enabled=(Test-Path -LiteralPath $startupFile)
        action_verified=if(Test-Path -LiteralPath $startupFile){[IO.File]::ReadAllText($startupFile).Contains($PSCommandPath)}elseif(Test-Path -LiteralPath $disabledFile){[IO.File]::ReadAllText($disabledFile).Contains($PSCommandPath)}else{$false}
        wake_to_run=$false
    } | ConvertTo-Json
}
