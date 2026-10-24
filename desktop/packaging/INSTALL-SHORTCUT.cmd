@echo off
setlocal
set "WITS_DEPLOY_DIR=%~dp0"
set "WITS_DEPLOY_STARTUP=%~1"
powershell -NoProfile -Command "$dir=$env:WITS_DEPLOY_DIR; $folder=[Environment]::GetFolderPath('Programs'); if ($env:WITS_DEPLOY_STARTUP -eq '--autostart') { $folder=[Environment]::GetFolderPath('Startup') }; $link=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $folder 'WITS Deploy.lnk')); $link.TargetPath=Join-Path $dir 'WITS-Deploy.exe'; $link.WorkingDirectory=$dir; $link.Save()"
exit /b %errorlevel%
