"""Managed opt-in policy profiles; no managed process is started."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import controller
import draft_profiles


class ManagedSpeculationPolicyTests(unittest.TestCase):
    repo = Path(__file__).resolve().parents[2]

    def profile(self, version='0.16.2'):
        return {'backend': {'identifier': 'halogen-v2', 'context': 262144},
                'engine': {'kind': 'halogen', 'directory': 'backends/halogen-wsl2-' + version,
                           'checkpoint': 'v2', 'context': 262144}}

    def tune(self, source, **options):
        try:
            return draft_profiles.tune(source, draft_tokens=2, **options)
        except TypeError as error:
            self.fail('Speculation policy profile support is missing: ' + str(error))

    def test_opt_in_is_copied_validated_and_forwarded_without_altering_source(self):
        source = self.profile()
        before = copy.deepcopy(source)
        policy = {'HALOGEN_PLD': '0', 'HALOGEN_SPEC_ADAPT': '32,0.35,64'}
        result = self.tune(source, speculation_policy=policy)
        self.assertEqual(source, before)
        self.assertEqual(result['qualification']['speculation_policy'], policy)
        directory = controller.validate_engine(result['engine'], self.repo)
        builder = getattr(controller, 'halogen_speculation_arguments', None)
        self.assertIsNotNone(builder, 'Managed policy forwarding is missing')
        args = builder(result['engine'], directory)
        self.assertEqual(args[0], '-SpeculationPolicyJson')
        self.assertEqual(json.loads(args[1]), policy)
        policy['HALOGEN_PLD'] = '3,3'
        self.assertEqual(result['engine']['speculation_policy']['HALOGEN_PLD'], '0')
        stock = self.tune(source)
        self.assertNotIn('speculation_policy', stock['engine'])
        self.assertEqual(builder(stock['engine'], directory), [])

    def test_invalid_inherited_explicit_legacy_and_native_policies_are_refused(self):
        for version, policy in (('0.16.2', {'HALOGEN_PLD': '3,4'}),
                                ('0.16.1', {'HALOGEN_PLD': '0'})):
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.tune(self.profile(version), speculation_policy=policy)
        inherited = self.profile()
        inherited['engine']['speculation_policy'] = {'HALOGEN_SPEC_ADAPT': True}
        with self.assertRaises(ValueError):
            self.tune(inherited)
        native = {'kind': 'native', 'qualified': True, 'speculation_policy': {'HALOGEN_PLD': '0'}}
        with self.assertRaisesRegex(ValueError, 'Halogen'):
            controller.validate_engine(native, self.repo)


if __name__ == '__main__':
    unittest.main()
