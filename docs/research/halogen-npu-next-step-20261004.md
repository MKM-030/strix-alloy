# Flash-Next NPU next step: actual expert selection — 4 October 2026

Subsequent hardware work is recorded in the
[parameter-input probe](halogen-npu-parameter-probe-20261004.md). Its NPU
execution failed the declared numerical gate; dynamic routing remains
unqualified. This host helper adds no Halogen acceptance or speed improvement.

The successful NPU replay fixes expert IDs 0–9. Its changing router coefficients
do not implement a token's selection among 512 experts. The new CPU host helper
`scripts/benchmarks/halogen_npu_routing_host.py` makes that selection and the
dispatch boundary explicit: it selects ten IDs from supplied logits, packs the
coefficients in a graph's exact ID order, and refuses a graph miss. It never
initializes an execution provider or compiles a graph.

This is a bounded implementation step toward dynamic routing. It does not
establish Halogen numerical parity, full MTP, live target-state handoff, acceptance
quality, or an end-to-end speedup. The measured builder, q4c decoder, and original
fixtures retain their previously recorded hashes. No model, driver, global
setting, gateway, or backend was changed.

## Public router contract and numerical limits

The official model config identifies the text decoder as `qwen4_exp_text`, with
512 experts, ten selected per token, hidden width 2560, intermediate width 640,
four residual streams, BF16 model dtype, and one indexed/full-attention MTP
layer. Its `output_gate_type: sigmoid` belongs to an attention output gate;
it is not the MoE router score function. [Official model config](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/blob/main/config.json).

