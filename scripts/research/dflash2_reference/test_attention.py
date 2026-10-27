"""Explicit CPU tests for the author's expanded-decode mask/layout and SDPA core.

SGLang oracle excerpts below are Apache-2.0; sources/SGLANG_LICENSE applies.
They are copied without arithmetic edits from the pinned TorchNative backend.
The copied source is parsed/compiled only during explicit --run-cpu tests.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
if __package__:
    from . import attention as ops
else:
    import attention as ops

# Original full file SHA5da07edadf56f4f4e4b8319ed48216b5a8ddb989224d3e95011b76800bf9926b.
# https://github.com/sgl-project/sglang/blob/3c560089e1818a5217a73f2168273485a5350341/python/sglang/srt/layers/attention/torch_native_backend.py
ORACLE_SOURCE = 'def _make_sliding_window_mask(\n    *,\n    q_len: int,\n    kv_len: int,\n    sliding_window_size: int,\n    device: torch.device,\n    query_offset: int = 0,\n) -> torch.Tensor:\n    q_pos = torch.arange(\n        query_offset, query_offset + q_len, device=device\n    ).unsqueeze(1)\n    k_pos = torch.arange(kv_len, device=device).unsqueeze(0)\n    return (k_pos <= q_pos) & (k_pos >= q_pos - sliding_window_size)\n\ndef _run_sdpa_forward_decode(\n    self,\n    query: torch.Tensor,\n    output: torch.Tensor,\n    k_cache: torch.Tensor,\n    v_cache: torch.Tensor,\n    req_to_token: torch.Tensor,\n    req_pool_indices: torch.Tensor,\n    seq_lens: torch.Tensor,\n    encoder_lens: Optional[torch.Tensor] = None,\n    scaling=None,\n    enable_gqa=False,\n    causal=False,\n    is_cross_attn=False,\n    sliding_window_size: Optional[int] = None,\n):\n    """Run the decode forward by using torch native sdpa op.\n\n    Args:\n        query: [num_tokens, num_heads, head_size]\n        output: [num_tokens, num_heads, head_size]\n        k_cache: [max_total_num_tokens, num_heads, head_size]\n        v_cache: [max_total_num_tokens, num_heads, head_size]\n        req_to_token: [max_num_reqs, max_context_len]\n        req_pool_indices: [num_seqs]\n        seq_lens: [num_seqs]\n        encoder_lens: [num_seqs] or None\n        scaling: float or None\n        enable_gqa: bool\n        causal: bool\n        is_cross_attn: bool\n\n    Returns:\n        output: [num_tokens, num_heads, head_size]\n    """\n\n    # [num_tokens, num_heads, head_size] -> [num_heads, num_tokens, head_size]\n    query = query.movedim(0, query.dim() - 2)\n\n    start_q, start_kv = 0, 0\n    for seq_idx in range(seq_lens.shape[0]):\n        # TODO: this loop process a sequence per iter, this is inefficient.\n        # Need optimize the performance later.\n\n        seq_len_q = 1\n        seq_len_kv = seq_lens[seq_idx]\n        end_q = start_q + seq_len_q\n        if encoder_lens is not None:\n            if is_cross_attn:\n                start_kv = 0\n                end_kv = encoder_lens[seq_idx]\n            else:\n                start_kv = encoder_lens[seq_idx]\n                end_kv = start_kv + seq_len_kv\n        else:\n            start_kv = 0\n            end_kv = start_kv + seq_len_kv\n\n        per_req_query = query[:, start_q:end_q, :]\n\n        # get key and value from cache. per_req_tokens contains the kv cache\n        # index for each token in the sequence.\n\n        req_pool_idx = req_pool_indices[seq_idx]\n        per_req_tokens = req_to_token[req_pool_idx, start_kv:end_kv]\n        per_req_key = k_cache[per_req_tokens].movedim(0, query.dim() - 2)\n        per_req_value = v_cache[per_req_tokens].movedim(0, query.dim() - 2)\n\n        if not (per_req_query.dtype == per_req_key.dtype == per_req_value.dtype):\n            # scaled_dot_product_attention() expects query, key, and value to have the same dtype\n            per_req_key = per_req_key.to(per_req_query.dtype)\n            per_req_value = per_req_value.to(per_req_query.dtype)\n\n        attn_mask = None\n        is_causal = causal\n        if sliding_window_size is not None and sliding_window_size > -1:\n            attn_mask = self._make_sliding_window_mask(\n                q_len=seq_len_q,\n                kv_len=seq_len_kv,\n                sliding_window_size=sliding_window_size,\n                device=per_req_query.device,\n                query_offset=seq_len_kv - seq_len_q,\n            )\n            is_causal = False\n\n        per_req_out = (\n            scaled_dot_product_attention(\n                per_req_query.unsqueeze(0),\n                per_req_key.unsqueeze(0),\n                per_req_value.unsqueeze(0),\n                attn_mask=attn_mask,\n                enable_gqa=enable_gqa,\n                scale=scaling,\n                is_causal=is_causal,\n            )\n            .squeeze(0)\n            .movedim(query.dim() - 2, 0)\n        )\n        output[start_q:end_q, :, :] = per_req_out\n        start_q, start_kv = end_q, end_kv\n\n    return output'
ORACLE_SHA256 = '7b59386367b85d516748de3feaf1311c6385da82fd1960c3795287c1e47f6256'

class PassiveTests(unittest.TestCase):
    def test_namespace_import_is_passive(self):
        code='import sys;from scripts.research.dflash2_reference import attention;assert "torch" not in sys.modules'
        run=subprocess.run([sys.executable,'-B','-c',code],cwd=Path(__file__).resolve().parents[3],capture_output=True,text=True,timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)

class AttentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        cls.t=torch;torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.set_grad_enabled(False)
        tree=ast.parse(ORACLE_SOURCE)
        if hashlib.sha256(ORACLE_SOURCE.encode()).hexdigest()!=ORACLE_SHA256:
            raise AssertionError('Pinned oracle source differs')
        ns={'torch':torch,'scaled_dot_product_attention':torch.nn.functional.scaled_dot_product_attention}
        body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*tree.body]
        exec(compile(ast.fix_missing_locations(ast.Module(body=body,type_ignores=[])),'pinned-native-SDPA','exec'),ns)
        cls.native=staticmethod(ns['_run_sdpa_forward_decode']);cls.source_mask=staticmethod(ns['_make_sliding_window_mask'])
        cls.generator=torch.Generator(device='cpu').manual_seed(27410)

    def same(self,x,y):
        self.assertEqual(x.device.type,'cpu');self.assertEqual(x.dtype,y.dtype)
        self.t.testing.assert_close(x,y,rtol=0,atol=0)

    def rand(self,shape,dtype,strided=False):
        if strided:
            x=self.t.randn((*shape[:-1],shape[-1]*2),generator=self.generator,device='cpu').to(dtype)[...,::2]
            self.assertFalse(x.is_contiguous());return x*.1
        return (self.t.randn(shape,generator=self.generator,device='cpu')*.1).to(dtype)

    def fixture(self,dtype,block=4,prefix=9,retained=None):
        retained=min(prefix,2048) if retained is None else retained
        q=self.rand((block,32,128),dtype)
        qk=self.rand((block,8,128),dtype);qv=self.rand((block,8,128),dtype)
        ck=self.rand((retained,8,128),dtype);cv=self.rand((retained,8,128),dtype)
        qp=self.t.arange(prefix,prefix+block,dtype=self.t.int64,device='cpu')
        cp=self.t.arange(prefix-retained,prefix,dtype=self.t.int64,device='cpu')
        return (q,qk,qv,ck,cv),dict(query_positions=qp,context_positions=cp)

    def oracle(self,args,positions):
        q,qk,qv,ck,cv=args;k=self.t.cat((ck,qk));v=self.t.cat((cv,qv));block=q.shape[0];n=k.shape[0]
        output=self.t.empty_like(q)
        box=SimpleNamespace(_make_sliding_window_mask=self.source_mask)
        self.native(box,q,output,k,v,self.t.arange(n,dtype=self.t.int64,device='cpu')[None,:],
                    self.t.zeros(block,dtype=self.t.int64,device='cpu'),
                    self.t.full((block,),n,dtype=self.t.int64,device='cpu'),
                    scaling=128**-.5,enable_gqa=True,causal=False,sliding_window_size=2047)
        return output

    def test_layout_is_anchor_plus_masks_at_real_absolute_positions(self):
        for block in (4,8):
            layout=ops.draft_block_layout(8192,block,723)
            self.assertEqual(layout.ids,(723,)+(248077,)*(block-1))
            self.assertEqual(layout.positions,tuple(range(8192,8192+block)))

    def test_mask_uses_common_block_end_not_per_query_causality(self):
        for block in (4,8):
            prefix=4096;qp=self.t.arange(prefix,prefix+block,dtype=self.t.int64,device='cpu')
            kp=self.t.arange(prefix-2048,prefix+block,dtype=self.t.int64,device='cpu')
            actual=ops.author_allow_mask(qp,kp)
            expected=self.source_mask(q_len=1,kv_len=len(kp),sliding_window_size=2047,device='cpu',query_offset=len(kp)-1).expand(block,-1)
            self.same(actual,expected)
            self.assertTrue(bool(actual[:,-1].all())) # future query K/V visible to query0
            self.assertFalse(bool(actual[:,block-1].any()))
            self.assertTrue(bool(actual[:,block].all()))
            self.assertEqual(actual.sum(-1).tolist(),[2048]*block)

    def test_short_context_mask_is_bidirectional(self):
        for prefix in (0,5):
            block=4;qp=self.t.arange(prefix,prefix+block,dtype=self.t.int64,device='cpu');kp=self.t.arange(prefix+block,dtype=self.t.int64,device='cpu')
            self.same(ops.author_allow_mask(qp,kp),self.t.ones((block,len(kp)),dtype=self.t.bool,device='cpu'))

    def test_source_native_core_exact_real_GQA_dimensions(self):
        for dtype in (self.t.float32,self.t.bfloat16):
            for block in (4,8):
                args,pos=self.fixture(dtype,block)
                self.same(ops.attend(*args,**pos),self.oracle(args,pos))

    def test_empty_context_and_future_query_values_are_visible(self):
        block=4;dtype=self.t.bfloat16
        q=self.t.zeros((block,32,128),dtype=dtype,device='cpu');k=self.t.zeros((block,8,128),dtype=dtype,device='cpu');v=self.t.zeros_like(k);v[-1]=4
        empty=self.t.empty((0,8,128),dtype=dtype,device='cpu')
        actual=ops.attend(q,k,v,empty,empty,query_positions=self.t.arange(block,dtype=self.t.int64,device='cpu'),context_positions=self.t.empty(0,dtype=self.t.int64,device='cpu'))
        self.same(actual,self.t.ones_like(q))

    def test_complete_window_exact_source_and_inputs_unchanged(self):
        args,pos=self.fixture(self.t.float32,4,prefix=8192)
        before=[x.clone() for x in args]
        self.same(ops.attend(*args,**pos),self.oracle(args,pos))
        for x,y in zip(args,before):self.same(x,y)

    def test_noncontiguous_inputs_follow_source(self):
        args,pos=self.fixture(self.t.bfloat16,8)
        strided=[]
        for x in args:
            wider=self.t.empty((*x.shape[:-1],256),dtype=x.dtype,device='cpu');wider[...,::2].copy_(x);strided.append(wider[...,::2])
        self.same(ops.attend(*strided,**pos),self.oracle(strided,pos))

    def test_rejects_missing_context_wrong_positions_shapes_dtypes_and_nonfinite(self):
        args,pos=self.fixture(self.t.float32)
        cases=[]
        bad=list(args);bad[0]=bad[0][:,:31];cases.append((bad,pos))
        bad=list(args);bad[1]=bad[1].to(self.t.bfloat16);cases.append((bad,pos))
        bad=list(args);bad[3]=bad[3][1:];bad[4]=bad[4][1:];badpos=dict(pos,context_positions=pos['context_positions'][1:]);cases.append((bad,badpos))
        badpos=dict(pos,query_positions=pos['query_positions']+1);cases.append((args,badpos))
        badpos=dict(pos,query_positions=pos['query_positions'].float());cases.append((args,badpos))
        bad=list(args);bad[0]=bad[0].clone();bad[0][0,0,0]=float('nan');cases.append((bad,pos))
        for bad,where in cases:
            with self.assertRaises((ValueError,TypeError)):ops.attend(*bad,**where)
        for values in [(-1,4,7),(1,3,7),(1,4,248077),(262143,4,7),(True,4,7)]:
            with self.assertRaises((ValueError,TypeError)):ops.draft_block_layout(*values)

if __name__=='__main__':
    if '--run-cpu' not in sys.argv:
        print(json.dumps(dict(prepared=True,executed=False,provider_calls=0,CPU_only=True,threads=1)))
    else:
        sys.argv.remove('--run-cpu');unittest.main(verbosity=2)
