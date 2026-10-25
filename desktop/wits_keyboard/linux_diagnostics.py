"""Read-only BlueZ state/reason diagnostics, scoped to one selected board."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from dbus_fast import BusType, DBusError, Message, MessageType
from dbus_fast.aio import MessageBus

logger = logging.getLogger(__name__)
DEVICE_FIELDS = ("Paired", "Bonded", "Connected", "ServicesResolved", "Trusted", "Blocked")
ADAPTER_FIELDS = ("Powered", "Discovering")


async def cached_linux_device(address: str) -> Any:
    """Resolve a remembered board from BlueZ without requiring advertising."""
    from bleak.backends.device import BLEDevice

    bus = MessageBus(bus_type=BusType.SYSTEM)
    try:
        async with asyncio.timeout(5):
            await bus.connect()
            reply = await bus.call(Message(
                destination="org.bluez", path="/",
                interface="org.freedesktop.DBus.ObjectManager", member="GetManagedObjects",
            ))
            if reply.message_type == MessageType.ERROR:
                raise DBusError(reply.error_name, reply.body[0] if reply.body else "BlueZ error")
            for path, interfaces in reply.body[0].items():
                values = interfaces.get("org.bluez.Device1", {})
                if "Address" not in values or values["Address"].value.lower() != address.lower():
                    continue
                props = {key: value.value for key, value in values.items()}
                return BLEDevice(props["Address"], props.get("Name", "WITS Deploy"),
                                 {"path": path, "props": props})
        return None
    finally:
        bus.disconnect()


class BlueZDiagnostics:
    def __init__(self, device: Any, callback: Callable[..., None]) -> None:
        self.address = device.address
        self.path = device.details["path"]
        self.adapter_path = self.path.rsplit("/dev_", 1)[0]
        self.callback = callback
        self.bus: Any = None
        self.rules: list[str] = []
        self.last_reason = ""

    async def _call(self, destination: str, path: str, interface: str,
                    member: str, signature: str = "", body: list[Any] | None = None) -> Any:
        reply = await self.bus.call(Message(
            destination=destination, path=path, interface=interface,
            member=member, signature=signature, body=body or [],
        ))
        if reply.message_type == MessageType.ERROR:
            raise DBusError(reply.error_name, reply.body[0] if reply.body else "BlueZ error")
        return reply

    async def start(self) -> None:
        self.bus = MessageBus(bus_type=BusType.SYSTEM)
        try:
            async with asyncio.timeout(5):
                await self.bus.connect()
                self.bus.add_message_handler(self._on_message)
                for path in (self.path, self.adapter_path):
                    rule = f"type='signal',sender='org.bluez',path='{path}'"
                    await self._call("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                     "org.freedesktop.DBus", "AddMatch", "s", [rule])
                    self.rules.append(rule)
                await self.snapshot("before pairing/connect")
        except BaseException:
            await self.close()
            raise

    async def snapshot(self, stage: str) -> None:
        async with asyncio.timeout(3):
            for path, interface, fields in (
                (self.path, "org.bluez.Device1", DEVICE_FIELDS),
                (self.adapter_path, "org.bluez.Adapter1", ADAPTER_FIELDS),
            ):
                reply = await self._call("org.bluez", path,
                                         "org.freedesktop.DBus.Properties", "GetAll", "s",
                                         [interface])
                values = {key: reply.body[0][key].value for key in fields if key in reply.body[0]}
                logger.info("BlueZ snapshot address=%s stage=%s interface=%s state=%s",
                            self.address, stage, interface, values)

    def _on_message(self, message: Any) -> None:
        if message.message_type != MessageType.SIGNAL:
            return
        if message.path == self.path and message.interface == "org.bluez.Device1" \
                and message.member == "Disconnected" and len(message.body) == 2:
            reason, description = message.body
            self.last_reason = reason
            logger.warning("BlueZ disconnect address=%s reason=%s description=%s",
                           self.address, reason, description)
            if reason == "org.bluez.Reason.Authentication":
                text = "Bluetooth authentication failed. Hold left for a PIN, then choose Re-pair."
            elif reason == "org.bluez.Reason.Timeout":
                text = "Bluetooth connection timed out. Check the board is powered and nearby."
            elif reason == "org.bluez.Reason.Remote":
                text = "The board ended the Bluetooth connection."
            elif reason == "org.bluez.Reason.Local":
                text = "Linux ended the Bluetooth connection."
            else:
                text = "Bluetooth disconnected; see the debug log for its reported reason."
            self.callback("link_diagnostic", message=text, reason=reason)
        elif message.interface == "org.freedesktop.DBus.Properties" \
                and message.member == "PropertiesChanged" and len(message.body) == 3:
            interface, changed, _invalid = message.body
            fields = DEVICE_FIELDS if message.path == self.path else ADAPTER_FIELDS
            if message.path not in (self.path, self.adapter_path):
                return
            values = {key: changed[key].value for key in fields if key in changed}
            if values:
                logger.info("BlueZ state changed address=%s interface=%s state=%s",
                            self.address, interface, values)

    async def close(self) -> None:
        bus, self.bus = self.bus, None
        if bus is None:
            return
        bus.remove_message_handler(self._on_message)
        # Closing the private bus also removes all of its signal match rules.
        self.rules.clear()
        bus.disconnect()
