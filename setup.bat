@echo off
setlocal
cd /d "%~dp0"
if not "%OS%"=="Windows_NT" goto fail
if not exist .venv\Scripts\python.exe (
  py -3.13 -m venv .venv
  if errorlevel 1 py -3.14 -m venv .venv
)
if not exist .venv\Scripts\python.exe goto fail
.venv\Scripts\python.exe -c "import sys; assert sys.version_info[:2] in ((3,13),(3,14)), 'Use Python 3.14 or 3.13; preserve an old environment before recreating it'"
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements.lock.txt
if errorlevel 1 goto fail
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\protect_local_data.ps1
if errorlevel 1 goto fail
if exist release-manifest.json if exist frontend\dist\index.html goto initialize
node -e "if(Number(process.versions.node.split('.')[0])!==24)throw Error('Install Node 24 LTS for source builds')"
if errorlevel 1 goto fail
pushd frontend
call npm.cmd ci
if errorlevel 1 goto buildfail
call npm.cmd run build
if errorlevel 1 goto buildfail
popd
:initialize
.venv\Scripts\python.exe scripts\initialize.py
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m backend.doctor
if errorlevel 1 goto fail
echo Setup complete. Double-click run.bat. Optional browser rehearsal: .venv\Scripts\python.exe -m playwright install chromium
exit /b 0
:buildfail
popd
:fail
echo Setup failed. Use Windows, Python 3.14 or 3.13, and Node 24 for source builds. Read the error above.
exit /b 1
