"""DFlash2 author's expanded-decode mask and bounded one-thread CPU SDPA core.

SGLang3c560089e1818a5217a73f2168273485a5350341, Apache-2.0;
sources/SGLANG_LICENSE applies. No tensor runtime is imported at import time.

Runtime contract: the validated model-card backend is trtllm_mha. Its
ENCODER_ONLY TARGET_VERIFY path repeats the full p+B cache length/page table
for B single-token decode rows (q_len_per_req=1), with left window2047.
Every query therefore sees the SAME last2048 keys ending at p+B-1; its RoPE
position is still p+j. This is not per-query causal/sliding attention.

Numerics here use the actual TorchNative backend's sequential one-token SDPA
operation/order with that expanded metadata. CPU FP32/BF16 primitive agreement
does not establish TRT-LLM/CUDA/Triton/NPU bit identity or performance.
Inputs are already normalized/RoPE-transformed Q/K and projected V. No weights,
hidden-state exporter, cache commit, native consumer or full drafter is supplied.

Source proof (all pinned in the saved research audit):
 - srt/models/dflash.py: is_causal=False -> ENCODER_ONLY; head_dim128.
 - srt/speculative/dflash_utils.py: config window2048 -> window_left2047.
 - srt/speculative/dflash_worker_v2.py: anchor/masks at absolute p..p+B-1;
   query KV writes occupy those slots after committed target-derived prefix KV.
 - srt/layers/attention/trtllm_mha_backend.py: expanded full-cache encoder rows.
 - FlashInfer0.7.2 (SGLang's pinned dependency), commit
   d84335d8c54e0c8f9f7e22faa15c7e34a58abf94: left inclusive window.
 - srt/layers/attention/torch_native_backend.py: one-query CPU SDPA core,
   SHA5da07edadf56f4f4e4b8319ed48216b5a8ddb989224d3e95011b76800bf9926b.

The upstream TorchNative backend normally ignores sliding windows for encoder
extend; this module explicitly realizes the author's TRT expanded-decode layout,
not that different full-prefix path. Temporary query KV never mutates context.
"""
from dataclasses import dataclass
@dataclass(frozen=True)
class DraftBlock:
    ids:tuple
    positions:tuple

def draft_block_layout(prefix_tokens,block_size,anchor_id,mask_id=248077):
    """Immutable worker IDs/positions, caller asserts authoritative anchor."""
    if any(type(x) is not int for x in (prefix_tokens,block_size,anchor_id,mask_id)):
        raise TypeError('Exact integer layout inputs required')
    if block_size not in (4,8) or not 0<=prefix_tokens<=262144-block_size:
        raise ValueError('Block4/8 and in-range absolute positions required')
    if not 0<=anchor_id<=248076 or mask_id!=248077:
        raise ValueError('Actual defined anchor ID and trained mask248077 required')
    return DraftBlock((anchor_id,)+(mask_id,)*(block_size-1),
                      tuple(range(prefix_tokens,prefix_tokens+block_size)))

def _positions(x,name,torch,*,allow_empty=False):
    if not isinstance(x,torch.Tensor) or x.device.type!='cpu' or x.dtype!=torch.int64:
        raise TypeError(name+' must be CPU int64')
    if x.ndim!=1 or (not allow_empty and not x.numel()):
        raise ValueError(name+' must be one-dimensional and nonempty')
    if x.numel() and (bool((x<0).any()) or bool((x>=262144).any())):
        raise ValueError(name+' outside target position capacity')
    if x.numel()>1 and not bool((x[1:]==x[:-1]+1).all()):
        raise ValueError(name+' must be contiguous increasing positions')

def author_allow_mask(query_positions,key_positions):
    """Boolean[block,keys], common full-block-end inclusive left2047 mask.

    Keys must be a complete contiguous retained tail through the block end.
    At most2048 committed context rows plus the block are admitted.
    """
    import torch
    _positions(query_positions,'query_positions',torch)
    _positions(key_positions,'key_positions',torch)
    block=query_positions.numel()
    if block not in (4,8) or not block<=key_positions.numel()<=2048+block:
        raise ValueError('Block4/8 and at most2048 committed key rows required')
    end=int(query_positions[-1])+1;left=max(0,end-2048)
    if int(key_positions[-1])!=end-1 or int(key_positions[0])>left:
        raise ValueError('Required visible key history or query block is missing')
    return ((key_positions>=left)&(key_positions<end))[None,:].expand(block,-1).clone()

def attend(query,query_key,query_value,context_key,context_value,*,query_positions,context_positions):
    """Return owned CPU[block,32,128], same floating dtype as inputs.

    Q:[block,32,128], queryKV:[block,8,128], contextKV:[N<=2048,8,128].
    context_positions is the contiguous committed tail ending just before p;
    query_positions is p..p+block-1. Callers flatten output to[block,4096]
    before the source o_proj. No input or persistent cache is modified.
    """
    import torch
    if torch.get_num_threads()!=1 or torch.get_num_interop_threads()!=1:
        raise ValueError('Explicit one-thread CPU execution required')
    values=(query,query_key,query_value,context_key,context_value)
    if any(not isinstance(x,torch.Tensor) or x.device.type!='cpu' for x in values):
        raise TypeError('Caller-owned CPU tensors required')
    dtype=query.dtype
    if dtype not in (torch.float32,torch.bfloat16) or any(x.dtype!=dtype for x in values):
        raise TypeError('Matching FP32/BF16 input dtypes required')
    if query.ndim!=3 or query.shape[0] not in (4,8) or query.shape[1:]!=(32,128):
        raise ValueError('Query must have shape[block4/8,32,128]')
    block=query.shape[0]
    if query_key.shape!=(block,8,128) or query_value.shape!=query_key.shape:
        raise ValueError('Query KV must have shape[block,8,128]')
    if context_key.ndim!=3 or context_key.shape[1:]!=(8,128) or context_key.shape[0]>2048 or context_value.shape!=context_key.shape:
        raise ValueError('Context KV must have shape[0..2048,8,128]')
    _positions(query_positions,'query_positions',torch)
    _positions(context_positions,'context_positions',torch,allow_empty=True)
    if query_positions.shape!=(block,) or context_positions.shape!=(context_key.shape[0],):
        raise ValueError('Position counts must match tensor rows')
    prefix=int(query_positions[0])
    if context_positions.numel():
        if int(context_positions[-1])!=prefix-1:
            raise ValueError('Context must end before the anchor position')
    elif prefix!=0:
        raise ValueError('Nonempty committed prefix cannot have empty context')
    if any(not bool(torch.isfinite(x).all()) for x in values):
        raise ValueError('Nonfinite attention input')
    keys=torch.cat((context_key,query_key),dim=0)
    vals=torch.cat((context_value,query_value),dim=0)
    mask=author_allow_mask(query_positions,torch.cat((context_positions,query_positions)))
    q=query.movedim(0,1);k=keys.movedim(0,1);v=vals.movedim(0,1)
    output=torch.empty_like(query)
    with torch.inference_mode():
        # Match upstream expanded one-token CPU SDPA calls, including GQA4:1.
        for row in range(block):
            result=torch.nn.functional.scaled_dot_product_attention(
                q[:,row:row+1].unsqueeze(0),k.unsqueeze(0),v.unsqueeze(0),
                attn_mask=mask[row:row+1],enable_gqa=True,scale=128**-.5,is_causal=False)
            output[row:row+1]=result.squeeze(0).movedim(1,0)
    if not bool(torch.isfinite(output).all()):
        raise ValueError('Attention output overflowed')
    return output
