# App shortcuts and standalone builds

App **0.2.0-dev11** adds Linux shortcuts and Windows/Linux native build tooling.
The Linux standalone build now exists and passed its offline startup check.
Its archive and all extracted file hashes were verified. The extracted app is
in `releases/desktop/0.2.0-dev11/native/WITS-Deploy-0.2.0-dev11-Linux-x86_64/`.
The project-root launcher points to it. For its menu entry, run that folder's
`INSTALL-LAUNCHER.sh`; KDE can pin the menu entry to its Task Manager.
The original Python app remains usable. Windows native builds and physical
Bluetooth/USB tests of the native package remain pending. The current GitHub
connector cannot access the org repository; CI must be triggered after pushing.

## One-click launching now

From the repository root on Kubuntu:

```bash
bash desktop/INSTALL-LAUNCHER-LINUX.sh
```

This installs **WITS Deploy** in the current user's application menu. It points
to this checkout's `desktop/START-LINUX.sh`, so Python setup is needed once.
The generated `WITS Deploy.desktop` in the checkout also launches it directly.
Keep the checkout in place; reinstall the shortcut if it moves.

Sign-in launching is optional and off by default:

```bash
bash desktop/INSTALL-LAUNCHER-LINUX.sh --autostart
bash desktop/INSTALL-LAUNCHER-LINUX.sh --remove-autostart
```

The first command installs the menu entry and sign-in entry; the second removes
only the sign-in entry. These are per-user desktop files, not system services.
Starting the app never arms a board or sends text; saved Target boxes remain
unchecked. Removing `~/.local/share/applications/com.whitehorseit.WITSDeploy.desktop`
removes the menu entry (adjust for `XDG_DATA_HOME` if configured).

## Build locally

PyInstaller bundles Python and the dependencies. It must build on the target
OS; it is not a Windows cross-compiler on Linux. This first build configuration
supports x86-64 Windows and Linux. Python 3.13 is used by CI; dependency versions
are in `desktop/requirements-build.txt` and `requirements-release.txt`.

Linux, from the repository root:

```bash
bash scripts/build-desktop-linux.sh
```

Windows, from Command Prompt at the repository root:

```bat
scripts\build-desktop-windows.cmd
```

Each wrapper creates `.venv-build`, installs the build requirements, runs app
tests and packages the native programs. Setup downloads need network access.
When dependencies are already installed, the common builder is:

```bash
python scripts/build-desktop.py
```

Artifacts go to `releases/desktop/0.2.0-dev11/`:

- `WITS-Deploy-0.2.0-dev11-Windows-x64.zip`
- `WITS-Deploy-0.2.0-dev11-Linux-x86_64.tar.gz`
- A companion `.sha256` file for each archive.

These names describe the intended outputs; the files exist only after a
successful native build. Existing archives are never overwritten. Use a new
app version for changed releases, or `--output SOME_OTHER_DIRECTORY` for an
isolated first build. The native app includes app/factory firmware for all three
boards. Local builds use the complete release named in
`desktop/packaging/firmware-release.txt`. If building from a source clone with
no binaries, extract a firmware ZIP and pass its common JSON, for example:

```bash
bash scripts/build-desktop-linux.sh --firmware /path/to/WITS-Keyboard-Release-0.2.0-dev11.ota.json
```

The builder validates every image's model, size, SHA-256 and matching app/factory
contents before packaging. The included JSON is preselected in both update
dialogs; selecting another release remains available. Native packages include
firmware inside their portable folder, with the GUI's resources. Source-only
app distributions still require separate firmware files.

## GitHub Actions

Push the committed source and workflow to `WhitehorseIT/wits-deploy`, then use
**Actions → Desktop binaries → Run workflow** on the main branch. A
`desktop-v*` tag push also triggers the workflow. Each run builds on
`windows-2022` and `ubuntu-22.04`, using Python 3.13. A preceding Linux job
builds all three board targets using PlatformIO 6.2.0 and platform 8.0.0 into
an isolated directory; both desktop jobs include those same validated images.
Tracked release metadata and prior binary releases are not overwritten. The
included firmware version must match `src/firmware_version.h`. CI generates
its own build metadata/checksums, so freshly compiled images may differ from
previous local builds. It uploads the included firmware and two desktop artifacts
with their archive checksums; it does not publish a GitHub Release or contact
The tester automatically. Download the artifact and extract the inner package.

The Ubuntu 22.04 runner establishes a more useful baseline than building only
on the newest Kubuntu. Linux bundles still depend on the host's glibc and
system graphics/Bluetooth libraries. Local builds inherit the local host's
glibc requirements; they are not universal Linux executables. Bluetooth/BlueZ,
serial permissions and Windows PIN pairing remain OS responsibilities.

## Standalone package contents and checks

Extract the complete archive, keeping `_internal/` and `helpers/` beside
`WITS-Deploy.exe` or `WITS-Deploy`. Double-click the executable; the receiving
PC needs no Python installation. Linux bundles include `INSTALL-LAUNCHER.sh`;
Windows bundles include `INSTALL-SHORTCUT.cmd` for a Start menu shortcut.
Each supports an explicit `--autostart` option for sign-in launching. Reinstall
shortcuts after moving a portable package. On Windows, remove the Startup
shortcut to disable sign-in launching.

The GUI and USB console helper are separate native programs. GUI USB operations
invoke the bundled helper, and the helper invokes its own embedded esptool.
This avoids accidentally relaunching the GUI when `sys.executable` no longer
means a Python interpreter. Esptool stubs and serial dependencies are collected.
The frozen GUI writes logs to per-user storage instead of its installation folder:

- Linux: `$XDG_STATE_HOME/wits-deploy/logs` or `~/.local/state/wits-deploy/logs`.
- Windows: `%LOCALAPPDATA%\Whitehorse IT Solutions\WITS Deploy\logs`.

Source runs keep `desktop/logs/`. Existing QSettings organization/application
identity is preserved, so names, rows and aliases remain available.

The builder runs tests and an offline check of the frozen Qt application,
platform Bluetooth backend, serial enumeration, bundled esptool stubs/CLI and
all six included firmware images.
It removes the checkout's `PYTHONPATH` for that check. Only a passing build
gets packaged. `BUILD-INFO.json`, `DEPENDENCIES.json`, license files and
`SHA256SUMS.txt` accompany the bundle. These checks do not replace testing
actual pairing, reconnect, PIN entry, typing, storage, OTA and USB flashing on
both operating systems. First native candidates are unsigned testing builds.

Primary references: [PyInstaller operating mode](https://pyinstaller.org/en/stable/operating-mode.html),
[runtime executable paths](https://pyinstaller.org/en/stable/runtime-information.html),
[subprocess considerations](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html),
and [desktop entry quoting](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html).
