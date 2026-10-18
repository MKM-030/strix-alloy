import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from voice.bridge import Bridge, Settings, load_config


class PortableBotSettingsTests(unittest.TestCase):
    def settings(self, origin='https://instance.example.test'):
        settings = Settings(user_id='fixture-identity')
        # Dynamic assignment deliberately lets these tests expose current source
        # routing before the new Settings field exists.
        settings.instance_url = origin
        return settings

    def bridge(self, origin='https://instance.example.test', enabled=True):
        settings = self.settings(origin)
        settings.service_now_enabled = enabled
        return Bridge(settings, 'sn-test-token', 'audio-test-token', 'callback-test-token')

    def fixture(self, folder, settings=None):
        for name in ('sn', 'audio', 'callback'):
            (folder / (name+'.txt')).write_text(name+'-test-token-at-least-sixteen', encoding='utf8')
        config = {'settings': {'user_id': 'fixture-identity'},
                  'servicenow_token_file': str(folder/'sn.txt'),
                  'audio_token_file': str(folder/'audio.txt'),
                  'callback_token_file': str(folder/'callback.txt')}
        config['settings'].update(settings or {})
        config_path = folder/'bridge.json'
        config_path.write_text(json.dumps(config), encoding='utf8')
        return config_path

    def test_configured_origin_is_the_actual_bot_destination(self):
        self.assertEqual(self.bridge().bot_url,
            'https://instance.example.test/api/sn_va_as_service/bot/integration')

    def test_canonical_origin_normalizes_host_case_and_root_slash(self):
        self.assertEqual(self.bridge('https://Instance.Example.Test:8443/').bot_url,
            'https://instance.example.test:8443/api/sn_va_as_service/bot/integration')

    def test_missing_origin_fails_closed_when_servicenow_enabled(self):
        with self.assertRaises(ValueError):
            Bridge(Settings(user_id='fixture-identity'), 'sn', 'audio', 'callback')

    def test_invalid_origins_are_rejected_without_disclosing_input(self):
        invalid = [None, True, 12, '', 'http://instance.example.test', '//instance.example.test',
            'https://user:private-pass@instance.example.test',
            'https://instance.example.test@attacker.example',
            'https://instance.example.test/api', 'https://instance.example.test//',
            'https://instance.example.test/?token=private-pass',
            'https://instance.example.test#private-pass',
            'https://instance.example.test\\@attacker.example',
            ' https://instance.example.test', 'https://instance.example.test ',
            'https://instance.example.test\r\nInjected: private-pass',
            'https://instance.example.test\t', 'https://instance.example.test:0',
            'https://instance.example.test:65536', 'https://instance.example.test:0443',
            'https://instance..example.test', 'https://-instance.example.test',
            'https://instance.example.test.', 'https://999.999.999.999',
            'https://0x7f000001', 'https://127.000.0.1', 'https://127.0.0x1',
            'https://0x7f.0.0.1', 'https://instance.example.test/%2f',
            'https://instance.example.test/'+'x'*2048]
        for origin in invalid:
            with self.subTest(origin=repr(origin)[:100]):
                with self.assertRaises(ValueError) as caught:
                    self.bridge(origin)
                self.assertNotIn('private-pass', str(caught.exception))

    def test_audio_only_configuration_needs_no_servicenow_origin(self):
        settings = Settings(service_now_enabled=False)
        bridge = Bridge(settings, '', 'audio-test-token', '')
        self.assertEqual(bridge.bot_url, '')

    def test_instance_url_is_accepted_as_a_settings_config_field(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            folder = Path(root)
            config_path = self.fixture(folder, {'instance_url':'https://target.example.test/'})
            try:
                bridge = load_config(config_path)
            except TypeError:
                self.fail('Settings does not yet accept instance_url in configuration')
            self.assertEqual(bridge.bot_url,
                'https://target.example.test/api/sn_va_as_service/bot/integration')

    def test_environment_override_is_the_actual_bot_destination(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ,
                {'SCC_VOICE_INSTANCE_URL':'https://environment.example.test'}, clear=True):
            config_path = self.fixture(Path(root))
            bridge = load_config(config_path)
            self.assertEqual(bridge.bot_url,
                'https://environment.example.test/api/sn_va_as_service/bot/integration')

    def test_explicit_empty_environment_override_does_not_fall_back_to_config(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ,
                {'SCC_VOICE_INSTANCE_URL':''}, clear=True):
            config_path = self.fixture(Path(root), {'instance_url':'https://target.example.test'})
            try:
                with self.assertRaises(ValueError):
                    load_config(config_path)
            except TypeError:
                self.fail('Settings does not yet accept instance_url in configuration')

    def test_missing_origin_fails_before_any_credential_file_read(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            config = Path(root)/'bridge.json'
            config.write_text(json.dumps({'settings':{'user_id':'fixture-identity'}}),encoding='utf8')
            try:
                with self.assertRaises(ValueError) as caught:
                    load_config(config)
            except KeyError:
                self.fail('Credential access occurred before instance origin validation')
            self.assertIn('instance_url', str(caught.exception))

    def test_operator_identity_inbound_and_credentials_are_preserved(self):
        settings = self.settings()
        settings.inbound_id = 'target-integration'
        settings.email = 'operator-fixture@example.test'
        bridge = Bridge(settings,'sn-test-token','audio-test-token','callback-test-token')
        self.assertEqual(bridge.settings.user_id,'fixture-identity')
        self.assertEqual(bridge.settings.inbound_id,'target-integration')
        self.assertEqual(bridge.settings.email,'operator-fixture@example.test')
        self.assertEqual(bridge.sn_token,'sn-test-token')
        self.assertEqual(bridge.callback_auth,'Bearer callback-test-token')


if __name__ == '__main__':
    unittest.main()
