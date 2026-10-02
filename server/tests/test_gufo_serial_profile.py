import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from gufo_serial_profile import serial_profile


class GufoSerialTests(unittest.TestCase):
    def test_clones_only_draft_options(self):
        source = {'minimum_reserve_gib': 20, 'backend': {'identifier': 'gufo-flash-next'},
                  'engine': {'kind': 'native', 'qualified': True, 'executable_sha256': 'pin',
                             'runtime_hashes': {'dll': 'pin'},
                             'command': ['gufo.exe', 'serve', 'llm', '--mtp-model', 'head.gguf',
                                         '--speculative', 'mtp', '--draft-tokens', '3',
                                         '--mtp-policy', 'length', '--mtp-draft-vocab', 'latin',
                                         '--prompt-lookup', '--context', '262144']}}
        original = copy.deepcopy(source)
        candidate = serial_profile(source)
        self.assertEqual(source, original)
        args = candidate['engine']['command']
        self.assertEqual(args[args.index('--speculative') + 1], 'off')
        self.assertNotIn('--mtp-model', args)
        self.assertNotIn('--prompt-lookup', args)
        self.assertEqual(args[args.index('--context') + 1], '262144')
        self.assertEqual(candidate['minimum_reserve_gib'], 20)
        self.assertEqual(candidate['engine']['executable_sha256'], 'pin')

    def test_unqualified_and_ambiguous_flags_refused(self):
        source = {'backend': {'identifier': 'gufo-flash-next'},
                  'engine': {'kind': 'native', 'qualified': False,
                             'command': ['gufo.exe', '--mtp-model', 'head', '--speculative', 'mtp']}}
        with self.assertRaises(ValueError):
            serial_profile(source)
        source['engine']['qualified'] = True
        source['engine']['command'].extend(['--speculative', 'mtp'])
        with self.assertRaises(ValueError):
            serial_profile(source)


if __name__ == '__main__':
    unittest.main()
