# Release files

Firmware is grouped by release version, then hardware model: `firmware/<version>/<model>/`. Each model
folder holds its app and factory binaries, individual OTA manifest, checksums and flashing notes. A
release's common manifest, `WITS-Deploy-Release-<version>.ota.json`, sits one level above the model
folders and refers to images by model-relative paths. It covers all three boards (T-QT Pro,
Waveshare 7-inch and Waveshare 1.47-inch).

Git tracks manifests, checksums and documentation. Generated `.bin` and `.zip` files are ignored, so a
source clone has none of them: download the firmware ZIP from the project's
[GitHub releases](https://github.com/WhitehorseIT/wits-deploy/releases) (or use the app's
**Download latest firmware**) before using a manifest.

Published releases also carry a signed `release-manifest.json` that lists every download with its size
and SHA-256; see [release signing](../docs/RELEASE-SIGNING.md).

Releases from 0.2.0-dev18 use the `WITS-Deploy` file prefix; older ones keep their original
`WITS-Keyboard` names and are never renamed. Historical combined app and T-QT Pro bundles stay with
their T-QT Pro release, and app-only distributions are under `desktop/<version>/`. Older ZIPs keep their
original internal paths, so extract them completely.

Builds and packagers refuse to replace an existing release. Bump the version before generating a changed
distribution.
