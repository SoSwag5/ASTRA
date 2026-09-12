param([ValidateSet('Enable','Disable','Remove','RunNow','Status')][string]$Action='Status',[ValidateSet(3,6,12,24)][int]$Hours=6)
$ErrorActionPreference='Stop'
$taskName='Ayham Job Hunter - Local Discovery'
$projectRoot=Split-Path $PSScriptRoot -Parent
$task=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($Action -eq 'Remove' -and $task) {Unregister-ScheduledTask -TaskName $taskName -Confirm:$false}
if ($Action -eq 'Disable' -and $task) {Disable-ScheduledTask -TaskName $taskName | Out-Null}
if ($Action -eq 'RunNow') {
    if (-not $task) {throw 'Enable the task first, or use Scan all sources in Discovery.'}
    Start-ScheduledTask -TaskName $taskName
}
if ($Action -eq 'Enable') {
    $pythonPath=Join-Path $projectRoot '.venv\Scripts\python.exe'
    $scriptPath=Join-Path $PSScriptRoot 'discovery_once.py'
    $taskAction=New-ScheduledTaskAction -Execute $pythonPath -Argument ('"'+$scriptPath+'" --trigger SCHEDULED') -WorkingDirectory $projectRoot
    $trigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Hours $Hours)
    $taskSettings=New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $taskSettings.WakeToRun=$false
    $principal=New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -Settings $taskSettings -Principal $principal -Description 'Opt-in local public ATS discovery. No application submission. Does not wake the computer.' -Force | Out-Null
}
$task=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    $info=Get-ScheduledTaskInfo -TaskName $taskName
    @{installed=$true;enabled=($task.State -ne 'Disabled');Frequency=$task.Triggers[0].Repetition.Interval;StartWhenAvailable=$task.Settings.StartWhenAvailable;WakeToRun=$task.Settings.WakeToRun;NetworkRequired=$task.Settings.RunOnlyIfNetworkAvailable;LastRunTime=$info.LastRunTime.ToString('o');NextRunTime=$info.NextRunTime.ToString('o');LastTaskResult=$info.LastTaskResult;TaskName=$taskName} | ConvertTo-Json
}
else { Write-Output '{"installed":false,"enabled":false,"StartWhenAvailable":true,"WakeToRun":false}' }
