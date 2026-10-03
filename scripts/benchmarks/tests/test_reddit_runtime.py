import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from reddit_runtime import ManagedClient, cold_cache_reused
from quality_gate import evaluate_code, judge


class RuntimeTests(unittest.TestCase):
    def test_cold_rejects_native_prefix_and_disk_cache_hits(self):
        self.assertFalse(cold_cache_reused({'cached_tokens': 0,
            'gufo': {'cache_hit': False}}, {'cache_n': 0}))
        self.assertTrue(cold_cache_reused({'cached_tokens': 12}, {}))
        self.assertTrue(cold_cache_reused({'prompt_tokens_details': {'cached_tokens': 12}}, {}))
        self.assertTrue(cold_cache_reused({'gufo': {'cache_disk_hit': True}}, {}))
        self.assertTrue(cold_cache_reused({}, {'cache_n': 12}))

    def test_managed_call_keeps_identity_and_cold_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            token = root / 'token.txt'
            token.write_text('x' * 40)
            profile = {'backend': {'identifier': 'halogen-v2', 'model': 'halogen-test',
                                   'context': 262144},
                       'engine': {'kind': 'halogen'}, 'minimum_reserve_gib': 18,
                       'token_file': str(token)}
            config = root / 'config.json'
            config.write_text(json.dumps(profile))
            state_file = root / 'current.json'
            state = {'run_id': 'run', 'phase': 'ready', 'backend': 'halogen-v2',
                     'context': 262144, 'port': 8840, 'minimum_reserve_gib': 18,
                     'profile_sha256': hashlib.sha256(config.read_bytes()).hexdigest()}
            state_file.write_text(json.dumps(state))
            memory = {'available_bytes': 30 * 1024**3,
                      'commit_headroom_bytes': 30 * 1024**3}
            with patch.object(ManagedClient, 'health', return_value={'backend': 'halogen-v2'}), \
                 patch('reddit_runtime.frame', return_value=memory):
                client = ManagedClient(config, 'run', state_path=state_file)
                captured = []

                def fake_request(path, body=None, timeout=1800):
                    captured.append(body)
                    return {'choices': [{'message': {'content': 'OK'}, 'finish_reason': 'length'}],
                            'usage': {'prompt_tokens': 16, 'completion_tokens': 2},
                            'timings': {'cache_n': 0, 'prompt_ms': 1.0}}

                with patch.object(client, 'request', side_effect=fake_request):
                    row = client.call([{'role': 'user', 'content': 'Reply OK'}],
                                      2, 'serial', 'test', cold=True)
                    structured = client.call([{'role': 'user', 'content': 'Return JSON'}],
                        2, 'serial', 'json', response_format={'type': 'json_object'})
                self.assertEqual(row['usage']['completion_tokens'], 2)
                self.assertTrue(captured[0]['cache_prompt'] is False)
                self.assertEqual(captured[0]['drafter'], 'serial')
                self.assertNotIn('response_format', captured[0])
                self.assertEqual(captured[1]['response_format'], {'type': 'json_object'})
                self.assertEqual(structured['response_format'], {'type': 'json_object'})
                self.assertNotIn('x' * 40, json.dumps(row))
                state['profile_sha256'] = 'wrong'
                state_file.write_text(json.dumps(state))
                with self.assertRaises(ValueError):
                    client.assert_identity()

    def test_quality_judges_and_executable_checks(self):
        self.assertTrue(judge('json_schema', '{"alpha":7,"beta":"ok","items":[2,4]}'))
        self.assertFalse(judge('tool_json', '{"tool":"lookup","arguments":{"id":43}}'))
        self.assertEqual(evaluate_code('def add_even(values):\n    return sum(x for x in values if x % 2 == 0)')[0], True)
        self.assertEqual(evaluate_code('import os\ndef add_even(values): return 0')[0], False)

    def test_isinstance_integer_filter_is_executed_and_stays_bounded(self):
        valid = 'def add_even(values):\n    return sum(v for v in values if isinstance(v, int) and v % 2 == 0)'
        self.assertEqual(evaluate_code(valid), (True, 'unit_tests_exit_0'))
        wrong = 'def add_even(values):\n    return sum(v for v in values if isinstance(v, int))'
        self.assertEqual(evaluate_code(wrong), (False, 'unit_tests_exit_1'))
        for source in (valid.replace('isinstance(v, int)', 'isinstance(v, float)'),
                       valid.replace('isinstance(v, int)', 'isinstance(v, int, int)'),
                       valid.replace('isinstance(v, int)', 'eval(v)')):
            with self.subTest(source=source):
                self.assertEqual(evaluate_code(source), (False, 'syntax_or_unsafe_ast'))


