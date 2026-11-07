"""Portable CPU-only replay. No local runtime assets, network or accelerator access."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def load_helper(relative, name):
    spec = importlib.util.spec_from_file_location(name, HERE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixed = load_helper('snapshots/mtp_cost_trace.py', 'portable_cost_trace_v2')
frozen = load_helper('snapshots/v1/mtp_cost_trace.py', 'portable_cost_trace_v1')


class PortableTraceReplayTests(unittest.TestCase):
    def setUp(self):
        self.text = (HERE / 'fixtures/native-trace.txt').read_text(encoding='utf-8')
        self.samples = json.loads((HERE / 'fixtures/api-speculation.json').read_bytes())

    def test_archived_sources_and_fixtures_match_manifest(self):
        manifest = json.loads((HERE / 'source-manifest.json').read_bytes())
        for rows in (manifest['sources'], manifest['fixtures']):
            for name, expected in rows.items():
                with self.subTest(path=name):
                    data = (HERE / name).read_bytes()
                    self.assertEqual(len(data), expected['bytes'])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), expected['sha256'])

    def test_real_four_request_fixture_reproduces_v1_failure(self):
        with self.assertRaisesRegex(ValueError, 'Native request and saved speculation counters differ'):
            frozen.qualify_trace(self.text, self.samples, 'gate')

    def test_corrected_helper_reconciles_all_four_actual_requests(self):
        result = fixed.qualify_trace(self.text, self.samples, 'gate')
        self.assertTrue(result['native_rule_activation_observed'])
        self.assertFalse(result['per_decision_policy_observed'])
        self.assertEqual([row['id'] for row in result['samples']], [4, 5, 6, 7])
        for row in result['samples']:
            self.assertEqual(row['rounds'], 57)
            self.assertEqual(row['legacy_accepted'], 45)
            self.assertEqual(row['head_rounds'], 57)
            self.assertEqual(row['head_drafted'], 109)
            self.assertEqual(row['head_accepted'], 69)

    def test_every_corresponding_API_counter_drift_is_rejected(self):
        for scope in ('head', 'lookup', 'grammar'):
            for key in ('rounds', 'drafted', 'accepted'):
                with self.subTest(scope=scope, key=key):
                    samples = copy.deepcopy(self.samples)
                    samples[0]['speculation'][scope][key] += 1
                    with self.assertRaisesRegex(ValueError, 'counters differ'):
                        fixed.qualify_trace(self.text, samples, 'gate')
        samples = copy.deepcopy(self.samples)
        samples[0]['speculation']['rounds'] += 1
        with self.assertRaisesRegex(ValueError, 'counters differ'):
            fixed.qualify_trace(self.text, samples, 'gate')

    def test_wrong_missing_duplicate_ID_and_wrong_rule_are_rejected(self):
        samples = copy.deepcopy(self.samples)
        samples[0]['native_request_id'] = 3
        with self.assertRaises(ValueError):
            fixed.qualify_trace(self.text, samples, 'gate')
        with self.assertRaises(ValueError):
            fixed.qualify_trace(self.text, self.samples[:3], 'gate')
        samples = copy.deepcopy(self.samples)
        samples[0]['native_request_id'] = samples[1]['native_request_id']
        with self.assertRaises(ValueError):
            fixed.qualify_trace(self.text, samples, 'gate')
        with self.assertRaises(ValueError):
            fixed.qualify_trace(self.text, self.samples, 'cost')

    def test_aggregate_without_API_correspondence_remains_diagnostic(self):
        text = self.text.replace('57 rounds 45 accepted;', '57 rounds 44 accepted;')
        result = fixed.qualify_trace(text, self.samples, 'gate')
        self.assertTrue(all(row['legacy_accepted'] == 44 for row in result['samples']))
        self.assertTrue(all(row['head_accepted'] == 69 for row in result['samples']))


if __name__ == '__main__':
    unittest.main()
