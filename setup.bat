@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  where py >nul 2>nul
  if errorlevel 1 (python -m venv .venv) else (py -3 -m venv .venv)
)
if errorlevel 1 goto fail
.venv\Scripts\python.exe -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12 or newer is required'"
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install --upgrade pip==26.2
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if errorlevel 1 goto fail
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\protect_local_data.ps1
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 goto fail
if not exist .env copy .env.example .env >nul
pushd frontend
call npm.cmd ci
if errorlevel 1 goto fail
call npm.cmd run build
if errorlevel 1 goto fail
popd
.venv\Scripts\python.exe scripts\initialize.py
if errorlevel 1 goto fail
echo Setup complete. Double-click run.bat to start.
exit /b 0
:fail
echo Setup failed. Read the error above. Python 3.12+ and Node.js 20+ are required.
exit /b 1
