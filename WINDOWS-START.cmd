@echo off
setlocal
rem WITS Deploy for Windows: checks Python and the app's packages, installs what is missing, then starts the app.
rem Run it again any time; it only installs when something is missing or the requirements changed.
cd /d "%~dp0"

set "APP="
if exist "desktop\run.py" set "APP=desktop"
if not defined APP if exist "app\run.py" set "APP=app"
if not defined APP goto not_extracted
cd /d "%~dp0%APP%"
if not exist requirements-release.txt goto not_extracted

echo WITS Deploy for Windows
echo.

echo Checking Python...
where py >nul 2>&1
if errorlevel 1 goto no_python
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto no_python

if exist ".venv\Scripts\python.exe" goto check_packages
echo Creating the app's private Python environment (first run only)...
py -3 -m venv .venv
if errorlevel 1 goto failed

:check_packages
echo Checking the app's packages...
if not exist ".venv\installed-requirements.txt" goto install_packages
fc /b requirements-release.txt ".venv\installed-requirements.txt" >nul 2>&1
if errorlevel 1 goto install_packages
".venv\Scripts\python.exe" -c "import PySide6, bleak, cryptography" >nul 2>&1
if errorlevel 1 goto install_packages
goto start_app

:install_packages
echo Installing the app's packages. The first time this takes a few minutes; please wait...
".venv\Scripts\python.exe" -m pip install -r requirements-release.txt
if errorlevel 1 goto failed
copy /y requirements-release.txt ".venv\installed-requirements.txt" >nul

:start_app
echo.
echo Starting WITS Deploy. Keep this window open while you use the app.
".venv\Scripts\python.exe" run.py
if errorlevel 1 goto app_failed
exit /b 0

:not_extracted
echo The program files were not found next to this script.
echo.
echo This usually means the ZIP was not extracted. Close this window,
echo right-click the downloaded ZIP, choose Extract All, and run
echo WINDOWS-START.cmd from the extracted folder.
pause
exit /b 1

:no_python
echo Python 3.11 or newer was not found.
echo.
echo Install 64-bit Python from https://www.python.org/downloads/windows/
echo On the first screen of the installer, tick "py launcher". Then run this file again.
pause
exit /b 1

:failed
echo.
echo Setup failed. If the messages above mention a broken environment, delete the
echo folder "%CD%\.venv" and run this file again. Otherwise use Save logs in the app, or send
echo a screenshot of this window.
pause
exit /b 1

:app_failed
echo.
echo WITS Deploy stopped with an error. Send the folder "%CD%\logs", or a screenshot of this window.
pause
exit /b 1
