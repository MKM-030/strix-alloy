"""CPU-only exact output checks for comparison/index-only selector saving."""
import ast
import hashlib
from pathlib import Path
import subprocess
import sys
import types
import unittest

try:
    import greedy_walk as ops
except ModuleNotFoundError:
    ops=None

class Passive(unittest.TestCase):
    def test_exists(self):self.assertIsNotNone(ops,'selector walk helper missing')
    @unittest.skipIf(ops is None,'component absent')
    def test_import_is_passive(self):
        p=subprocess.run([sys.executable,'-B','-c',"import sys;from scripts.research.dflash2_gpu import greedy_walk;assert 'torch' not in sys.modules"],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)

@unittest.skipIf(ops is None,'component absent')
class CPU(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        cls.t=torch;torch.set_num_threads(1);torch.set_num_interop_threads(1)
        cls.g=torch.Generator(device='cpu').manual_seed(1831)
        path=Path(__file__).resolve().parents[1]/'dflash2_reference/sources/sglang_dflash.py'
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!='b7b541368cbbb072a679d08ba5bf0f952f4a43f02b6c078562b2ea7a9ddfd01b':raise ValueError('source changed')
        tree=ast.parse(data);nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_follow_maps']
        selector=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='CandidateSelector')
        nodes.append(next(n for n in selector.body if isinstance(n,ast.FunctionDef) and n.name=='sample_path'))
        class Hints(ast.NodeTransformer):
            def visit_FunctionDef(self,n):
                for dec in n.decorator_list:
                    if not isinstance(dec,ast.Call) or ast.unparse(dec.func)!='torch.compile':raise ValueError('unexpected decorator')
                n.decorator_list=[];return self.generic_visit(n)
            def visit_Expr(self,n):
                if isinstance(n.value,ast.Call) and ast.unparse(n.value.func)=='torch._dynamo.mark_static':return ast.copy_location(ast.Pass(),n)
                return self.generic_visit(n)
        module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*nodes],type_ignores=[])
        ns={'torch':torch,'F':torch.nn.functional}
        exec(compile(ast.fix_missing_locations(Hints().visit(module)),str(path),'exec'),ns)
        cls.source=staticmethod(ns['sample_path'])

    def compare(self,ids,scores):
        t=self.t;b,s,_=ids.shape
        expected=self.source(types.SimpleNamespace(top_k=16),candidate_ids=ids,scores=scores,
            uniforms=t.zeros((b,s),device='cpu'),temperatures=t.ones(b,device='cpu'),greedy_mask=t.ones(b,dtype=t.bool,device='cpu'))
        actual=ops.walk_greedy(ids,scores)
        t.testing.assert_close(actual.tokens,expected[0],rtol=0,atol=0)
        t.testing.assert_close(actual.q_rows,expected[1],rtol=0,atol=0)
        t.testing.assert_close(actual.path_indices,expected[1].argmax(-1),rtol=0,atol=0)
        return actual

    def test_blocks4_8_batches_and_noncontiguous_lattices(self):
        t=self.t
        for b in (1,2):
            for slots in (3,7):
                ids=t.arange(b*slots*16,device='cpu',dtype=t.int64).view(b,slots,16)%64
                backing=t.randn((b,slots,16,32),generator=self.g,device='cpu')
                scores=backing[...,::2]
                before=scores.clone();self.compare(ids,scores)
                t.testing.assert_close(scores,before,rtol=0,atol=0)

    def test_ties_nan_inf_and_predecessor_conditioning(self):
        t=self.t;ids=t.arange(3*16,device='cpu',dtype=t.int64).view(1,3,16)
        scores=t.zeros((1,3,16,16),device='cpu')
        scores[:,0,0,3]=100
        for p in range(16):
            scores[:,1,p,(p+1)%16]=50;scores[:,2,p,(p+1)%16]=50
        actual=self.compare(ids,scores);self.assertEqual(actual.path_indices.tolist(),[[3,4,5]])
        scores.zero_();self.assertEqual(self.compare(ids,scores).path_indices.tolist(),[[0,0,0]])
        scores[:,0,0,2]=float('nan');scores[:,0,0,4]=float('nan')
        scores[:,1,2,6]=float('inf');scores[:,1,2,7]=float('inf')
        scores[:,2,6,:]=-float('inf')
        self.assertEqual(self.compare(ids,scores).path_indices.tolist(),[[2,6,0]])

    def test_metadata_and_owned_outputs(self):
        t=self.t;ids=t.zeros((1,3,16),device='cpu',dtype=t.int64);scores=t.zeros((1,3,16,16),device='cpu')
        result=self.compare(ids,scores)
        self.assertEqual(result.q_rows.dtype,t.float32);self.assertNotEqual(result.tokens.data_ptr(),ids.data_ptr())
        for bad_ids,bad_scores in ((ids.float(),scores),(ids,scores.bfloat16()),(ids[:,:,:8],scores),(ids,scores[:,:2])):
            with self.assertRaises((TypeError,ValueError)):ops.walk_greedy(bad_ids,bad_scores)

if __name__=='__main__':
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(Passive)])
    if '--run-cpu' in sys.argv:suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(CPU))
    result=unittest.TextTestRunner(verbosity=2).run(suite);raise SystemExit(not result.wasSuccessful())
