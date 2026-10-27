"""Independent pinned original-source Torch-native query oracle, CPU or GPU.

SGLang3c560089e1818a5217a73f2168273485a5350341, Apache-2.0;
../dflash2_reference/sources/SGLANG_LICENSE. Import is stdlib/passive. Explicit
setup hashes original files and compiles selected original AST methods. Only
torch.compile decorators and mark_static hints are stripped; signatures/body
arithmetic remain unchanged. Future annotations avoid importing SGLang types.

Linear/tuple/module dependencies are same-device Torch adapters; QK norm uses
original native RMSNorm through reshape adapters. Attention realizes the author
common-block-end left2047 window with independent rowwise SDPA. This diagnoses
same-device Torch primitive/order differences; it does NOT emulate fused
SGLang/Triton/TRT kernels, force a GPU backend or establish trained quality.
No model loader, CPU-only validators, device discovery, settings or publication.
Caller owns immutable same-device tensors and invokes all GPU work explicitly.

Explicit use: o=SourceGPUOracle.setup(device='cuda:0'); body=o.backbone(weights)
then body.forward(embeddings,context_key,context_value,prefix_tokens=p,trace=True).
Weights are unpacked layers0..4 plus norm.weight; context is[5,N,8,128].
body.last_trace maps layer indices to native-stage tensors and final_norm to the
final output; no trace tensor is copied to CPU. Query embeddings/context arrive
already prepared: this oracle does not cover embedding or context preparation.
"""
import ast
import copy
import hashlib
from pathlib import Path
import types

SOURCES=Path(__file__).resolve().parents[1]/'dflash2_reference'/'sources'
SOURCE_REVISION='3c560089e1818a5217a73f2168273485a5350341'
SOURCE_PINS={
 'sglang_dflash.py':'b7b541368cbbb072a679d08ba5bf0f952f4a43f02b6c078562b2ea7a9ddfd01b',
 'sglang_layernorm.py':'ba362ab14822415e251f46b369d13aa427d9d4958ac82d6fc2df719af732b758',
 'sglang_activation.py':'5725a11725ded609484d846d05430235fdf2a7767307d7bdd1686821ae26cdd8',
 'sglang_rotary_base.py':'bbe1dbf6a7b2a62496c0490fa2ede237010381b8bbffdcbf9e9ef8e270dbf177',
 'sglang_rotary_utils.py':'828a50285218e40c3429d2f4e75b1d051e3a89d831a7ab005e8c2609278aeddc'}
LAYER_SHAPES={
 'input_layernorm.weight':(2560,),'post_attention_layernorm.weight':(2560,),
 'self_attn.q_proj.weight':(4096,2560),'self_attn.k_proj.weight':(1024,2560),
 'self_attn.v_proj.weight':(1024,2560),'self_attn.o_proj.weight':(2560,4096),
 'self_attn.q_norm.weight':(128,),'self_attn.k_norm.weight':(128,),
 'mlp.gate_proj.weight':(7680,2560),'mlp.up_proj.weight':(7680,2560),
 'mlp.down_proj.weight':(2560,7680)}
for _prefix in ('attention_conv','mlp_conv'):
    LAYER_SHAPES[_prefix+'.base_kernel']=(2,2,2560)
    LAYER_SHAPES[_prefix+'.kernel_projection.weight']=(640,2560)


class _HintsOnly(ast.NodeTransformer):
    def visit_FunctionDef(self,node):
        for decorator in node.decorator_list:
            if not isinstance(decorator,ast.Call) or ast.unparse(decorator.func)!='torch.compile':
                raise ValueError('Unexpected decorator in pinned oracle selection')
        node.decorator_list=[]
        return self.generic_visit(node)
    def visit_Expr(self,node):
        if isinstance(node.value,ast.Call) and ast.unparse(node.value.func)=='torch._dynamo.mark_static':
            return ast.copy_location(ast.Pass(),node)
        return self.generic_visit(node)


