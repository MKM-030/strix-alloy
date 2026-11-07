"""CPU-only saved-evidence and frozen-mode regressions for the cost companion."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import export_comparison as exporter

sys.path.append(str(exporter.HERE))
legacy_spec = importlib.util.spec_from_file_location(
    'frozen_exporter_tests', exporter.HERE / 'test_export_comparison.py')
legacy = importlib.util.module_from_spec(legacy_spec)
legacy_spec.loader.exec_module(legacy)

RULE = 'HALOGEN_MTP_GATE_RULE'
EXPERIMENT = 'mtp_gate_cost'
SELECTED = exporter.HERE.parent / 'serving0191-text32k-one-slot-2048.json'


def projected_profile(arm):
    value = json.loads(SELECTED.read_bytes())
    value['engine']['kernel_controls'].update(
        HALOGEN_PHASE_RAW=1, HALOGEN_SERVE_TRACE=1, HALOGEN_DRAFT_VOCAB_Q8=0)
    value['engine']['speculation_policy'][RULE] = 'cost' if arm == 'candidate' else 'gate'
    return value


class CostProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'profile.json'

    def select(self, value):
        legacy.save(self.path, value)
        return exporter.safe_profile(self.path, exporter.sha(self.path), EXPERIMENT)

    def test_valid_fixed_q4_profiles_expose_the_gate_cost_gate_rule(self):
        for arm, rule in zip(exporter.ARMS, ('gate', 'cost', 'gate')):
            with self.subTest(arm=arm):
                selected = self.select(projected_profile(arm))
                self.assertEqual(exporter.arm_profile(selected, arm, EXPERIMENT)['slots'], 1)
                self.assertEqual(selected['mtp_gate_rule'], rule)
                self.assertEqual(selected['draft_vocab_q8'], 0)
                self.assertEqual(selected['serve_trace'], 1)

    def test_rule_strings_and_numeric_control_types_are_strict(self):
        original = projected_profile('candidate')
        mutations = [
            ('kernel_controls', 'HALOGEN_DRAFT_VOCAB_Q8', True),
            ('kernel_controls', 'HALOGEN_DRAFT_VOCAB_Q8', 0.0),
            ('kernel_controls', 'HALOGEN_DRAFT_VOCAB_Q8', '0'),
            ('kernel_controls', 'HALOGEN_DRAFT_VOCAB_Q8', 1),
            ('kernel_controls', 'HALOGEN_SERVE_TRACE', True),
            ('kernel_controls', 'HALOGEN_SERVE_TRACE', 0),
            ('kernel_controls', 'HALOGEN_PHASE_RAW', True),
            ('kernel_controls', 'HALOGEN_DECODE_PREFETCH', 1),
            ('speculation_policy', RULE, 'Cost'),
            ('speculation_policy', RULE, 'cost '),
            ('speculation_policy', RULE, True),
            ('speculation_policy', 'HALOGEN_MTP_GATE_LINE', '0.88'),
        ]
        for group, key, value in mutations:
            with self.subTest(group=group, key=key, value=value):
                profile = copy.deepcopy(original)
                profile['engine'][group][key] = value
                with self.assertRaises(ValueError):
                    self.select(profile)

    def test_every_other_selected_profile_field_stays_exact(self):
        original = projected_profile('candidate')
        mutations = [
            (('engine', 'api_defaults', 'max_thinking_tokens'), 4096),
            (('engine', 'api_defaults', 'enable_thinking'), 0),
            (('engine', 'speculation_policy', 'HALOGEN_PLD'), '3,4'),
            (('engine', 'context'), 32768.0),
            (('engine', 'prefill_chunk'), 4096),
            (('engine', 'max_prefill_tokens'), 4096),
            (('request_seconds',), 1801),
            (('backend', 'expected', 'slot_ctx'), 65536),
        ]
        for keys, value in mutations:
            with self.subTest(keys=keys):
                profile = copy.deepcopy(original)
                target = profile
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
                with self.assertRaises(ValueError):
                    self.select(profile)
        profile = copy.deepcopy(original)
        profile['engine']['kernel_controls']['HALOGEN_UNUSED'] = 0
        with self.assertRaises(ValueError):
            self.select(profile)

    def test_arm_rule_mismatch_rejects_the_other_canonical_rule(self):
        for arm, wrong_rule in (('before', 'cost'), ('candidate', 'gate'), ('after', 'cost')):
            profile = projected_profile(arm)
            profile['engine']['speculation_policy'][RULE] = wrong_rule
            selected = self.select(profile)
            with self.subTest(arm=arm), self.assertRaises(ValueError):
                exporter.arm_profile(selected, arm, EXPERIMENT)


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromModule(legacy))
    suite.addTests(loader.loadTestsFromTestCase(CostProfileTests))
    return suite


if __name__ == '__main__':
    unittest.main()
