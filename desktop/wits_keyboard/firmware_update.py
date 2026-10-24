"""App-only image validation and windowed upload over the existing encrypted BLE link."""
from dataclasses import dataclass
import asyncio
import secrets
import sys
import hashlib
import json
import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True, repr=False)
class FirmwareImage:
    board: str
    version: str
    filename: str
    sha256: str
    data: bytes
    kind: str = "app"


@dataclass(frozen=True)
class FirmwareBinary:
    filename: str
    size: int
    sha256: str


@dataclass(frozen=True)
class FirmwareTarget:
    board: str
    filename: str
    size: int
    sha256: str
    factory: FirmwareBinary | None = None


@dataclass(frozen=True)
class FirmwareRelease:
    version: str
    directory: Path
    targets: tuple[FirmwareTarget, ...]

    def select(self, board: str, factory: bool = False) -> FirmwareImage:
        if not isinstance(board, str) or board not in BOARD_CODES:
            raise ValueError("Unsupported connected board model")
        target = next((item for item in self.targets if item.board == board), None)
        if target is None:
            raise ValueError("This release has no firmware for the connected board")
        if factory:
            if target.factory is None:
                raise ValueError("This manifest has no factory image; choose a complete release manifest")
            target = target.factory
        image = (self.directory / target.filename).resolve()
        if not image.is_relative_to(self.directory):
            raise ValueError("Firmware image must stay inside the release folder")
        if image.stat().st_size != target.size:
            raise ValueError("Firmware size does not match the manifest")
        with image.open("rb") as stream:
            data = stream.read(target.size + 1)
        if len(data) != target.size:
            raise ValueError("Firmware size changed while reading the image")
        digest = hashlib.sha256(data).hexdigest()
        if digest != target.sha256:
            raise ValueError("Firmware SHA-256 does not match the manifest")
        app_offset = 0x10000 if factory else 0
        if data[0] != 0xe9 or data[app_offset:app_offset + 1] != b"\xe9" or data[app_offset + 32:app_offset + 36] != bytes.fromhex("3254cdab"):
            raise ValueError("This is not the expected ESP-IDF app-only/factory image")
        return FirmwareImage(board, self.version, target.filename, digest, data, "factory" if factory else "app")


def load_release(manifest_path: str | Path) -> FirmwareRelease:
    path = Path(manifest_path).resolve()
    if path.stat().st_size > 8192:
        raise ValueError("OTA manifest is too large")
    with path.open("r", encoding="utf-8") as stream:
        raw = stream.read(8193)
    if len(raw) > 8192:
        raise ValueError("OTA manifest is too large")
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or type(manifest.get("schema")) is not int:
        raise ValueError("Unsupported OTA manifest")
    schema = manifest["schema"]
    if schema == 1:
        if not isinstance(manifest.get("board"), str):
            raise ValueError("Unsupported firmware target")
        images = {manifest.get("board"): manifest}
    elif schema == 2:
        images = manifest.get("images")
    else:
        raise ValueError("Unsupported OTA manifest")
    if not isinstance(images, dict) or not 1 <= len(images) <= len(BOARD_CODES):
        raise ValueError("Invalid firmware target list")
    version = manifest.get("firmware")
    if not isinstance(version, str) or not 1 <= len(version) <= 32 or any(not 32 <= ord(c) <= 126 for c in version):
        raise ValueError("Invalid firmware version")
    targets = []
    for board, entry in images.items():
        if board not in BOARD_CODES or not isinstance(entry, dict) or entry.get("chip") != "esp32s3":
            raise ValueError("Unsupported firmware target")
        name = entry.get("filename")
        if (not isinstance(name, str) or not name.endswith(".app.bin") or
                any(part in ("", ".", "..") for part in name.split("/")) or
                "\\" in name or ":" in name or (schema == 1 and "/" in name)):
            raise ValueError("Manifest must refer to a local app-only image")
        size = entry.get("size")
        if type(size) is not int or not 256 <= size <= 4 * 1024 * 1024:
            raise ValueError("Invalid firmware size")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid firmware SHA-256")
        factory = None
        if "factory" in entry:
            item = entry["factory"]
            if not isinstance(item, dict):
                raise ValueError("Invalid factory image descriptor")
            factory_name, factory_size, factory_hash = item.get("filename"), item.get("size"), item.get("sha256")
            if (not isinstance(factory_name, str) or not factory_name.endswith(".factory.bin") or
                    any(part in ("", ".", "..") for part in factory_name.split("/")) or
                    "\\" in factory_name or ":" in factory_name or
                    type(factory_size) is not int or not 0x10100 <= factory_size <= 16 * 1024 * 1024 or
                    not isinstance(factory_hash, str) or len(factory_hash) != 64 or
                    any(c not in "0123456789abcdef" for c in factory_hash)):
                raise ValueError("Invalid factory image descriptor")
            factory = FirmwareBinary(factory_name, factory_size, factory_hash)
        targets.append(FirmwareTarget(board, name, size, digest, factory))
    return FirmwareRelease(version, path.parent, tuple(targets))