def _sources():
    result={}
    for name,pin in SOURCE_PINS.items():
        data=(SOURCES/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=pin:raise ValueError('Pinned source differs: '+name)
        result[name]=ast.parse(data,filename=str(SOURCES/name))
    return result


class SourceGPUOracle:
    @classmethod
    def setup(cls,*,device,max_positions=262144):
        """Explicit source setup/cache allocation on exactly caller-selected device.

        No device enumeration/availability checks. CPU fixtures may use a small
        cache; actual query positions must fit it. Cache retains source FP32.
        """
        trees=_sources()
        import torch
        chosen=torch.device(device)
        if chosen.type not in ('cpu','cuda') or (chosen.type=='cuda' and chosen.index is None):
            raise ValueError('Explicit cpu or indexed cuda:N required')
        if type(max_positions) is not int or not 8<=max_positions<=262144:
            raise ValueError('Explicit source cache capacity8..262144 required')
        obj=cls();obj.t=torch;obj.device=chosen;obj.max_positions=max_positions
        ns={'torch':torch,'F':torch.nn.functional,'nn':torch.nn,'_is_npu':False}
        def qk(q,k,qn,kn,head):
            return qn(q.reshape(-1,head)).reshape_as(q),kn(k.reshape(-1,head)).reshape_as(k)
        ns['apply_qk_norm']=qk
        obj.extracted={}
        def extract(file,owner,name):
            body=trees[file].body
            if owner is not None:body=next(n for n in body if isinstance(n,ast.ClassDef) and n.name==owner).body
            node=copy.deepcopy(next(n for n in body if isinstance(n,ast.FunctionDef) and n.name==name))
            node=_HintsOnly().visit(node)
            future=ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)
            module=ast.fix_missing_locations(ast.Module(body=[future,node],type_ignores=[]))
            exec(compile(module,str(SOURCES/file),'exec'),ns)
            value=ns[name];obj.extracted[(owner+'.' if owner else '')+name]=value;return value
        extract('sglang_dflash.py',None,'_grouped_conv')
        obj.conv={name:extract('sglang_dflash.py','DFlashGroupedConv',name) for name in ('_convolve','prepare','finish')}
        obj.decoder=extract('sglang_dflash.py','DFlashDecoderLayer','forward')
        obj.attention=extract('sglang_dflash.py','DFlashAttention','forward')
        obj.attention_output=extract('sglang_dflash.py','DFlashAttention','apply_attention_output')
        obj.mlp=extract('sglang_dflash.py','DFlashMLP','forward')
        obj.activation=extract('sglang_activation.py','SiluAndMul','forward_native')
        obj.native_norm=extract('sglang_layernorm.py','RMSNorm','forward_native')
        apply_rotary=extract('sglang_rotary_utils.py',None,'apply_rotary_emb')
        inv=extract('sglang_rotary_base.py','RotaryEmbedding','_compute_inv_freq')
        cache=extract('sglang_rotary_base.py','RotaryEmbedding','_compute_cos_sin_cache')
        obj.native_rotary=extract('sglang_rotary_base.py','RotaryEmbedding','forward_native')
        rope=types.SimpleNamespace(rotary_dim=128,head_size=128,base=10000.,position_start=0,
             max_position_embeddings=max_positions,_force_native=False,is_neox_style=True,
             _apply_rotary_emb_wrapped=apply_rotary)
        rope._compute_inv_freq=types.MethodType(inv,rope)
        # Original constructors rely on a device context for device=None aranges.
        # Local context, not set_default_device or a process-wide setting change.
        with torch.inference_mode(),torch.device(chosen):
            rope.cos_sin_cache=cache(rope)
        obj.rope=rope
        return obj

    def norm(self,weight,*,record=None,name='norm'):
        obj=types.SimpleNamespace(weight=weight,hidden_size=weight.shape[0],override_orig_dtype=None,
             variance_size_override=None,variance_epsilon=1e-6,cast_x_before_out_mul=False,fp32_residual=False)
        def call(*args):
            result=self.native_norm(obj,*args)
            if record is not None:record(name,result)
            return result
        return call

    def rotary(self,positions,q,k):
        return self.native_rotary(self.rope,positions,q,k)

    def attend(self,q,k,v,context_key,context_value,*,prefix_tokens):
        """Independent rowwise author-mask adapter, no persistent cache writes."""
        t=self.t;rows=q.shape[0];n=context_key.shape[0]
        if type(prefix_tokens) is not int or rows not in (4,8) or not 0<=n<=min(2048,prefix_tokens):
            raise ValueError('Block4/8 and bounded retained history required')
        end=prefix_tokens+rows;left=max(0,end-2048)
        if prefix_tokens-n>left:raise ValueError('Visible author history missing')
        keys=t.cat((context_key,k.reshape(rows,8,128)),dim=0).transpose(0,1)
        values=t.cat((context_value,v.reshape(rows,8,128)),dim=0).transpose(0,1)
        query=q.reshape(rows,32,128).transpose(0,1)
        positions=t.arange(prefix_tokens-n,end,device=q.device,dtype=t.int64)
        mask=((positions>=left)&(positions<end)).view(1,-1)
        output=[]
        for row in range(rows):
            value=t.nn.functional.scaled_dot_product_attention(query[:,row:row+1].unsqueeze(0),
                keys.unsqueeze(0),values.unsqueeze(0),attn_mask=mask,
                dropout_p=0.,is_causal=False,scale=128**-.5,enable_gqa=True)
            output.append(value[0,:,0].reshape(1,4096))
        return t.cat(output,dim=0)

    def layer(self,weights):return SourceLayer(self,weights)

    def backbone(self,weights):
        shapes={f'layers.{i}.{name}':shape for i in range(5) for name,shape in LAYER_SHAPES.items()}
        shapes['norm.weight']=(2560,)
        self._weights(weights,shapes)
        return SourceBackbone(self,[self.layer({name:weights[f'layers.{i}.{name}'] for name in LAYER_SHAPES}) for i in range(5)],weights['norm.weight'])

    def _weights(self,weights,shapes):
        if type(weights) is not dict or set(weights)!=set(shapes):raise ValueError('Exact same-device source weights required')
        dtype=next(iter(weights.values())).dtype
        for name,shape in shapes.items():self._tensor(weights[name],shape,dtype,name)
        return dtype

    def _tensor(self,x,shape,dtype,name):
        if not isinstance(x,self.t.Tensor) or x.device!=self.device or x.dtype!=dtype or dtype not in (self.t.float32,self.t.bfloat16) or tuple(x.shape)!=tuple(shape):
            raise ValueError('Caller same-device tensor metadata differs: '+name)


