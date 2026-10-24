"""Linux pairing through an application-owned BlueZ passkey agent.

The agent and Device1.Pair call must use the SAME D-Bus connection. Registering
an agent on a separate connection from Bleak's Pair call would still leave
BlueZ using the desktop's default agent.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from dbus_fast import BusType, DBusError, Message, MessageType
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method

logger = logging.getLogger(__name__)
PasskeyCallback = Callable[[str, str], Awaitable[int | None]]
AGENT_PATH = "/com/whitehorseit/WitsKeyboard/PairingAgent"


class PasskeyAgent(ServiceInterface):
    def __init__(self, device: Any, callback: PasskeyCallback) -> None:
        super().__init__("org.bluez.Agent1")
        self.device_path = device.details["path"]
        self.address = device.address
        # ServiceInterface.name is the D-Bus interface identity. Overwriting it
        # exports our methods under the board name, so BlueZ gets UnknownMethod.
        self.device_name = device.name or "WITS Keyboard"
        self.callback = callback
        self.prompt_task: asyncio.Task[int | None] | None = None

    def _check_device(self, device: str) -> None:
        if device != self.device_path:
            raise DBusError("org.bluez.Error.Rejected", "Unexpected pairing device")

    def cancel(self) -> None:
        if self.prompt_task is not None:
            self.prompt_task.cancel()

    async def request_passkey(self, device: str) -> int:
        self._check_device(device)
        if self.prompt_task is not None:
            raise DBusError("org.bluez.Error.InProgress", "PIN entry already active")
        logger.info("BlueZ requested PIN entry address=%s", self.address)
        self.prompt_task = asyncio.create_task(self.callback(self.address, self.device_name))
        try:
            value = await asyncio.wait_for(self.prompt_task, timeout=60.0)
            if value is None:
                raise DBusError("org.bluez.Error.Canceled", "PIN entry canceled")
            if type(value) is not int or not 0 <= value <= 999999:
                raise DBusError("org.bluez.Error.Rejected", "Invalid six-digit PIN")
            logger.info("PIN entry submitted address=%s value=omitted", self.address)
            return value
        except (asyncio.CancelledError, TimeoutError):
            raise DBusError("org.bluez.Error.Canceled", "PIN entry canceled or expired") from None
        finally:
            self.prompt_task = None

    @method()
    async def RequestPasskey(self, device: "o") -> "u":
        return await self.request_passkey(device)

    @method()
    def RequestPinCode(self, device: "o") -> "s":
        self._check_device(device)
        raise DBusError("org.bluez.Error.Rejected", "Legacy PIN pairing is unsupported")

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u"):
        self._check_device(device)
        raise DBusError("org.bluez.Error.Rejected", "Enter the PIN displayed on the board")

    @method()
    def RequestAuthorization(self, device: "o"):
        self._check_device(device)
        raise DBusError("org.bluez.Error.Rejected", "Pairing requires the board's PIN")

    @method()
    def AuthorizeService(self, device: "o", uuid: "s"):
        self._check_device(device)
        from .protocol import SERVICE_UUID

        if uuid.lower() != SERVICE_UUID:
            raise DBusError("org.bluez.Error.Rejected", "Unexpected service")

    @method()
    def Cancel(self):
        logger.info("BlueZ canceled pairing prompt address=%s", self.address)
        self.cancel()

    @method()
    def Release(self):
        self.cancel()


async def pair_linux(device: Any, callback: PasskeyCallback) -> bool:
    """Pair this device using our prompt; do not replace the default OS agent."""
    bus = MessageBus(bus_type=BusType.SYSTEM)
    agent = PasskeyAgent(device, callback)
    registered = False
    pair_started = False

    async def call(path: str, interface: str, member: str,
                   signature: str = "", body: list[Any] | None = None) -> Any:
        reply = await bus.call(Message(
            destination="org.bluez", path=path, interface=interface,
            member=member, signature=signature, body=body or [],
        ))
        if reply.message_type == MessageType.ERROR:
            raise DBusError(reply.error_name, reply.body[0] if reply.body else "BlueZ error")
        return reply

    try:
        async with asyncio.timeout(90):
            await bus.connect()
            reply = await call(agent.device_path, "org.freedesktop.DBus.Properties",
                               "Get", "ss", ["org.bluez.Device1", "Paired"])
            if reply.body[0].value:
                logger.info("Existing OS bond address=%s; PIN not requested", device.address)
                return False
            bus.export(AGENT_PATH, agent)
            await call("/org/bluez", "org.bluez.AgentManager1", "RegisterAgent",
                       "os", [AGENT_PATH, "KeyboardOnly"])
            registered = True
            logger.info("App pairing agent registered address=%s", device.address)
            pair_started = True
            await call(agent.device_path, "org.bluez.Device1", "Pair")
            pair_started = False
            logger.info("App-agent pairing completed address=%s", device.address)
            return True
    finally:
        agent.cancel()
        if bus.connected:
            try:
                async with asyncio.timeout(3):
                    if pair_started:
                        try:
                            await call(agent.device_path, "org.bluez.Device1", "CancelPairing")
                        except DBusError:
                            pass
                    if registered:
                        await call("/org/bluez", "org.bluez.AgentManager1",
                                   "UnregisterAgent", "o", [AGENT_PATH])
            except (DBusError, TimeoutError):
                logger.debug("Pairing agent cleanup incomplete address=%s", device.address)
        bus.unexport(AGENT_PATH)
        bus.disconnect()
