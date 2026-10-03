param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force $runtimeDir | Out-Null
$pidPath = Join-Path $runtimeDir 'server.json'
# Expected start problems end with plain guidance and exit code 1, not a PowerShell error trace.
function Exit-WithGuidance([string[]]$Lines) {
    Write-Output ''
    $Lines | ForEach-Object { Write-Output $_ }
    Write-Output 'No other program was stopped.'
    exit 1
}
$portGuidance = @(
    'http://localhost:8787 always shows whichever ASTRA copy is already running, which may be an older version.',
    'To use this version:',
    '  1. Open the folder of the ASTRA copy that is running and double-click its own stop.bat.',
    '  2. Double-click Open ASTRA.bat in this folder again.',
    'If no other ASTRA copy is open, another program is using port 8787. Close that program first.'
)
if (Test-Path $pidPath) {
    $previous = Get-Content -Raw $pidPath | ConvertFrom-Json
    $existing = Get-Process -Id $previous.pid -ErrorAction SilentlyContinue
    if ($existing -and [Math]::Abs(($existing.StartTime.ToUniversalTime() - ([datetime]$previous.started).ToUniversalTime()).TotalSeconds) -lt 1) {
        try { $health = Invoke-RestMethod 'http://127.0.0.1:8787/api/health' }
        catch { Exit-WithGuidance @('ASTRA from this folder is still starting or is not responding.', 'Wait a few seconds, then double-click Open ASTRA.bat again. If this repeats, double-click stop.bat in this folder first.') }
        if ($health.version -ne (Get-Content -Raw (Join-Path $projectRoot 'VERSION')).Trim() -or $health.stale) {
            Exit-WithGuidance (@('ASTRA cannot open: a different or older ASTRA version is already running.') + $portGuidance)
        }
        if (-not $NoBrowser) { Start-Process 'http://localhost:8787/' }
        Write-Output 'ASTRA is already running at http://localhost:8787'
        exit 0
    }
}
$listener = Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue
if ($listener) { Exit-WithGuidance (@('ASTRA cannot open: port 8787 is already in use.') + $portGuidance) }
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
& (Join-Path $PSScriptRoot 'protect_local_data.ps1')
# The normal launcher opens the workspace, without developer trust exceptions.
$env:ASTRA_DEMO_ONLY = '0'
$env:ASTRA_DEV_ORIGIN = ''
$server = Start-Process -FilePath $pythonPath -ArgumentList '-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8787','--no-access-log' -WorkingDirectory $projectRoot -RedirectStandardOutput (Join-Path $runtimeDir 'server.out.log') -RedirectStandardError (Join-Path $runtimeDir 'server.err.log') -WindowStyle Hidden -PassThru
@{pid=$server.Id; started=$server.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content $pidPath
$servedByOther = $false
for ($attempt=0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8787/api/health'
        if ($health.version -ne (Get-Content -Raw (Join-Path $projectRoot 'VERSION')).Trim() -or $health.stale) { $servedByOther = $true; throw 'An older app process is still running on port 8787.' }
        $owned = Get-CimInstance Win32_Process -Filter "ProcessId = $($health.pid)"
        if ($health.pid -ne $server.Id -and $owned.ParentProcessId -ne $server.Id) { $servedByOther = $true; throw 'Port is served by another process.' }
        $serviceProcess = Get-Process -Id $health.pid -ErrorAction Stop
        @{pid=$serviceProcess.Id; started=$serviceProcess.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content $pidPath
        if (-not $NoBrowser) { Start-Process 'http://localhost:8787' }
        Write-Output 'ASTRA is running at http://localhost:8787'
        exit 0
    } catch { Start-Sleep -Milliseconds 500 }
}
if ($servedByOther) { Exit-WithGuidance (@('ASTRA cannot open: another program or ASTRA copy answered on port 8787.') + $portGuidance) }
Exit-WithGuidance @('ASTRA did not finish starting. Details are in .runtime\server.err.log in this folder.', 'Double-click stop.bat in this folder, then double-click Open ASTRA.bat again.')
