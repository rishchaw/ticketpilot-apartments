@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Project Python environment is missing. See README.md for setup.
  popd
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\stop_services.py"
set "TicketPilotStopResult=%ERRORLEVEL%"
echo.
if not "%TicketPilotStopResult%"=="0" echo Some stop checks failed. Review the report above and the private .tools logs.
popd
pause
exit /b %TicketPilotStopResult%