def load_image(manifest_path: str | Path, board: str | None = None) -> FirmwareImage:
    """Load legacy single-board manifests, or select one model from a release."""
    release = load_release(manifest_path)
    if board is None:
        if len(release.targets) != 1:
            raise ValueError("A connected board model is required for this release")
        board = release.targets[0].board
    return release.select(board)


OTA_CONTROL_UUID = "f42aa901-5ac7-4b64-983a-2c4433216101"
OTA_DATA_UUID = "f42aa902-5ac7-4b64-983a-2c4433216101"
OTA_STATUS_UUID = "f42aa903-5ac7-4b64-983a-2c4433216101"
ERRORS = {
    1: "Disarm the board and finish keyboard activity before updating",
    2: "Safely eject the writable USB drive on its PC before updating",
    3: "Board rejected firmware size, target or transfer sequence",
    4: "Firmware SHA-256 verification failed; current firmware retained",
    5: "Firmware write/image validation failed; current firmware retained",
    6: "Firmware update aborted",
    7: "Firmware transfer timed out; current firmware retained",
}
BOARD_CODES = {"waveshare7": 1, "tqtpro": 2}
BOARD_NAMES = {"waveshare7": "Waveshare 7-inch", "tqtpro": "T-QT Pro"}


async def upload_image(client, image: FirmwareImage, progress: Callable[[str, int], None], cancelled=None) -> None:
    if not client.is_connected:
        raise ValueError("Connect the board over Bluetooth first")
    if image.kind != "app":
        raise ValueError("Bluetooth OTA requires an app-only image")
    if image.board not in BOARD_CODES:
        raise ValueError("Unsupported Bluetooth firmware target")
    control = client.services.get_characteristic(OTA_CONTROL_UUID)
    data = client.services.get_characteristic(OTA_DATA_UUID)
    status = client.services.get_characteristic(OTA_STATUS_UUID)
    if control is None or data is None or status is None:
        raise ValueError("Bluetooth OTA services are not visible. On dev8 or newer, hold PAIR and use "
                         "Re-pair to refresh cached services. Older firmware needs the USB bootstrap.")
    tag = secrets.randbelow(0xffffffff) + 1
    prefix = bytes([1])
    tag_bytes = tag.to_bytes(4, "little")
    queue = asyncio.Queue(maxsize=32)
    verified = False
    began = False
    started_at = asyncio.get_running_loop().time()
    last_logged_percent = -10
    transfer_started_at = None
    previous_ack_at = None
    previous_accepted = 0
    smoothed_rate = None
    last_logged_at = started_at
    write_limit = None

    def notification(_sender, value):
        raw = bytes(value)
        if len(raw) == 11 and raw[0] == 1 and int.from_bytes(raw[3:7], "little") == tag:
            if not queue.full():
                queue.put_nowait(raw)

    def check_cancel():
        if cancelled is not None and cancelled.is_set():
            raise asyncio.CancelledError("Firmware update canceled")
        if not client.is_connected:
            raise ValueError("Bluetooth disconnected during firmware update")

    async def acknowledgment(kind, offset):
        deadline = asyncio.get_running_loop().time() + 15
        while True:
            check_cancel()
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("Verification acknowledgment was lost; check the board version before retrying"
                                   if kind == 2 else "Board did not acknowledge the firmware transfer")
            try:
                raw = await asyncio.wait_for(queue.get(), min(0.25, remaining))
            except TimeoutError:
                continue
            code, detail = raw[1], raw[2]
            accepted = int.from_bytes(raw[7:11], "little")
            if code == 3:
                raise ValueError(ERRORS.get(detail, "Board rejected firmware update"))
            if accepted > len(image.data):
                raise ValueError("Board reported an invalid firmware offset")
            if code == kind and accepted > offset:
                raise ValueError("Board reported an unexpected firmware offset")
            if code == kind and accepted == offset:
                return accepted

    check_cancel()
    if sys.platform == "linux" and isinstance(getattr(client, "address", None), str):
        from .linux_ota_link import negotiated_write_size
        progress("Checking Bluetooth packet size…", 0)
        write_limit = await negotiated_write_size(client.address, OTA_DATA_UUID)
    check_cancel()
    await client.start_notify(status, notification)
    try:
        progress(f"Preparing authenticated Bluetooth update for {BOARD_NAMES[image.board]}…", 0)
        check_cancel()
        begin = prefix + bytes([1]) + tag_bytes + len(image.data).to_bytes(4, "little") + bytes([BOARD_CODES[image.board]]) + bytes.fromhex(image.sha256)
        began = True
        logger.info("BLE OTA begin board=%s version=%s bytes=%d", image.board, image.version, len(image.data))
        await asyncio.wait_for(client.write_gatt_char(control, begin, response=True), 10)
        await acknowledgment(0, 0)
        # Respect the public negotiated write size. Four packets per window
        # fit the board's bounded eight-packet queue; acknowledgments represent
        # bytes accepted by the firmware writer, rather than queued by the OS.
        def packet_size():
            size = min(504, (write_limit if write_limit is not None else data.max_write_without_response_size) - 8)
            if size < 1:
                raise ValueError("Bluetooth write size is too small for firmware packets")
            return size
        chunk_size = packet_size()
        logger.info("BLE OTA link write_without_response_bytes=%d payload_bytes=%d window_packets=4",
                    write_limit if write_limit is not None else data.max_write_without_response_size, chunk_size)
        transfer_started_at = previous_ack_at = asyncio.get_running_loop().time()
        sent = 0
        while sent < len(image.data):
            # Some backends initially expose the minimum MTU and report its
            # negotiated size later. Never freeze that first tiny value for
            # the whole image. BlueZ's acquired MTU belongs to this live link.
            next_size = packet_size()
            if next_size != chunk_size:
                logger.info("BLE OTA payload changed old=%d new=%d", chunk_size, next_size)
                chunk_size = next_size
            for _ in range(4):
                check_cancel()
                if sent == len(image.data):
                    break
                part = image.data[sent:sent + chunk_size]
                frame = tag_bytes + sent.to_bytes(4, "little") + part
                await asyncio.wait_for(client.write_gatt_char(data, frame, response=False), 5)
                sent += len(part)
            accepted = await acknowledgment(1, sent)
            percent = min(98, accepted * 98 // len(image.data))
            now = asyncio.get_running_loop().time()
            interval = now - previous_ack_at
            if interval > 0:
                rate = (accepted - previous_accepted) / interval
                smoothed_rate = rate if smoothed_rate is None else 0.25 * rate + 0.75 * smoothed_rate
            average_rate = accepted / max(now - transfer_started_at, 0.001)
            remaining = (len(image.data) - accepted) / max(smoothed_rate or average_rate, 0.001)
            minutes, seconds = divmod(int(remaining + 0.999), 60)
            progress(f"Updating {BOARD_NAMES[image.board]} · {average_rate / 1024:.1f} KiB/s · "
                     f"about {minutes}m {seconds:02d}s remaining", percent)
            if percent >= last_logged_percent + 10 or now - last_logged_at >= 5:
                logger.info("BLE OTA transfer accepted=%d total=%d progress=%d bytes_per_second=%.1f remaining_seconds=%.0f",
                            accepted, len(image.data), percent, average_rate, remaining)
                last_logged_percent = percent
                last_logged_at = now
            previous_ack_at, previous_accepted = now, accepted
        check_cancel()
        progress("Verifying image on the board…", 99)
        await asyncio.wait_for(client.write_gatt_char(control, prefix + bytes([2]) + tag_bytes, response=True), 10)
        await acknowledgment(2, len(image.data))
        verified = True
        logger.info("BLE OTA verified board=%s version=%s seconds=%.2f", image.board, image.version,
                    asyncio.get_running_loop().time() - started_at)
        progress("Verified. Board is restarting into programming mode.", 100)
    finally:
        if began and not verified and client.is_connected:
            logger.info("BLE OTA incomplete; requesting abort before disconnect/retry")
            try:
                await asyncio.wait_for(client.write_gatt_char(control, prefix + bytes([3]) + tag_bytes, response=True), 3)
            except BaseException:
                pass
        if client.is_connected:
            try:
                await client.stop_notify(status)
            except Exception:
                pass
