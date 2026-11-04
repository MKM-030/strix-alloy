"""Startup restores explicit own-voice UUIDs with process-bound receipts only."""
from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_start_services import startup

VOICE_ID = '81959ffa-c2ef-4db5-bf95-5df2a24c9404'


class VoiceRegistrationStartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipt = self.root / 'registered-voice.json'
        self.alias = dict(profile_id='active-alias-profile', reference_sha256='a' * 64, name='Active voice')
        self.bound = dict(voice_id=VOICE_ID, profile=dict(profile_id='fixed-uuid-profile',
                          reference_sha256='b' * 64, name='Fixed voice'))
        self.owner = dict(pid=111, created=1234.5)
        self.speech = SimpleNamespace(SERVICES=dict(tts={}), start=Mock(),
                                      owners=Mock(side_effect=lambda: dict(tts=dict(self.owner))))
        def register(profile, *, voice_id='scc-demo'):
            self.assertFalse(self.receipt.exists(), 'A possibly committing POST retained an old receipt')
        self.manager = SimpleNamespace(PROFILE_ROOT=self.root, VOICE_ALIAS='scc-demo',
            activation_lock=Mock(side_effect=lambda root: nullcontext()),
            selected_profile=Mock(side_effect=lambda: dict(self.alias)),
            native_registrations=Mock(side_effect=lambda: [self.bound]),
            native_register=Mock(side_effect=register),
            read_json=lambda path: json.loads(path.read_text()),
            atomic_json=lambda path, value: path.write_text(json.dumps(value), encoding='utf-8'))
        self.patches = [patch.object(startup, 'RUNTIME', self.root),
            patch.object(startup, 'module', side_effect=lambda name, path:
                         self.speech if name == 'scc_speech_start' else self.manager)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_restart_restores_alias_and_explicit_profile_independently(self):
        startup.speech_start(['tts'])
        calls = self.manager.native_register.call_args_list
        self.assertEqual([(c.args[0]['profile_id'], c.kwargs.get('voice_id')) for c in calls],
                         [('active-alias-profile', 'scc-demo'), ('fixed-uuid-profile', VOICE_ID)])
        stamp = json.loads(self.receipt.read_text())
        self.assertEqual((stamp['pid'], stamp['created']), (111, 1234.5))
        self.assertEqual([item['voice_id'] for item in stamp['registrations']], ['scc-demo', VOICE_ID])

    def test_cache_requires_exact_process_identity_and_complete_binding_plan(self):
        startup.speech_start(['tts'])
        self.assertEqual(self.manager.native_register.call_count, 2)
        startup.speech_start(['tts'])
        self.assertEqual(self.manager.native_register.call_count, 2)
        self.owner['created'] += 1
        startup.speech_start(['tts'])
        self.assertEqual(self.manager.native_register.call_count, 4)
        self.alias['reference_sha256'] = 'c' * 64
        startup.speech_start(['tts'])
        self.assertEqual(self.manager.native_register.call_count, 6)
        self.bound['profile']['reference_sha256'] = 'd' * 64
        startup.speech_start(['tts'])
        self.assertEqual(self.manager.native_register.call_count, 8)

    def test_complete_manifest_is_validated_before_first_post(self):
        self.manager.native_registrations.side_effect = ValueError('malformed manifest hash')
        with self.assertRaisesRegex(ValueError, 'manifest'):
            startup.speech_start(['tts'])
        self.manager.native_register.assert_not_called()
        self.assertFalse(self.receipt.exists())

    def test_ambiguous_registration_does_not_leave_cache_receipt(self):
        self.receipt.write_text('{"old":"receipt"}')
        self.manager.native_register.side_effect = TimeoutError('response lost')
        with self.assertRaises(TimeoutError):
            startup.speech_start(['tts'])
        self.assertFalse(self.receipt.exists())

    def test_changed_tts_owner_after_post_cannot_produce_reusable_receipt(self):
        self.speech.owners.side_effect = [dict(tts=dict(self.owner)),
            dict(tts=dict(self.owner, created=self.owner['created'] + 1))]
        with self.assertRaisesRegex(RuntimeError, 'identity changed'):
            startup.speech_start(['tts'])
        self.assertFalse(self.receipt.exists())


if __name__ == '__main__':
    unittest.main()
