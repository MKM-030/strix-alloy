"""DFlash2 five-layer query body, explicit CPU native/sequential reference.

SGLang@3c560089e1818a5217a73f2168273485a5350341, Apache-2.0.
See sources/SGLANG_LICENSE. This consumes caller-owned embeddings/context and
synthetic or separately authenticated tensors. It neither loads model payloads
nor authenticates target features, native cache ownership or request lifetime.
No import-time tensor runtime, accelerator selection, downloads or inference.
Attention realizes the author TRT mask on CPU; it does not emulate GPU rounding.
"""
from pathlib import Path

SOURCES = Path(__file__).with_name('sources')
SOURCE_PINS = {
    'sglang_dflash.py': 'b7b541368cbbb072a679d08ba5bf0f952f4a43f02b6c078562b2ea7a9ddfd01b',
    'sglang_layernorm.py': 'ba362ab14822415e251f46b369d13aa427d9d4958ac82d6fc2df719af732b758',
    'sglang_activation.py': '5725a11725ded609484d846d05430235fdf2a7767307d7bdd1686821ae26cdd8',
    'sglang_rotary_base.py': 'bbe1dbf6a7b2a62496c0490fa2ede237010381b8bbffdcbf9e9ef8e270dbf177',
    'sglang_rotary_utils.py': '828a50285218e40c3429d2f4e75b1d051e3a89d831a7ab005e8c2609278aeddc'}
LAYER_SHAPES = {
    'input_layernorm.weight': (2560,), 'post_attention_layernorm.weight': (2560,),
    'self_attn.q_proj.weight': (4096,2560), 'self_attn.k_proj.weight': (1024,2560),
    'self_attn.v_proj.weight': (1024,2560), 'self_attn.o_proj.weight': (2560,4096),
    'self_attn.q_norm.weight': (128,), 'self_attn.k_norm.weight': (128,),
    'mlp.gate_proj.weight': (7680,2560), 'mlp.up_proj.weight': (7680,2560),
    'mlp.down_proj.weight': (2560,7680)}
for _name in ('attention_conv','mlp_conv'):
    LAYER_SHAPES[_name+'.base_kernel']=(2,2,2560)
    LAYER_SHAPES[_name+'.kernel_projection.weight']=(640,2560)


def _runtime():
    import torch
    if torch.get_num_threads()!=1 or torch.get_num_interop_threads()!=1:
        raise ValueError('Explicit one-thread CPU execution required')
    return torch


def _tensor(x, shape, dtype, name, t):
    if not isinstance(x,t.Tensor) or x.device.type!='cpu' or x.dtype!=dtype or tuple(x.shape)!=tuple(shape):
        raise ValueError('CPU tensor shape/dtype differs: '+name)
    # Bound validation temporaries; no full-weight finite mask is retained.
    for start in range(0,x.shape[0],64):
        if not bool(t.isfinite(x[start:start+64]).all()):
            raise ValueError('Nonfinite tensor: '+name)


def _weights(weights, shapes, dtype, t):
    if type(weights) is not dict or set(weights)!=set(shapes):
        raise ValueError('Exact query-body tensor mapping required')
    for name,shape in shapes.items():
        _tensor(weights[name],shape,dtype,name,t)


def _hidden(x,block_size,t):
    if type(block_size) is not int or block_size not in (4,8):
        raise ValueError('Only block4 or block8 is supported')
    if not isinstance(x,t.Tensor) or x.dtype not in (t.float32,t.bfloat16):
        raise TypeError('CPU FP32/BF16 embeddings required')
    _tensor(x,(block_size,2560),x.dtype,'hidden',t)


def _positions(p,rows,name,t):
    if not isinstance(p,t.Tensor) or p.device.type!='cpu' or p.dtype!=t.int64:
        raise TypeError(name+' must be CPU int64')
    if p.shape!=(rows,) or bool((p<0).any()) or bool((p>=262144).any()):
        raise ValueError(name+' must match rows and remain within capacity')
    if rows>1 and not bool((p[1:]==p[:-1]+1).all()):
        raise ValueError(name+' must be contiguous absolute positions')


def _layout(hidden,positions,ck,cv,cp,t):
    if __package__:
        from .attention import author_allow_mask
    else:
        from attention import author_allow_mask
    _positions(positions,hidden.shape[0],'query positions',t)
    if not isinstance(ck,t.Tensor) or ck.ndim!=3 or ck.shape[1:]!=(8,128) or ck.shape[0]>2048:
        raise ValueError('Context must have shape[0..2048,8,128]')
    _tensor(ck,ck.shape,hidden.dtype,'context key',t)
    _tensor(cv,ck.shape,hidden.dtype,'context value',t)
    _positions(cp,ck.shape[0],'context positions',t)
    prefix=int(positions[0])
    if (cp.numel() and int(cp[-1])!=prefix-1) or (not cp.numel() and prefix!=0):
        raise ValueError('Committed context must end immediately before anchor')
    # Validate the complete visible history before any expensive projection.
    author_allow_mask(positions,t.cat((cp,positions)))


def _norm(x,weight,residual,t):
    # Native RMSNorm defaultFalse: add residual in FP32 and retain that FP32
    # value for statistics; cast residual storage and normalized output once.
    value=x.float()
    new_residual=None
    if residual is not None:
        value=value+residual.float()
        new_residual=value.to(x.dtype)
    normalized=value*t.rsqrt(value.pow(2).mean(-1,keepdim=True)+1e-6)
    out=(normalized*weight).to(x.dtype)
    return out,new_residual


