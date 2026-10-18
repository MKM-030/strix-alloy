import copy
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from native_bridge import Config, Dialog


class CapturingDialog(Dialog):
    def __init__(self):
        super().__init__(Config())
        self.http = object()
        self.greeting_history_allowed = True
        self.session_info = {'csrf': 'test-session', 'serviceNowEnabled': True,
                             'started': False, 'initialBotHistoryAllowed': True}
        self.messages = []
        self.fail_message = False
        self.end_acknowledged = True

    async def request(self, method, path, **kwargs):
        if path == '/api/session':
            return self.session_info
        if path == '/api/message':
            self.messages.append(copy.deepcopy(kwargs['json']))
            if self.fail_message:
                raise RuntimeError('request not acknowledged')
            return {'accepted': True}
        if path == '/api/end':
            return {'ended': self.end_acknowledged}
        return {'cursor': self.cursor + 1, 'events': [], 'busy': False}


class NativeHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_configured_employee_question_preserves_first_name_as_real_user_text(self):
        config = Config(**json.loads(Path(__file__).with_name('config.example.json').read_text(
            encoding='utf-8-sig')))
        dialog = CapturingDialog()
        await dialog.open()
        dialog.record_greeting(config.greeting)
        await dialog.turn('Philipp Borchert')
        await dialog.turn('Berlin')
        first, following = dialog.messages
        self.assertEqual(first['text'], 'Philipp Borchert')
        self.assertEqual(len(first['history']), 1)
        self.assertTrue(first['history'][0]['isBotMessage'])
        self.assertEqual(first['history'][0]['value'], config.greeting)
        self.assertIn('Smart Country Convention', config.greeting)
        self.assertIn('Mitarbeiter', config.greeting)
        self.assertEqual(following, {'text': 'Berlin'})

    async def test_actual_fallback_is_forwarded_once_with_first_real_user_message(self):
        dialog = CapturingDialog()
        with patch('native_bridge.time.time', return_value=1791878400.125):
            dialog.record_greeting('Guten Tag. Wie kann ich helfen?')
        await dialog.turn('Ich benötige einen Laptop.')
        await dialog.turn('Für Alex Sommer.')
        self.assertEqual(dialog.messages, [
            {'text': 'Ich benötige einen Laptop.', 'history': [{
                'isBotMessage': True, 'value': 'Guten Tag. Wie kann ich helfen?',
                'displayName': 'Bot', 'type': 'text', 'timestamp': '1791878400125'}]},
            {'text': 'Für Alex Sommer.'}])

    async def test_no_greeting_means_no_history_and_late_record_cannot_replay_it(self):
        dialog = CapturingDialog()
        await dialog.turn('Hallo')
        dialog.record_greeting('Darf nicht nachgereicht werden')
        await dialog.turn('Weiter')
        self.assertEqual(dialog.messages, [{'text': 'Hallo'}, {'text': 'Weiter'}])

    async def test_uncertain_first_delivery_never_replays_history(self):
        dialog = CapturingDialog()
        dialog.record_greeting('Hallo')
        dialog.fail_message = True
        with self.assertRaises(RuntimeError):
            await dialog.turn('Erste Anfrage')
        self.assertEqual(len(dialog.messages), 1)
        dialog.fail_message = False
        await dialog.turn('Expliziter zweiter Versuch')
        self.assertEqual(dialog.messages[0]['history'][0]['value'], 'Hallo')
        self.assertNotIn('history', dialog.messages[1])
        await dialog.turn('Nächste Frage')
        self.assertNotIn('history', dialog.messages[-1])

    async def test_clean_owned_end_clears_old_greeting_and_allows_a_fresh_one(self):
        dialog = CapturingDialog()
        dialog.record_greeting('Alte Begrüßung')
        await dialog.reset_owned_session()
        self.assertFalse(dialog.greeting_history_allowed)
        dialog.record_greeting('Ohne erneute Freigabe nicht erlaubt')
        await dialog.turn('Neue Unterhaltung ohne Begrüßung')
        self.assertNotIn('history', dialog.messages[-1])
        await dialog.reset_owned_session()
        await dialog.open()
        dialog.record_greeting('Neue Begrüßung')
        dialog.record_greeting('Doppelte Begrüßung')
        await dialog.turn('Neue Unterhaltung')
        history = dialog.messages[-1]['history']
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['value'], 'Neue Begrüßung')
        self.assertIsNotNone(re.fullmatch(r'\d{13}', history[0]['timestamp']))

    async def test_failed_end_keeps_history_until_owned_end_is_acknowledged(self):
        dialog = CapturingDialog()
        dialog.record_greeting('Hallo')
        dialog.end_acknowledged = False
        with self.assertRaises(RuntimeError):
            await dialog.reset_owned_session()
        await dialog.turn('Noch dieselbe Unterhaltung')
        self.assertEqual(dialog.messages[-1]['history'][0]['value'], 'Hallo')

    async def test_nondeferred_or_missing_capability_sends_no_fallback_history(self):
        for marker in (False, None, 'true'):
            with self.subTest(marker=marker):
                dialog = CapturingDialog()
                if marker is None:
                    del dialog.session_info['initialBotHistoryAllowed']
                else:
                    dialog.session_info['initialBotHistoryAllowed'] = marker
                self.assertEqual(await dialog.open(), [])
                dialog.record_greeting('Tatsächlich ausgegebener Fallback')
                await dialog.turn('Echte Benutzerfrage')
                self.assertEqual(dialog.messages, [{'text': 'Echte Benutzerfrage'}])

    async def test_only_explicit_session_capability_enables_fallback_history(self):
        dialog = CapturingDialog()
        dialog.greeting_history_allowed = False
        dialog.record_greeting('Vor open nicht erlaubt')
        await dialog.open()
        dialog.record_greeting('Freigegebener Fallback')
        await dialog.turn('Echte Benutzerfrage')
        self.assertEqual(dialog.messages[-1]['history'][0]['value'], 'Freigegebener Fallback')


if __name__ == '__main__':
    unittest.main()
