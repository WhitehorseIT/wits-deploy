WITS KEYBOARD - APP + FIRMWARE rc12 - TESTER'S WINDOWS TEST BUNDLE
Prepared October 22, 2026

START HERE

Extract the entire ZIP to a writable folder. It contains:
  app\       Latest Python desktop controller, setup/launch scripts and tests
  firmware\  rc12 app-only and factory images, flash helper and release notes

This is a Python source app, not a standalone Windows EXE. It requires 64-bit
Python 3, Bluetooth LE, and internet access for the first dependency install.
Download Python from https://www.python.org/downloads/windows/ and include the
Python launcher. Run "py -3 --version" in a terminal to check it is available.

1. UPDATE THE FIRMWARE ON YOUR EXISTING WORKING BOARD

Close the controller before flashing. For your already-working T-QT Pro,
use WITS-Keyboard-0.1.0-rc12.app.bin. It writes only the application at 0x10000,
preserving the board's NVS Bluetooth bonds and existing partition layout.

The .factory.bin image is for initial setup/recovery. It writes at 0x0 and
can clear existing pairing data. It is not needed for this normal update.

One-time flashing prerequisite, in a Windows terminal:
  py -m pip install esptool

Enter the ROM bootloader: hold left/BOOT while pressing RESET, then release
left/BOOT. Alternatively, on the blue PROGRAM screen, hold left/FLASH for two
seconds. Find the board's COM port in Device Manager > Ports (COM & LPT).

Open a terminal in the firmware folder and run (replace COM5 if needed):
  .\flash-windows.cmd COM5 .\WITS-Keyboard-0.1.0-rc12.app.bin

Use the flash helper supplied in THIS bundle: it recognizes .app.bin and
selects 0x10000. Older helpers always used 0x0.

After successful verification, press RESET manually. On the PROGRAM screen,
hold the right/HID button for two seconds to enter HID mode.

2. SET UP AND RUN THE APP

Open the app folder, double-click SETUP-WINDOWS.cmd, and wait for Setup
complete. Then double-click START-WINDOWS.cmd. Keep its console open during
testing. If setup fails, send Whitehorse IT Solutions a screenshot of the console output.

3. CONNECT USING YOUR EXISTING PAIRING

If Windows and the board still have their saved bond, select the board row
and Connect. Scan once if it is not listed. You should not have to hold left
or enter another PIN with rc12. The board remains disarmed on connection.

If this is a first pairing or either side has lost the saved bond, hold left
until the board shows its PIN, then pair through Windows Bluetooth Settings.
The Windows in-app PIN entry path is not implemented yet; the Linux dialog
does not apply on Windows. After Windows pairing, use Connect in the app.
For stale Windows bonds, remove only this WITS Keyboard in Windows Settings,
then perform fresh physical PIN pairing. Avoid the app's Re-pair button on
Windows for now: it removes the bond and tries the unverified in-app path.

4. QUICK FEEDBACK CHECKLIST

- Connect, Ping, Disconnect, and Connect again without holding left.
- Close/reopen the app; check the saved row/alias returns and reconnects.
- Rename the board; Identify while disarmed should display the new alias.
- Check the Targets band in dark mode and the larger ID under DISARMED.
- Check DISARM appears as the right action when armed or typing.
- For typing, plug the board into a separate USB target computer with
  Notepad focused, check its Target box in the controller, physically arm,
  and send sample text such as WITS-test-123!.
- Check Backspace, Delete, Enter, and STOP ALL against sample text.

Hardware tests of the new rc12 reconnect path are still pending, particularly
with Windows private Bluetooth addresses. Treat this as a feedback build.
The app passed 38 automated Linux tests and offscreen UI/settings checks;
firmware compilation, release hashes and linked pairing guard were verified.

SEND BACK TO WHITEHORSE IT SOLUTIONS

Report your Windows version, Bluetooth adapter, successful steps and exact
errors, and what the board showed. Include app\logs\wits-keyboard-debug.log
and rotated logs if present. See app\README-WINDOWS.txt for more detail.
The bundle contains no existing logs or saved pairings.

MANIFEST.json records the packaged files and local dependency versions used
for development. SHA256SUMS.txt verifies all files in the bundle; the firmware
folder also contains its original release checksums.
