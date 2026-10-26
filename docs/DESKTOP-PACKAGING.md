# Packaging, shortcuts and app updates

## The packaged Linux build

Each release carries `WITS-Deploy-<version>-Linux-x86_64.tar.gz` with a `.sha256` file. It bundles
Python and every dependency, so the receiving computer needs no Python. Extract the **whole**
archive to a permanent folder, keeping `_internal/` and `helpers/` beside the `WITS-Deploy`
executable:

```bash
sha256sum -c WITS-Deploy-<version>-Linux-x86_64.tar.gz.sha256
mkdir -p ~/Apps && tar xzf WITS-Deploy-<version>-Linux-x86_64.tar.gz -C ~/Apps
cd ~/Apps/WITS-Deploy-<version>-Linux-x86_64 && bash INSTALL-LAUNCHER.sh
```

`INSTALL-LAUNCHER.sh` adds a per-user menu entry (`~/.local/share/applications/com.whitehorseit.WITSDeploy.desktop`).
Add `--autostart` to also start at graphical sign-in, or `--remove-autostart` to undo it. These are
per-user desktop files, not services, and starting the app never arms a board or sends text. Reinstall
the shortcut if you move the folder.

The build is made on Ubuntu 22.04, so it needs a system at least as new as that (glibc), plus the
usual system Bluetooth (BlueZ), Qt platform libraries and serial-port permissions. Nothing changes
those settings for you.

Contents: the app and helper programs, `README-FIRST.txt`, `BUILD-INFO.json`, `DEPENDENCIES.json`
(third-party versions and licenses), `licenses/` and `SHA256SUMS.txt`. The bundled firmware for all
three boards is preselected in the update dialogs.

## Updating the app (Linux)

When a newer release has a verified signature, **Update app to X…** appears next to the *Devices*
heading. It is hidden for source installs and when the install folder is not writable.

1. The app downloads the signed archive and checks its size and SHA-256 against the signed manifest.
2. It unpacks the archive beside the running copy, in the same parent folder (for example `~/Apps`),
   and renames it into place only when complete. The running copy is never modified.
3. A small wrapper restarts the app into the new version after two seconds, so Bluetooth is released.
   If the new version fails before it has confirmed itself (step 4), the wrapper starts the previous one
   instead.
4. After the new version has run for 15 seconds it confirms itself: it removes the update marker,
   rebuilds KDE's menu cache and moves your menu and sign-in shortcuts to itself, and logs where the
   previous copy is. Delete that folder when you are satisfied. A crash after this is never rolled back.

Updates need your confirmation and are blocked while a board is armed or typing. See
[release signing](RELEASE-SIGNING.md) for how releases are verified.

## Windows

Windows binaries are not published, because unsigned executables trigger SmartScreen warnings.
Windows users run the app from Python; see the [repository README](../README.md#windows-run-from-python)
and `desktop/SETUP-WINDOWS.cmd` / `desktop/START-WINDOWS.cmd`. CI still builds a Windows package as
an artifact of the **Desktop binaries** workflow for testing. It contains `WITS-Deploy.exe` and
`INSTALL-SHORTCUT.cmd` (Start menu shortcut, or `--autostart` for sign-in).

## Source installs and shortcuts

On Linux, from the repository root:

```bash
bash desktop/INSTALL-LAUNCHER-LINUX.sh              # app-menu entry pointing at this checkout
bash desktop/INSTALL-LAUNCHER-LINUX.sh --autostart  # also start at sign-in
bash desktop/INSTALL-LAUNCHER-LINUX.sh --remove-autostart
```

The entry runs `desktop/START-LINUX.sh`, so run `bash desktop/SETUP-LINUX.sh` once first. Keep the
checkout in place, or reinstall the shortcut if it moves.

## Build locally

PyInstaller must build on the target operating system. Python 3.13 is used by CI; dependency versions
are in `desktop/requirements-build.txt` and `requirements-release.txt`.

```bash
bash scripts/build-desktop-linux.sh        # Linux
scripts\build-desktop-windows.cmd          # Windows, from Command Prompt at the repository root
```

Each wrapper creates `.venv-build`, installs the build requirements, runs the tests and packages the
app. Artifacts go to `releases/desktop/<version>/` unless you pass `--output DIRECTORY`; existing
archives are never overwritten. Local builds bundle the release named in
`desktop/packaging/firmware-release.txt`. From a source clone with no firmware binaries, extract a
firmware ZIP and pass its common JSON:

```bash
bash scripts/build-desktop-linux.sh --firmware /path/to/WITS-Deploy-Release-<version>.ota.json
```

The builder checks every image's model, size, SHA-256 and matching app/factory contents, then runs an
offline check of the packaged Qt app, Bluetooth backend, serial enumeration, bundled esptool and all
six firmware images. Only a passing build is packaged. These checks do not replace testing real
pairing, reconnect, typing, storage, OTA and USB flashing on each operating system.

The app and the USB helper are separate programs: GUI USB operations call the bundled helper, which
embeds esptool. This avoids relaunching the GUI where `sys.executable` is no longer a Python
interpreter.

## GitHub Actions

- **Release** (tag `v<version>`): builds the Linux app, bundling the already published firmware named in
  `desktop/packaging/firmware-release.txt`, then signs the manifest and publishes the app release.
- **Firmware release** (tag `fw-v<version>`): builds the three board images, signs the manifest and
  publishes the firmware release. See [release signing](RELEASE-SIGNING.md).
- **Desktop binaries** (manual, or a `desktop-v*` tag): builds the three firmware images once, then the
  desktop app on `ubuntu-22.04` and `windows-2022`, and uploads them as workflow artifacts. It does not
  publish a release or send the builds anywhere. Use it to test a commit before tagging.

Both workflows build firmware with PlatformIO 6.2.0 (platform 8.0.0) in an isolated directory, so
freshly compiled images can differ byte-for-byte from earlier local builds. The firmware version must
match `src/firmware_version.h`.

## Logs and settings

The packaged app writes its log to per-user storage, not the install folder:

- Linux: `$XDG_STATE_HOME/wits-deploy/logs` or `~/.local/state/wits-deploy/logs`.
- Windows: `%LOCALAPPDATA%\Whitehorse IT Solutions\WITS Deploy\logs`.

Source runs keep `desktop/logs/`. The saved-settings identity is unchanged across versions, so saved
boards, names and delays carry over.

References: [PyInstaller operating mode](https://pyinstaller.org/en/stable/operating-mode.html),
[runtime paths](https://pyinstaller.org/en/stable/runtime-information.html), and
[desktop entry quoting](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html).
