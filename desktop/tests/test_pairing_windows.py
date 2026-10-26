import asyncio
import sys
import types
import unittest
from enum import IntFlag
from unittest.mock import MagicMock

from wits_keyboard import pairing_windows


class Kinds(IntFlag):
    NONE = 0
    CONFIRM_ONLY = 1
    DISPLAY_PIN = 2
    PROVIDE_PIN = 4
    CONFIRM_PIN_MATCH = 8


class Level:
    ENCRYPTION_AND_AUTHENTICATION = 3


class Status:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return getattr(other, "name", other) == self.name

    def __hash__(self):
        return hash(self.name)


class Results:
    PAIRED, ALREADY_PAIRED = Status("PAIRED"), Status("ALREADY_PAIRED")
    AUTHENTICATION_FAILURE = Status("AUTHENTICATION_FAILURE")


class Unpair:
    UNPAIRED, ALREADY_UNPAIRED, FAILED = Status("UNPAIRED"), Status("ALREADY_UNPAIRED"), Status("FAILED")


class FakeArgs:
    def __init__(self, kind):
        self.pairing_kind = kind
        self.accepted = []
        self.deferral_done = asyncio.Event()
        self.completed = False

    def get_deferral(self):
        outer = self
        return types.SimpleNamespace(complete=lambda: setattr(outer, "completed", True))

    def accept(self, *pin):
        self.accepted.append(pin)


class FakeCustom:
    """Plays the Windows side: raises a pairing request, then reports a result."""

    def __init__(self, kind, status, args_holder):
        self.kind, self.status, self.args_holder, self.handler = kind, status, args_holder, None
        self.removed = False

    def add_pairing_requested(self, handler):
        self.handler = handler
        return "token"

    def remove_pairing_requested(self, token):
        self.removed = token == "token"

    async def pair_async(self, kinds, level):
        self.requested = (kinds, level)
        args = FakeArgs(self.kind)
        self.args_holder.append(args)
        self.handler(None, args)
        await asyncio.sleep(0.05)  # lets the answer arrive from the asyncio loop
        return types.SimpleNamespace(status=self.status)


def install_fakes(custom, paired=False, missing=False, unpair_status=None):
    async def unpair_async():
        return types.SimpleNamespace(status=unpair_status)

    native = types.SimpleNamespace(
        device_information=types.SimpleNamespace(pairing=types.SimpleNamespace(
            is_paired=paired, custom=custom, unpair_async=unpair_async)),
        close=MagicMock())

    async def from_address(_address):
        return None if missing else native

    bluetooth = types.ModuleType("winrt.windows.devices.bluetooth")
    bluetooth.BluetoothLEDevice = types.SimpleNamespace(from_bluetooth_address_async=from_address)
    enumeration = types.ModuleType("winrt.windows.devices.enumeration")
    enumeration.DevicePairingKinds = Kinds
    enumeration.DevicePairingProtectionLevel = Level
    enumeration.DevicePairingResultStatus = Results
    enumeration.DeviceUnpairingResultStatus = Unpair
    for name, module in (("winrt", types.ModuleType("winrt")), ("winrt.windows", types.ModuleType("winrt.windows")),
                         ("winrt.windows.devices", types.ModuleType("winrt.windows.devices")),
                         ("winrt.windows.devices.bluetooth", bluetooth),
                         ("winrt.windows.devices.enumeration", enumeration)):
        sys.modules[name] = module
    return native


class WindowsPairingTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        for name in [n for n in sys.modules if n == "winrt" or n.startswith("winrt.")]:
            del sys.modules[name]

    device = types.SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="WITS Deploy-1234")

    async def test_the_pin_is_asked_for_and_sent_to_windows(self):
        holder, asked = [], []
        custom = FakeCustom(Kinds.PROVIDE_PIN, Results.PAIRED, holder)
        native = install_fakes(custom)

        async def prompt(address, name):
            asked.append((address, name))
            return 4821

        self.assertTrue(await pairing_windows.pair_windows(self.device, prompt))
        self.assertEqual(asked, [("AA:BB:CC:DD:EE:FF", "WITS Deploy-1234")])
        self.assertEqual(holder[0].accepted, [("004821",)])  # zero padded to six digits
        self.assertTrue(holder[0].completed)
        self.assertTrue(custom.removed)
        native.close.assert_called_once()
        self.assertIn(Kinds.PROVIDE_PIN, custom.requested[0])
        self.assertEqual(custom.requested[1], Level.ENCRYPTION_AND_AUTHENTICATION)

    async def test_cancelling_the_pin_prompt_fails_pairing_without_answering(self):
        holder = []
        custom = FakeCustom(Kinds.PROVIDE_PIN, Results.AUTHENTICATION_FAILURE, holder)
        install_fakes(custom)

        async def prompt(address, name):
            return None

        with self.assertRaises(pairing_windows.WindowsPairingError) as raised:
            await pairing_windows.pair_windows(self.device, prompt)
        self.assertEqual(holder[0].accepted, [])
        self.assertTrue(holder[0].completed)
        self.assertIn("PIN was wrong", str(raised.exception))

    async def test_confirm_style_requests_are_accepted(self):
        holder = []
        install_fakes(FakeCustom(Kinds.CONFIRM_ONLY, Results.PAIRED, holder))
        self.assertTrue(await pairing_windows.pair_windows(self.device, lambda *a: None))
        self.assertEqual(holder[0].accepted, [()])

    async def test_an_existing_bond_asks_for_nothing(self):
        custom = FakeCustom(Kinds.PROVIDE_PIN, Results.PAIRED, [])
        install_fakes(custom, paired=True)
        self.assertFalse(await pairing_windows.pair_windows(self.device, lambda *a: None))
        self.assertIsNone(custom.handler)

    async def test_a_board_windows_cannot_see_gives_a_clear_message(self):
        install_fakes(FakeCustom(Kinds.PROVIDE_PIN, Results.PAIRED, []), missing=True)
        with self.assertRaises(pairing_windows.WindowsPairingError) as raised:
            await pairing_windows.pair_windows(self.device, lambda *a: None)
        self.assertIn("pairing button", str(raised.exception))

    async def test_unpair_removes_the_windows_pairing(self):
        native = install_fakes(None, paired=True, unpair_status=Unpair.UNPAIRED)
        self.assertIn("Removed", await pairing_windows.unpair_windows("AA:BB:CC:DD:EE:FF"))
        native.close.assert_called_once()

    async def test_unpair_of_an_unknown_or_unpaired_board_is_not_an_error(self):
        install_fakes(None, missing=True)
        self.assertIn("no pairing", await pairing_windows.unpair_windows("AA:BB:CC:DD:EE:FF"))
        install_fakes(None, paired=False)
        self.assertIn("no pairing", await pairing_windows.unpair_windows("AA:BB:CC:DD:EE:FF"))

    async def test_unpair_failure_says_to_use_windows_settings(self):
        install_fakes(None, paired=True, unpair_status=Unpair.FAILED)
        with self.assertRaises(pairing_windows.WindowsPairingError) as raised:
            await pairing_windows.unpair_windows("AA:BB:CC:DD:EE:FF")
        self.assertIn("Windows Settings", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
