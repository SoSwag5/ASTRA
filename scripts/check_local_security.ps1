$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$dataRoot=if ($env:HUNTER_DATA_DIR) {$env:HUNTER_DATA_DIR} else {Join-Path $projectRoot 'data'}
$allowed=@([System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value,'S-1-5-18','S-1-5-32-544')
$unsafe=0
$entries=@(Get-Item -LiteralPath $dataRoot)+@(Get-ChildItem -LiteralPath $dataRoot -Recurse -Force)
foreach ($entry in $entries) {
    foreach ($rule in (Get-Acl -LiteralPath $entry.FullName).Access) {
        $sid=$rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        if ($rule.AccessControlType -eq 'Allow' -and $sid -notin $allowed) {$unsafe++}
    }
}
$task=Get-ScheduledTask -TaskName 'Ayham Job Hunter - Local Discovery' -ErrorAction SilentlyContinue
$schedulerSafe=$true
if ($task) {
    $expected=Join-Path $projectRoot '.venv\Scripts\python.exe'
    $schedulerSafe=($task.Actions[0].Execute -eq $expected) -and (Test-Path -LiteralPath $expected) -and (-not $task.Settings.WakeToRun) -and ($task.Principal.RunLevel -eq 'Limited') -and ($task.Settings.MultipleInstances -eq 'IgnoreNew')
}
@{acl_safe=($unsafe -eq 0);scheduler_installed=[bool]$task;scheduler_safe=$schedulerSafe} | ConvertTo-Json -Compress
