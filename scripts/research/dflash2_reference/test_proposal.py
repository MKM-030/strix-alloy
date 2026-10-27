"""Explicit CPU-only proposal checks; synthetic vocab32/64, true width/rank."""
import ast
import copy
import hashlib
import json
import subprocess
import sys
import types
import typing
import unittest
from pathlib import Path

try:
    import proposal as ops
except ModuleNotFoundError:
    ops=None

class Passive(unittest.TestCase):
    def test_component_exists(self):
        self.assertIsNotNone(ops,'TP1 full-head greedy selector component missing')

    def test_import_and_pinned_source_metadata_are_passive(self):
        self.assertNotIn('torch',sys.modules)
        self.assertIsNotNone(ops)
        result=ops.verify_sources()
        self.assertEqual((result['width'],result['rank'],result['top_k']),(2560,256,16))
        code="import sys,types;sys.modules['math_ops']=types.ModuleType('math_ops');from scripts.research.dflash2_reference import proposal;assert 'torch' not in sys.modules;proposal.verify_sources()"
        p=subprocess.run([sys.executable,'-B','-c',code],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)

class StripCompileOnly(ast.NodeTransformer):
    def visit_FunctionDef(self,node):
        for dec in node.decorator_list:
            if not isinstance(dec,ast.Call) or ast.unparse(dec.func)!='torch.compile':
                raise AssertionError('Unexpected source decorator')
        node.decorator_list=[]
        return self.generic_visit(node)
    def visit_Expr(self,node):
        if isinstance(node.value,ast.Call) and ast.unparse(node.value.func)=='torch._dynamo.mark_static':return ast.copy_location(ast.Pass(),node)
        return self.generic_visit(node)