class RuntimeStateSharingTests(unittest.TestCase):
    def client(self):
        # Exercise the actual identity validator without initialization or HTTP.
        client = ManagedClient.__new__(ManagedClient)
        client.state_path = pathlib.Path('offline-current.json')
        client.expected_run_id = 'owned-run'
        client.profile_sha256 = 'profile-sha'
        client.profile = {'backend': {'identifier': 'halogen-v2', 'context': 262144},
                          'minimum_reserve_gib': 18}
        return client

    def ready(self):
        return {'phase': 'ready', 'run_id': 'owned-run', 'backend': 'halogen-v2',
                'context': 262144, 'profile_sha256': 'profile-sha',
                'minimum_reserve_gib': 18}

    def test_transient_sharing_retries_before_validating_managed_identity(self):
        client, state = self.client(), self.ready()
        failures = [PermissionError('sharing'), PermissionError('sharing'), json.dumps(state)]
        with patch.object(pathlib.Path, 'read_text', side_effect=failures) as raw, \
             patch('controller.time.monotonic', return_value=0), \
             patch('controller.time.sleep') as pause:
            self.assertEqual(client.assert_identity(), state)
        self.assertEqual(raw.call_count, 3)
        self.assertTrue(all(call.kwargs == {'encoding': 'utf-8-sig'} for call in raw.call_args_list))
        self.assertEqual([call.args for call in pause.call_args_list], [(.025,), (.025,)])

    def test_changed_identity_after_sharing_retry_remains_rejected(self):
        for change in ({'run_id': 'replacement'}, {'profile_sha256': 'replacement'},
                       {'phase': 'stopped'}, {'phase': 'failed'}, {'minimum_reserve_gib': 17}):
            with self.subTest(change=change):
                state = dict(self.ready(), **change)
                with patch.object(pathlib.Path, 'read_text',
                                  side_effect=[PermissionError('sharing'), json.dumps(state)]) as raw, \
                     patch('controller.time.monotonic', return_value=0), \
                     patch('controller.time.sleep') as pause:
                    with self.assertRaises(ValueError):
                        self.client().assert_identity()
                self.assertEqual(raw.call_count, 2)
                pause.assert_called_once_with(.025)

    def test_persistent_sharing_remains_bounded_and_propagates_permission_error(self):
        now = [0.0]
        failure = PermissionError('persistent sharing')

        def pause(seconds):
            now[0] += seconds

        with patch.object(pathlib.Path, 'read_text', side_effect=failure) as raw, \
             patch('controller.time.monotonic', side_effect=lambda: now[0]), \
             patch('controller.time.sleep', side_effect=pause):
            with self.assertRaises(PermissionError) as caught:
                self.client().assert_identity()
        self.assertIs(caught.exception, failure)
        self.assertGreaterEqual(now[0], 1.0)
        self.assertLessEqual(now[0], 1.025)
        self.assertLessEqual(raw.call_count, 42)

    def test_missing_or_malformed_state_does_not_retry_or_gain_identity(self):
        for value, error in ((FileNotFoundError('missing'), FileNotFoundError),
                             ('not JSON', json.JSONDecodeError),
                             (OSError('other I/O'), OSError)):
            with self.subTest(value=value):
                with patch.object(pathlib.Path, 'read_text', side_effect=[value]) as raw, \
                     patch('controller.time.monotonic', return_value=0), \
                     patch('controller.time.sleep') as pause:
                    with self.assertRaises(error):
                        self.client().assert_identity()
                raw.assert_called_once_with(encoding='utf-8-sig')
                pause.assert_not_called()


if __name__ == '__main__':
    unittest.main()
