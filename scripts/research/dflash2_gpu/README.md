# Explicit DFlash2 tensor graph

This experimental graph has persistent caller-owned weights for an explicit
`cpu` or indexed ROCm/CUDA PyTorch device. Importing its modules imports no
Torch, opens no model/source files and selects no device. There is no payload
loader or automatic provider selection.

```python
from scripts.research.dflash2_gpu.producer import DFlashGraph

# Root explicitly supplies the already acquired/validated81 CPU model tensors
# and the target's separate dense CPU head. Nothing is loaded by this API.
model = DFlashGraph.from_cpu(
    model_weights, target_head,
    device="cuda:0", org_vocab_size=248320,
    batched_attention=False,
)

# features:[N,12800], already completed/owned on that explicit device.
# embeds:[4|8,2560], actual target embeddings for anchor+mask248077 rows.
# anchor:[1] int64, actual correction/bonus anchor, on the same device.
context = model.context.prepare(features, start_position=context_start)
private = model.propose(embeds, context, anchor, prefix_tokens=actual_prefix)
```

The startup factory checks CPU tensor shapes/dtypes/finiteness once, clones
the weights, and packs QKV/gate+up permanently. Context projection reuses the
already-owned query-body K/V and k_norm weights rather than transferring a
second copy. The complete key set is81 trained tensors; the dense target head
is external because the trained checkpoint contains neither head nor input
embedding table.

For lower startup retention, create `QueryBackbone.from_cpu` and then
`ContextGraph.from_owned_body` first. Retain only the three CPU selector
tensors, release the CPU body/FC tensors, then acquire the separate head and
create `ProposalGraph.from_cpu`. Finally call
`DFlashGraph.from_owned_parts(body, context, selector)`. That constructor checks
exact component types, matching dtype/device and `context._body is body`, and
retains references without copying or transferring any tensor. The caller owns
actual CPU-source release and memory admission; no measured peak reduction is
claimed by this source change. `from_cpu` uses the same final composition path.

The tensor critical path uses no `.all()`, `.item()`, boolean Tensor, host copy
or per-kernel weight scan. Its metadata checks read host tensor shapes/dtypes
and explicit Python logical positions. Context/feature integrity and actual
completion must be established by Root outside this graph. Returned KV and
proposals are private; they grant no native owner, generation, fence, token
domain, acceptance or injection authority. Python privacy is not a security
boundary. Position/view caches and static graph capture are not implemented.
The current native consumer admits at most3 proposals, so block4 is the
matching attachment shape. Block8 produces7 private proposals and does not
authorize truncating or publishing a wider result through that consumer.

The default `batched_attention=False` retains the exact frozen CPU one-query
SDPA call order. Every query attends noncausally to the same inclusive last2048
keys ending at the entire query-block end, while RoPE remains at its own
absolute position. It preserves native residual/RMS rounding, source two-tap
grouped convolution and retained output coefficients, full dense top16 and
the learned rank256 predecessor-conditioned selector, discarding row0 before
proposal selection. Greedy q is an exact point mass.

`batched_attention=True` is an explicit optimization candidate: all4/8 queries
use one SDPA call per layer with the same complete author mask. It reduces
Python/kernel submissions without changing the intended visibility. Different
GPU reductions/kernel choices still need Root's numerical and timing checks;
CPU tests do not prove GPU bit identity. The default reference path remains
available unchanged.

Synthetic CPU source checks passed8 query-body tests in18.176s and6 partition/
composition tests in8.398s after the staged constructor. Reference comparisons use unchanged rtol0/atol0,
real width2560/rank256/top16 and synthetic vocabulary32. They cover FP32/BF16,
blocks4/8, first/later residuals and the five-layer/final-norm order; context
with absolute positions259992; the complete81-key composition; owned startup
storage; and real forward execution while Tensor boolean/scalar conversion is
poisoned. The batched candidate has a separate exact uniform-attention test
showing that the last query value affects the first query for both block sizes.
That controlled test makes no random-GPU numerical claim.

Root's first real-weight GPU query-body experiment observed a CPU/GPU output
difference. GPU/source parity and usable latency remain unqualified; this
package does not relax the CPU tolerance or present that experiment as a
verified speed result. A separate independent original-source GPU oracle is
being prepared to isolate source arithmetic from backend reduction behavior.

Run these finite CPU checks explicitly with the existing CPU PyTorch runtime:

```text
python -B scripts/research/dflash2_gpu/test_graph.py --run-cpu
python -B scripts/research/dflash2_gpu/test_partitions.py --run-cpu
```

No GPU/NPU, real model tensor or engine was used by this package's author.
Root owns all real device placement, completion, memory admission, actual
numerical acceptance and end-to-end Prefill/Decode/MTP benchmarks. The stock
serving engine is not modified by these modules.
