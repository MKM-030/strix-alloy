import pathlib, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import controller

class DraftForwardingTests(unittest.TestCase):
    def args(self, config):
        fn = getattr(controller, 'halogen_draft_arguments', None)
        self.assertIsNotNone(fn, 'Controller draft forwarding missing')
        return fn(config)

    def test_legacy_unchanged(self): self.assertEqual(self.args({}), [])

    def test_depth_forwarded(self):
        self.assertEqual(self.args({'draft_tokens': 1}), ['-DraftTokens', '1'])

    def test_bad_config_refused(self):
        for value in (0, 4, '1', True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.args({'draft_tokens': value})
