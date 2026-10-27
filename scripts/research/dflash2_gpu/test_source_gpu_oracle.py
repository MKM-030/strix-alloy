"""Explicit bounded CPU checks for independent same-device source oracle."""
import subprocess
import sys
import unittest
from pathlib import Path

try:
    import source_gpu_oracle as ops
except ModuleNotFoundError:
    ops=None

class Passive(unittest.TestCase):
    def test_exists(self):self.assertIsNotNone(ops,'independent same-device source oracle missing')
    @unittest.skipIf(ops is None,'oracle absent')
    def test_passive_namespace_import(self):
        code="import sys;from scripts.research.dflash2_gpu import source_gpu_oracle as o;assert 'torch' not in sys.modules;assert o.SOURCE_PINS"
        p=subprocess.run([sys.executable,'-B','-c',code],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)

@unittest.skipIf(ops is None,'oracle absent')
class CPU(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        cls.t=torch;torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.set_grad_enabled(False)
        cls.oracle=ops.SourceGPUOracle.setup(device='cpu',max_positions=32)
    def test_original_ast_native_norm_and_rope(self):
        t=self.t;o=self.oracle
        for dtype in (t.float32,t.bfloat16):
            x=t.linspace(-2,2,4*128,device='cpu').reshape(4,128).to(dtype)
            w=t.linspace(.6,1.4,128,device='cpu').to(dtype)
            y=o.norm(w)(x)
            expected=((x.float()*t.rsqrt(x.float().pow(2).mean(-1,keepdim=True)+1e-6))*w).to(dtype)
            t.testing.assert_close(y,expected,rtol=0,atol=0)
            pos=t.arange(8,12,device='cpu',dtype=t.int64)
            q=x[:,None,:].expand(-1,2,-1).contiguous().flatten(1)
            rq,rk=o.rotary(pos,q,q)
            self.assertEqual(tuple(rq.shape),(4,256));t.testing.assert_close(rq,rk,rtol=0,atol=0)
    def test_author_window_is_common_block_end(self):
        o=self.oracle;t=self.t
        q=t.ones((4,4096),device='cpu');k=t.ones((4,1024),device='cpu');v=t.arange(4,device='cpu').float()[:,None].expand(-1,1024)
        ck=t.ones((2048,8,128),device='cpu');cv=t.zeros_like(ck)
        out=o.attend(q,k,v,ck,cv,prefix_tokens=2048)
        for row in range(1,4):t.testing.assert_close(out[row],out[0],rtol=0,atol=0)
        t.testing.assert_close(out,t.full_like(out,6/2048),rtol=2e-6,atol=1e-8)
    def test_no_graph_arithmetic_dependency(self):
        text=Path(ops.__file__).read_text()
        self.assertNotIn('from .graph',text);self.assertNotIn('from .backbone',text)
        self.assertIn('DFlashDecoderLayer.forward',self.oracle.extracted)
        self.assertIn('RMSNorm.forward_native',self.oracle.extracted)
    def test_full_width_original_method_adapter_against_frozen_cpu_reference(self):
        root=str(Path(__file__).resolve().parents[3])
        if root not in sys.path:sys.path.insert(0,root)
        from scripts.research.dflash2_reference import backbone
        t=self.t
        for dtype in (t.float32,t.bfloat16):
            # True2560/7680/32Q/8KV/128/two-tap geometry, tiny backing storage.
            # No trained weights or GPU work. Packing occurs only in the oracle.
            weights={}
            for name,shape in ops.LAYER_SHAPES.items():
                if name.endswith('base_kernel'):
                    value=t.zeros(shape,device='cpu',dtype=dtype);value[:,0]=1
                elif len(shape)==1:value=t.linspace(.8,1.2,shape[0],device='cpu').to(dtype)
                else:value=t.tensor(.0001,device='cpu',dtype=dtype).expand(shape)
                weights[name]=value
            x=t.linspace(-.1,.2,4*2560,device='cpu').reshape(4,2560).to(dtype)
            ck=t.ones((8,8,128),device='cpu',dtype=dtype)*.01;cv=ck*.5
            layer=self.oracle.layer(weights)
            actual=layer.forward(x,None,ck,cv,prefix_tokens=8,trace=True)
            expected=backbone.layer_forward(x,None,t.arange(8,12,device='cpu'),ck,cv,
                t.arange(8,device='cpu'),weights,block_size=4)
            for a,b in zip(actual,expected):t.testing.assert_close(a,b,rtol=0,atol=0)
            self.assertTrue(bool(actual[0].abs().sum()>0))
            self.assertIn('attention_conv.finish',layer.last_trace)
            self.assertIn('mlp_conv.prepare',layer.last_trace)

if __name__=='__main__':
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(Passive)])
    if '--run-cpu' in sys.argv:suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(CPU))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
