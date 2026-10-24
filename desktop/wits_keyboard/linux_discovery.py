"""Keep a targeted BlueZ discovery session alive during Linux connection.

A saved Device1 object proves identity/bond state, not current radio presence.
Own the discovery on a separate D-Bus connection so its lifecycle cannot stop
the desktop's discovery session or collide with Bleak's shared scanner bus.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from dbus_fast import BusType, DBusError, Message, MessageType, Variant
from dbus_fast.aio import MessageBus

logger = logging.getLogger(__name__)


class LinuxConnectionDiscovery:
    def __init__(self, device: Any, callback: Callable[..., None]) -> None:
        self.address = device.address
        self.path = device.details["path"]
        self.adapter = self.path.rsplit("/dev_", 1)[0]
        self.callback = callback
        self.seen = asyncio.Event()
        self.bus: Any = None
        self.started = False

    async def _call(self, destination: str, path: str, interface: str,
                    member: str, signature: str = "", body: list[Any] | None = None) -> Any:
        reply = await self.bus.call(Message(
            destination=destination, path=path, interface=interface,
            member=member, signature=signature, body=body or [],
        ))
        if reply.message_type == MessageType.ERROR:
            raise DBusError(reply.error_name, reply.body[0] if reply.body else "BlueZ error")
        return reply

    def _on_message(self, message: Any) -> None:
        if message.message_type != MessageType.SIGNAL:
            return
        properties = None
        if message.path == self.path and message.interface == "org.freedesktop.DBus.Properties" \
                and message.member == "PropertiesChanged" and len(message.body) == 3 \
                and message.body[0] == "org.bluez.Device1":
            properties = message.body[1]
        elif message.interface == "org.freedesktop.DBus.ObjectManager" \
                and message.member == "InterfacesAdded" and len(message.body) == 2 \
                and message.body[0] == self.path:
            properties = message.body[1].get("org.bluez.Device1", {})
        # Do not accept a cached Name/Paired/Connected change as a live report.
        if properties is not None and "RSSI" in properties and not self.seen.is_set():
            logger.info("Live advertisement received address=%s rssi=%s",
                        self.address, properties["RSSI"].value)
            self.seen.set()
            self.callback("progress", message="Board found over Bluetooth; connecting…")

    async def start(self) -> None:
        self.callback("progress", message="Checking for the board's live HID advertisement…")
        self.bus = MessageBus(bus_type=BusType.SYSTEM)
        try:
            async with asyncio.timeout(5):
                await self.bus.connect()
                reply = await self._call("org.bluez", self.path,
                                         "org.freedesktop.DBus.Properties", "GetAll", "s",
                                         ["org.bluez.Device1"])
                connected = reply.body[0].get("Connected")
                if connected is not None and connected.value:
                    logger.info("Existing live BLE link address=%s; discovery not required", self.address)
                    self.callback("progress", message="Existing Bluetooth link found; authenticating…")
                    return
                self.bus.add_message_handler(self._on_message)
                for rule in (
                    f"type='signal',sender='org.bluez',path='{self.path}',interface='org.freedesktop.DBus.Properties'",
                    "type='signal',sender='org.bluez',interface='org.freedesktop.DBus.ObjectManager',member='InterfacesAdded'",
                ):
                    await self._call("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                     "org.freedesktop.DBus", "AddMatch", "s", [rule])
                await self._call("org.bluez", self.adapter, "org.bluez.Adapter1",
                                 "SetDiscoveryFilter", "a{sv}", [{
                                     "Transport": Variant("s", "le"),
                                     "Pattern": Variant("s", self.address),
                                     "RSSI": Variant("n", -127),
                                     "DuplicateData": Variant("b", True),
                                 }])
                await self._call("org.bluez", self.adapter, "org.bluez.Adapter1", "StartDiscovery")
                self.started = True
                logger.info("Targeted discovery started address=%s adapter=%s", self.address, self.adapter)
            try:
                await asyncio.wait_for(self.seen.wait(), timeout=8)
            except TimeoutError:
                raise RuntimeError(
                    "Linux knows this board, but did not see it advertising. "
                    "Check it is powered, nearby and in HID mode with rc12 or newer. "
                    "Any saved pairing has been kept."
                ) from None
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        if self.bus is None:
            return
        self.bus.remove_message_handler(self._on_message)
        try:
            if self.started:
                async with asyncio.timeout(2):
                    await self._call("org.bluez", self.adapter, "org.bluez.Adapter1", "StopDiscovery")
        except (DBusError, OSError, TimeoutError):
            logger.debug("Discovery cleanup deferred to bus close address=%s", self.address)
        finally:
            self.bus.disconnect()
            self.bus = None
            self.started = False
