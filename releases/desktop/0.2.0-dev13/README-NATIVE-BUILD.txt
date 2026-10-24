WITS Deploy 0.2.0-dev13 — verified Linux standalone candidate

Includes firmware13 for all three board models, the new opt-in Auto-connect
column, paired-only reconnect with bounded retries/manual pause, and the SD
write-access lifetime fix. Keyboard output still disarms on disconnect.

IMPORTANT: flash firmware13 for USB R/W to survive app closure/reconnection.
App13 alone cannot fix old board firmware. Safely eject existing writable
storage before OTA/USB updating. Then test copying with the app closed and
reopened, and compare the copy's hash against its source after safe eject.

From the project root, replace the per-user menu launcher with:
  bash releases/desktop/0.2.0-dev13/native/WITS-Deploy-0.2.0-dev13-Linux-x86_64/INSTALL-LAUNCHER.sh

Close the old application first. The project-root WITS Deploy.desktop also
points to this extracted native13 installation. Targets stay unchecked on a
fresh launch. Enable Auto-connect separately for each saved paired board.
Manual Disconnect pauses until Connect, toggle or app restart. No automatic
PIN pairing is initiated. Physical ARM is still required before typing.

All139 app tests pass; all three firmware builds and compile-time checks pass.
The native archive/extracted hashes, six included firmware images and bundled
esptool/serial/Qt/backend startup passed offline verification. Real radio and
copy/disconnect/reconnect tests of these new paths remain pending. Windows
native build/testing remains pending; the GitHub workflow is prepared.
This local Linux build uses glibc2.43/Python3.14.4 for the current Kubuntu host.
