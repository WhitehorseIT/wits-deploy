"""Windows pairing from inside the app.

The board shows a six-digit PIN and the computer must type it back ("provide PIN" pairing). Bleak's
Windows backend only supports confirm-style pairing, so this talks to the Windows pairing API directly
and answers the PIN request with the same prompt the Linux version uses.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)
PasskeyCallback = Callable[[str, str], Awaitable[int | None]]


class WindowsPairingError(RuntimeError):
    pass


def describe_status(status: Any) -> str:
    """A readable reason for a failed pairing result."""
    name = getattr(status, "name", str(status)).replace("_", " ").lower()
    hints = {
        "authentication failure": "the PIN was wrong, or the board's pairing window closed",
        "rejected by handler": "the PIN entry was cancelled",
        "pairing canceled": "pairing was cancelled",
        "connection rejected": "the board refused the connection; hold its pairing button until the PIN shows",
        "authentication timeout": "pairing timed out; hold the board's pairing button and try again",
        "protection level could not be met": "Windows could not reach the required security level",
    }
    return f"Windows pairing failed: {hints.get(name, name)}"


async def pair_windows(device: Any, callback: PasskeyCallback, timeout: float = 90.0) -> bool:
    """Pair with ``device``. True if a new bond was made, False if one already existed."""
    from winrt.windows.devices.bluetooth import BluetoothLEDevice
    from winrt.windows.devices.enumeration import (
        DevicePairingKinds, DevicePairingProtectionLevel, DevicePairingResultStatus)

    loop = asyncio.get_running_loop()
    address = int(device.address.replace(":", ""), 16)
    native = await BluetoothLEDevice.from_bluetooth_address_async(address)
    if native is None:
        raise WindowsPairingError("Windows cannot see this board yet. Hold its pairing button until a PIN "
                                  "shows, then scan again.")
    try:
        pairing = native.device_information.pairing
        if pairing.is_paired:
            logger.info("Existing Windows bond address=%s; PIN not requested", device.address)
            return False
        name = device.name or "WITS Deploy"
        custom = pairing.custom

        def on_pairing_requested(_sender: Any, args: Any) -> None:
            # Windows calls this on its own thread. Take a deferral, ask the app's PIN prompt on the
            # asyncio loop, then answer and release the deferral.
            kind = args.pairing_kind
            logger.info("Windows pairing request address=%s kind=%s", device.address, kind)
            if kind == DevicePairingKinds.PROVIDE_PIN:
                deferral = args.get_deferral()
                future = asyncio.run_coroutine_threadsafe(callback(device.address, name), loop)

                def answered(done: Any) -> None:
                    try:
                        pin = done.result()
                        if pin is not None:
                            text = f"{int(pin):06d}"
                            getattr(args, "accept_with_pin", args.accept)(text)
                    except Exception:
                        logger.exception("Windows PIN answer failed address=%s", device.address)
                    finally:
                        deferral.complete()

                future.add_done_callback(answered)
            elif kind in (DevicePairingKinds.CONFIRM_ONLY, DevicePairingKinds.CONFIRM_PIN_MATCH):
                args.accept()
            # Anything else is left unanswered, which fails the pairing cleanly.

        token = custom.add_pairing_requested(on_pairing_requested)
        try:
            kinds = (DevicePairingKinds.PROVIDE_PIN | DevicePairingKinds.CONFIRM_ONLY
                     | DevicePairingKinds.CONFIRM_PIN_MATCH)
            result = await asyncio.wait_for(
                custom.pair_async(kinds, DevicePairingProtectionLevel.ENCRYPTION_AND_AUTHENTICATION), timeout)
        finally:
            custom.remove_pairing_requested(token)
        status = result.status
        logger.info("Windows pairing result address=%s status=%s", device.address, status)
        if status == DevicePairingResultStatus.PAIRED:
            return True
        if status == DevicePairingResultStatus.ALREADY_PAIRED:
            return False
        raise WindowsPairingError(describe_status(status))
    finally:
        native.close()
