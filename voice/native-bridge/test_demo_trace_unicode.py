"""Acceptance telemetry must round-trip Unicode on narrow Windows consoles."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from demo_audio_smoke import Trace


class TraceUnicodeTests(unittest.TestCase):
    def test_console_encoding_does_not_abort_or_lose_a_dialog_event(self):
        text = 'Ja \u65e5\u672c\u8a9e \U0001f50a'
        raw = io.BytesIO()
        console = io.TextIOWrapper(raw, encoding='cp1252', errors='strict')
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'report.json'
            with redirect_stdout(console):
                Trace(target).add('dialog_ready', text=text)
            console.flush()
            self.assertEqual(json.loads(raw.getvalue().decode('cp1252'))['text'], text)
            self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['events'][0]['text'], text)


if __name__ == '__main__':
    unittest.main()
