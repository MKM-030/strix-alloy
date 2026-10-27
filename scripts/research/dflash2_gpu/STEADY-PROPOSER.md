# Private steady-window proposer

`steady_proposer.py` is a default-off wrapper around an already-owned
`DFlashGraph`. It owns persistent inputs and computes RoPE positions from an
int64 device scalar, allowing an advancing prefix to use one fixed-shape
captured graph. It changes none of `graph.py`, `partitions.py` or `producer.py`.
There is no serving hook, model loader, native callback or publication path.

For block size B in 4/8 it accepts exactly N=2048-B committed context rows,
starting at P-N and ending immediately before anchor position P. P must be
between N and 262144-B inclusive. All query rows see the same noncausal
2048-key block-end window after their query KV is appended. Short contexts
continue to use the existing eager `DFlashGraph.propose` API. This wrapper
never pads, crops, reorders or reprojects a supplied context.

The fixed owned inputs are embeddings `[B,2560]`, key and value
`[5,N,8,128]`, anchor int64 `[1]`, prefix int64 scalar, int64 offsets `0..B-1`,
the all-visible Boolean mask `[B,2048]`, and previous-row mask `[B,1,1]`.
The mask expands one owned `[1,2048]` row with stride `(0,1)`, matching the
original `QueryLayer.layout` rather than materializing separate query rows.
BF16 key+value capacity is 41,861,120 bytes for block4 or 41,779,200 bytes for
block8; FP32 doubles those two buffers. These figures exclude model tensors,
captured intermediates, outputs, allocator overhead and backend workspaces.

## Parameterized arithmetic

`positions = prefix_scalar + offsets` executes inside the captured compute.
It is followed by exactly the frozen source's FP32 position conversion,
frequency outer-product einsum, cosine/sine, dtype materialization and head
axis insertion. It uses the first owned query layer's existing frequency
tensor. The private `Layout.prefix_tokens` field contains the device scalar;
the frozen layer forwards do not consume that field in arithmetic. They use
the computed positions/cos/sin and fixed shape/mask fields.

The wrapper calls the same five `QueryLayer.forward` methods in order, the
existing residual `_norm`, and the complete existing `selector.propose`.
It introduces no head crop, quantization, reordered reduction or tolerance
change. Any previously selected owned body's attention mode remains that
body's mode and still needs its own backend qualification.

## Ownership and lifecycle

Construct with `SteadyProposer.from_owned_graph(model, block_size=4,
stream=caller_stream)`. CPU fixtures use an explicitly CPU model and omit the
stream. Importing the module imports no Torch and performs no device access,
files, downloads, allocation, threads or serving changes. CPU construction,
validation, compute and close do not call CUDA APIs.

GPU construction requires a caller-owned `torch.cuda.Stream` on the exact
indexed device of the model. Allocation, all private copies/fills, warmup,
capture, eager execution and replay use that same stream. The caller must
establish every model-setup dependency and input-producer dependency before
entry. Supplying a stream does not establish those dependencies. Calls must
be serialized, and model storage must remain unchanged/alive through close.
There is no discovery of a current/default stream or device-wide synchronize.

`prepare(embeddings, context, prefix_tokens=P, anchor_token_id=host_id)` first
revokes any prior local permission, then checks exact host metadata and an
ordinary host anchor ID in 0..248076. It reads no tensor scalar and checks no
weight, embedding, feature or native provenance. The context can be a
`ContextRing.context_for` view; its chronological interval must be exact and
its source storage must remain alive through completion of the copies.

Successful prepare grants one consumption by `eager()`, `capture()` or
`replay()`. A bad prepare cannot leave a prior round available. A failed
submitted copy/compute/capture/replay retires the wrapper. Capture is once
per wrapper, accepts an exact warmup count1..16 (default2), returns no proposal,
and requires a fresh prepare before replay. Warmup drains only the supplied
stream. Direct `capture_begin`/`capture_end` avoid the broader synchronization
and cache cleanup in `torch.cuda.graph`. Failed capture remains failed even
when ending capture succeeds; cleanup is not a completion/safety receipt.

