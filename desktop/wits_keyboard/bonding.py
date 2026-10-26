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


async def windows_link_is_up(address: str) -> bool:
    """True if Windows already holds a live connection to this board (it reconnects "maintained" sessions by
    itself, and a connected board stops advertising, so scanning alone would never see it)."""
    if sys.platform != "win32":
        return False
    try:
        from winrt.windows.devices.bluetooth import BluetoothConnectionStatus, BluetoothLEDevice
        async with asyncio.timeout(5):
            native = await BluetoothLEDevice.from_bluetooth_address_async(int(address.replace(":", ""), 16))
        if native is None:
            return False
        try:
            return native.connection_status == BluetoothConnectionStatus.CONNECTED
        finally:
            native.close()
    except Exception:
        return False
