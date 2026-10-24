# Development

Run the commands below from the repository root unless stated otherwise.

## Source layout

| Folder | Contents |
| --- | --- |
| `src/` | Shared firmware and board adapters |
| `desktop/` | Python controller, setup scripts, and app tests |
| `web/` | Browser-based keyboard controller |
| `deploy/` | Static hosting and Cloudflare Tunnel configuration |
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

Build both supported targets:

```bash
.venv-pio/bin/pio run -e tqtpro -e waveshare7
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
```

Output is grouped by model:

```text
releases/firmware/VERSION/
  tqtpro/
  waveshare7/
  WITS-Keyboard-Release-VERSION.ota.json
```

Each model folder contains app/factory images, checksums, and its individual
manifest. Once both builds are available, the builder generates the common
release manifest. It can also be generated explicitly:

```bash
python3 scripts/make-ota-catalog.py releases/firmware/VERSION
```

Package the firmware and common manifest:

```bash
python3 scripts/package-ota-release.py releases/firmware/VERSION/WITS-Keyboard-Release-VERSION.ota.json
```

For the app, set `desktop/wits_keyboard/__init__.py` to the intended app version
and prepare `releases/desktop/VERSION/README-FIRST.txt`, then run:

```bash
python3 scripts/package-controller.py
```

Firmware and app versions may differ. Build and package scripts refuse to
overwrite existing releases; bump the relevant version for changed artifacts.
Existing filenames retain the `WITS-Keyboard` prefix.

See the [release layout](../releases/README.md) and
[update/recovery guide](OTA-UPDATES.md) for distribution and flashing details.
