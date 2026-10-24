# Release files

Firmware is grouped by release version, then hardware model. Each model folder
contains its app/factory binaries, individual OTA manifest, checksums and
flashing notes. A release's common manifest lives one level above its model
folders and refers to images using model-relative paths.

The latest common manifest is
`firmware/0.2.0-dev13/WITS-Keyboard-Release-0.2.0-dev13.ota.json`.
It contains T-QT Pro, Waveshare7 and the Waveshare147 bring-up build. The new
1.47-inch board needs physical validation; see its model folder's README.
App-only distributions and instructions are in `desktop/<version>/`.
Historical combined app/T-QT Pro bundles stay with their T-QT Pro release.

Git tracks manifests, checksums and documentation. Generated `.bin` and `.zip`
files are ignored: keep release artifacts separately backed up or upload them
as GitHub Release assets when publishing. A source clone does not include those
ignored files; build/download the images before using a release manifest.

Existing binaries and ZIP archives were moved without changing their bytes.
Archived ZIPs retain their original internal paths; extract them completely.
The loose common manifest was updated for the new `tqtpro/` path. New firmware
bundles use named model folders for each board.

Builds and packagers refuse to replace an existing release. Bump the relevant
version before generating a changed distribution.
