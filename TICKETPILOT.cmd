@echo off
setlocal EnableExtensions DisableDelayedExpansion
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
pushd "%~dp0"
if errorlevel 1 exit /b 1
if not exist ".venv\Scripts\python.exe" (
  echo Project Python environment is missing. Follow docs\STACK_GUIDE.md setup.
  if "%~1"=="" pause
  popd
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\control.py" %*
set "TicketPilotControlResult=%ERRORLEVEL%"
popd
if not "%TicketPilotControlResult%"=="0" if "%~1"=="" pause
exit /b %TicketPilotControlResult%
