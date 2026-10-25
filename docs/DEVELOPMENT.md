# Development

Run the commands below from the repository root unless stated otherwise.

## Source layout

| Folder | Contents |
| --- | --- |
| `src/` | Shared firmware and board adapters |
| `desktop/` | Python controller, setup scripts, and app tests |
| `web/` | Early browser (Web Bluetooth) keyboard controller prototype; see the [roadmap](ROADMAP.md) |
| `scripts/` | Build, package, flash, and diagnostic tools |
| `tests/` | Firmware compile-time checks |
| `docs/` | Guides and hardware plans |
| `releases/` | Versioned release metadata and local generated artifacts |

## Build firmware

Install PlatformIO in a local environment if needed:

```bash
python3 -m venv .venv-pio
.venv-pio/bin/python -m pip install platformio
```

Build all targets (the 1.47-inch target is still in hardware bring-up):

```bash
.venv-pio/bin/pio run -e tqtpro -e waveshare7 -e waveshare147
```

Board settings and dependencies are defined in [platformio.ini](../platformio.ini).
Each model needs its own image; units of the same model use the same image.

## Test the controller

After running the desktop setup script:

```bash
cd desktop
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests
```

The offscreen setting lets Qt tests run without opening application windows.
Automated tests use simulated Bluetooth/USB devices and do not replace physical
tests of flashing, boot behavior, or interrupted transfers.

## Build a release

Set the firmware version in `src/firmware_version.h`, then replace `VERSION`
below with that exact value:

```bash
bash scripts/build-release.sh VERSION tqtpro
bash scripts/build-release.sh VERSION waveshare7
bash scripts/build-release.sh VERSION waveshare147
```

Output is grouped by model:

```text
releases/firmware/VERSION/
  tqtpro/
  waveshare7/
  waveshare147/
  WITS-Deploy-Release-VERSION.ota.json
```

Each model folder contains app/factory images, checksums, and its individual
manifest. Once all three builds are available, the builder generates the common
release manifest. It can also be generated explicitly for available models
(including older two-model releases):

```bash
python3 scripts/make-ota-catalog.py releases/firmware/VERSION
```

Package the firmware and common manifest:

```bash
python3 scripts/package-ota-release.py releases/firmware/VERSION/WITS-Deploy-Release-VERSION.ota.json
```

For the app, set `desktop/wits_keyboard/__init__.py` to the intended app version
and prepare `releases/desktop/VERSION/README-FIRST.txt`, then run:

```bash
python3 scripts/package-controller.py
```

Firmware and app versions may differ. Build and package scripts refuse to
overwrite existing releases; bump the relevant version for changed artifacts.

## Naming

The product is **WITS Deploy**. Releases from 0.2.0-dev18 name their files with the `WITS-Deploy`
prefix (`WITS-Deploy-TQTPro-VERSION`, `WITS-Deploy-Waveshare7-VERSION`,
`WITS-Deploy-Waveshare147-VERSION`, `WITS-Deploy-Release-VERSION.ota.json`,
`WITS-Deploy-Firmware-VERSION.zip`). Older releases keep their original `WITS-Keyboard` names
and are never renamed or rewritten; the scripts and the app look for the new name first and fall
back to the old one.

Some internal identifiers keep the old name on purpose, because changing them would break
something for existing users:

| Identifier | Why it stays |
| --- | --- |
| Saved-settings key (`QSettings("Whitehorse IT Solutions", "WITS Keyboard")`) | Renaming it would forget every user's saved boards, names and delays |
| Python package `wits_keyboard` and the log file `wits-keyboard-debug.log` | Internal names with no user-facing effect; renaming adds churn without benefit |
| Pairing agent path `/com/whitehorseit/WitsKeyboard/PairingAgent` | Internal D-Bus identifier |
| `scripts/package-stable-release.py` | Legacy promotion of the 0.1.x T-QT Pro releases, which keep their names |

See the [release layout](../releases/README.md) and
[update/recovery guide](OTA-UPDATES.md) for distribution and flashing details.

## Native desktop packages

Use `bash scripts/build-desktop-linux.sh` on Linux or
`scripts\build-desktop-windows.cmd` on Windows. The app includes the complete
firmware release configured in `desktop/packaging/firmware-release.txt`; supply
`--firmware PATH_TO_COMMON_JSON` for another extracted complete release.
The GitHub Desktop binaries workflow builds firmware once and includes it
in Windows/Linux artifacts. See [native packaging](DESKTOP-PACKAGING.md).
