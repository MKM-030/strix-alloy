# Incremental private context KV

`context_ring.py` adds a persistent, mirrored2048-row cache for the actual
five-layer `[5,N,8,128]` context KV. It does not alter `producer.py`,
`partitions.py`, the frozen source reference or the native engine.

The useful mechanism is incremental projection. After the initial actual PF
suffix, `ContextGraph.prepare` only processes the new1..4 actual Verify INPUT
feature rows at their absolute positions. The ring selects exactly the first
`accepted+1` rows and preserves previously projected rows. It never projects
or appends an emitted correction/bonus until that token has appeared in a
subsequent real target-input capture. The CPU fixture checks storage and row
selection only; it does not qualify GPU reductions for different GEMM sizes.

The fixed circular storage has two mirrored halves. New KV rows are copied to
both halves so each layer's chronological view crosses wraparound without
reordering or copying the previous full tail. Storage for K+V is80MiB in BF16
or160MiB in FP32, allocated once on the explicit device. This extra capacity
is a tradeoff; no measured memory or speed improvement is claimed. Returned
`PrivateContext` objects alias the ring. They expire on its next mutation.

## Exact saved native source relationship

The current sources used to design this API are:

- `current-hcmean-prefill-binding/prefill_binding.h`: real PF absolute row
  intervals and suffix selection; initial tail starts at`max(0,P-2048)`.
- `current-pld-native-commit/native_commit.h`: actual committed INPUT rows are
  `[old_current]+proposal[:accepted]`, count`accepted+1`. The last emitted
  correction/bonus has no committed feature row in that receipt.
- `current-native-prefix-binding-v2/prefix.h` and
  `current-pld-native-attachment-v4/bridge.cpp`: the saved joined Bridge builds
  birth/model/tokenizer hashes and native generation/round from its owner
  chain. `Frontier.position` is the number of processed target inputs.
  `Frontier.prefix_tokens` counts the still-unprocessed frontier token too.
- `current-native-composition/README.md`: its HC mean enqueue has no immutable
  generation-bound readiness receipt and no installed full native callbacks.

These packets are under
`server/.local/halogen-update-20261025/primary01816/`. This module does not
install, call or authenticate any of them. `SequenceKey` and `InputCommit` are
host assertions only. A caller-created dataclass is not a native receipt.

## Explicit integration shape

```python
from scripts.research.dflash2_gpu.context_ring import ContextRing, SequenceKey, InputCommit

ring = ContextRing.allocate(device=model.body.device, dtype=model.body.dtype)

# Values must come from the actual joined native owner, not local counters.
key = SequenceKey(frontier.birth, frontier.model, frontier.tokenizer, frontier.generation)
ring.begin(key, prompt_tokens=actual_prompt_length)

# Cover the exact actual PF tail contiguously, possibly across multiple chunks.
# Capture completion and same-stream/owned feature lifetime are caller duties.
kv = model.context.prepare(actual_pf_features, start_position=actual_pf_first)
ring.append_prompt(kv, sequence=key, input_ids=actual_pf_input_ids_tuple)

# Before a proposal, use processed input count/anchor POSITION, not canonical
# prefix length including that anchor. The initial native round is1.
context = ring.context_for(key, round=frontier.round,
                           anchor_position=frontier.position, block_size=4)
private = model.propose(embeds, context, anchor, prefix_tokens=frontier.position)

# After the same real native Verify and commit, project its actual input rows.
kv = model.context.prepare(actual_verify_features, start_position=receipt.base_position)
commit = InputCommit(key, prior_frontier.round, receipt.base_position,
                     actual_captured_input_ids_tuple, receipt.accepted,
                     actual_committed_input_ids_tuple)
ring.append_committed(kv, commit)
# The next actual Bridge frontier must have round=prior+1 and position advanced
# by accepted+1. Its bonus/correction is still only the next unprocessed anchor.
```

For block4/8, the view starts at`max(0,anchor_position+block_size-2048)`.
Thus a long prefix supplies2044/2040 visible committed rows respectively, and
all query rows see the same exact2048-key source block-end window after query
KV is appended. The ring itself retains2048 actual committed rows.

Every call must be serialized on a caller-owned ordered stream, with completed
captures and readers/writers retained until actual completion. No events,
stream discovery, GPU synchronization, native lease, token publication or
asynchronous reclamation is supplied. `retire` invalidates local metadata;
it does not drain work. A fresh`begin` requires a strictly newer native
generation and the same model/tokenizer. The owner must drain any old device
work before reusing ring storage. Validation failures preserve the last local
state; if the actual native frontier has advanced, the owner must retire that
stale state instead of using it for another proposal.

## Bounded CPU verification

The first test-first run failed because the new module was absent. After its
implementation,8 tests passed in7.394s, exit0, with CPU intra/inter-op threads1.
The process is terminal and tensors were released. It loaded no model weights
and used no GPU, NPU, WSL, native engine or real feature capture.

The fixtures cover split PF tail coverage, mirrored rollover, exact retained
IDs/KV and source windows for both blocks, accepted-input selection excluding
rejected/bonus rows, source-storage independence, gap/duplicate/stale-round
rejection, generation retirement/reset, high absolute positions, canonical
length/anchor-position mismatch, dtype/defined-token failures, and tensor paths
with scalar reads and host-copy methods poisoned. Ring arithmetic comparisons
use unchanged rtol0/atol0. No projection/backend or token-rate equivalence is
inferred from these storage tests.

```text
python -B scripts/research/dflash2_gpu/test_context_ring.py --run-cpu
```
