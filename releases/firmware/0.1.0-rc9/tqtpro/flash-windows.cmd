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

py -m esptool --chip esp32s3 --port "%~1" --baud 460800 write-flash 0x0 "%~2"
if errorlevel 1 exit /b %errorlevel%

echo.
echo Flash completed successfully. Unplug and reconnect the board normally.
