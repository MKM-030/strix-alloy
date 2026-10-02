import pathlib, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import controller

class MemoryReserveTests(unittest.TestCase):
    def policy(self, value):
        fn = getattr(controller, 'memory_reserve_gib', None)
        self.assertIsNotNone(fn, 'Configurable stricter reserve is missing')
        return fn(value)

    def test_legacy_default_is_not_relaxed(self):
        self.assertEqual(self.policy({}), 12.0)

    def test_stricter_eighteen_gib_reserve(self):
        self.assertEqual(self.policy({'minimum_reserve_gib': 18}), 18.0)

    def test_invalid_or_relaxed_reserves_are_rejected(self):
        for value in (0, 11.9, 129, True, None, '18', float('nan'), float('inf')):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.policy({'minimum_reserve_gib': value})
