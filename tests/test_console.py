import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bt_scanner.transcript import command_bytes, decode_incoming


class TranscriptTests(unittest.TestCase):
    def test_command_bytes_adds_the_chosen_ending(self) -> None:
        self.assertEqual(command_bytes("LED ON", "lf"), b"LED ON\n")
        self.assertEqual(command_bytes("LED ON", "crlf"), b"LED ON\r\n")
        self.assertEqual(command_bytes("LED ON", "none"), b"LED ON")
        self.assertEqual(command_bytes("", "lf"), b"\n")
        self.assertEqual(command_bytes("", "none"), b"")

    def test_command_bytes_does_not_duplicate_a_newline(self) -> None:
        self.assertEqual(command_bytes("LED ON\n", "crlf"), b"LED ON\n")
        self.assertEqual(command_bytes("tensión", "lf"), "tensión\n".encode("utf-8"))

    def test_decode_incoming_normalizes_newlines(self) -> None:
        self.assertEqual(decode_incoming(b"ok\r\nlisto\r"), "ok\nlisto\n")
        self.assertEqual(decode_incoming(b"caf\xe9"), "caf\ufffd")

    def test_link_module_does_not_import_winrt(self) -> None:
        import subprocess

        code = (
            "import bt_scanner.link, sys; "
            "raise SystemExit(0 if hasattr(bt_scanner.link, 'Link') and "
            "not any(name == 'winrt' or name.startswith('winrt.') for name in sys.modules) else 1)"
        )
        completed = subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=False)
        self.assertEqual(completed.returncode, 0)
