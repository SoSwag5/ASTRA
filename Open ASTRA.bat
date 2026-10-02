@echo off
setlocal
cd /d "%~dp0"
title ASTRA Beta - Open
if not exist .venv\Scripts\python.exe (
  echo Install ASTRA first: double-click Install ASTRA.bat.
  pause
  exit /b 1
)
call run.bat
if errorlevel 1 (
  echo ASTRA could not start. Read the message above or open START HERE.html.
  pause
  exit /b 1
)
