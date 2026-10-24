WITS Deploy 0.2.0-dev11 — first verified Linux standalone build

Archive: WITS-Deploy-0.2.0-dev11-Linux-x86_64.tar.gz
The companion .sha256 file verifies the archive. It includes Python, Qt,
Bluetooth/serial dependencies, esptool and app/factory firmware for all three
board models. Windows builds remain pending on a Windows runner or machine.

The local extracted installation is under:
  native/WITS-Deploy-0.2.0-dev11-Linux-x86_64/

Launch WITS-Deploy in that folder, or install the native menu launcher:
  bash native/WITS-Deploy-0.2.0-dev11-Linux-x86_64/INSTALL-LAUNCHER.sh
Run this command from this release directory. It adds WITS Deploy to the
current user's application menu. Right-click that menu entry to pin it to
KDE's Task Manager. Reinstall the launcher if the extracted folder moves.
The project-root WITS Deploy.desktop now points to this native installation.

The archive and every extracted file's SHA-256 passed verification. An offline
startup check passed from the extracted executable: Qt/backend imports, serial
enumeration, included firmware hashes for all models and the bundled esptool
helper/CLI. No real Bluetooth pairing or hardware flashing was performed by
these checks. BUILD-INFO-Linux-x86_64.json records the original build report.

This local build uses glibc 2.43 and targets the current Kubuntu machine.
Use the Ubuntu 22.04 CI build for a broader Linux compatibility baseline.
Generated archives, binaries and native/ are Git-ignored; preserve the archive
separately when publishing or backing up the source.
