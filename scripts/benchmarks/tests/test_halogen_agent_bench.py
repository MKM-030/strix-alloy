"""Offline three-turn fixtures. No network, engine, or real tokenizer is used."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

BENCHMARKS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCHMARKS))


class CharacterTokenizer:
    def encode(self, value, add_special_tokens=False):
        return type('Encoding', (), {'ids': list(value.encode('utf-8'))})()


class FakeClient:
    def __init__(self):
        self.profile = {'backend': {'context': 32768}, 'engine': {'kind': 'halogen'}}
        self.calls = []
        self.last_request = self.last_response = None

    def call(self, messages, max_tokens, mode, label, **kwargs):
        self.calls.append(copy.deepcopy(messages))
        turn = (len(self.calls) - 1) % 3 + 1
        self.last_request = {'messages': copy.deepcopy(messages), 'max_tokens': max_tokens}
        self.last_response = {'choices': [{'message': {'role': 'assistant',
            'content': f'answer-{turn}', 'reasoning_content': f'private-{turn}'},
            'finish_reason': 'length' if turn == 1 else 'stop'}]}
        return {'name': label, 'mode': mode, 'text': f'private-{turn}answer-{turn}',
            'sha256': hashlib.sha256(f'private-{turn}answer-{turn}'.encode()).hexdigest(),
            'usage': {'prompt_tokens': 9000 + turn, 'completion_tokens': 10},
            'timings': {'cache_n': 0 if len(self.calls) == 1 else 8192,
                        'draft_n': 8, 'draft_n_accepted': 6},
            'wall_seconds': .1, 'minimum_memory': {'available_bytes': 20 * 1024**3,
                'commit_headroom_bytes': 21 * 1024**3}, 'finish_reason': 'length' if turn == 1 else 'stop',
            'drafted': 8, 'accepted': 6, 'draft_acceptance': .75}


class AgentBenchTests(unittest.TestCase):
    def load(self):
        path = BENCHMARKS / 'halogen_agent_bench.py'
        self.assertTrue(path.is_file(), 'The agent benchmark harness has not been implemented')
        spec = importlib.util.spec_from_file_location('halogen_agent_bench', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def workload(self, m, root):
        (root / 'server').mkdir()
        (root / 'server/controller.py').write_bytes(b'def controller():\r\n    return 1\r\n')
        (root / 'server/gateway.py').write_bytes(b'def gateway():\n    return 2\n')
        return m.build_workload(root, CharacterTokenizer(), 'a' * 64)

    def test_workload_is_deterministic_token_bounded_and_snapshots_raw_bytes(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.workload(m, root)
            second = m.build_workload(root, CharacterTokenizer(), 'a' * 64)
            self.assertEqual(first, second)
            self.assertGreaterEqual(first['manifest']['system_text_tokens'], 8192)
            self.assertEqual(len(first['turns']), 3)
            self.assertIn('read_file', first['turns'][1])
            self.assertIn('synthetic', first['turns'][1])
            source = first['manifest']['source_snapshots'][0]
            self.assertEqual(first['assets'][source['file']], (root / source['source']).read_bytes())
            self.assertEqual(source['sha256'], hashlib.sha256(first['assets'][source['file']]).hexdigest())

    def test_workload_reload_checks_immutable_files_and_tokenizer_pin(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workload = self.workload(m, root)
            m.save_workload(root / 'workload', workload)
            self.assertEqual(m.load_workload(root / 'workload', CharacterTokenizer(), 'a' * 64), workload)
            with self.assertRaisesRegex(ValueError, 'tokenizer'):
                m.load_workload(root / 'workload', CharacterTokenizer(), 'b' * 64)
            (root / 'workload/turn2.txt').write_text('changed', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'hash|bytes'):
                m.load_workload(root / 'workload', CharacterTokenizer(), 'a' * 64)

    def test_three_turn_prefix_preserves_every_actual_assistant_message_and_length(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workload = self.workload(m, root)
            output = root / 'out'
            output.mkdir()
            client = FakeClient()
            rows, summary = m.run_conversations(client, workload, output,
                CharacterTokenizer(), mode='speculative', reps=3, max_tokens=128)
            self.assertEqual(len(client.calls), 9)
            self.assertEqual(len(rows), 9)
            self.assertEqual(client.calls[1][:2], client.calls[0])
            self.assertEqual(client.calls[1][2], {'role': 'assistant', 'content': 'answer-1',
                                              'reasoning_content': 'private-1'})
            self.assertEqual(client.calls[2][:4], client.calls[1])
            self.assertEqual(client.calls[0], client.calls[3])
            self.assertTrue(summary['passed_execution'])
            self.assertFalse(rows[0]['output_complete'])
            self.assertEqual(summary['length_limited_calls'], 3)
            self.assertEqual(summary['cache_observations'], {'hit': 8, 'miss': 1, 'unknown': 0})
            self.assertEqual(summary['minimum_memory']['available_bytes'], 20 * 1024**3)
            self.assertEqual(len((output / 'samples.jsonl').read_text().splitlines()), 9)
            recorded = json.loads((output / rows[0]['response_file']).read_text())
            self.assertEqual(recorded['choices'][0]['message']['content'], 'answer-1')

    def test_comparison_reports_input_and_raw_message_drift_by_turn(self):
        m = self.load()
        identity = {'backend': 'halogen-v2', 'context_capacity': 32768,
            'harness_sha256': 'h', 'workload_sha256': 'w', 'tokenizer_sha256': 't',
            'reps': 1, 'max_tokens': 128}
        rows = [{'rep': 0, 'turn': n, 'messages_sha256': 'p',
            'assistant_message_sha256': 'a', 'prompt_tokens': 9000, 'output_tokens': 10,
            'finish_reason': 'stop'} for n in (1, 2, 3)]
        current = copy.deepcopy(rows)
        current[0]['assistant_message_sha256'] = 'changed'
        current[1]['messages_sha256'] = 'prefix-drift'
        result = m.compare_recordings(identity, rows, identity, current)
        self.assertFalse(result['passed'])
        self.assertEqual(result['output_drift'], ['rep0/turn1'])
        self.assertEqual(result['input_drift'], ['rep0/turn2'])
        with self.assertRaisesRegex(ValueError, 'workload|identity'):
            m.compare_recordings(identity, rows, {**identity, 'workload_sha256': 'x'}, current)
        with self.assertRaisesRegex(ValueError, 'three|complete'):
            m.compare_recordings(identity, rows, identity, current[:2])

    def test_tokenizer_hash_pin_is_verified_before_loading(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tokenizer.json'
            path.write_bytes(b'{"fixture":true}')
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            loaded = []
            tokenizer, receipt = m.load_tokenizer(path, expected,
                loader=lambda raw: loaded.append(raw) or CharacterTokenizer())
            self.assertIsInstance(tokenizer, CharacterTokenizer)
            self.assertEqual(receipt['sha256'], expected)
            self.assertEqual(loaded, [path.read_bytes()])
            with self.assertRaisesRegex(ValueError, 'tokenizer'):
                m.load_tokenizer(path, '0' * 64, loader=lambda raw: self.fail('Wrong pin loaded'))

    def test_failed_call_retains_actual_request_and_response(self):
        m = self.load()
        class FailingClient(FakeClient):
            def call(self, *args, **kwargs):
                super().call(*args, **kwargs)
                raise ValueError('Synthetic memory accounting failure')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workload = self.workload(m, root)
            output = root / 'out'
            output.mkdir()
            rows, summary = m.run_conversations(FailingClient(), workload, output,
                CharacterTokenizer(), mode='serial', reps=3, max_tokens=128)
            self.assertFalse(summary['passed_execution'])
            self.assertEqual(len(rows), 1)
            self.assertTrue((output / rows[0]['request_file']).exists())
            self.assertTrue((output / rows[0]['response_file']).exists())
            self.assertIn('accounting failure', summary['error'])

    def test_grading_rejects_length_and_safely_checks_requested_port_behavior(self):
        m = self.load()
        self.assertTrue(callable(getattr(m, 'grade_output', None)), 'Per-turn grader is missing')
        original = ('def parse_port(value):\n'
                    '    if type(value) is not int or not 1 <= value <= 65535:\n'
                    '        raise ValueError()\n    return value\n')
        self.assertTrue(m.grade_output(1, original, 'stop')['passed'])
        self.assertFalse(m.grade_output(1, original, 'length')['passed'])
        self.assertFalse(m.grade_output(1, 'def parse_port(value):\n    return int(value)', 'stop')['passed'])
        self.assertFalse(m.grade_output(1, "import os\nos.remove('file')", 'stop')['passed'])
        updated = ('def parse_port(value):\n'
                   '    if type(value) is str:\n        value = value.strip()\n'
                   '        if not value.isascii() or not value.isdecimal():\n'
                   '            raise ValueError()\n        value = int(value)\n'
                   '    if type(value) is not int or not 1 <= value <= 65535:\n'
                   '        raise ValueError()\n    return value\n')
        self.assertTrue(m.grade_output(3, updated, 'stop')['passed'])
        tests = ('def test_bool():\n    with pytest.raises(ValueError):\n        parse_port(True)\n\n'
                 'def test_range():\n    with pytest.raises(ValueError):\n        parse_port(65536)\n')
        self.assertTrue(m.grade_output(2, tests, 'stop')['passed'])

    def test_missing_cache_and_draft_counters_are_unknown(self):
        m = self.load()
        self.assertEqual(m.cache_observation({}, {}), (None, 'unknown'))
        self.assertTrue(callable(getattr(m, 'draft_metrics', None)), 'Counter normalization is missing')
        self.assertEqual(m.draft_metrics({}, {}),
                         {'drafted': None, 'accepted': None, 'draft_acceptance': None})
        self.assertEqual(m.draft_metrics({}, {'draft_n': 8, 'draft_n_accepted': 6})['draft_acceptance'], .75)

    def test_cache_identity_uses_the_actual_engine_profile(self):
        m = self.load()
        self.assertTrue(callable(getattr(m, 'profile_cache', None)), 'Engine cache identity is missing')
        for mode in ('Off', 'Exact', 'Flexible'):
            profile = {'prompt_cache': 'Off', 'engine': {'prompt_cache': mode}}
            self.assertEqual(m.profile_cache(profile), mode)
        self.assertEqual(m.profile_cache({'engine': {}}), 'Off')

    def test_turn_two_grading_rejects_unreachable_or_replaced_assertions(self):
        m = self.load()
        normal = ('def test_bool():\n    with pytest.raises(ValueError):\n        parse_port(True)\n\n'
                  'def test_range():\n    with pytest.raises(ValueError):\n        parse_port(65536)\n')
        self.assertTrue(m.grade_output(2, normal, 'stop')['passed'])
        early_return = normal.replace('    with pytest.raises', '    return\n    with pytest.raises')
        self.assertFalse(m.grade_output(2, early_return, 'stop')['passed'])
        conditional = normal.replace('    with pytest.raises(ValueError):\n        parse_port',
                                     '    if False:\n        with pytest.raises(ValueError):\n            parse_port')
        self.assertFalse(m.grade_output(2, conditional, 'stop')['passed'])
        duplicate_name = normal.replace('def test_range():', 'def test_bool():')
        self.assertFalse(m.grade_output(2, duplicate_name, 'stop')['passed'])
        raised_before_call = normal.replace('        parse_port', '        raise ValueError()\n        parse_port')
        self.assertFalse(m.grade_output(2, raised_before_call, 'stop')['passed'])


if __name__ == '__main__':
    unittest.main()