`Qwen4ExpTextTopKRouter` computes the router matvec, float32 softmax across all
experts, top-k, optional selected-weight renormalization, then casts coefficients
to the logits dtype. The shared expert has its own sigmoid gate and is added
after routed-expert aggregation. [Transformers v5.16.1 implementation](https://github.com/huggingface/transformers/blob/v5.16.1/src/transformers/models/qwen4_exp/modeling_qwen4_exp.py).
The config's `norm_topk_prob` default is true; the published checkpoint config
omits that field. [Transformers v5.16.1 config](https://github.com/huggingface/transformers/blob/v5.16.1/src/transformers/models/qwen4_exp/configuration_qwen4_exp.py).
These sources define the helper's reference policy, not the closed Halogen
engine's exact arithmetic.

The helper uses float32 NumPy softmax and sums. Its default rounds the final
coefficients to BF16 with round-to-nearest-even, then represents those values in
the measured graph's float32 ABI. The optional float32 mode is for comparison.
Supplied logits must already reflect the caller's router output dtype. The
helper converts them to FP32, without adding BF16 input quantization. The separate `router_logits_fp32`
function accumulates and returns FP32, so it does not reproduce a BF16 router
matvec's output rounding.

Selected IDs are sorted to provide a canonical cache identity, while coefficient
association is preserved. `pack_for_graph` also supports an existing graph's
different ID order. Canonical ordering changes the floating-point reduction
order relative to an engine that aggregates in rank order; output parity must
be checked on captured traces. Exact ties at the tenth/eleventh boundary are
refused. PyTorch does not promise stable tied indices, so a lower-ID choice
would be an invented engine policy. [PyTorch top-k contract](https://docs.pytorch.org/docs/2.10/generated/torch.topk.html).
Near ties also need trace validation; a positive reference margin is not a
guarantee that Halogen chooses the same set.

## Implemented safeguards and bounded evidence

The helper provides five usable pieces:

- `route_top10`: one finite 512-score vector, configured normalization and dtype,
  diagnostic probability mass and boundary margin, and immutable coefficients.
- `pack_for_graph`: requires the same ten unique IDs as the route and returns
  contiguous float32 `[10,1,1]` coefficients in graph order. A miss refuses dispatch.
- `graph_cache_key`: binds canonical IDs, checkpoint manifest, builder, provider
  manifest and runtime configuration hashes. This is identity planning; callers
  still must verify graph/data/context receipts on a hit.
- `memory_admission`: checks physical availability and commit headroom after
  explicit incremental runtime plus transient allocations. Both must retain
  18 GiB. Unknown overhead refuses admission, and estimates below the known
  decoded weight bytes are rejected. Exactly those bytes plus zero transient
  allowance can pass; callers still must provide trustworthy provider and
  transient estimates. This snapshot calculation does not replace the live process guard.
- `load_router_bf16` and `router_logits_fp32`: verify the trusted manifest hash,
  exact router geometry, payload SHA and XOR checksum, then decode only the
  existing small extracted router for a one-token CPU reference.

Eleven focused fixtures passed using the local Python/NumPy environment with
`OPENBLAS_NUM_THREADS=1` and `OMP_NUM_THREADS=1`. They cover ID/weight alignment,
existing graph order, BF16 rounding including ties-to-even, invalid scores and
boundary ties, graph misses, identity invalidation, memory reserve boundaries,
payload verification, the one-token matvec contract, and bounded actual input
reads after file growth. The initial missing
helper and missing cache/reader functions were observed failing before those
implementations were added. Only this fixture file was run; no broad suite or
hardware test was performed.

The existing router payload is BF16 `[512,2560]`, 2,621,440 bytes; expansion uses
5,242,880 float32 bytes. The verified finite weight range was -1.546875 to
0.7578125. Sixteen seeded synthetic hidden vectors selected sixteen different
expert sets spanning 125 IDs. Consecutive overlaps were 0–2 IDs. This demonstrates
why fixed IDs do not describe the reference routing experiment; synthetic
overlap is not a live Halogen cache-hit estimate. BF16 coefficient sums ranged
from 0.9986572265625 to 1.00048828125 after normalization then rounding. There
is intentionally no second normalization after BF16 rounding.

The receipt is retained outside Git at
`C:\AI\halogen-mtp-npu\routing-host-20261004\synthetic-router.json`.
It records seed 20261004, every input/logit/route hash and selected set, plus:

| Identity | SHA-256 |
| --- | --- |
| Helper used by the synthetic probe | `08ce34fafbf369e67ef2968cda5d9968df6408b82bff05acddcb1965fe829502` |
| Focused fixtures used by the probe | `a57da8b90e21c273db421d800fbaf569a42df9fecb0871493216fecb880c180e` |
| Trusted extraction manifest | `9c65cd40eb50d8f2f3343bbbeb865949523a3d022902935be77820493f849967` |
| Router BF16 payload | `f0d35fa41b360a08bc0c5b1e5766aa42df960291716ee189208b5d2599462c20` |
| Synthetic receipt | `7f22d29a4e9703874c84fcb6b976073f71e7269507a7939a8826627c0969db11` |

The table identifies the exact files used by the completed synthetic probe.
Independent review then found a stat/read race in the CLI's size check. The
final CLI now reads at most 65,537 bytes from the stream, rejects oversized
input before decoding, and passes an added file-growth fixture. That I/O fix
does not change routing arithmetic. Final helper SHA-256 is
`66e1612135ddbb18f7ee4b7f9dd61d97a231fa9b75719cf1bbb27eadffb0bcbc`;
final eleven-fixture source SHA-256 is
`5ce26fc353e9ab21cf361353cb950fcbfea6f7ea0d5759bab8c9e500e3244783`.
The earlier synthetic receipt is preserved, rather than relabeled as a run of
these later sources.

CLI example, using a supplied JSON vector of 512 logits:

```powershell
python scripts/benchmarks/halogen_npu_routing_host.py --logits C:/AI/router-logits.json
```

The CLI's default graph order is canonical and is planning output. Supplying
`--graph-experts 0,1,2,3,4,5,6,7,8,9` asks whether the selected set can use the
already measured graph; a different set fails. It does not create that graph
or prove any cache entry is present.

## What changing IDs costs

There are `512 choose 10 = 312,268,282,598,377,321,216` possible expert sets.
Canonical ordering removes permutations of one set, not this combinatorial
limit. The final NPU replay initialized one graph in 32,704.2376 ms and ran
warm calls at 1.504985 ms, versus 6.394102 ms on single-thread CPU. Those figures
remain synthetic, fixed-expert evidence from the separate
`halogen-npu-top10-20261004.md` report.

As an explicitly optimistic calculation, charging each miss that observed
initialization cost would require a miss probability below approximately
0.01495% to beat that CPU expert replay: fewer than one miss per about 6,689
calls, even before decoding, transport, shared expert, attention or lm-head
work. Cached contexts could initialize differently, so this is not a measured
miss penalty or a live bound. It explains why an unbounded per-set session cache
is not a sufficient dynamic-routing implementation.

The next implementation choices are:

| Approach | Concrete next probe | Unresolved cost |
| --- | --- | --- |
| Bounded fixed-set cache | Capture real routed sets and time verified context/session reuse | Miss latency, memory and locality are unknown |
| One parameterized top10 graph | Compile a tiny same-shape graph with both expert matrices as inputs, then alternate supplied weights | VitisAI support/fusion and host-to-NPU weight traffic are unknown |
| Resident expert bank with indexed dispatch | Native runtime/kernel prototype with an ID/weight ABI | New dispatch/dequant kernels and memory admission are required |

The parameterized graph is the smallest useful next hardware question. A tiny
shape test can establish support before any new full-width weight expansion.
At full width, ten FP32 experts are 196,608,000 bytes (187.5 MiB) per selected
buffer. Feeding that buffer every token may consume the replay's advantage.
Keeping all 512 FP32 experts would require 10,066,329,600 bytes (9.375 GiB) just
for decoded weights. The stored q4c selected payload is about 27.85 MB before
dequantization. These are storage arithmetic, not measured transfers or runtime
resident footprints. No such allocation or graph compilation was attempted.

## Full-head pieces and required native seam

The retained w4b geometry manifest makes the next dense pieces small enough to
inspect independently. These counts exclude norms/state and provider copies:

| Piece | Stored bytes | FP32 matrix bytes |
| --- | ---: | ---: |
| Shared expert plus scalar gate | 2,786,976 | 19,671,040 |
| MTP embedding/hidden projections | 7,372,928 | 52,428,800 |
| Three hyperconnection down/up mixer pairs | 11,428,224 | 78,643,200 |
| Attention q/k/v/output projections | 28,016,896 | 199,229,440 |

These pieces have not been expanded or measured in this phase. Attention also
needs QSA indexing, rotary positions, norms and correct persistent KV/indexer
state. The MLP input is 2560-wide after mixing; the target residual carries four
streams totaling 10240, so the raw target residual cannot feed this helper
directly. The shared target lm-head is outside the 31 MTP tensors and would be
2,542,796,800 FP32 bytes. A full-head plan must handle that output projection and
the token embedding, rather than treating the expert replay as the entire head.
These dimensions come from the retained local geometry/inspector reports and
the official configuration, not a new full-checkpoint read.

The current Halogen upstream still documents native Linux `amdxdna`, host XRT
with its NPU plugin, firmware, IOMMU, and a held top fabric clock for concurrent
GPU/NPU work. Its published NPU architectures are selected small models and
their compatible fine-tunes. The WSL GPU DXG adaptation does not supply that
native NPU host ABI; Flash-Next MTP is not listed as an accepted NPU model.
[Pinned upstream NPU documentation](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/NPU.md).
Upstream says the engine is closed source and WSL is unsupported.
[Pinned upstream deployment scope](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/AGENTS.md).

A native Windows host is technically distinct from enabling those Linux
container flags. Windows ML documents C/C++ catalog discovery and ORT provider
library registration, which can support a persistent native host without a
Python-per-token process. [Windows ML provider initialization](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/initialize-execution-providers).
The measured verified provider-copy path remains required by the observed
WindowsApps compilation issue. No Windows host service was built in this phase.

A future host bridge needs a versioned, length-bounded binary contract carrying
checkpoint/graph/runtime identities, request and branch generation, sequence
position, target residual dtype/shape, token embedding or token ID, and draft
state ownership. Begin-draft must snapshot target and drafter state; verification
must identify the accepted prefix; commit or rollback must acknowledge that same
branch generation. Stale responses, cancellation, graph misses and EP failures
must return to the authoritative GPU path before committing tokens. MTP KV and
indexer state should remain persistent in the draft owner, with bounded lifetime
and an explicit restore mechanism. Transport and copies need separate timings.

This is a proposed contract, not an available Halogen API. The retained local
seam report finds internal tap/prefill switches but no supported online external
state export or draft import. No newer seam was found in the pinned upstream
deployment surface. Without engine support, a host sidecar cannot replace
Halogen's internal MTP even if its standalone kernels become faster.

Promotion therefore requires, in order: same-checkpoint real trace parity,
dynamic-ID dispatch qualification with all NPU nodes attributed, complete head
and rollback validation, and matched GPU/NPU end-to-end acceptance/throughput
measurement under the existing memory/coexistence guard. The fixed-expert replay
and this host helper are retained as separately scoped evidence.
