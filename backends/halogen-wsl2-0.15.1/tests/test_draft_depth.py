import pathlib, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import service

class DraftDepthTests(unittest.TestCase):
    def env(self, depth):
        try: return service.environment(262144, 'v2', 'Off', draft_tokens=depth)
        except TypeError as exc: self.fail('Draft depth not wired into environment: '+str(exc))

    def test_default_environment_is_unchanged(self):
        self.assertEqual(self.env(None), service.environment(262144, 'v2', 'Off'))

    def test_supported_depth_one_and_two(self):
        base = service.environment(262144, 'v2', 'Off')
        for depth in (1, 2, 3):
            expected = dict(base, HALOGEN_MTP_DEPTH=str(depth))
            self.assertEqual(self.env(depth), expected)

    def test_bad_depths_refused(self):
        for depth in (0, 4, True, '1', 1.5):
            with self.subTest(depth=depth), self.assertRaises(ValueError): self.env(depth)
