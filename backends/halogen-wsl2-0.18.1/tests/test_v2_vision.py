"""Checks the actual 0.18.1 launch environment and vision readiness contract."""
import sys
import unittest

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import service


class VisionLaunchTests(unittest.TestCase):
    def test_v2_container_loads_tower_and_retains_memory_reserve(self):
        env = service.environment(262144, checkpoint='v2', prompt_cache='Exact')
        self.assertEqual(env.get('HALOGEN_VISION_TOWER'), '/models/qwen38-flash-next-vision.hgn')
        self.assertEqual(env['HALOGEN_CHECKPOINT'], '/models/qwen38-flash-next-v2.hgn')
        self.assertEqual(env['HALOGEN_HOST_RESERVE_GIB'], '18')
        self.assertEqual(env['HALOGEN_PROMPT_CACHE'], '1')

    def test_legacy_checkpoint_is_unchanged(self):
        self.assertNotIn('HALOGEN_VISION_TOWER', service.environment(262144, checkpoint='w4b'))

    def test_v2_readiness_rejects_text_only_engine(self):
        health = {'status': 'ok', 'version': {'api': '0.18.1', 'engine': '0.18.1', 'match': True},
                  'context': 262144, 'slot_ctx': 262144, 'kv_pool_positions': 262144,
                  'slots': 1, 'vision': {'enabled': False}}
        with self.assertRaisesRegex(ValueError, 'vision tower'):
            service.validate_health(health, 262144)
        health['vision']['enabled'] = True
        service.validate_health(health, 262144)


if __name__ == '__main__':
    unittest.main()
