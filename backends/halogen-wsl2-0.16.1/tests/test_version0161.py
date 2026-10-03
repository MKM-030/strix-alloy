"""Pin the upgraded engine without silently switching the user's model assets."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import portable
import service
import bridge_adapter

class Version0161Tests(unittest.TestCase):
    def test_exact_image_and_engine_identity(self):
        self.assertEqual(portable.RELEASE['version'],'0.16.1')
        self.assertEqual(portable.IMAGE,'ghcr.io/peonist-ai/halogen-flash-server@sha256:089701309a7ed9f70c91daca6a66080828e032788d4e6d0da4d427587387ede5')
        self.assertEqual(bridge_adapter.ENGINE_SHA,portable.RELEASE['engine_sha256'])
        self.assertEqual(bridge_adapter.SITE_RVA,0x1876e70)
        self.assertEqual(bridge_adapter.SITE_OFFSET,0x1875e70)

    def test_old_checkpoint_and_overlay_are_explicit(self):
        env=service.environment(129024)
        self.assertEqual(env['HALOGEN_CHECKPOINT'],'/models/qwen38-flash-next-w4b.hgn')
        self.assertEqual(env['HALOGEN_CK_OVERLAY'],'/models/qwen38-flash-next-w4b.overlay.hgn')
        self.assertEqual(env['HALOGEN_CTX'],'129024')
        self.assertEqual(env['HALOGEN_KV_POOL_POSITIONS'],'129024')
        self.assertNotIn('HALOGEN_DOWNLOAD',env)
        self.assertEqual(env['HALOGEN_KV_SLOTS'],'1')

    def test_old_version_health_cannot_pass_new_readiness(self):
        h={'status':'ok','version':{'api':'0.14.2','engine':'0.14.2','match':True},
           'context':129024,'slot_ctx':129024,'kv_pool_positions':129024,'slots':1}
        with self.assertRaises(ValueError): service.validate_health(h,129024)
        h['version']={'api':'0.16.1','engine':'0.16.1','match':True}
        service.validate_health(h,129024)

    def test_default_continuous_126k_and_auth_wrapper_retained(self):
        o=service.options()
        self.assertEqual((o.context_size,o.serve_seconds),(129024,0))
        self.assertTrue((ROOT/'scripts/auth_api.py').exists())
        self.assertTrue((ROOT/'scripts/startup_cache.py').exists())
        self.assertTrue((ROOT/'scripts/startup_monitor.py').exists())
        self.assertEqual(service.floors(129024),(46,121))

if __name__=='__main__': unittest.main()
