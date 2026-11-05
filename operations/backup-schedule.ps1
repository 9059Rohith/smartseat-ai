[CmdletBinding()]
param(
    [ValidateSet('Install','Status','Run','Remove')]
    [string]$Mode = 'Status',
    [string]$TaskName = 'SmartSeat Encrypted Backup',
    [string]$DailyAt = '02:30'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$pythonWindowlessPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$backupScript = Join-Path $PSScriptRoot 'backup.py'
$projectRef = 'tnwrnwhitnbxuhdfuwvh'

if ($Mode -eq 'Run') {
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw 'SmartSeat virtual environment is unavailable.'
    }
    & $pythonPath $backupScript create --cloud-project $projectRef
    exit $LASTEXITCODE
}
if ($Mode -eq 'Remove') {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output 'Backup task removed; encrypted archives retained.'
    exit 0
}
if ($Mode -eq 'Install') {
    if (-not (Test-Path -LiteralPath $pythonWindowlessPath -PathType Leaf)) {
        throw 'SmartSeat virtual environment is unavailable.'
    }
    $time = [datetime]::ParseExact($DailyAt, 'HH:mm', [cultureinfo]::InvariantCulture)
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $arguments = '"' + $backupScript + '" create --cloud-project ' + $projectRef
    $action = New-ScheduledTaskAction -Execute $pythonWindowlessPath -Argument $arguments -WorkingDirectory $projectRoot
    $daily = New-ScheduledTaskTrigger -Daily -At $time
    $logon = New-ScheduledTaskTrigger -AtLogOn -User $user
    # Interactive preserves the signed-in user's DPAPI profile and CLI login.
    # No password is stored; backups run while this user is logged on.
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 15) -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($daily,$logon) `
        -Principal $principal -Settings $settings `
        -Description 'Daily and logon SmartSeat encrypted SQLite + read-only Supabase application snapshot; CurrentUser DPAPI.' -Force | Out-Null
}
$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{
    TaskName = $task.TaskName
    State = [string]$task.State
    LogonType = [string]$task.Principal.LogonType
    RunLevel = [string]$task.Principal.RunLevel
    Actions = @($task.Actions | ForEach-Object { @{ Execute=$_.Execute; Arguments=$_.Arguments; WorkingDirectory=$_.WorkingDirectory } })
    Triggers = @($task.Triggers | ForEach-Object { @{ Type=$_.CimClass.CimClassName; StartBoundary=$_.StartBoundary; Enabled=$_.Enabled } })
    StartWhenAvailable = $task.Settings.StartWhenAvailable
    MultipleInstances = [string]$task.Settings.MultipleInstances
    LastRunTime = $info.LastRunTime.ToString('o')
    LastTaskResult = $info.LastTaskResult
    NextRunTime = $info.NextRunTime.ToString('o')
} | ConvertTo-Json -Depth 5
