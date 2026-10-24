@echo off
setlocal

if "%~1"=="" (
  echo Usage: flash-windows.cmd COM_PORT FIRMWARE_FILE
  echo Example: flash-windows.cmd COM5 WITS-Keyboard-0.1.0.factory.bin
  exit /b 2
)

if "%~2"=="" (
  echo Firmware filename is required.
  exit /b 2
)

set "image_name=%~nx2"
set "flash_offset=0x0"
if /i "%image_name:~-8%"==".app.bin" set "flash_offset=0x10000"
py -m esptool --chip esp32s3 --port "%~1" --baud 460800 write-flash %flash_offset% "%~2"
if errorlevel 1 exit /b %errorlevel%

echo.
echo Flash completed successfully. Unplug and reconnect the board normally.
