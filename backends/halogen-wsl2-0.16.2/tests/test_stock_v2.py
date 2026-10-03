"""The new release uses its own compute defaults and the installed lookup source."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import service
import portable
import startup_guard


class StockV2Tests(unittest.TestCase):
    def test_configured_existing_lookup_source_is_used(self):
        with patch.object(service.r, 'MACHINE', {'ngram_source': '/mnt/c/models/w4b.hgn'}):
            env = service.environment(262144, 'v2')
        self.assertEqual(env['HALOGEN_NGRAM_TABLE'], '/ngram-w4b.hgn')

    def test_native_model_store_lookup_source_is_used_without_override(self):
        with patch.object(service.r, 'MACHINE', None):
            env = service.environment(262144, 'v2')
        self.assertEqual(env['HALOGEN_NGRAM_TABLE'], '/models/qwen38-flash-next-w4b.hgn')

    def test_compute_defaults_are_left_to_pinned_upstream_image(self):
        env = service.environment(262144, 'v2')
        for key in ('HALOGEN_MAX_TOK', 'HALOGEN_PREFILL_CHUNK', 'HALOGEN_MTP_DEPTH'):
            self.assertNotIn(key, env)

    def test_standalone_guard_uses_this_exact_release(self):
        self.assertEqual(startup_guard.IMAGE, portable.IMAGE)

    def test_kernel_controls_reach_cli_and_recorded_environment(self):
        options = service.options(['--checkpoint', 'v2', '--kernel-controls-json',
                                   '{"HALOGEN_DN_SCAN":1}'])
        env = service.environment(262144, 'v2',
                                  kernel_controls=options.kernel_controls_json)
        self.assertEqual(env['HALOGEN_DN_SCAN'], '1')
        self.assertNotIn('HALOGEN_DN_FUSED', env)


if __name__ == '__main__':
    unittest.main()
