# Development

Run the commands below from the repository root unless stated otherwise.

## Source layout

| Folder | Contents |
| --- | --- |
| `src/` | Shared firmware and board adapters |
| `desktop/` | Python controller, setup scripts, and app tests |
| `web/` | Early browser (Web Bluetooth) keyboard controller prototype; see the [roadmap](ROADMAP.md) |
| `.github/workflows/` | CI: desktop test builds and the signed release workflow |
| `scripts/` | Build, package, flash, and diagnostic tools |
| `tests/` | Firmware compile-time checks |
| `docs/` | Guides and hardware plans |
| `releases/` | Versioned release metadata and local generated artifacts |

## Build firmware

Install PlatformIO in a local environment if needed:

```bash
python3 -m venv .venv-pio
.venv-pio/bin/python -m pip install platformio==6.2.0
```

Build all targets:

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

## Crash-fallback test build

A crash or hang must start programming mode instead of looping as a keyboard (see `src/boot_mode.h`).
Compile-time tests cover the rule; to check it on a real board, build the test-only firmware, which
crashes on purpose 20 seconds after reaching HID mode, using a different fault on each run (a bad
memory store, an interrupts-off hang caught by the interrupt watchdog, and `abort()`):

```bash
.venv-pio/bin/pio run -e tqtpro-faulttest -e waveshare7-faulttest -e waveshare147-faulttest
```

Package the three `firmware.bin` files as an app-only OTA release outside the repository, install it
with **OTA Update…**, and confirm that every crash returns in PROGRAM mode and stays there. Holding HID
starts the next fault kind. Recover the board with **USB Flash/Update… > Update working board**. The
`-faulttest` environments are never released, and a normal build does not contain the fault code.

## Publish a release

Releases are built, signed and published by GitHub Actions; see [release signing](RELEASE-SIGNING.md).

The app and the firmware have separate versions and separate releases; see
[compatibility](COMPATIBILITY.md). A firmware release is cut only when the firmware code changes.

1. **Firmware release:** set the version in `src/firmware_version.h` and write
   `docs/release-notes/firmware-<version>.md`. **App release:** set the version in
   `desktop/wits_keyboard/__init__.py`, write `docs/release-notes/<version>.md`, and set
   `desktop/packaging/firmware-release.txt` to the published firmware release the app should bundle
   (publish the firmware release first). Notes need `## What's new` and `## Files` sections.
2. **Review the documentation** against what changed (checklist below).
3. Run the checks: the desktop tests above (they include `scripts/check-docs.py`), and
   `.venv-pio/bin/pio run -e tqtpro -e waveshare7 -e waveshare147`.
4. Push, then push a tag: `fw-v<firmware version>` runs the **Firmware release** workflow and
   `v<app version>` runs the **Release** workflow. Each checks the tag against the version files, builds,
   signs the manifest and creates the GitHub release. The **Desktop binaries** workflow is an optional dry
   run of the app build; it builds the firmware from source, so it needs the bundled firmware version to
   equal `src/firmware_version.h`.

### Development snapshots

Every push to `main` also runs the **Snapshot** workflow, which signs a source archive of the commit and replaces
the rolling `snapshot` pre-release (about a minute; no firmware or binaries are built). That is how a fix pushed
to `main` reaches a Windows tester quickly: they choose **Check for updates…** with **Include development
builds** ticked. See [release signing](RELEASE-SIGNING.md#source-updates-and-development-snapshots-run-from-source-installs).

### Documentation checklist

`scripts/check-docs.py` fails the tests and the Release workflow if the version files disagree, the
current version has no release notes, a relative link or heading anchor is broken, a guide is not
linked from another document, or the retired product name appears outside the naming notes. It cannot
tell whether the text is *correct*, so for every release also read through:

- `README.md`: features, install steps, status and limitations (move items between "tested" and "still
  to test" as hardware testing happens).
- `desktop/README.md`: anything that changed in the app's behavior or buttons.
- `docs/OTA-UPDATES.md`, `docs/STORAGE.md` and the board guides in `docs/boards/` for firmware and
  hardware changes.
- `docs/DESKTOP-PACKAGING.md` and `docs/RELEASE-SIGNING.md` for packaging, update and signing changes.
- `docs/ROADMAP.md`: move finished items to Done and record new plans.
- `SECURITY.md`: add anything new to the in-scope list.
- `desktop/packaging/README-NATIVE.txt` and `scripts/FLASHING-INSTRUCTIONS.txt`, which ship inside
  packages.

### Building a release by hand

The steps the workflow runs are available as scripts. Replace `VERSION` with the exact value in
`src/firmware_version.h`:

```bash
bash scripts/build-release.sh VERSION tqtpro
bash scripts/build-release.sh VERSION waveshare7
bash scripts/build-release.sh VERSION waveshare147
python3 scripts/package-ota-release.py releases/firmware/VERSION/WITS-Deploy-Release-VERSION.ota.json
```

Output is grouped by model under `releases/firmware/VERSION/` (`tqtpro/`, `waveshare7/`,
`waveshare147/` and the common `WITS-Deploy-Release-VERSION.ota.json`). Each model folder holds
app/factory images, checksums and its own manifest; the builder writes the common manifest once all
three exist, and `python3 scripts/make-ota-catalog.py releases/firmware/VERSION` can generate it for
the models available. Build and package scripts refuse to overwrite existing releases; bump the
version for changed artifacts. For the desktop package, see [packaging](DESKTOP-PACKAGING.md).

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

See the [release layout](../releases/README.md), [packaging](DESKTOP-PACKAGING.md) and the
[update/recovery guide](OTA-UPDATES.md) for distribution and flashing details.
