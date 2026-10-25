@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto no_setup
echo Starting WITS Deploy Controller...
echo Keep this console open while using the controller.
".venv\Scripts\python.exe" run.py
if errorlevel 1 goto failed
exit /b 0
:no_setup
echo Run SETUP-WINDOWS.cmd first.
pause
exit /b 1
:failed
echo.
echo Controller exited with an error. Please send the logs folder to Whitehorse IT Solutions.
echo If no log file exists, send a screenshot of this window.
pause
exit /b 1
