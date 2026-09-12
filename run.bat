@echo off
cd /d "%~dp0"
if not exist frontend\dist\index.html (
  echo Please run setup.bat first.
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start.ps1
