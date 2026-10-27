"""Explicit CPU query-backbone checks; synthetic weights, no model/device loading."""
import ast
import hashlib
import subprocess
import sys
import types
import unittest
from pathlib import Path

try:
    import backbone as ops
except ModuleNotFoundError:
    ops = None


class Passive(unittest.TestCase):
    def test_backbone_exists(self):
        self.assertIsNotNone(ops, 'Actual DFlash2 query backbone is not implemented')

    def test_import_does_not_load_torch(self):
        code = "import sys;from scripts.research.dflash2_reference import backbone;assert 'torch' not in sys.modules"
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipIf(ops is None, 'backbone absent')
class Numerical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        cls.t = torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.set_grad_enabled(False)
        g = torch.Generator(device='cpu').manual_seed(8319)
        cls.w = {}
        # One real-dimension layer shared between tests, not a trained checkpoint.
        for name, shape in ops.LAYER_SHAPES.items():
            if name.endswith('base_kernel'):
                v = torch.randn(shape, generator=g, device='cpu') * .01
                v[:, 0] += 1
            elif len(shape) == 1:
                v = torch.linspace(.8, 1.2, shape[0], device='cpu')
            else:
                v = torch.randn(shape, generator=g, device='cpu') * .008
            cls.w[name] = v
        cls.x = torch.randn((4, 2560), generator=g, device='cpu') * .1
        cls.r = torch.randn((4, 2560), generator=g, device='cpu') * .2
        cls.pos = torch.arange(8, 12, device='cpu', dtype=torch.int64)
        cls.cp = torch.arange(8, device='cpu', dtype=torch.int64)
        cls.ck = torch.randn((8, 8, 128), generator=g, device='cpu') * .1
        cls.cv = torch.randn((8, 8, 128), generator=g, device='cpu') * .1

    def extract(self, filename, classname, method):
        data = ops.SOURCES.joinpath(filename).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), ops.SOURCE_PINS[filename])
        tree = ast.parse(data)
        body = tree.body if classname is None else next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == classname).body
        node = next(n for n in body if isinstance(n, ast.FunctionDef) and n.name == method)
        node.decorator_list = []; node.returns = None
        for arg in node.args.args:
            arg.annotation = None
        ns = {'torch': self.t, 'F': self.t.nn.functional}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), filename, 'exec'), ns)
        return ns[method]

    def oracle(self, x, residual, w, pos=None, ck=None, cv=None, cp=None):
        """Run the unchanged upstream decoder method with actual norm/conv bodies.

        Attention is separately checked by attention.py; this oracle checks the
        complete residual/norm/convolution/MLP ordering around it. It does not
        establish CUDA/TRT identity.
        """
        from source_oracle import source_functions
        t = self.t
        native_norm = self.extract('sglang_layernorm.py', 'RMSNorm', 'forward_native')
        def norm(weight):
            obj = types.SimpleNamespace(weight=weight, override_orig_dtype=None, hidden_size=2560,
                variance_size_override=None, variance_epsilon=1e-6, cast_x_before_out_mul=False, fp32_residual=False)
            return lambda *args: native_norm(obj, *args)
        conv_class = source_functions()['DFlashGroupedConv']
        def conv(prefix):
            obj = conv_class(2560, x.shape[0], 2, 16).to(dtype=x.dtype, device='cpu')
            obj.base_kernel.data.copy_(w[prefix + '.base_kernel'])
            obj.kernel_projection.weight.data.copy_(w[prefix + '.kernel_projection.weight'])
            return obj
        mlp_method = self.extract('sglang_dflash.py', 'DFlashMLP', 'forward')
        activation = self.extract('sglang_activation.py', 'SiluAndMul', 'forward_native')
        mlp_obj = types.SimpleNamespace(
            gate_up_proj=lambda a: (t.nn.functional.linear(a, t.cat((w['mlp.gate_proj.weight'], w['mlp.up_proj.weight']))), None),
            act_fn=lambda a: activation(None, a),
            down_proj=lambda a: (t.nn.functional.linear(a, w['mlp.down_proj.weight']), None))
        layer = types.SimpleNamespace(input_layernorm=norm(w['input_layernorm.weight']),
            post_attention_layernorm=norm(w['post_attention_layernorm.weight']),
            attention_conv=conv('attention_conv'), mlp_conv=conv('mlp_conv'),
            self_attn=lambda positions, hidden_states, forward_batch: ops.query_attention(
                hidden_states, positions, self.ck.to(x.dtype) if ck is None else ck,
                self.cv.to(x.dtype) if cv is None else cv, self.cp if cp is None else cp, w),
            mlp=lambda a: mlp_method(mlp_obj, a))
        method = self.extract('sglang_dflash.py', 'DFlashDecoderLayer', 'forward')
        return method(layer, self.pos if pos is None else pos, x, None, residual)

    def call(self, x=None, residual=None, w=None):
        x = self.x if x is None else x
        return ops.layer_forward(x, residual, self.pos, self.ck.to(x.dtype), self.cv.to(x.dtype), self.cp,
                                 self.w if w is None else w, block_size=4)

    def test_first_and_later_layer_match_upstream_residual_order(self):
        for dtype in (self.t.float32, self.t.bfloat16):
            w = {n: v.to(dtype) for n, v in self.w.items()}
            x = self.x.to(dtype)
            for residual in (None, self.r.to(dtype)):
                expected = self.oracle(x, residual, w)
                actual = self.call(x, residual, w)
                for a, e in zip(actual, expected):
                    self.t.testing.assert_close(a, e, rtol=0, atol=0)

    def test_real_attention_matches_upstream_projection_call_order(self):
        # The upstream method executes QKV once, then norm/RoPE, then output
        # projection. Different learned norm weights make missing norms visible.
        method = self.extract('sglang_dflash.py', 'DFlashAttention', 'forward')
        for dtype in (self.t.float32, self.t.bfloat16):
            w = {n: v.to(dtype) for n, v in self.w.items()}
            x = self.x.to(dtype)
            ns = method.__globals__
            ns['_is_npu'] = False
            ns['apply_qk_norm'] = lambda q,k,qn,kn,head: (qn(q.reshape(-1,head)).reshape_as(q), kn(k.reshape(-1,head)).reshape_as(k))
            native_norm = self.extract('sglang_layernorm.py', 'RMSNorm', 'forward_native')
            def norm(name):
                obj=types.SimpleNamespace(weight=w[name], override_orig_dtype=None, hidden_size=128,
                    variance_size_override=None, variance_epsilon=1e-6, cast_x_before_out_mul=False, fp32_residual=False)
                return lambda a:native_norm(obj,a)
            from attention import attend
            o=types.SimpleNamespace(qkv_proj=lambda a:(self.t.nn.functional.linear(a,self.t.cat([w['self_attn.'+s+'_proj.weight'] for s in ('q','k','v')])),None),
                use_table_qk_norm_rope=False, q_size=4096, kv_size=1024, head_dim=128,
                q_norm=norm('self_attn.q_norm.weight'), k_norm=norm('self_attn.k_norm.weight'),
                rotary_emb=lambda p,q,k:(ops.rotary(q.reshape(-1,32,128),p).flatten(-2),ops.rotary(k.reshape(-1,8,128),p).flatten(-2)),
                v_scale=None, attention_sink_bias=None,
                attn=lambda q,k,v,f:attend(q.reshape(-1,32,128),k.reshape(-1,8,128),v.reshape(-1,8,128),self.ck.to(dtype),self.cv.to(dtype),query_positions=self.pos,context_positions=self.cp).flatten(-2),
                apply_attention_output=lambda a,h:a,
                o_proj=lambda a:(self.t.nn.functional.linear(a,w['self_attn.o_proj.weight']),None))
            expected=method(o,self.pos,x,None)
            actual=ops.query_attention(x,self.pos,self.ck.to(dtype),self.cv.to(dtype),self.cp,w)
            self.t.testing.assert_close(actual,expected,rtol=0,atol=0)

    def test_rotary_matches_independent_source_for_Q_K_and_long_positions(self):
        t=self.t
        native=self.extract('sglang_rotary_base.py','RotaryEmbedding','forward_native')
        inv=self.extract('sglang_rotary_base.py','RotaryEmbedding','_compute_inv_freq')
        cache=self.extract('sglang_rotary_base.py','RotaryEmbedding','_compute_cos_sin_cache')
        apply=self.extract('sglang_rotary_utils.py',None,'apply_rotary_emb')
        positions=t.arange(260000,260004,device='cpu',dtype=t.int64)
        box=types.SimpleNamespace(_force_native=False,rotary_dim=128,head_size=128,base=10000,
            position_start=0,max_position_embeddings=260004,is_neox_style=True,_apply_rotary_emb_wrapped=apply)
        box._compute_inv_freq=types.MethodType(inv,box)
        full_cache=cache(box)
        for dtype in (t.float32,t.bfloat16):
            box.cos_sin_cache=full_cache.to(dtype)
            for heads in (8,32):
                x=(t.arange(4*heads*128,device='cpu',dtype=t.float32).reshape(4,heads,128).sin()*.1).to(dtype)
                expected,_=native(box,positions,x.flatten(-2),x.flatten(-2))
                actual=ops.rotary(x,positions)
                t.testing.assert_close(actual.flatten(-2),expected,rtol=0,atol=0)

    def test_inputs_and_committed_context_stay_unchanged(self):
        before=[a.clone() for a in (self.x,self.r,self.ck,self.cv)]
        y,r=self.call(residual=self.r)
        for actual,expected in zip((self.x,self.r,self.ck,self.cv),before):
            self.t.testing.assert_close(actual,expected,rtol=0,atol=0)
        self.assertNotEqual(y.data_ptr(),self.x.data_ptr())
        self.assertNotEqual(r.data_ptr(),self.r.data_ptr())

    def test_invalid_weight_dtype_and_missing_tensor_are_rejected(self):
        bad=dict(self.w);del bad['mlp.up_proj.weight']
        with self.assertRaises(ValueError): self.call(w=bad)
        bad=dict(self.w);bad['self_attn.q_norm.weight']=bad['self_attn.q_norm.weight'].to(self.t.bfloat16)
        with self.assertRaises((ValueError,TypeError)):self.call(w=bad)

    def test_invalid_positions_are_rejected_before_projection(self):
        for positions in (self.pos[:0], self.pos[:3], self.pos[:,None], self.pos.float()):
            with self.assertRaises((ValueError,TypeError)):
                ops.layer_forward(self.x,None,positions,self.ck,self.cv,self.cp,self.w,block_size=4)

    def test_empty_prefix_matches_upstream_with_private_query_kv(self):
        t=self.t
        for dtype in (t.float32,t.bfloat16):
            x=self.x.to(dtype);w={n:v.to(dtype) for n,v in self.w.items()}
            positions=t.arange(4,device='cpu',dtype=t.int64)
            empty=t.empty((0,8,128),device='cpu',dtype=dtype)
            cp=t.empty((0,),device='cpu',dtype=t.int64)
            actual=ops.layer_forward(x,None,positions,empty,empty,cp,w,block_size=4)
            expected=self.oracle(x,None,w,pos=positions,ck=empty,cv=empty,cp=cp)
            for a,e in zip(actual,expected):t.testing.assert_close(a,e,rtol=0,atol=0)

    def test_five_layer_block_and_final_norm_match_source_method(self):
        t=self.t
        for block,dtype in ((4,t.float32),(8,t.float32),(4,t.bfloat16),(8,t.bfloat16)):
            layer_weights={n:v.to(dtype) for n,v in self.w.items()}
            x=self.x.repeat(block//4,1).to(dtype)
            pos=t.arange(8,8+block,device='cpu',dtype=t.int64)
            # Retain full trained geometry but share synthetic layer storage.
            # Different layer norm vectors detect a wrong layer-index mapping.
            w={f'layers.{i}.{n}':v for i in range(5) for n,v in layer_weights.items()}
            for i in range(5):w[f'layers.{i}.input_layernorm.weight']=(self.w['input_layernorm.weight']*(1+i*.03)).to(dtype)
            w['norm.weight']=t.linspace(.6,1.3,2560,device='cpu').to(dtype)
            ck=self.ck.to(dtype).unsqueeze(0).expand(5,-1,-1,-1)
            cv=self.cv.to(dtype).unsqueeze(0).expand(5,-1,-1,-1)
            actual=ops.query_block(x,pos,ck,cv,self.cp,w,block_size=block)
            hidden=x;residual=None
            for i in range(5):
                layer={n:w[f'layers.{i}.{n}'] for n in ops.LAYER_SHAPES}
                hidden,residual=self.oracle(hidden,residual,layer,pos=pos,ck=ck[i],cv=cv[i])
            native_norm=self.extract('sglang_layernorm.py','RMSNorm','forward_native')
            norm=types.SimpleNamespace(weight=w['norm.weight'],override_orig_dtype=None,hidden_size=2560,
                variance_size_override=None,variance_epsilon=1e-6,cast_x_before_out_mul=False,fp32_residual=False)
            expected,_=native_norm(norm,hidden,residual)
            t.testing.assert_close(actual,expected,rtol=0,atol=0)


if __name__=='__main__':
    if '--run-cpu' not in sys.argv:
        print('Passive default; --run-cpu explicitly executes synthetic CPU tests.')
    else:
        sys.argv.remove('--run-cpu')
        unittest.main(verbosity=2)