```python
from scripts.research.dflash2_gpu.steady_proposer import SteadyProposer

# Caller has already established model/setup and context-producer dependencies
# on caller_stream, and obtained the actual host anchor and processed position.
steady = SteadyProposer.from_owned_graph(model, block_size=4, stream=caller_stream)
steady.prepare(embeds, exact_context, prefix_tokens=position, anchor_token_id=anchor_id)
steady.capture(warmup=2)  # private warmup/capture only; no output is returned

# The next real round can change context, embeddings, anchor and position.
# Its authoritative native identity and completion proofs remain caller duties.
steady.prepare(next_embeds, next_context, prefix_tokens=next_position,
               anchor_token_id=next_anchor_id)
private = steady.replay()
# private tensors alias captured storage and expire on the next compute/update.
# Establish completion and take immutable owned copies before native publication.

steady.close()  # drains only caller_stream before releasing owned references
```

`eager()` and `replay()` return a `PrivateProposal` whose tensors are borrowed,
mutable private results. Capture outputs alias graph storage; keeping the
dataclass does not preserve an earlier round. No result supplies GEN authority,
full native prefix proof, stream-completion proof, weight provenance, learned
acceptance, engine integration or token-rate claim. Native authentication,
immutable publication and any cross-stream consumer remain caller duties.

`close()` revokes readiness and drains the wrapper's supplied stream before
releasing graph/input references. If draining raises, it retains them and
stays failed. A caller must retain the wrapper and explicitly close it; garbage
collection is not a fence. Close cannot drain unrelated streams that a caller
used to consume borrowed outputs.

## Bounded CPU evidence and remaining work

The absent-module RED run failed with `Steady-window private proposer is
missing` (one failure, six explicitly skipped CPU tests). After implementation
the bounded suite passed9 tests in3.009s, exit0, with intra/inter-op threads1.
One intermediate test expected a capture-device error after already consuming
prepare; it was corrected to prepare again before testing that separate branch.
The final measured bounded run passed10 tests in2.711163s, zero failures/errors
or skips, PID34284, terminal exit0. Windows `GetProcessMemoryInfo` recorded
peak working set541,732,864 bytes (516.64MiB) and peak pagefile/private-commit
counter1,316,515,840 bytes (1255.53MiB). These are whole-process peaks including
Torch/runtime and fixtures; working set is physical residency, while the
pagefile counter is process commit rather than an additional physical amount.
The terminal process released its tensors. Only required fixed BF16 inputs
plus tiny source backing were allocated, with no full layer/model tensors.

```text
C:/Users/Marcel/AppData/Local/Programs/Python/Python312/python.exe -B scripts/research/dflash2_gpu/test_steady_proposer.py --run-cpu
```

The independent numerical oracle is the original `QueryLayer.layout`, invoked
through a weight-free layer metadata fixture. FP32/BF16 and blocks4/8 compare
positions, cos, sin, allow mask and previous-row mask at unchanged rtol0/atol0.
Prefixes include the exact long-window boundary,2044,8192,8193,260000 and the
capacity edge. Advancing prefixes must actually change the RoPE tensors.
An additional wrapper-level stride regression first failed for both blocks:
the previous contiguous mask had stride `(2048,1)`, while the original oracle
has `(0,1)`. Changing allocation to one row expanded across B made both stride
and zero-tolerance values match. This establishes layout fidelity; it supplies
no GPU performance or backend numerical claim.

Other fixtures substitute all five expensive layer forwards and the selector.
They establish routing/order, real final normalization, input independence,
fixed storage reuse, one-shot permission, bad-update invalidation, exact context
chronology/length and host ID/type refusal. Tensor scalar/host-transfer methods
and CUDA initialization/stream/synchronization/capture APIs are poisoned on
the CPU path. Two orchestration fixtures replace CUDA graph/stream methods
with CPU doubles to check ordering, capture permission, failure retirement and
drain-before-release behavior. These fixtures do not execute or qualify any
CUDA/ROCm operation, trained model arithmetic, complete selector math or GPU
capture cleanup.

Root must still independently review and run the real pinned full trained
GPU proposer with original target head after the shared hardware window is
available. That test must establish actual setup/producer dependencies and
compare eager versus replay at advancing P with changed embeddings, anchor
and exact committed context. GPU execution with the matched mask strides,
output parity, latency and memory remain unqualified here. Only a later actual native
owner/capture/publication join
and full-engine frozen cohort can establish useful integrated behavior.