@unittest.skipIf(ops is None,'component absent')
class Numerical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        cls.t=torch
        torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.set_grad_enabled(False)
        cls.gen=torch.Generator(device='cpu').manual_seed(181630)

    def fixture(self,block=4,vocab=32,dtype=None,batch=2):
        t=self.t;dtype=dtype or t.float32
        rand=lambda shape:(t.randn(shape,generator=self.gen,device='cpu')*.08).to(dtype)
        hidden=rand((batch*block,2560));head=rand((vocab,2560))
        weights={'candidate_selector.hidden_projection.weight':rand((256,2560)),
                 'candidate_selector.predecessor_codebook':rand((vocab,256)),
                 'candidate_selector.successor_codebook':rand((vocab,256))}
        anchors=t.tensor([3+4*i for i in range(batch)],dtype=t.int64,device='cpu')
        return hidden,anchors,head,weights

    def call(self,f,block=4,org=None):
        return ops.propose_greedy(*f,block_size=block,org_vocab_size=org or f[2].shape[0])

    def actual_source_oracle(self,f,block,org):
        """Actual CPU source functions/classes plus actual worker sampler body.

        Only torch.compile and mark_static are removed. Dense TP1 dependencies
        are explicit stubs; no arithmetic, slicing, RNG or q construction edits.
        """
        t=self.t
        source=ops.SOURCE.read_bytes();worker=ops.WORKER_SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),ops.SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(worker).hexdigest(),ops.WORKER_SHA256)
        model_tree=ast.parse(source);worker_tree=ast.parse(worker)
        names=('_radix_topk','_project_candidate_logits','candidate_topk','_score_edges','_follow_maps')
        body=[copy.deepcopy(n) for n in model_tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
        body.append(copy.deepcopy(next(n for n in model_tree.body if isinstance(n,ast.ClassDef) and n.name=='CandidateSelector')))
        dflash=next(n for n in model_tree.body if isinstance(n,ast.ClassDef) and n.name=='DFlash2DraftModel')
        body.extend(copy.deepcopy(n) for n in dflash.body if isinstance(n,ast.FunctionDef) and n.name in ('_transform_unary_logits','compute_candidates'))
        body.append(copy.deepcopy(next(n for n in worker_tree.body if isinstance(n,ast.FunctionDef) and n.name=='_selector_lattice')))
        sampler_cls=next(n for n in worker_tree.body if isinstance(n,ast.ClassDef) and n.name=='_SelectorDraftSampler')
        body.append(copy.deepcopy(next(n for n in sampler_cls.body if isinstance(n,ast.FunctionDef) and n.name=='__call__')))
        tree=ast.fix_missing_locations(StripCompileOnly().visit(ast.Module(body=body,type_ignores=[])))
        ns={'torch':t,'nn':t.nn,'F':t.nn.functional,'Tuple':typing.Tuple,'Optional':typing.Optional,
            '_flashinfer_top_k':None,'logger':types.SimpleNamespace(warning=lambda *a,**kw:None),
            'get_parallel':lambda:types.SimpleNamespace(tp_size=1),
            'should_apply_lm_head_quant_method':lambda head,method:False,
            'is_dense_head_weight':lambda w:isinstance(w,t.Tensor) and w.ndim==2 and w.dtype in (t.float32,t.bfloat16)}
        exec(compile(tree,'hash-pinned-proposal-oracle','exec'),ns)
        hidden,anchors,head,w=f;vocab=head.shape[0];batch=hidden.shape[0]//block;gamma=block-1
        selector=ns['CandidateSelector'](hidden_size=2560,vocab_size=vocab,state_rank=256,top_k=16).to(dtype=hidden.dtype,device='cpu')
        selector.hidden_projection.weight.data.copy_(w['candidate_selector.hidden_projection.weight'])
        selector.predecessor_codebook.data.copy_(w['candidate_selector.predecessor_codebook'])
        selector.successor_codebook.data.copy_(w['candidate_selector.successor_codebook'])
        model=types.SimpleNamespace(lm_head=types.SimpleNamespace(weight=head,org_vocab_size=org),candidate_selector=selector,
            draft_config=types.SimpleNamespace(output_multiplier=1.,final_logit_softcapping=None))
        model._transform_unary_logits=types.MethodType(ns['_transform_unary_logits'],model)
        model.compute_candidates=types.MethodType(ns['compute_candidates'],model)
        sampler=types.SimpleNamespace(block_size=block,draft_model=model,selector=selector,
            uniforms=t.zeros((batch,gamma),device='cpu'),temperatures=t.ones(batch,device='cpu'),
            greedy_mask=t.ones(batch,dtype=t.bool,device='cpu'),out=t.empty(batch*gamma,dtype=t.int64,device='cpu'),
            candidate_out=t.empty((batch,gamma,16),dtype=t.int64,device='cpu'),q_out=t.empty((batch,gamma,16),device='cpu'))
        input_ids=t.zeros((batch,block),dtype=t.int64,device='cpu');input_ids[:,0]=anchors
        ns['__call__'](sampler,hidden,input_ids.reshape(-1))
        predicted=hidden.view(batch,block,2560)[:,1:]
        ids,scores=ns['_selector_lattice'](model,predicted,anchors)
        _,unary=model.compute_candidates(predicted.reshape(-1,2560))
        return dict(tokens=sampler.out.view(batch,gamma),candidate_ids=ids,unary_logits=unary.view(batch,gamma,16),
                    edge_scores=scores,q_rows=sampler.q_out,path_indices=sampler.q_out.argmax(-1))

    def same_source(self,result,expected):
        for name,value in expected.items():
            self.t.testing.assert_close(getattr(result,name),value,rtol=0,atol=0)

    def test_complete_source_body_oracle_real_dimensions_and_padding(self):
        for block,vocab,dtype in [(4,32,self.t.float32),(8,64,self.t.float32),(4,32,self.t.bfloat16),(8,64,self.t.bfloat16)]:
            f=self.fixture(block,vocab,dtype);org=vocab-8
            f[2][org:].fill_(10000)
            expected=self.actual_source_oracle(f,block,org)
            result=self.call(f,block,org)
            self.same_source(result,expected)
            self.assertTrue(bool((result.candidate_ids<org).all()))
            self.assertEqual(tuple(result.tokens.shape),(2,block-1))
            self.assertTrue(bool((result.q_rows.sum(-1)==1).all()))
            self.assertTrue(bool(((result.q_rows==0)|(result.q_rows==1)).all()))

    def test_anchor_hidden_row_is_discarded_for_every_block(self):
        for block in (4,8):
            f=self.fixture(block,64);before=self.call(f,block)
            altered=f[0].clone().view(2,block,2560);altered[:,0].fill_(100)
            after=self.call((altered.reshape(-1,2560),*f[1:]),block)
            for name in ('tokens','candidate_ids','unary_logits','edge_scores','q_rows','path_indices'):
                self.t.testing.assert_close(getattr(before,name),getattr(after,name),rtol=0,atol=0)

    def test_learned_coherent_path_differs_from_independent_unary_argmax(self):
        t=self.t
        for block in (4,8):
            for dtype in (t.float32,t.bfloat16):
                x=t.zeros((block,2560),dtype=dtype,device='cpu');x[:,0]=1
                head=t.zeros((32,2560),dtype=dtype,device='cpu');head[:,0]=-t.arange(32,device='cpu').to(dtype)*.01
                projection=t.zeros((256,2560),dtype=dtype,device='cpu');projection[:,0]=1
                pred=t.zeros((32,256),dtype=dtype,device='cpu');pred[:,:32]=t.eye(32,dtype=dtype,device='cpu')
                succ=t.zeros_like(pred)
                for token in range(32):succ[token,(token-1)%32]=100
                f=(x,t.tensor([3],dtype=t.int64,device='cpu'),head,dict(zip(ops.SELECTOR_KEYS,(projection,pred,succ))))
                result=self.call(f,block)
                self.same_source(result,self.actual_source_oracle(f,block,32))
                self.assertEqual(result.tokens.tolist(),[list(range(4,block+3))])
                self.assertTrue(bool((result.candidate_ids[:,:,0]==0).all()))

    def test_mixed_dense_head_precision_uses_source_cast(self):
        f=list(self.fixture(4,32,self.t.bfloat16));f[2]=f[2].float()
        self.same_source(self.call(f),self.actual_source_oracle(f,4,32))

    def test_exact_cpu_topk_tie_behavior_matches_source_not_gpu_claim(self):
        f=self.fixture(4,32);f[2].zero_()
        self.same_source(self.call(f),self.actual_source_oracle(f,4,32))

    def test_input_and_parameters_are_unchanged_and_outputs_are_owned(self):
        f=self.fixture();before=[x.clone() for x in f[:3]]+[x.clone() for x in f[3].values()]
        rng_before=self.t.random.get_rng_state().clone()
        result=self.call(f)
        self.t.testing.assert_close(self.t.random.get_rng_state(),rng_before,rtol=0,atol=0)
        for actual,expected in zip([*f[:3],*f[3].values()],before):self.t.testing.assert_close(actual,expected,rtol=0,atol=0)
        self.assertFalse(result.edge_scores.requires_grad)
        self.assertNotEqual(result.tokens.data_ptr(),f[1].data_ptr())

    def test_invalid_geometry_ids_domains_and_nonfinite_fail_closed(self):
        t=self.t;f=self.fixture()
        for block in (True,3,16):
            with self.assertRaises((TypeError,ValueError)):self.call(f,block)
        for org in (True,15,33):
            with self.assertRaises((TypeError,ValueError)):ops.propose_greedy(*f,block_size=4,org_vocab_size=org)
        for hidden in (f[0][:3],f[0][:,:256],f[0].double()):
            with self.assertRaises((TypeError,ValueError)):self.call((hidden,*f[1:]))
        for anchor in (t.tensor([-1,2],device='cpu'),t.tensor([32,2],device='cpu'),f[1].float(),f[1][:1]):
            with self.assertRaises((TypeError,ValueError)):self.call((f[0],anchor,*f[2:]))
        broken=dict(f[3]);broken.pop(ops.SELECTOR_KEYS[0])
        with self.assertRaises(ValueError):self.call((*f[:3],broken))
        broken=dict(f[3]);broken[ops.SELECTOR_KEYS[0]]=broken[ops.SELECTOR_KEYS[0]][:128]
        with self.assertRaises(ValueError):self.call((*f[:3],broken))
        bad=f[0].clone();bad[1,0]=float('nan')
        with self.assertRaises(ValueError):self.call((bad,*f[1:]))
        for key in ops.SELECTOR_KEYS:
            broken=dict(f[3]);broken[key]=broken[key].clone();broken[key][0,0]=float('inf')
            with self.assertRaises(ValueError):self.call((*f[:3],broken))
        broken=dict(f[3]);broken[ops.SELECTOR_KEYS[0]]=broken[ops.SELECTOR_KEYS[0]].bfloat16()
        with self.assertRaises(ValueError):self.call((*f[:3],broken))
        bad_head=f[2].clone();bad_head[0,0]=float('nan')
        with self.assertRaises(ValueError):self.call((f[0],f[1],bad_head,f[3]))
        huge=list(f);huge[0]=f[0].clone().fill_(1e38);huge[2]=f[2].clone().fill_(1e38)
        with self.assertRaises(ValueError):self.call(huge)

if __name__=='__main__':
    if '--run-cpu' not in sys.argv:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Passive))
    else:
        sys.argv.remove('--run-cpu')
        suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(Passive),unittest.defaultTestLoader.loadTestsFromTestCase(Numerical)])
        result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
