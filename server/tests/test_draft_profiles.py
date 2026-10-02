import copy, pathlib, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
try:
    import draft_profiles as module
except ImportError:
    module = None

class DraftProfilesTests(unittest.TestCase):
    def tune(self, profile, **kwargs):
        self.assertIsNotNone(module, 'Backend-specific draft profile generator missing')
        return module.tune(profile, **kwargs)

    def gufo(self):
        return {'backend': {'identifier': 'gufo-flash-next'},
                'engine': {'kind': 'native', 'qualified': True,
                    'command': ['gufo.exe', 'serve', 'llm', '--draft-tokens', '3',
                                '--speculative', 'mtp', '--mtp-model', 'head.gguf'],
                    'environment': {}, 'executable_sha256': 'pinned'},
                'qualification': {'source_commit': 'retained'}}

    def test_gufo_shallow_keeps_identity_and_input_unchanged(self):
        source = self.gufo(); before = copy.deepcopy(source)
        got = self.tune(source, draft_tokens=1)
        self.assertEqual(source, before)
        args = got['engine']['command']
        self.assertEqual(args[args.index('--draft-tokens')+1], '1')
        self.assertEqual(got['engine']['executable_sha256'], 'pinned')
        self.assertEqual(got['minimum_reserve_gib'], 18)
        self.assertNotIn('--tensor-split', args)

    def test_gufo_latin_survival_are_explicit(self):
        got = self.tune(self.gufo(), draft_tokens=3, draft_vocab='latin', mtp_policy='survival')
        args = got['engine']['command']
        self.assertEqual(args[args.index('--mtp-draft-vocab')+1], 'latin')
        self.assertEqual(args[args.index('--mtp-policy')+1], 'survival')
        self.assertEqual(got['qualification']['source_commit'], 'retained')
        self.assertTrue(got['qualification']['experimental'])

    def test_halogen_only_sets_supported_engine_option(self):
        source = {'backend': {'identifier': 'halogen-v2'},
                  'engine': {'kind': 'halogen', 'checkpoint': 'v2'}}
        got = self.tune(source, draft_tokens=1)
        self.assertEqual(got['engine']['draft_tokens'], 1)
        self.assertNotIn('command', got['engine'])
        with self.assertRaises(ValueError):
            self.tune(source, draft_tokens=1, draft_vocab='latin')

    def test_invalid_depth_and_unqualified_engine_rejected(self):
        for depth in (0, 4, True, 1.5, None):
            with self.subTest(depth=depth), self.assertRaises(ValueError):
                self.tune(self.gufo(), draft_tokens=depth)
        bad = self.gufo(); bad['engine']['qualified'] = False
        with self.assertRaises(ValueError): self.tune(bad, draft_tokens=1)

    def test_stricter_existing_reserve_not_relaxed(self):
        source=self.gufo(); source['minimum_reserve_gib']=24
        self.assertEqual(self.tune(source, draft_tokens=1)['minimum_reserve_gib'], 24)
