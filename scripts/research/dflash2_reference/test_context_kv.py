"""Explicit one-thread CPU context-KV checks; no model data or devices on import."""
import ast
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

try:
    import context_kv as ops
except ModuleNotFoundError:
    ops = None

class PassiveTests(unittest.TestCase):
    def test_partition_exists(self):
        self.assertIsNotNone(ops, '17-tensor context KV reference is not implemented')

    def test_import_is_passive_and_header_exact(self):
        self.assertNotIn('torch',sys.modules)
        self.assertIsNotNone(ops)
        result=ops.verify_sources()
        self.assertEqual(result['partition_tensors'],17)
        self.assertEqual(result['parameters'],58985600)
        self.assertFalse(result['model_payload_opened'])

    def test_namespace_import_ignores_unrelated_top_level_modules(self):
        code="import sys,types;sys.modules['contract']=types.ModuleType('contract');from scripts.research.dflash2_reference import context_kv;m=context_kv.verify_sources();assert m['partition_tensors']==17;assert 'torch' not in sys.modules"
        result=subprocess.run([sys.executable,'-B','-c',code],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

@unittest.skipIf(ops is None, 'partition not implemented')
class ContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        cls.t=torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.set_grad_enabled(False)
        cls.weights={}
        # Real geometry, deterministic synthetic weights only: <250MiB FP32.
        g=torch.Generator(device='cpu').manual_seed(39811)
        for name,shape in ops.WEIGHT_SHAPES.items():
            cls.weights[name]=(torch.randn(shape,generator=g,device='cpu')*.01 if len(shape)==2 else torch.linspace(.8,1.2,shape[0],device='cpu'))
        cls.x=torch.randn((4,12800),generator=g,device='cpu')*.1
        cls.pos=torch.tensor([8190,8191,8192,8193],dtype=torch.int64,device='cpu')
        cls.owner=ops.OwnerMetadata(b'b'*32,b'm'*32,b't'*32,b'p'*32,1,7)

    def oracle(self,x,pos,weights):
        """Independent per-layer FP64 scalar-equation evaluation (fixed tolerances)."""
        t=self.t
        # Independent FP64 accumulation in feature tiles avoids a full262MiB
        # FP64 FC copy while retaining reference precision, unlike the FP32 MM.
        z=t.zeros((x.shape[0],2560),dtype=t.float64,device='cpu')
        for start in range(0,12800,256):
            z+=x[:,start:start+256].double()@weights['fc.weight'][:,start:start+256].double().T
        z=z/t.sqrt((z*z).mean(-1,keepdim=True)+1e-6)*weights['hidden_norm.weight'].double()
        keys=[];vals=[]
        angles=pos.double()[:,None]*(10000.**(-t.arange(0,128,2,device='cpu',dtype=t.float64)/128))[None,:]
        c,s=angles.cos()[:,None,:],angles.sin()[:,None,:]
        for i in range(5):
            prefix=f'layers.{i}.self_attn.'
            k=(z@weights[prefix+'k_proj.weight'].double().T).reshape(-1,8,128)
            v=(z@weights[prefix+'v_proj.weight'].double().T).reshape(-1,8,128)
            k=k/t.sqrt((k*k).mean(-1,keepdim=True)+1e-6)*weights[prefix+'k_norm.weight'].double()
            a,b=k[...,:64],k[...,64:]
            keys.append(t.cat((a*c-b*s,b*c+a*s),-1));vals.append(v)
        return t.stack(keys).float(),t.stack(vals).float()

    def prepare(self,**kwargs):
        return ops.prepare_context(kwargs.get('x',self.x),kwargs.get('positions',self.pos),kwargs.get('weights',self.weights),owner=kwargs.get('owner',self.owner))

    def extracted(self,filename,classname,names):
        pins={'sglang_layernorm.py':'ba362ab14822415e251f46b369d13aa427d9d4958ac82d6fc2df719af732b758','sglang_rotary_base.py':'bbe1dbf6a7b2a62496c0490fa2ede237010381b8bbffdcbf9e9ef8e270dbf177','sglang_rotary_utils.py':'828a50285218e40c3429d2f4e75b1d051e3a89d831a7ab005e8c2609278aeddc','sglang_dflash.py':ops.SOURCE_SHA256}
        data=ops.SOURCE.with_name(filename).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),pins[filename])
        tree=ast.parse(data)
        body=tree.body if classname is None else next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==classname).body
        selected=[]
        for name in names:
            node=next(n for n in body if isinstance(n,ast.FunctionDef) and n.name==name)
            node.returns=None;node.decorator_list=[]
            for arg in node.args.args:arg.annotation=None
            selected.append(node)
        ns={'torch':self.t,'F':self.t.nn.functional,'can_dflash_slice_qkv_weight':lambda _: (True,None)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=selected,type_ignores=[])),filename,'exec'),ns)
        return ns

    def stage_ordered_source_oracle(self,weights):
        """Unmodified pinned native method bodies, not reference helper calls."""
        from types import SimpleNamespace
        import types
        t=self.t;dtype=weights['fc.weight'].dtype
        native_norm=self.extracted('sglang_layernorm.py','RMSNorm',['forward_native'])['forward_native']
        def norm(weight):
            box=SimpleNamespace(weight=weight,override_orig_dtype=None,hidden_size=weight.shape[0],variance_size_override=None,variance_epsilon=1e-6,cast_x_before_out_mul=False,fp32_residual=False)
            return lambda x:native_norm(box,x)
        class Linear:
            in_features=12800
            def __call__(inner,x):return t.nn.functional.linear(x,weights['fc.weight'])
        model=SimpleNamespace(quantizable=False,fc=Linear(),hidden_norm=norm(weights['hidden_norm.weight']))
        project=self.extracted('sglang_dflash.py','DFlashDraftModel',['project_target_hidden'])['project_target_hidden']
        kv_only=self.extracted('sglang_dflash.py','DFlashAttention',['kv_proj_only'])['kv_proj_only']
        rope_ns=self.extracted('sglang_rotary_base.py','RotaryEmbedding',['_compute_inv_freq','_compute_cos_sin_cache','forward_native'])
        apply=self.extracted('sglang_rotary_utils.py',None,['apply_rotary_emb'])['apply_rotary_emb']
        rope=SimpleNamespace(_force_native=False,rotary_dim=128,head_size=128,base=10000,position_start=0,max_position_embeddings=int(self.pos.max())+1,is_neox_style=True,_apply_rotary_emb_wrapped=apply)
        rope._compute_inv_freq=types.MethodType(rope_ns['_compute_inv_freq'],rope)
        rope.cos_sin_cache=rope_ns['_compute_cos_sin_cache'](rope).to(dtype)
        z=project(model,self.x.to(dtype))
        # Keep the actual QKV geometry while never reading unused Q rows.
        qkv=SimpleNamespace(weight=t.empty((6144,2560),device='cpu',dtype=dtype),bias=None)
        attn=SimpleNamespace(q_size=4096,kv_size=1024,v_scale=None,qkv_proj=qkv)
        keys=[];values=[]
        for layer in range(5):
            p=f'layers.{layer}.self_attn.'
            qkv.weight[4096:5120].copy_(weights[p+'k_proj.weight']);qkv.weight[5120:].copy_(weights[p+'v_proj.weight'])
            k,v=kv_only(attn,z)
            k=norm(weights[p+'k_norm.weight'])(k.reshape(-1,128)).reshape(4,1024)
            _,k=rope_ns['forward_native'](rope,self.pos,t.zeros_like(k),k)
            keys.append(k.reshape(4,8,128));values.append(v.reshape(4,8,128))
        return t.stack(keys),t.stack(values)

    def test_native_bf16_stage_order_exact_source_oracle(self):
        weights={n:w.to(self.t.bfloat16) for n,w in self.weights.items()}
        expected_k,expected_v=self.stage_ordered_source_oracle(weights)
        p=self.prepare(x=self.x.to(self.t.bfloat16),weights=weights)
        self.t.testing.assert_close(p.k,expected_k,rtol=0,atol=0)
        self.t.testing.assert_close(p.v,expected_v,rtol=0,atol=0)

    def test_native_fp32_stage_order_exact_source_oracle(self):
        expected_k,expected_v=self.stage_ordered_source_oracle(self.weights)
        p=self.prepare()
        self.t.testing.assert_close(p.k,expected_k,rtol=0,atol=0)
        self.t.testing.assert_close(p.v,expected_v,rtol=0,atol=0)

    def test_source_oracle_rejects_missing_norm_and_missing_rotation(self):
        weights={n:w.to(self.t.bfloat16) for n,w in self.weights.items()}
        expected,_=self.stage_ordered_source_oracle(weights)
        for name,mutant in [('_rms',lambda x,w,t:x),('_rotary',lambda k,c,s,t:k)]:
            original=getattr(ops,name)
            try:
                setattr(ops,name,mutant)
                wrong=self.prepare(x=self.x.to(self.t.bfloat16),weights=weights)
                with self.assertRaises(AssertionError):
                    self.t.testing.assert_close(wrong.k,expected,rtol=0,atol=0)
            finally:setattr(ops,name,original)

    def test_fp32_real_geometry_and_descriptive_fp64_error(self):
        p=self.prepare();k,v=self.oracle(self.x,self.pos,self.weights)
        self.assertEqual(tuple(p.k.shape),(5,4,8,128))
        self.assertEqual(tuple(p.v.shape),(5,4,8,128))
        # Source uses FP32 position/frequency/trig; FP64 measures mathematical
        # error but is not a replacement for the exact source stage oracle.
        print(json.dumps({'FP32_vs_FP64_descriptive_max_K':(p.k-k).abs().max().item(),'FP32_vs_FP64_descriptive_max_V':(p.v-v).abs().max().item()}),flush=True)
        self.assertEqual(p.k.device.type,'cpu')

    def test_upstream_ast_projection_and_kv_only_methods(self):
        # Execute only two pinned arithmetic methods, no upstream imports/runtime.
        source=ops.SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),ops.SOURCE_SHA256)
        tree=ast.parse(source)
        methods=[]
        for classname,method in [('DFlashDraftModel','project_target_hidden'),('DFlashAttention','kv_proj_only')]:
            cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==classname)
            node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==method)
            node.returns=None
            for arg in node.args.args:arg.annotation=None
            methods.append(node)
        namespace={'torch':self.t,'F':self.t.nn.functional,'can_dflash_slice_qkv_weight':lambda _: (True,None)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=methods,type_ignores=[])),'pinned-context-methods','exec'),namespace)
        class Box:pass
        model=Box();model.quantizable=False
        model.fc=self.t.nn.Linear(12800,2560,bias=False,device='meta')
        model.fc.weight=self.t.nn.Parameter(self.weights['fc.weight'],requires_grad=False)
        model.hidden_norm=lambda x:x*self.t.rsqrt((x.float()*x.float()).mean(-1,keepdim=True)+1e-6)*self.weights['hidden_norm.weight']
        z=namespace['project_target_hidden'](model,self.x)
        attn=Box();attn.q_size=4096;attn.kv_size=1024;attn.v_scale=None;attn.qkv_proj=Box()
        # Reserve actual QKV geometry; unused Q rows are never initialized/read.
        # Only the trained-shape K/V slices participate in this source method.
        attn.qkv_proj.weight=self.t.empty((6144,2560),device='cpu')
        attn.qkv_proj.weight[4096:5120].copy_(self.weights['layers.0.self_attn.k_proj.weight'])
        attn.qkv_proj.weight[5120:].copy_(self.weights['layers.0.self_attn.v_proj.weight'])
        attn.qkv_proj.bias=None
        k,v=namespace['kv_proj_only'](attn,z)
        p=self.prepare()
        self.t.testing.assert_close(p.v[0].reshape(4,1024),v,rtol=2e-5,atol=2e-6)
        self.assertEqual(tuple(k.shape),(4,1024))

    def test_commit_is_verified_inputs_not_bonus(self):
        for accepted in (0,1,3):
            p=self.prepare();before=p.k
            committed=ops.select_committed_inputs(p,[accepted],self.owner)
            self.assertEqual(tuple(committed.k.shape),(5,accepted+1,8,128))
            self.t.testing.assert_close(committed.k,before[:,:accepted+1],rtol=0,atol=0)
            self.assertEqual(committed.positions.tolist(),self.pos[:accepted+1].tolist())
            with self.assertRaises(ValueError):ops.select_committed_inputs(p,[accepted],self.owner)

    def test_invalid_owner_length_and_replay_fail_closed(self):
        p=self.prepare();wrong=ops.OwnerMetadata(b'c'*32,b'm'*32,b't'*32,b'p'*32,1,7)
        for lens,owner in [([-1],self.owner),([4],self.owner),([1,1],self.owner),([True],self.owner),([1],wrong)]:
            with self.assertRaises((TypeError,ValueError)):ops.select_committed_inputs(p,lens,owner)
        ops.select_committed_inputs(p,[1],self.owner)
        for field in ('birth','model','tokenizer','prefix'):
            args=dict(birth=b'b'*32,model=b'm'*32,tokenizer=b't'*32,prefix=b'p'*32,generation=1,round=7);args[field]=b'\0'*32
            with self.assertRaises(ValueError):self.prepare(owner=ops.OwnerMetadata(**args))

    def test_geometry_dtype_nonfinite_and_row_limits(self):
        for x,pos in [(self.x[:,:2560],self.pos),(self.x,self.pos.float()),(self.x,self.pos[:3]),(self.x,self.t.tensor([-1,0,1,2],device='cpu')),(self.x[:0],self.pos[:0]),(self.x[:1].expand(2049,-1),self.pos)]:
            with self.assertRaises((TypeError,ValueError)):self.prepare(x=x,positions=pos)
        weights=dict(self.weights);weights.pop('hidden_norm.weight')
        with self.assertRaises(ValueError):self.prepare(weights=weights)
        weights=dict(self.weights);weights['foreign.weight']=self.x
        with self.assertRaises(ValueError):self.prepare(weights=weights)
        x=self.x.clone();x[0,0]=float('nan')
        with self.assertRaises(ValueError):self.prepare(x=x)

    def test_private_outputs_do_not_alias_inputs_or_public_copies(self):
        p=self.prepare();expected=p.k;public=p.k;public.zero_()
        self.t.testing.assert_close(p.k,expected,rtol=0,atol=0)
        committed=ops.select_committed_inputs(p,[0],self.owner)
        self.assertEqual(committed.positions.tolist(),[8190])

    def test_bf16_mathematical_error_is_descriptive_only(self):
        weights={n:w.to(self.t.bfloat16) for n,w in self.weights.items()}
        p=self.prepare(x=self.x.to(self.t.bfloat16),weights=weights)
        self.assertEqual(p.k.dtype,self.t.bfloat16)
        k,v=self.oracle(self.x.to(self.t.bfloat16),self.pos,weights)
        # This is an error report only, never BF16 qualification by loose tolerance.
        print(json.dumps({'BF16_vs_FP64_descriptive_max_K':(p.k.float()-k).abs().max().item(),'BF16_vs_FP64_descriptive_max_V':(p.v.float()-v).abs().max().item()}),flush=True)
        self.assertTrue(bool(self.t.isfinite(p.k).all()))

    def test_complete_2048_row_window_with_bounded_chunk_workspace(self):
        p=self.prepare(x=self.x[:1].expand(2048,-1),positions=self.t.arange(2048,dtype=self.t.int64,device='cpu'))
        self.assertEqual(tuple(p._k.shape),(5,2048,8,128))
        self.assertEqual(p._k.numel()*p._k.element_size()*2,83886080)
        self.assertEqual(ops.CHUNK_ROWS,64)

    def tearDown(self):
        print(json.dumps({'completed_test':self._testMethodName,'own_peak_bytes':peak_process_bytes()}),flush=True)

def peak_process_bytes():
    """Own test process memory only; no process enumeration/device query."""
    if sys.platform=='win32':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        current=ctypes.windll.kernel32.GetCurrentProcess
        current.restype=wintypes.HANDLE
        query=ctypes.windll.psapi.GetProcessMemoryInfo
        query.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        if not query(current(),ctypes.byref(counters),counters.cb):raise OSError('Own process memory receipt unavailable')
        return counters.PeakWorkingSetSize
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)

if __name__=='__main__':
    if '--run-cpu' not in sys.argv:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PassiveTests))
        raise SystemExit(not result.wasSuccessful())
    else:
        sys.argv.remove('--run-cpu')
        suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(PassiveTests),unittest.defaultTestLoader.loadTestsFromTestCase(ContextTests)])
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        peak=peak_process_bytes()
        print(json.dumps({'CPU_threads':1,'peak_process_working_set_bytes':peak,'budget_bytes':1024**3,'model_payload_opened':False}))
        raise SystemExit(not result.wasSuccessful() or peak>=1024**3)
