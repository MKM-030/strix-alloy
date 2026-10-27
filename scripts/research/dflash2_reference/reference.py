"""Explicit CPU assembly of the pinned trained drafter equations.

No import-time tensor runtime, downloads, target weight lookup or inference.
This is one private query block conditioned on supplied known target features,
not a native cache materializer, verifier or request-authority implementation.
External target evidence is REQUIRED provenance metadata, not validated native
ownership. Provided embedding rows must actually correspond to returned IDs;
this reference cannot authenticate their origin from tensor values or hashes.
"""
from dataclasses import dataclass
import re
if __package__:
 from . import weights
else:import weights

@dataclass(frozen=True)
class TargetEvidence:
 """Caller records authenticated target source identities; not native authority."""
 model_id:str
 revision:str
 tokenizer_sha256:str
 embedding_sha256:str
 head_sha256:str

@dataclass(frozen=True)
class ReferenceResult:
 hidden:object
 proposal:object
 embedding_ids:tuple
 query_positions:object
 private_context:object

def _target(target):
 if type(target) is not TargetEvidence:raise TypeError('Explicit external target provenance required')
 if any(type(s) is not str or not s.strip() for s in (target.model_id,target.revision)):raise ValueError('Target model and pinned revision required')
 for s in (target.tokenizer_sha256,target.embedding_sha256,target.head_sha256):
  if type(s) is not str or re.fullmatch('[0-9a-f]{64}',s) is None or s=='0'*64:raise ValueError('Nonzero lowercase SHA256 target identities required')

def _run(tensors,features,context_positions,input_embeds,*,anchor_token_id,head_weight,target,owner,block_size,org_vocab_size):
 """Internal assembly plumbing; synthetic mapping tests do not authenticate files."""
 import torch
 if __package__:
  from . import attention,backbone,context_kv,proposal
 else:import attention,backbone,context_kv,proposal
 if torch.get_num_threads()!=1 or torch.get_num_interop_threads()!=1:raise ValueError('Explicit one-thread CPU execution required')
 _target(target);context_kv._owner(owner)
 expected=weights.expected_header()
 if type(tensors) is not dict or set(tensors)!=set(expected):raise ValueError('Exact81 trained tensor mapping required')
 if type(org_vocab_size) is not int or not 16<=org_vocab_size<=248320:raise ValueError('Explicit original vocabulary prefix required')
 if type(anchor_token_id) is not int or not 0<=anchor_token_id<min(org_vocab_size,248077):raise ValueError('Defined in-prefix anchor ID required')
 if not isinstance(features,torch.Tensor) or features.device.type!='cpu' or features.dtype!=torch.bfloat16:raise TypeError('CPU BF16 target HC means required for loaded BF16 weights')
 if features.ndim!=2 or features.shape[1]!=12800 or not 0<=features.shape[0]<=2048:raise ValueError('Known target features must be [0..2048,12800]')
 n=features.shape[0]
 if not isinstance(context_positions,torch.Tensor) or context_positions.device.type!='cpu' or context_positions.dtype!=torch.int64:raise TypeError('CPU int64 context positions required')
 if context_positions.shape!=(n,) or bool((context_positions<0).any()) or bool((context_positions>=262144).any()):raise ValueError('Context position rows/capacity differ')
 if n>1 and not bool((context_positions[1:]==context_positions[:-1]+1).all()):raise ValueError('Contiguous known target-input positions required')
 prefix=int(context_positions[-1])+1 if n else 0
 layout=attention.draft_block_layout(prefix,block_size,anchor_token_id)
 if not isinstance(input_embeds,torch.Tensor) or input_embeds.device.type!='cpu' or input_embeds.dtype!=torch.bfloat16:raise TypeError('Provided CPU BF16 anchor+mask embedding rows required')
 if tuple(input_embeds.shape)!=(block_size,2560):raise ValueError('One actual target embedding row per anchor/mask ID required')
 if not isinstance(head_weight,torch.Tensor) or head_weight.device.type!='cpu' or head_weight.dtype not in (torch.bfloat16,torch.float32):raise TypeError('Caller-owned CPU BF16/FP32 full target head required')
 if tuple(head_weight.shape)!=(248320,2560):raise ValueError('Actual full target-head geometry required')
 context_weights={key:tensors[key] for key in context_kv.WEIGHT_SHAPES}
 body_keys=[f'layers.{i}.{name}' for i in range(5) for name in backbone.LAYER_SHAPES]+['norm.weight']
 body_weights={key:tensors[key] for key in body_keys}
 selector_weights={key:tensors[key] for key in proposal.SELECTOR_KEYS}
 private=None
 with torch.inference_mode():
  if n:
   private=context_kv.prepare_context(features,context_positions,context_weights,owner=owner)
   ck,cv=private.k,private.v
  else:
   ck=torch.empty((5,0,8,128),device='cpu',dtype=torch.bfloat16);cv=torch.empty_like(ck)
  query_positions=torch.tensor(layout.positions,device='cpu',dtype=torch.int64)
  hidden=backbone.query_block(input_embeds,query_positions,ck,cv,context_positions,body_weights,block_size=block_size)
  anchors=torch.tensor([anchor_token_id],device='cpu',dtype=torch.int64)
  selected=proposal.propose_greedy(hidden,anchors,head_weight,selector_weights,block_size=block_size,org_vocab_size=org_vocab_size)
 return ReferenceResult(hidden,selected,layout.ids,query_positions,private)

def run(loaded,features,context_positions,input_embeds,*,anchor_token_id,head_weight,target,owner,block_size=4,org_vocab_size=248077):
 """Run actual loaded model with supplied target context, embedding rows and head.

Call weights.load(path) explicitly first. Caller configures CPU threads=1 and
provides actual BF16 raw HC4 means at completed layers5/15/25/35/45, target
embedding rows for [anchor,248077,...], and the complete target head. Target
source hashes and context owner fields are assertions, never native permission.
The result is a private greedy proposal; only the target verifier can accept it.
No trained quality, native integration or accelerator identity follows here.
"""
 if type(loaded) is not weights.LoadedWeights:raise TypeError('Pinned weights.load result required')
 return _run(loaded._select(loaded.names),features,context_positions,input_embeds,anchor_token_id=anchor_token_id,head_weight=head_weight,target=target,owner=owner,block_size=block_size,org_vocab_size=org_vocab_size)
