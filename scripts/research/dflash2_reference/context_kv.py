"""Actual DFlash2 17-tensor context-KV partition, explicit CPU reference only.

Adapted equations: SGLang@3c560089e1818a5217a73f2168273485a5350341,
Apache-2.0, sources/SGLANG_LICENSE; model source SHA pinned below.
No torch import, file read, model loading, thread change or device call at import.

Numerical contract: the pinned source-native/sequential CPU path. FP32 or BF16
input/weights, CPU torch linear/MM rounded to that dtype; RMS statistics and
weight multiply FP32, followed by one output cast (native RMSNorm defaultFalse).
RoPE uses source FP32 inverse frequencies/absolute-position outer product/trig,
cos/sin cast to activation dtype, then separate activation-dtype products and
add/sub materializations as native apply_rotary_emb. In BF16 this differs from
fused GPU norm/RoPE, which keeps K normalization FP32 through the final store.
This is not bitwise BF16 CUDA/Triton or future NPU equivalence.
Both inputs and weights must already be caller-owned CPU tensors. One request per
publication; 1..2048 rows, absolute positions, chunked workspace. No model loader.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

SOURCE=Path(__file__).with_name('sources')/'sglang_dflash.py'
SOURCE_SHA256='b7b541368cbbb072a679d08ba5bf0f952f4a43f02b6c078562b2ea7a9ddfd01b'
SOURCE_REVISION='3c560089e1818a5217a73f2168273485a5350341'
PRIMITIVE_PINS={
 'sglang_layernorm.py':'ba362ab14822415e251f46b369d13aa427d9d4958ac82d6fc2df719af732b758',
 'sglang_rotary_base.py':'bbe1dbf6a7b2a62496c0490fa2ede237010381b8bbffdcbf9e9ef8e270dbf177',
 'sglang_rotary_utils.py':'828a50285218e40c3429d2f4e75b1d051e3a89d831a7ab005e8c2609278aeddc'}
MAX_ROWS=2048
CHUNK_ROWS=64
WEIGHT_SHAPES={'fc.weight':(2560,12800),'hidden_norm.weight':(2560,)}
for _layer in range(5):
    for _suffix,_shape in [('k_proj.weight',(1024,2560)),('v_proj.weight',(1024,2560)),('k_norm.weight',(128,))]:
        WEIGHT_SHAPES[f'layers.{_layer}.self_attn.{_suffix}']=_shape

def verify_sources():
    """Explicit metadata/source check, never reads tensor payloads."""
    if __package__:
        from .contract import verify_saved_contract
    else:
        from contract import verify_saved_contract
    result=verify_saved_contract()
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=SOURCE_SHA256:
        raise ValueError('Pinned SGLang context source differs')
    for name,expected in PRIMITIVE_PINS.items():
        if hashlib.sha256(SOURCE.with_name(name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Pinned SGLang primitive differs: '+name)
    header=json.loads(SOURCE.with_name('safetensors-header.json').read_bytes())
    for name,shape in WEIGHT_SHAPES.items():
        if header[name]['shape']!=list(shape) or header[name]['dtype']!='BF16':
            raise ValueError('Partition header differs: '+name)
    return dict(partition_tensors=17,parameters=58985600,model_payload_opened=False,
                model_id=result['model_id'],revision=SOURCE_REVISION)

@dataclass(frozen=True)
class OwnerMetadata:
    """Owner assertions, not proof of native lifecycle/authentication.

    A real owner must supply fresh immutable birth/model/tokenizer/prefix hashes
    plus actual generation and round, then retire on reset/cancel. The reference
    never infers ownership from storage addresses and has no runtime attachment.
    """
    birth:bytes
    model:bytes
    tokenizer:bytes
    prefix:bytes
    generation:int
    round:int

def _owner(owner):
    if type(owner) is not OwnerMetadata:
        raise TypeError('OwnerMetadata required')
    for tag in (owner.birth,owner.model,owner.tokenizer,owner.prefix):
        if type(tag) is not bytes or len(tag)!=32 or not any(tag):
            raise ValueError('Nonzero 32-byte owner identity required')
    if any(type(n) is not int or not 0<n<2**64 for n in (owner.generation,owner.round)):
        raise ValueError('Positive generation and round required')

@dataclass(frozen=True)
class CommittedInputs:
    k:object
    v:object
    positions:object
    owner:OwnerMetadata

class PrivateKV:
    """Owned private outputs; public access returns copies, selection is one-shot.

    Python privacy is not a security boundary. This object does not grant a native
    cache lease; selection returns owned CPU rows, never scatters to native memory.
    """
    def __init__(self,k,v,positions,owner):
        self._k=k;self._v=v;self._positions=positions;self._owner=owner;self._consumed=False
    @property
    def k(self):return self._k.clone()
    @property
    def v(self):return self._v.clone()

def _rms(x,weight,torch):
    value=x.float()
    normalized=value*torch.rsqrt(value.square().mean(-1,keepdim=True)+1e-6)
    return (normalized*weight.float()).to(x.dtype)

def _rotary(k,cos,sin,torch):
    first,second=k[...,:64],k[...,64:]
    return torch.cat((first*cos-second*sin,second*cos+first*sin),-1)

def _finite(x,torch):
    # Validation must share the bounded workspace contract; avoid full FC- or
    # window-sized boolean temporaries, including for strided CPU tensors.
    return all(bool(torch.isfinite(x[start:start+CHUNK_ROWS]).all())
               for start in range(0,x.shape[0],CHUNK_ROWS))

def prepare_context(X,positions,weights,*,owner):
    """Prepare private [5,N,8,128] KV for N known target INPUT rows.

    X concatenates raw completed HC means at layers5/15/25/35/45, [N,12800].
    This graph needs neither query embeddings nor full transformer/head weights.
    Caller explicitly configures torch CPU intra-op and inter-op threads to one.
    Peak live graph tensors at N<=2048 with FP32 weights/workspace are <1GiB;
    caller-retained aliases, foreign allocations and framework overhead excluded.
    """
    _owner(owner)
    import torch
    if torch.get_num_threads()!=1 or torch.get_num_interop_threads()!=1:
        raise ValueError('Explicit one-thread CPU execution required')
    if not isinstance(X,torch.Tensor) or X.device.type!='cpu' or X.dtype not in (torch.float32,torch.bfloat16):
        raise TypeError('CPU FP32/BF16 X required')
    if X.ndim!=2 or X.shape[1]!=12800 or not 1<=X.shape[0]<=MAX_ROWS:
        raise ValueError('X must have shape [1..2048,12800]')
    n=X.shape[0]
    if not isinstance(positions,torch.Tensor) or positions.device.type!='cpu' or positions.dtype!=torch.int64:
        raise TypeError('CPU int64 absolute positions required')
    if positions.shape!=(n,) or bool((positions<0).any()) or bool((positions>=262144).any()):
        raise ValueError('One in-range absolute position per row required')
    if n>1 and not bool((positions[1:]==positions[:-1]+1).all()):
        raise ValueError('One contiguous target-input sequence required')
    if type(weights) is not dict or set(weights)!=set(WEIGHT_SHAPES):
        raise ValueError('Exactly the 17 context partition tensors required')
    for name,shape in WEIGHT_SHAPES.items():
        w=weights[name]
        if not isinstance(w,torch.Tensor) or w.device.type!='cpu' or w.dtype!=X.dtype or tuple(w.shape)!=shape:
            raise ValueError('Partition CPU tensor shape/dtype differs: '+name)
        if not _finite(w,torch):raise ValueError('Nonfinite weight: '+name)
    if not _finite(X,torch):raise ValueError('Nonfinite features')
    with torch.inference_mode():
        # Same stacked [K0,V0,...,K4,V4] projection as upstream, evaluated in
        # five output tiles to avoid a105MiB FP32 stacked-weight duplicate.
        # This reference makes five CPU MMs, not a performance model of its
        # single fused GPU MM. Each output dot product retains its input order.
        k_out=torch.empty((5,n,8,128),dtype=X.dtype,device='cpu')
        v_out=torch.empty_like(k_out)
        frequency=1.0/(10000.**(torch.arange(0,128,2,dtype=torch.float32,device='cpu')/128))
        for start in range(0,n,CHUNK_ROWS):
            stop=min(n,start+CHUNK_ROWS)
            z=_rms(torch.nn.functional.linear(X[start:stop],weights['fc.weight']),weights['hidden_norm.weight'],torch)
            angles=torch.einsum('i,j -> ij',positions[start:stop].float(),frequency)
            cos=angles.cos().to(X.dtype)[:,None,:];sin=angles.sin().to(X.dtype)[:,None,:]
            for layer in range(5):
                kv_weight=torch.cat([weights[f'layers.{layer}.self_attn.{s}_proj.weight'] for s in ('k','v')],dim=0)
                kv=torch.mm(z,kv_weight.T).view(stop-start,2,8,128)
                k=_rms(kv[:,0],weights[f'layers.{layer}.self_attn.k_norm.weight'],torch)
                k_out[layer,start:stop]=_rotary(k,cos,sin,torch)
                v_out[layer,start:stop]=kv[:,1]
        if not bool(torch.isfinite(k_out).all()) or not bool(torch.isfinite(v_out).all()):
            raise ValueError('Context graph overflowed')
        return PrivateKV(k_out,v_out,positions.clone(),owner)

def select_committed_inputs(KV,accept_lens,owner):
    """Select anchor+accepted proposal INPUT rows, never invent bonus hidden.

    Single-request API: accept_lens is a one-element list/tuple of proposal
    acceptance count. Native scatter mask is row<accept_len+1. Caller supplies
    authoritative acceptance and the exact owner metadata bound at preparation.
    No reset/cancel observation, transport auth, slot ownership or device scatter
    is implemented. Invalid calls do not consume a valid private publication.
    """
    _owner(owner)
    if type(KV) is not PrivateKV:raise TypeError('PrivateKV required')
    if KV._consumed or owner!=KV._owner:raise ValueError('Retired, replayed or foreign publication')
    if type(accept_lens) not in (list,tuple) or len(accept_lens)!=1 or type(accept_lens[0]) is not int:
        raise TypeError('One exact integer acceptance count required')
    count=accept_lens[0]+1
    if not 1<=count<=KV._k.shape[1]:raise ValueError('Acceptance exceeds prepared input rows')
    # Copy first; allocation failure must not retire the publication prematurely.
    result=CommittedInputs(KV._k[:,:count].clone(),KV._v[:,:count].clone(),KV._positions[:count].clone(),owner)
    KV._consumed=True
    return result
