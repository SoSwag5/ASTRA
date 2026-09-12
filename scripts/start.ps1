param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force $runtimeDir | Out-Null
$pidPath = Join-Path $runtimeDir 'server.json'
if (Test-Path $pidPath) {
    $previous = Get-Content -Raw $pidPath | ConvertFrom-Json
    $existing = Get-Process -Id $previous.pid -ErrorAction SilentlyContinue
    if ($existing -and [Math]::Abs(($existing.StartTime.ToUniversalTime() - ([datetime]$previous.started).ToUniversalTime()).TotalSeconds) -lt 1) {
        Write-Output 'ASTRA is already running at http://localhost:8787'
        exit 0
    }
}
$listener = Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw 'Port 8787 is already occupied. Stop the existing app using its own launcher; no process was terminated.' }
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
& (Join-Path $PSScriptRoot 'protect_local_data.ps1')
$server = Start-Process -FilePath $pythonPath -ArgumentList '-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8787','--no-access-log' -WorkingDirectory $projectRoot -RedirectStandardOutput (Join-Path $runtimeDir 'server.out.log') -RedirectStandardError (Join-Path $runtimeDir 'server.err.log') -WindowStyle Hidden -PassThru
@{pid=$server.Id; started=$server.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content $pidPath
for ($attempt=0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8787/api/health'
        if ($health.version -ne '1.0.0-rc.1' -or $health.stale) { throw 'An older app process is still running on port 8787.' }
        $owned = Get-CimInstance Win32_Process -Filter "ProcessId = $($health.pid)"
        if ($health.pid -ne $server.Id -and $owned.ParentProcessId -ne $server.Id) { throw 'Port is served by another process.' }
        $serviceProcess = Get-Process -Id $health.pid -ErrorAction Stop
        @{pid=$serviceProcess.Id; started=$serviceProcess.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content $pidPath
        if (-not $NoBrowser) { Start-Process 'http://localhost:8787' }
        Write-Output 'ASTRA is running at http://localhost:8787'
        exit 0
    } catch { Start-Sleep -Milliseconds 500 }
}
throw 'Server did not become ready. See .runtime/server.err.log.'
