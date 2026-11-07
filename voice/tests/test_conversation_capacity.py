"""Offline startup guard for a direct Voice route after controller selection."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


path = Path(__file__).resolve().parents[1] / 'native-start/start_current_voice.py'
spec = importlib.util.spec_from_file_location('conversation_capacity_starter', path)
starter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(starter)


class ConversationCapacityTests(unittest.TestCase):
    def test_direct_route_requires_parallel_controller_and_halogen_slots(self):
        cases = (
            (8840, 1, 1, False),
            (8840, 2, 1, False),
            (8840, 2, 2, True),
            (8841, 1, 1, True),
            (8841, 2, 2, True),
        )
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'native.json'
            for port, concurrency, slots, allowed in cases:
                with self.subTest(port=port, concurrency=concurrency, slots=slots):
                    config.write_text(json.dumps(dict(conversation_transport='controller-text',
                        conversation_http_url=f'http://127.0.0.1:{port}/v1/chat/completions')))
                    selected = dict(profile=dict(concurrency=concurrency,
                        engine=dict(kind='halogen', slots=slots)))
                    with patch.object(starter, 'NATIVE_CONFIG', config), \
                            patch.object(starter, 'selected_controller', selected):
                        if allowed:
                            self.assertIsNone(starter.conversation_stage(check_only=True))
                        else:
                            with self.assertRaisesRegex(RuntimeError, '8841'):
                                starter.conversation_stage(check_only=True)


if __name__ == '__main__':
    unittest.main()
