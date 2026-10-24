"""Read OS pairing state without initiating or replacing a bond."""
import asyncio
import sys


class PairingRequired(RuntimeError):
    pass


async def has_saved_bond(device):
    async with asyncio.timeout(8):
        if sys.platform == "linux":
            from .linux_diagnostics import cached_linux_device
            cached = await cached_linux_device(device.address)
            return bool(cached and cached.details.get("props", {}).get("Paired"))
        if sys.platform == "win32":
            from winrt.windows.devices.bluetooth import BluetoothLEDevice
            native = await BluetoothLEDevice.from_bluetooth_address_async(int(device.address.replace(":", ""), 16))
            if native is None:
                return False
            try:
                return bool(native.device_information.pairing.is_paired)
            finally:
                native.close()
    raise RuntimeError("Automatic reconnect supports Windows and Linux")
