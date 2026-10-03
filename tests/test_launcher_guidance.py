"""The Windows launchers explain expected start problems without a PowerShell error trace.

Each test copies the real scripts/start.ps1 or scripts/stop.ps1 into a fictional
temporary project folder and runs it in Windows PowerShell with every process,
port and HTTP cmdlet replaced by a recording mock. Nothing listens, is started,
is stopped or is requested on port 8787; a harness guard exits before the
launcher runs if any mock is missing.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which('powershell')
pytestmark = pytest.mark.skipif(os.name != 'nt' or not POWERSHELL,
                                reason='Windows PowerShell launcher behaviour')

VERSION = '1.1.0-test.0'
STARTED = '2026-01-05T09:30:00.0000000Z'
HEALTH_URL = 'http://127.0.0.1:8787/api/health'
TRACE_MARKERS = ('CategoryInfo', 'FullyQualifiedErrorId', 'At line', 'char:', '+ ~')
UVICORN = 'python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8787'

HARNESS = r'''
param([string]$Script, [switch]$NoBrowser)
$global:AstraTestScenario = Get-Content -Raw $env:ASTRA_TEST_SCENARIO | ConvertFrom-Json
function global:Write-AstraTestLog([string]$Line) { Add-Content -LiteralPath $env:ASTRA_TEST_LOG -Value $Line }
function global:Get-NetTCPConnection { [CmdletBinding()] param($LocalPort, $State)
    Write-AstraTestLog "listen-check $LocalPort"
    if ($global:AstraTestScenario.listener) { [pscustomobject]@{LocalPort=$LocalPort; OwningProcess=4242} } }
function global:Invoke-RestMethod { [CmdletBinding()] param([Parameter(Position=0)]$Uri)
    Write-AstraTestLog "health $Uri"
    if ($null -eq $global:AstraTestScenario.health) { throw 'Unable to connect to the remote server' }
    $global:AstraTestScenario.health }
function global:Invoke-WebRequest { throw 'Unexpected web request in launcher test' }
function global:Start-Process { [CmdletBinding()] param([Parameter(Position=0)]$FilePath, $ArgumentList, $WorkingDirectory, $RedirectStandardOutput, $RedirectStandardError, $WindowStyle, [switch]$PassThru)
    $target = if ($FilePath -like 'http*') { $FilePath } else { Split-Path $FilePath -Leaf }
    Write-AstraTestLog ("start " + $target + " " + ($ArgumentList -join ' ')).Trim()
    if ($PassThru) { [pscustomobject]@{Id=[int]$global:AstraTestScenario.server.id; StartTime=[datetime]$global:AstraTestScenario.server.started} } }
function global:Stop-Process { [CmdletBinding()] param([int]$Id) Write-AstraTestLog "STOP $Id" }
function global:Start-Sleep { [CmdletBinding()] param($Milliseconds, $Seconds) }
function global:Get-Process { [CmdletBinding()] param([int]$Id)
    $started = $global:AstraTestScenario.processes."$Id"
    if ($started) { return [pscustomobject]@{Id=$Id; StartTime=[datetime]$started} }
    if ($ErrorActionPreference -eq 'Stop') { throw "Cannot find a process with the process identifier $Id." } }
function global:Get-CimInstance { [CmdletBinding()] param([Parameter(Position=0)]$ClassName, $Filter)
    if ($Filter -match 'ParentProcessId = (\d+)') { return }
    if ($Filter -match 'ProcessId = (\d+)') { [pscustomobject]@{ProcessId=[int]$Matches[1]; ParentProcessId=$global:AstraTestScenario.parent; CommandLine=$global:AstraTestScenario.commandLine} } }
foreach ($name in 'Get-NetTCPConnection','Invoke-RestMethod','Invoke-WebRequest','Start-Process','Stop-Process','Start-Sleep','Get-Process','Get-CimInstance') {
    if ((Get-Command $name).CommandType -ne 'Function') { Write-Output "MOCK-MISSING $name"; exit 99 }
}
$global:LASTEXITCODE = 0
if ($NoBrowser) { & $Script -NoBrowser } else { & $Script }
exit $LASTEXITCODE
'''


def run_launcher(tmp_path, script, scenario, record=None, no_browser=True):
    project = tmp_path / 'fictional-astra'
    (project / 'scripts').mkdir(parents=True)
    (project / 'VERSION').write_text(VERSION + '\n')
    shutil.copy(ROOT / 'scripts' / script, project / 'scripts' / script)
    (project / 'scripts' / 'protect_local_data.ps1').write_text(
        "Add-Content -LiteralPath $env:ASTRA_TEST_LOG -Value 'protect'\n")
    if record is not None:
        (project / '.runtime').mkdir()
        (project / '.runtime' / 'server.json').write_text(json.dumps(record))
    harness = tmp_path / 'harness.ps1'
    harness.write_text(HARNESS)
    scenario_path = tmp_path / 'scenario.json'
    scenario_path.write_text(json.dumps(scenario))
    log = tmp_path / 'calls.log'
    log.write_text('')
    env = {k: v for k, v in os.environ.items() if k.upper() != 'PSMODULEPATH'}
    env.update(ASTRA_TEST_SCENARIO=str(scenario_path), ASTRA_TEST_LOG=str(log),
               TEMP=str(tmp_path), TMP=str(tmp_path))
    args = [POWERSHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', str(harness), '-Script', str(project / 'scripts' / script)]
    if no_browser:
        args.append('-NoBrowser')
    done = subprocess.run(args, capture_output=True, text=True, errors='replace',
                          env=env, timeout=120, cwd=tmp_path)
    output = done.stdout + done.stderr
    assert 'MOCK-MISSING' not in output, output
    calls = [line for line in log.read_text().splitlines() if line]
    saved = project / '.runtime' / 'server.json'
    return done.returncode, output, calls, (json.loads(saved.read_text()) if saved.exists() else None)


def assert_plain_guidance(output):
    for marker in TRACE_MARKERS:
        assert marker not in output, output


def assert_port_guidance(output):
    assert_plain_guidance(output)
    assert 'whichever ASTRA copy is already running' in output
    assert 'double-click its own stop.bat' in output
    assert 'Double-click Open ASTRA.bat in this folder again.' in output
    assert 'No other program was stopped.' in output


def test_unrelated_listener_gets_guidance_and_is_left_running(tmp_path):
    code, output, calls, _ = run_launcher(tmp_path, 'start.ps1', {'listener': True})
    assert code == 1
    assert 'ASTRA cannot open: port 8787 is already in use.' in output
    assert_port_guidance(output)
    assert calls == ['listen-check 8787'], 'no health request, start, adoption or termination'


@pytest.mark.parametrize('processes', [{}, {'31337': '2026-01-05T09:30:05.0000000Z'}],
                         ids=['pid-gone', 'pid-reused'])
def test_stale_record_is_not_trusted_or_adopted(tmp_path, processes):
    code, output, calls, saved = run_launcher(
        tmp_path, 'start.ps1', {'listener': True, 'processes': processes},
        record={'pid': 31337, 'started': STARTED})
    assert code == 1
    assert_port_guidance(output)
    assert calls == ['listen-check 8787']
    assert saved == {'pid': 31337, 'started': STARTED}


@pytest.mark.parametrize('health', [{'version': '1.1.0-beta.1', 'pid': 5000},
                                    {'version': VERSION, 'pid': 5000, 'stale': True}],
                         ids=['older-version', 'stale-build'])
def test_owned_older_or_stale_instance_fails_closed(tmp_path, health):
    code, output, calls, _ = run_launcher(
        tmp_path, 'start.ps1', {'health': health, 'processes': {'5000': STARTED}},
        record={'pid': 5000, 'started': STARTED})
    assert code == 1
    assert 'a different or older ASTRA version is already running' in output
    assert_port_guidance(output)
    assert calls == ['health ' + HEALTH_URL]


def test_owned_but_unresponsive_instance_gets_guidance(tmp_path):
    code, output, calls, _ = run_launcher(
        tmp_path, 'start.ps1', {'health': None, 'processes': {'5000': STARTED}},
        record={'pid': 5000, 'started': STARTED})
    assert code == 1
    assert 'still starting or is not responding' in output
    assert_plain_guidance(output)
    assert calls == ['health ' + HEALTH_URL]


@pytest.mark.parametrize('no_browser', [True, False], ids=['no-browser', 'browser'])
def test_same_owned_launch_stays_idempotent(tmp_path, no_browser):
    code, output, calls, saved = run_launcher(
        tmp_path, 'start.ps1', {'health': {'version': VERSION, 'pid': 5000}, 'processes': {'5000': STARTED}},
        record={'pid': 5000, 'started': STARTED}, no_browser=no_browser)
    assert code == 0, output
    assert 'ASTRA is already running at http://localhost:8787' in output
    assert calls == ['health ' + HEALTH_URL] + ([] if no_browser else ['start http://localhost:8787/'])
    assert saved == {'pid': 5000, 'started': STARTED}


def test_normal_start_binds_loopback_and_records_owned_service(tmp_path):
    code, output, calls, saved = run_launcher(tmp_path, 'start.ps1', {
        'server': {'id': 7000, 'started': STARTED}, 'parent': 7000,
        'health': {'version': VERSION, 'pid': 7001}, 'processes': {'7001': STARTED}})
    assert code == 0, output
    assert 'ASTRA is running at http://localhost:8787' in output
    assert calls == ['listen-check 8787', 'protect', 'start ' + UVICORN + ' --no-access-log',
                     'health ' + HEALTH_URL]
    assert saved['pid'] == 7001


def test_port_taken_during_start_is_not_adopted(tmp_path):
    code, output, calls, saved = run_launcher(tmp_path, 'start.ps1', {
        'server': {'id': 7000, 'started': STARTED}, 'parent': 1,
        'health': {'version': VERSION, 'pid': 8000}, 'processes': {'8000': STARTED}})
    assert code == 1
    assert 'another program or ASTRA copy answered on port 8787' in output
    assert_port_guidance(output)
    assert not [c for c in calls if c.startswith('STOP')]
    assert saved['pid'] == 7000, 'the unrelated listener is never recorded as owned'


def test_server_that_never_answers_gets_guidance(tmp_path):
    code, output, calls, _ = run_launcher(tmp_path, 'start.ps1', {
        'server': {'id': 7000, 'started': STARTED}, 'health': None})
    assert code == 1
    assert 'ASTRA did not finish starting' in output
    assert r'.runtime\server.err.log' in output
    assert_plain_guidance(output)
    assert calls.count('health ' + HEALTH_URL) == 30


def test_stop_without_own_record_points_to_the_running_copy(tmp_path):
    code, output, calls, _ = run_launcher(tmp_path, 'stop.ps1', {})
    assert code == 0
    assert 'No ASTRA started from this folder is running. Nothing was stopped.' in output
    assert "another ASTRA copy is running: double-click stop.bat in that copy's folder" in output
    assert calls == []


def test_stop_ends_only_the_owned_backend(tmp_path):
    code, output, calls, saved = run_launcher(
        tmp_path, 'stop.ps1', {'processes': {'5000': STARTED}, 'commandLine': UVICORN},
        record={'pid': 5000, 'started': STARTED})
    assert code == 0, output
    assert 'ASTRA stopped.' in output
    assert calls == ['STOP 5000']
    assert saved is None


def test_stop_still_refuses_a_recorded_non_astra_process(tmp_path):
    code, output, calls, saved = run_launcher(
        tmp_path, 'stop.ps1', {'processes': {'5000': STARTED}, 'commandLine': 'notepad.exe'},
        record={'pid': 5000, 'started': STARTED})
    assert code != 0
    assert 'refusing to stop it' in output
    assert calls == []
    assert saved == {'pid': 5000, 'started': STARTED}
