@echo off
setlocal
cd /d "%~dp0"
echo WITS Deploy Controller - Windows setup
echo.
if exist requirements-release.txt goto have_files
if exist requirements.txt goto have_files
goto not_extracted
:have_files
where py >nul 2>&1
if errorlevel 1 goto no_python
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto no_python
if exist ".venv\Scripts\python.exe" goto install
py -3 -m venv .venv
if errorlevel 1 goto failed
:install
set "requirements_file=requirements.txt"
if exist requirements-release.txt set "requirements_file=requirements-release.txt"
".venv\Scripts\python.exe" -m pip install -r "%requirements_file%"
if errorlevel 1 goto failed
echo.
echo Setup complete. Double-click START-WINDOWS.cmd to run the controller.
pause
exit /b 0
:no_python
echo Python launcher was not found.
echo Install 64-bit Python 3.11 or newer from https://www.python.org/downloads/windows/
echo Include the Python launcher in the installation, then run this file again.
pause
exit /b 1
:not_extracted
echo The program files were not found next to this script.
echo.
echo This usually means the ZIP was not extracted. Close this window,
echo right-click the downloaded ZIP, choose Extract All, and run
echo SETUP-WINDOWS.cmd from the extracted desktop folder.
pause
exit /b 1
:failed
echo.
echo Setup failed. Please send a screenshot of this window to Whitehorse IT Solutions.
pause
exit /b 1
