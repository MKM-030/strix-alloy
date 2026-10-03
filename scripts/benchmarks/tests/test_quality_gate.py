import contextlib
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import quality_gate


class QualityGateTests(unittest.TestCase):
    def test_fenced_json_has_functional_grade_and_retains_strict_failure(self):
        value = '```json\n{"tool":"lookup","arguments":{"id":42}}\n```'
        grade = quality_gate.grade('tool_json', value)
        self.assertTrue(grade['functional_passed'])
        self.assertFalse(grade['format_passed'])
        self.assertFalse(grade['passed'])
        self.assertFalse(quality_gate.judge('tool_json', value))
        for invalid in ('Explanation\n' + value, value + '\nExplanation',
                        value + '\n' + value, '```json\n{"tool":"other"}\n```'):
            with self.subTest(invalid=invalid):
                self.assertFalse(quality_gate.grade('tool_json', invalid)['functional_passed'])
        wrong = quality_gate.grade('tool_json', '{"tool":"lookup","arguments":{"id":43}}')
        self.assertTrue(wrong['format_passed'])
        self.assertFalse(wrong['functional_passed'])

    def test_structured_policy_and_all_call_memory_are_recorded(self):
        outputs = {'logprob_probe': 'OK', 'arithmetic': '5017',
            'german': 'Berlin ist die Hauptstadt Deutschlands.', 'cyrillic': 'Москва',
            'json_schema': '{"alpha":7,"beta":"ok","items":[2,4]}',
            'tool_json': '{"tool":"lookup","arguments":{"id":42}}',
            'code': 'def add_even(values):\n    return sum(v for v in values if isinstance(v, int) and v % 2 == 0)',
            'long_needle_8192': 'NEEDLE-7319', 'long_needle_16384': 'NEEDLE-7319',
            'multi_turn_ack': 'ACK', 'multi_turn': 'COBALT-731', 'repeat_state': 'STATE-OK'}
        valid_top = [{'token': 'A', 'logprob': -0.1,
                      'top_logprobs': [{'token': 'A', 'logprob': -0.1}]}]
        digests = []
        for structured in (False, True):
            for low_event in ('logprob_probe', 'arithmetic_first_token', 'multi_turn_ack',
                              'distractor0', 'repeat_state'):
                with self.subTest(structured=structured, low_event=low_event), \
                     tempfile.TemporaryDirectory() as directory:
                    root = pathlib.Path(directory)
                    out = root / 'server/.local/quality'

                    class RecordedClient:
                        profile = {'backend': {'context': 32768}, 'engine': {'kind': 'halogen'}}
                        profile_sha256 = 'profile-hash'
                        model = 'halogen-v2'
                        repeated = 0

                        def call(self, messages, limit, mode, label, *, top_logprobs=False,
                                 response_format=None):
                            if top_logprobs and response_format is not None:
                                raise urllib.error.HTTPError('fixture', 400,
                                    'logprobs with response_format is not supported', {}, None)
                            text = outputs.get(label, label.upper())
                            if label == 'tool_json' and response_format is None:
                                text = '```json\n' + text + '\n```'
                            low = label == low_event
                            if label == 'repeat_state':
                                self.repeated += 1
                                low = low and self.repeated == 1
                            memory = (19 if low else 30) * 1024**3
                            return {'name': label, 'mode': mode, 'text': text,
                                'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                                'top_logprobs': valid_top if top_logprobs else None,
                                'response_format': response_format,
                                'minimum_memory': {'available_bytes': memory,
                                                   'commit_headroom_bytes': memory}}

                    argv = ['quality_gate.py', '--profile', 'fixture.json', '--run-id', 'run',
                            '--out', str(out), '--mode', 'serial']
                    if structured:
                        argv.append('--structured-json')
                    with patch.object(quality_gate, 'ROOT', root), \
                         patch.object(quality_gate, 'ManagedClient', return_value=RecordedClient()), \
                         patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
                        result = quality_gate.main()
                    summary = json.loads((out / 'quality.json').read_text(encoding='utf-8'))
                    self.assertEqual(result, 0 if structured else 2, summary.get('error'))
                    self.assertTrue(summary['functional_passed'])
                    self.assertEqual(summary['passed'], structured)
                    self.assertEqual(summary['structured_json'], structured)
                    self.assertIsNone(summary['parity_passed'])
                    self.assertEqual(summary['minimum_memory']['available_bytes'], 19 * 1024**3)
                    self.assertEqual(len(summary['observations']), 27 if structured else 29)
                    tool = next(row for row in summary['rows'] if row['name'] == 'tool_json')
                    self.assertEqual(tool['sha256'], hashlib.sha256(tool['text'].encode()).hexdigest())
                    self.assertEqual(tool['format_passed'], structured)
                    if structured:
                        self.assertEqual(tool['logprob_evidence'], 'unavailable_due_to_grammar_mask')
                        self.assertIsNone(tool['top_logprobs'])
                        self.assertNotIn('first_token_probe', tool)
                    if low_event == 'logprob_probe':
                        digests.append(summary['suite_sha256'])
                    if structured and low_event == 'logprob_probe':
                        control = root / 'control.json'
                        control.write_text(json.dumps(dict(summary, structured_json=False)), encoding='utf-8')
                        mismatch_out = root / 'server/.local/policy-mismatch'
                        mismatch_argv = list(argv) + ['--control', str(control)]
                        mismatch_argv[mismatch_argv.index('--out') + 1] = str(mismatch_out)
                        with patch.object(quality_gate, 'ROOT', root), \
                             patch.object(quality_gate, 'ManagedClient', return_value=RecordedClient()), \
                             patch.object(sys, 'argv', mismatch_argv), contextlib.redirect_stdout(io.StringIO()):
                            mismatch_result = quality_gate.main()
                        mismatch = json.loads((mismatch_out / 'quality.json').read_text(encoding='utf-8'))
                        self.assertEqual(mismatch_result, 2)
                        self.assertFalse(mismatch['passed'])
                        self.assertFalse(mismatch['parity_passed'])
                        self.assertIn('policy differs', mismatch['error'])
        self.assertNotEqual(digests[0], digests[1])

    def test_probe_reaches_functional_cases_with_and_without_logprobs(self):
        outputs = {
            'logprob_probe': 'OK', 'arithmetic': '5017',
            'german': 'Berlin ist die Hauptstadt Deutschlands.',
            'cyrillic': 'Москва',
            'json_schema': '{"alpha":7,"beta":"ok","items":[2,4]}',
            'tool_json': '{"tool":"lookup","arguments":{"id":42}}',
            'code': 'def add_even(values):\n    return sum(x for x in values if x % 2 == 0)',
            'long_needle_8192': 'NEEDLE-7319', 'long_needle_16384': 'NEEDLE-7319',
            'multi_turn_ack': 'ACK', 'multi_turn': 'COBALT-731', 'repeat_state': 'STATE-OK',
        }
        valid_top = [{'token': 'A', 'logprob': -0.1,
                      'top_logprobs': [{'token': 'A', 'logprob': -0.1}]}]
        for exposed in (None, valid_top):
            with self.subTest(logprobs=bool(exposed)), tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory)
                out = root / 'server/.local/quality'

                class RecordedClient:
                    profile = {'backend': {'context': 32768}, 'engine': {'kind': 'halogen'}}
                    profile_sha256 = 'profile-hash'
                    model = 'halogen-v2'

                    def call(self, messages, limit, mode, label, *, top_logprobs=False):
                        if top_logprobs and limit != 1:
                            raise ValueError('Greedy top-N is exposed only for one generated token')
                        text = outputs.get(label, label.upper())
                        return {'name': label, 'mode': mode, 'text': text,
                                'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                                'top_logprobs': exposed if top_logprobs else None,
                                'minimum_memory': {'available_bytes': 30 * 1024**3,
                                                   'commit_headroom_bytes': 30 * 1024**3}}

                argv = ['quality_gate.py', '--profile', 'fixture.json', '--run-id', 'run',
                        '--out', str(out), '--mode', 'serial']
                with patch.object(quality_gate, 'ROOT', root), \
                     patch.object(quality_gate, 'ManagedClient', return_value=RecordedClient()), \
                     patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
                    result = quality_gate.main()
                summary = json.loads((out / 'quality.json').read_text(encoding='utf-8'))
                self.assertEqual(result, 0, summary.get('error'))
                self.assertTrue(summary['passed'])
                self.assertEqual(summary['total'], 10)
                self.assertEqual(summary['logprob_capability']['supported'], bool(exposed))
                repeated = next(row for row in summary['rows'] if row['name'] == 'repeat_state')
                self.assertEqual(len(repeated['sample_hashes']), 5)


if __name__ == '__main__':
    unittest.main()
