@echo off
setlocal
cd /d "%~dp0.."
py -3 -m venv .venv-build
if errorlevel 1 exit /b %errorlevel%
".venv-build\Scripts\python.exe" -m pip install -r desktop/requirements-build.txt
if errorlevel 1 exit /b %errorlevel%
".venv-build\Scripts\python.exe" scripts\build-desktop.py %*
exit /b %errorlevel%