def rotary(x,positions):
    """Source-native NeoX RoPE with FP32 cache and activation-dtype products."""
    t=_runtime()
    if not isinstance(x,t.Tensor) or x.device.type!='cpu' or x.dtype not in (t.float32,t.bfloat16):
        raise TypeError('CPU FP32/BF16 rotary activations required')
    if x.ndim!=3 or x.shape[0] not in (4,8) or x.shape[1] not in (8,32) or x.shape[2]!=128:
        raise ValueError('Rotary activation geometry differs')
    _positions(positions,x.shape[0],'rotary positions',t)
    frequency=1.0/(10000.**(t.arange(0,128,2,device='cpu',dtype=t.float32)/128))
    angle=t.einsum('i,j -> ij',positions.float(),frequency)
    c=angle.cos().to(x.dtype)[:,None,:];s=angle.sin().to(x.dtype)[:,None,:]
    first,second=x[...,:64],x[...,64:]
    return t.cat((first*c-second*s,second*c+first*s),-1)


def query_attention(hidden,positions,context_key,context_value,context_positions,weights):
    """QKV/native norm/RoPE/author-mask attention/output projection; no cache writes.

    Internal arithmetic interface. Public layer_forward/query_block validate
    every body weight before entering it. attention.attend validates positions,
    context geometry and required visible history.
    """
    if __package__:
        from .attention import attend
    else:
        from attention import attend
    t=_runtime()
    _hidden(hidden,hidden.shape[0],t)
    _layout(hidden,positions,context_key,context_value,context_positions,t)
    weight=t.cat([weights['self_attn.'+s+'_proj.weight'] for s in ('q','k','v')],dim=0)
    qkv=t.nn.functional.linear(hidden,weight)
    q,k,v=qkv.split([4096,1024,1024],dim=-1)
    q,_=_norm(q.reshape(-1,32,128),weights['self_attn.q_norm.weight'],None,t)
    k,_=_norm(k.reshape(-1,8,128),weights['self_attn.k_norm.weight'],None,t)
    q=rotary(q,positions);k=rotary(k,positions)
    a=attend(q,k,v.reshape(-1,8,128),context_key,context_value,
             query_positions=positions,context_positions=context_positions)
    return t.nn.functional.linear(a.flatten(-2),weights['self_attn.o_proj.weight'])


def _layer(hidden,residual,positions,ck,cv,cp,w,block_size,t):
    if __package__:
        from .math_ops import prepare_convolution,finish_convolution
    else:
        from math_ops import prepare_convolution,finish_convolution
    if residual is None:
        residual=hidden
        hidden,_=_norm(hidden,w['input_layernorm.weight'],None,t)
    else:
        hidden,residual=_norm(hidden,w['input_layernorm.weight'],residual,t)
    a,coeff=prepare_convolution(hidden,w['attention_conv.kernel_projection.weight'],w['attention_conv.base_kernel'],block_size)
    a=query_attention(a,positions,ck,cv,cp,w)
    a=finish_convolution(a,coeff,w['attention_conv.base_kernel'],block_size)
    hidden,residual=_norm(a,w['post_attention_layernorm.weight'],residual,t)
    hidden,coeff=prepare_convolution(hidden,w['mlp_conv.kernel_projection.weight'],w['mlp_conv.base_kernel'],block_size)
    gate_up=t.nn.functional.linear(hidden,t.cat((w['mlp.gate_proj.weight'],w['mlp.up_proj.weight']),dim=0))
    hidden=t.nn.functional.silu(gate_up[...,:7680])*gate_up[...,7680:]
    hidden=t.nn.functional.linear(hidden,w['mlp.down_proj.weight'])
    hidden=finish_convolution(hidden,coeff,w['mlp_conv.base_kernel'],block_size)
    return hidden,residual


def layer_forward(hidden,residual,positions,context_key,context_value,context_positions,weights,*,block_size):
    """Single real-width layer; owned outputs, committed input cache untouched."""
    t=_runtime();_hidden(hidden,block_size,t)
    _layout(hidden,positions,context_key,context_value,context_positions,t)
    _weights(weights,LAYER_SHAPES,hidden.dtype,t)
    if residual is not None:_tensor(residual,hidden.shape,hidden.dtype,'residual',t)
    with t.inference_mode():
        return _layer(hidden,residual,positions,context_key,context_value,context_positions,weights,block_size,t)


def query_block(input_embeds,positions,context_key,context_value,context_positions,weights,*,block_size):
    """Five actual DFlash2 layers and final native residual RMSNorm.

    weights contains75 layer tensors plus norm.weight. The17 context tensors,
    target embedding/head and selector are separate. input_embeds must be actual
    target embeddings for anchor+mask rows in a future trained execution.
    This function computes hidden rows only; it never selects or commits tokens.
    """
    t=_runtime();_hidden(input_embeds,block_size,t)
    shapes={f'layers.{i}.{n}':s for i in range(5) for n,s in LAYER_SHAPES.items()}
    shapes['norm.weight']=(2560,)
    _weights(weights,shapes,input_embeds.dtype,t)
    for name,x in (('context_key',context_key),('context_value',context_value)):
        if not isinstance(x,t.Tensor) or x.ndim!=4 or x.shape[0]!=5:
            raise ValueError('Five layer-specific context tensors required: '+name)
    for layer in range(5):
        _layout(input_embeds,positions,context_key[layer],context_value[layer],context_positions,t)
    hidden=input_embeds;residual=None
    with t.inference_mode():
        for layer in range(5):
            w={n:weights[f'layers.{layer}.{n}'] for n in LAYER_SHAPES}
            hidden,residual=_layer(hidden,residual,positions,context_key[layer],context_value[layer],context_positions,w,block_size,t)
        hidden,_=_norm(hidden,weights['norm.weight'],residual,t)
        return hidden
