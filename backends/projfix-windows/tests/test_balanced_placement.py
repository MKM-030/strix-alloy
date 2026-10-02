import importlib.util
from pathlib import Path
import re
import unittest
spec=importlib.util.spec_from_file_location('projfix_profile_under_test',Path(__file__).parents[1]/'profile.py')
profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)

class BalancedPlacementTests(unittest.TestCase):
    def test_serial_places_only_first_eighteen_expert_layers_in_host_buffer(self):
        args=profile.command('runtime','target','draft',262144,mode='serial')
        self.assertIn('-ot',args)
        pattern,buffer=args[args.index('-ot')+1].rsplit('=',1)
        self.assertEqual(buffer,'CPU')
        selected=re.compile(pattern)
        for layer in range(48):
            for part in ('gate','up','down'):
                name=f'blk.{layer}.ffn_{part}_exps.weight'
                self.assertEqual(bool(selected.search(name)),layer<18,name)
        for name in ('output.weight','token_embd.weight','per_layer_token_embd.weight',
                     'blk.0.ffn_gate_inp.weight','blk.0.ffn_down_shexp.weight','blk.0.attn_qkv.weight'):
            self.assertIsNone(selected.search(name),name)
        self.assertEqual(args[args.index('-ctk')+1],'f16')
        self.assertEqual(args[args.index('-ctv')+1],'f16')
        self.assertNotIn('-md',args)

if __name__=='__main__':unittest.main()
