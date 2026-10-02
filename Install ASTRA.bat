@echo off
setlocal
cd /d "%~dp0"
title ASTRA Beta - Install
echo.
echo ASTRA Beta - your local job-search workspace
echo Install once. Open ASTRA.bat starts it next time.
echo.
py -3.13 -c "import sys; assert sys.version_info[:2] == (3,13)" >nul 2>&1
if errorlevel 1 (
  echo First install Python 3.13 for Windows from the official website.
  echo Choose the Windows 64-bit installer and keep the Python launcher enabled.
  echo Then return here and double-click Install ASTRA.bat again.
  echo Instructions: START HERE.html
  start "" "https://www.python.org/downloads/release/python-31316/"
  pause
  exit /b 1
)
call setup.bat
if errorlevel 1 (
  echo.
  echo Installation did not finish. Keep this window open and read the message above.
  echo See START HERE.html for help. Do not disable antivirus or security controls.
  pause
  exit /b 1
)
echo.
echo Ready. Double-click Open ASTRA.bat to launch your workspace.
pause
