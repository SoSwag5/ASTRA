$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pidPath = Join-Path $projectRoot '.runtime\server.json'
$stopped = $false
if (Test-Path $pidPath) {
    $record = Get-Content -Raw $pidPath | ConvertFrom-Json
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if ($process -and [Math]::Abs(($process.StartTime.ToUniversalTime() - ([datetime]$record.started).ToUniversalTime()).TotalSeconds) -lt 1) {
        $owned = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)"
        if ($owned.CommandLine -notlike '*uvicorn*backend.main:app*') { throw 'Recorded PID is not an ASTRA backend; refusing to stop it.' }
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($process.Id)"
        foreach ($child in $children) {
            if ($child.CommandLine -like '*uvicorn*backend.main:app*') { Stop-Process -Id $child.ProcessId }
        }
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
        $stopped = $true
    }
    Remove-Item -LiteralPath $pidPath
}
if ($stopped) { Write-Output 'ASTRA stopped.'; exit 0 }
# This stop.bat only stops the copy started from its own folder.
Write-Output 'No ASTRA started from this folder is running. Nothing was stopped.'
Write-Output 'If http://localhost:8787 still opens, another ASTRA copy is running: double-click stop.bat in that copy''s folder.'
