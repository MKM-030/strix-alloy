"""Offline checks: authentication never infers a ServiceNow instance."""
import unittest
from unittest.mock import patch

from native_bridge import Config
from sdk_deployment import SDKDeploymentPolicy


class InstanceConfigurationTests(unittest.TestCase):
    def test_servicenow_auth_requires_explicit_canonical_instance_before_network(self):
        for value in ('', None, 17, 'https://example.service-now.com',
                      'example.service-now.com', 'UPPERCASE', 'demo/escape',
                      '-demo', 'demo-', 'a' * 64, 'demo\n', 'démo'):
            with self.subTest(instance=value):
                with patch('native_bridge.ClientSession', side_effect=AssertionError('network is forbidden')):
                    with self.assertRaises(ValueError):
                        Config(auth_mode='servicenow', instance_name=value,
                               native_sdk_enabled=False)

    def test_explicit_instances_derive_independent_urls_without_source_fallback(self):
        first = Config(auth_mode='servicenow', instance_name='community-demo')
        second = Config(auth_mode='servicenow', instance_name='different-42')
        self.assertEqual(first.instance_url, 'https://community-demo.service-now.com')
        self.assertEqual(second.instance_url, 'https://different-42.service-now.com')
        self.assertEqual(first.instance_name, 'community-demo')
        self.assertEqual(second.instance_name, 'different-42')
        self.assertIsNone(first.sdk_policy)
        self.assertIsNone(second.sdk_policy)

    def test_canonical_instance_label_boundaries_match_sdk_policy(self):
        for value in ('a', '0', 'demo-42', 'a' * 63):
            with self.subTest(instance=value):
                config = Config(auth_mode='servicenow', instance_name=value)
                policy = SDKDeploymentPolicy(value, '1' * 32, '2' * 32,
                                             'https://voice.community.example')
                self.assertEqual(config.instance_url, policy.instance_url)

    def test_offline_empty_config_has_no_implicit_instance_or_network_target(self):
        with patch('native_bridge.ClientSession', side_effect=AssertionError('network is forbidden')):
            config = Config()
        self.assertEqual(config.auth_mode, 'deny')
        self.assertEqual(config.instance_name, '')
        self.assertEqual(config.instance_url, '')
        self.assertIsNone(config.sdk_policy)

    def test_sdk_still_requires_and_binds_its_complete_startup_policy(self):
        values = dict(auth_mode='servicenow', native_sdk_enabled=True,
                      instance_name='community-demo', voice_service_id='1' * 32,
                      required_agent_id='2' * 32, sdk_public_origin='https://voice.community.example')
        config = Config(**values)
        self.assertIsInstance(config.sdk_policy, SDKDeploymentPolicy)
        self.assertEqual(config.sdk_policy.instance_url, config.instance_url)
        for field, value in (('instance_name', ''), ('voice_service_id', ''),
                             ('required_agent_id', ''), ('sdk_public_origin', ''),
                             ('auth_mode', 'deny')):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    Config(**dict(values, **{field: value}))


if __name__ == '__main__':
    unittest.main()
