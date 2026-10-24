# Waveshare storage extension — agreed direction, 2026-10-23

User wants the 7-inch capacitive touchscreen ESP32-S3 board to connect to a
deployment PC as both a USB HID keyboard and a MicroSD-backed mass-storage
device. Storage must default to read-only; an authenticated desktop-app
control may enable read/write. This is not implemented in firmware 0.1.1.

Hardware confirmed by user: **ESP32-S3-Touch-LCD-7 Ver1.1** (base model).
Initial prototype 0.2.0-dev implemented; see WAVESHARE7.md for code, flashing,
storage controls and hardware test steps. User successfully flashed it and
esptool confirmed 8 MB flash / 8 MB PSRAM. Both board builds and 68 desktop
tests pass. Dev2 hardware retest confirms working screen/touch and USB mass
storage, with a clean software restart into HID+MSC and SD/USB/BLE startup
completed. Keyboard output alongside storage, write protection and access-mode
transitions still await hardware validation; see WAVESHARE7.md.

## Current status: dev8

Dev3 typing and improved SD access were confirmed by the user. A later eject
spinner showed actual pending host writeback (~480 KiB/s), not an idle UI-only
hang; wait for safe eject to complete. Dev8 adds SCSI flush handling and retains
the eject requirement after write-grant revocation. Bluetooth OTA for both
models is implemented, with hardware testing pending; it does not use Wi-Fi
or require taking the PC offline. See OTA-UPDATES.md. The earlier rollout
notes below are historical.

## Proposed implementation order

1. Add a separate board target and display/touch/SD hardware adapter. Keep
   shared keyboard and BLE behavior. One binary per hardware target, with
   per-unit identities still derived automatically.
2. Bring up the touchscreen and card detection, then a read-only MSC + HID
   composite interface through native USB. USB descriptors must be complete
   before USB.begin(). Enforce write protection in device callbacks and
   SCSI responses, not only an app setting.
3. Add capability/version/status reporting so the app can discover card
   presence, capacity, export state and access mode. Existing T-QT Pro boards
   should report unsupported storage without losing keyboard functionality.
4. Add explicit per-target app controls for storage export and write access,
   plus clear touchscreen status. Keep HID arming independent of storage
   permissions. Enable writes only over the authenticated connection.
5. Test copies and checksums on Windows and Linux while typing, absent/card
   error cases, rejected writes in read-only mode, eject/remount, and resets.

## Current storage/UI update

Dev3 firmware/controller is ready for retest after dev2 produced kernel USB
read timeouts and slow access. It batches sector transfers at up to 20MHz,
decouples display/metadata status from disk I/O locks, and verifies remount
state in the app. It also adds a held PROGRAM button and contrasting ARM/STOP
colors. No improved hardware throughput is claimed until user retesting.

## Ordered 1.47-inch board

The user's Amazon title matches Waveshare ESP32-S3-Touch-LCD-1.47 (exact
shortlink item could not be opened). Manufacturer specifies 172x320 capacitive
touch, JD9853 SPI LCD, AXS5106L I2C touch, 16MB flash, 8MB PSRAM, TF slot and
full-speed USB. Dev10 now provides a separate hardware target and display/touch/storage
adapters while retaining the shared BLE/protocol/controller behavior. See
[Waveshare147 setup](boards/WAVESHARE147.md) for the first hardware tests and
the portrait controls. Native USB throughput remains
full-speed; the smaller display does not change the USB peripheral's ceiling.

References:
- https://www.waveshare.com/esp32-s3-touch-lcd-1.47.htm
- https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.47
- https://files.waveshare.com/wiki/ESP32-S3-Touch-LCD-1.47/ESP32-S3-Touch-LCD-1.47-Schematic.pdf

## Storage ownership and transitions

While exported, the PC owns the block device; the firmware must not mount
the same filesystem locally, even just to browse cached directory data.
Require host-side safe eject and a confirmed idle/unmounted handoff before
changing export or read/write mode. A successful SD write callback does not
prove the host has flushed its filesystem cache. Do not force re-enumeration
during active writes or a HID command; USB disconnect may affect both classes.

Recommended write permission is volatile: reboot always starts read-only.
An unexpected app/BLE disconnect should deny further writes and report the
loss of permission; recovery must account for potentially interrupted host
writes. Do not pretend a forced disconnect safely flushed the PC. Define and
validate the disconnect policy during the prototype before release.

Use USB/the card reader for bulk installer provisioning initially; BLE remains
the control path. Benchmark throughput before promising large-image deployment:
the S3's native USB peripheral is full-speed, unlike a typical USB 3 flash drive.

## References

- Espressif composite HID/MSC and storage ownership documentation:
  https://docs.espressif.com/projects/esp-usb/en/latest/esp32s3/usb_device.html
- Base-model pin documentation: https://docs.waveshare.com/ESP32-S3-Touch-LCD-7
- Installed Arduino core 3.3.12 provides USBMSC::isWritable(bool), read/write
  callbacks and onStartStop; evaluate actual host eject behavior as part of
  the prototype. Newer ESP-IDF examples may use APIs absent from this core.

## Confirmed next board — 2026-10-24

User explicitly requested future compatibility for Waveshare
ESP32-S3-Touch-LCD-1.47: https://www.waveshare.com/esp32-s3-touch-lcd-1.47.htm
Manufacturer documentation: https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.47
It lists ESP32-S3R8, 16MB flash/8MB PSRAM, 172x320 capacitive display, JD9853,
AXS5106L and TF card slot. Dev10 implements target `waveshare147`, OTA code 3,
its display/touch/pin adapter and dedicated SPI SD bus, release catalog entry
and 16MB wired-flash checks. Shared keyboard, paired BLE, storage policy and
OTA behavior are retained. Firmware builds and automated tests pass; physical
validation remains pending. Test touch, HID and read-only MSC before enabling
writes. Do not substitute T-QT Pro or Waveshare7 firmware.
