"""Obtain the current connection's MTU using BlueZ's public AcquireWrite API."""
import asyncio
import logging
import os

logger = logging.getLogger(__name__)


async def negotiated_write_size(address: str, uuid: str) -> int | None:
    # Acquiring then closing this socket forces completion of MTU negotiation.
    # The socket is never used for payloads; ordinary Bleak writes resume only
    # after BlueZ confirms its temporary WriteValue lock has been released.
    from dbus_fast import BusType, Message, MessageType
    from dbus_fast.aio import MessageBus
    bus = MessageBus(bus_type=BusType.SYSTEM, negotiate_unix_fd=True)
    descriptors = []
    acquired = False
    try:
        async with asyncio.timeout(8):
            await bus.connect()
            reply = await bus.call(Message(destination="org.bluez", path="/",
                interface="org.freedesktop.DBus.ObjectManager", member="GetManagedObjects"))
            if reply.message_type == MessageType.ERROR:
                return None
            objects = reply.body[0]
            devices = [path for path, interfaces in objects.items()
                       if (device := interfaces.get("org.bluez.Device1")) and
                       device.get("Address") and device["Address"].value.upper() == address.upper() and
                       device.get("Connected") and device["Connected"].value]
            paths = [path for path, interfaces in objects.items()
                     if any(path.startswith(device + "/") for device in devices) and
                     (char := interfaces.get("org.bluez.GattCharacteristic1")) and
                     char.get("UUID") and char["UUID"].value.lower() == uuid.lower() and
                     "WriteAcquired" in char and not char["WriteAcquired"].value]
            if len(paths) != 1:
                return None
            path = paths[0]
            reply = await bus.call(Message(destination="org.bluez", path=path,
                interface="org.bluez.GattCharacteristic1", member="AcquireWrite",
                signature="a{sv}", body=[{}]))
            descriptors = list(reply.unix_fds)
            if reply.message_type == MessageType.ERROR:
                logger.info("BlueZ OTA MTU query unavailable error=%s", reply.error_name)
                return None
            acquired = True
            index, mtu = reply.body
            if not descriptors or not 0 <= index < len(descriptors) or not 23 <= mtu <= 517:
                raise ValueError("BlueZ returned an invalid OTA write socket/MTU")
            for descriptor in descriptors:
                os.close(descriptor)
            descriptors = []
            while True:
                reply = await bus.call(Message(destination="org.bluez", path=path,
                    interface="org.freedesktop.DBus.Properties", member="Get",
                    signature="ss", body=["org.bluez.GattCharacteristic1", "WriteAcquired"]))
                if reply.message_type == MessageType.ERROR:
                    raise RuntimeError("Could not confirm Bluetooth write lock release; reconnect before retrying")
                if not reply.body[0].value:
                    logger.info("BlueZ OTA negotiated mtu=%d write_bytes=%d", mtu, min(512, mtu - 3))
                    return min(512, mtu - 3)
                await asyncio.sleep(0.02)
    except TimeoutError:
        # Disconnecting this bus also releases any server-side acquisition.
        if acquired:
            raise RuntimeError("Bluetooth write channel did not release; reconnect before retrying") from None
        logger.warning("BlueZ OTA MTU query timed out; using the reported write limit")
        return None
    except (OSError, ConnectionError) as error:
        logger.warning("BlueZ OTA MTU query unavailable: %s", type(error).__name__)
        return None
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
        bus.disconnect()
