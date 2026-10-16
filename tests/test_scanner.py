import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bt_scanner.devices import (
    address_int,
    format_address,
    merge_devices,
    parse_address,
    signal_percent,
)
from bt_scanner.view import (
    detail_label,
    detail_text,
    device_class,
    display_name,
    filter_devices,
    is_input_device,
    kind_label,
    pairing_message,
    services_label,
    sort_devices,
    state_label,
    summary_text,
    unpair_message,
)

HEADPHONES = {
    "address": "B8:F6:53:FE:2A:2C",
    "name": "JBL TUNE500BT",
    "kind": "classic",
    "rssi": -28,
    "signal": 100,
    "paired": True,
    "connected": False,
    "present": True,
    "cod_major": 4,
    "cod_minor": 1,
    "services": [
        "0000110b-0000-1000-8000-00805f9b34fb",
        "0000110e-0000-1000-8000-00805f9b34fb",
    ],
    "company_id": None,
}

MOUSE = {
    "address": "AA:BB:CC:DD:EE:01",
    "name": "",
    "kind": "ble",
    "rssi": -70,
    "signal": 50,
    "paired": False,
    "connected": False,
    "present": True,
    "cod_major": 5,
    "cod_minor": 0x20,
    "appearance": 15,
    "services": ["00001812-0000-1000-8000-00805f9b34fb"],
    "company_id": 0x004C,
}


class DeviceTests(unittest.TestCase):
    def test_address_and_signal(self) -> None:
        self.assertEqual(format_address(0xB8F653FE2A2C), "B8:F6:53:FE:2A:2C")
        self.assertEqual(parse_address("b8-f6-53-fe-2a-2c"), "B8:F6:53:FE:2A:2C")
        self.assertEqual(address_int("B8:F6:53:FE:2A:2C"), 0xB8F653FE2A2C)
        self.assertEqual(signal_percent(-28), 100)
        self.assertEqual(signal_percent(-70), 50)
        self.assertEqual(signal_percent(-100), 0)
        self.assertEqual(signal_percent(-120), 0)
        self.assertIsNone(signal_percent(None))

    def test_merge_keeps_identity_and_latest_facts(self) -> None:
        devices = merge_devices(
            [
                {
                    "address": "b8:f6:53:fe:2a:2c",
                    "name": "JBL TUNE500BT",
                    "kind": "classic",
                    "paired": True,
                    "connected": False,
                    "services": ["110B"],
                    "cod_major": 4,
                    "cod_minor": 1,
                },
                {
                    "address": "B8:F6:53:FE:2A:2C",
                    "kind": "ble",
                    "rssi": -40,
                    "present": True,
                    "name": "",
                },
            ]
        )
        self.assertEqual(len(devices), 1)
        device = devices[0]
        self.assertEqual(device["name"], "JBL TUNE500BT")
        self.assertEqual(device["kind"], "dual")
        self.assertTrue(device["paired"])
        self.assertFalse(device["connected"])
        self.assertTrue(device["present"])
        self.assertEqual(device["signal"], 100)
        self.assertEqual(device["services"], ["0000110b-0000-1000-8000-00805f9b34fb"])

    def test_later_connection_state_wins(self) -> None:
        devices = merge_devices(
            [
                {"address": "AA:BB:CC:DD:EE:10", "connected": True, "paired": True},
                {"address": "AA:BB:CC:DD:EE:10", "connected": False},
            ]
        )
        self.assertFalse(devices[0]["connected"])
        self.assertTrue(devices[0]["paired"])


class ViewTests(unittest.TestCase):
    def test_labels(self) -> None:
        self.assertEqual(display_name(HEADPHONES), "JBL TUNE500BT")
        self.assertEqual(display_name(MOUSE), "Dispositivo sin nombre")
        self.assertEqual(kind_label(HEADPHONES), "Clásico")
        self.assertEqual(state_label(HEADPHONES), "Emparejado")
        self.assertEqual(device_class(HEADPHONES), "Audio · Auriculares")
        self.assertEqual(device_class(MOUSE), "Periférico · Ratón")
        self.assertEqual(services_label(HEADPHONES), "Audio (receptor) · Control de audio")
        self.assertEqual(detail_label(MOUSE), "Apple")
        self.assertTrue(is_input_device(MOUSE))
        self.assertFalse(is_input_device(HEADPHONES))
        self.assertIn("JBL TUNE500BT", detail_text(HEADPHONES))
        self.assertIn("-28 dBm", detail_text(HEADPHONES))
        self.assertIn("Audio (receptor)", detail_text(HEADPHONES))

    def test_summary_filter_and_sort(self) -> None:
        radio = {
            "local_name": "Equipo",
            "state": "on",
            "address": "2C:3B:70:68:88:4E",
            "classic": True,
            "ble": True,
            "discoverable": False,
            "connectable": True,
        }
        text = summary_text(radio)
        self.assertIn("Equipo · Encendido", text)
        self.assertIn("Admite clásico y BLE", text)
        self.assertIn("No visible", text)
        rows = filter_devices([HEADPHONES, MOUSE], "auriculares")
        self.assertEqual(rows, [HEADPHONES])
        ordered = sort_devices([MOUSE, HEADPHONES], "signal")
        self.assertEqual(ordered[0]["address"], HEADPHONES["address"])
        by_state = sort_devices(
            [MOUSE, {**HEADPHONES, "connected": True}],
            "state",
        )
        self.assertTrue(by_state[0]["connected"])

    def test_action_messages(self) -> None:
        self.assertEqual(pairing_message("PAIRED"), "Emparejado.")
        self.assertEqual(pairing_message("PAIRING_CANCELED"), "Se canceló el emparejamiento.")
        self.assertIn("olvidó", unpair_message("UNPAIRED").lower())


class GuidTests(unittest.TestCase):
    def test_windows_guid_text(self) -> None:
        import ctypes

        from bt_scanner.classic import _Guid, guid_to_text

        guid = _Guid()
        raw = uuid.UUID("0000110b-0000-1000-8000-00805f9b34fb").bytes_le
        ctypes.memmove(ctypes.addressof(guid), raw, 16)
        self.assertEqual(guid_to_text(guid), "0000110b-0000-1000-8000-00805f9b34fb")


if __name__ == "__main__":
    unittest.main()