class SourceLayer:
    """Original method bodies around independently bound same-device adapters."""
    def __init__(self,oracle,weights):
        self.o=oracle;self.dtype=oracle._weights(weights,LAYER_SHAPES);self.w=weights
        self.last_trace={};t=oracle.t
        with t.inference_mode():
            self.qkv=t.cat([weights['self_attn.'+p+'_proj.weight'] for p in ('q','k','v')])
            self.gate_up=t.cat([weights['mlp.'+p+'_proj.weight'] for p in ('gate','up')])

    def forward(self,hidden,residual,context_key,context_value,*,prefix_tokens,trace=False):
        o=self.o;t=o.t;rows=hidden.shape[0]
        if rows not in (4,8) or type(prefix_tokens) is not int or not 0<=prefix_tokens<=o.max_positions-rows:
            raise ValueError('Query block/position exceeds explicit source cache')
        o._tensor(hidden,(rows,2560),self.dtype,'hidden')
        if residual is not None:o._tensor(residual,hidden.shape,self.dtype,'residual')
        if context_key.ndim!=3:raise ValueError('Context rank differs')
        o._tensor(context_key,(context_key.shape[0],8,128),self.dtype,'context key')
        o._tensor(context_value,context_key.shape,self.dtype,'context value')
        self.last_trace={}
        def record(name,value):
            if trace:self.last_trace[name]=value
        def linear(weight,name,tuple_output):
            def call(x):
                y=t.nn.functional.linear(x,weight);record(name,y)
                return (y,None) if tuple_output else y
            return call
        def conv(prefix):
            obj=types.SimpleNamespace(block_size=rows,taps=2,group_size=16,num_groups=160,
                base_kernel=self.w[prefix+'.base_kernel'],
                kernel_projection=linear(self.w[prefix+'.kernel_projection.weight'],prefix+'.projection',False))
            for name,fn in o.conv.items():setattr(obj,name,types.MethodType(fn,obj))
            original=obj._convolve
            def traced_convolve(hidden,delta,side):
                out=original(hidden,delta,side)
                record(prefix+('.prepare' if side==0 else '.finish'),out)
                return out
            obj._convolve=traced_convolve
            return obj
        def norm(name):return o.norm(self.w[name+'.weight'],record=record,name=name)
        attention=types.SimpleNamespace(qkv_proj=linear(self.qkv,'qkv',True),
            q_size=4096,kv_size=1024,head_dim=128,use_table_qk_norm_rope=False,
            q_norm=norm('self_attn.q_norm'),k_norm=norm('self_attn.k_norm'),rotary_emb=o.rotary,
            v_scale=None,attention_sink_bias=None,o_proj=linear(self.w['self_attn.o_proj.weight'],'o_proj',True))
        def sdpa(q,k,v,forward_batch):
            record('rotated_q',q);record('rotated_k',k);record('query_v',v)
            out=o.attend(q,k,v,context_key,context_value,prefix_tokens=prefix_tokens)
            record('sdpa',out);return out
        attention.attn=sdpa
        attention.apply_attention_output=types.MethodType(o.attention_output,attention)
        mlp=types.SimpleNamespace(gate_up_proj=linear(self.gate_up,'gate_up',True),
            act_fn=lambda x:o.activation(None,x),down_proj=linear(self.w['mlp.down_proj.weight'],'down_proj',True))
        layer=types.SimpleNamespace(input_layernorm=norm('input_layernorm'),post_attention_layernorm=norm('post_attention_layernorm'),
            attention_conv=conv('attention_conv'),mlp_conv=conv('mlp_conv'),
            self_attn=lambda **kw:o.attention(attention,**kw),mlp=lambda x:o.mlp(mlp,x))
        with t.inference_mode():
            positions=t.arange(prefix_tokens,prefix_tokens+rows,device=o.device,dtype=t.int64)
            result=o.decoder(layer,positions,hidden,None,residual)
            record('output',result)
            return result


class SourceBackbone:
    def __init__(self,oracle,layers,final_norm):self.o=oracle;self.layers=tuple(layers);self.final_norm=final_norm;self.last_trace={}
    def forward(self,embeddings,context_key,context_value,*,prefix_tokens,trace=False):
        n=context_key.shape[1]
        self.o._tensor(context_key,(5,n,8,128),self.final_norm.dtype,'five context keys')
        self.o._tensor(context_value,context_key.shape,self.final_norm.dtype,'five context values')
        hidden=embeddings;residual=None;self.last_trace={}
        for i,layer in enumerate(self.layers):
            hidden,residual=layer.forward(hidden,residual,context_key[i],context_value[i],prefix_tokens=prefix_tokens,trace=trace)
            if trace:self.last_trace[i]=layer.last_trace
        with self.o.t.inference_mode():
            result,_=self.o.norm(self.final_norm)(hidden,residual)
            if trace:self.last_trace['final_norm']=result
            return result
