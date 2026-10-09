# DFlash K3 component prototype

This package is disabled by default and does not register with Halogen. Imports
do not load a tensor runtime, initialize an accelerator or acquire model files.
Execution requires explicit local assets, a new result path and root hardware
coordination. It uses the existing pinned CPU reference in
`scripts/research/dflash_k3_reference`.

The fixed-capacity worker owns accepted context, keeps transient query KV out of
that context and copies only the inputs processed by target verification. Native
transaction rounds are kept separate from mathematical proposal rounds. An
optional `OriginalEmbeddingRows` binding validates and maps the complete original
embedding shard once, then returns independent row copies for arbitrary anchors.
No native/Linux GPU address can be passed to this Windows worker.

The GPU candidates use one full-vocabulary BF16 GEMM for the head and two 2D
GEMMs per KV group for attention, avoiding twelve-fold KV materialization.
Default capacity 16640 accommodates a 16K prefix plus generated inputs. Both
candidates remain preparation options; no production defaults changed.

The complete one-row ONNX context exporter copies17 actual BF16 learned tensors
from the pinned drafter. It offers native BF16 and a separate FLOAT graph with
explicit BF16 rounding after each source BF16 materialization. The FLOAT graph
has unqualified differences from source arithmetic. It is not a quantized or
substituted checkpoint. ONNX export is construction/checking only.

`prepare_context_fixture.py` creates a CPU BF16 fixture from the pinned owner
AST. `run_context_ep.py` executes only an explicitly supplied installed EP
library. It never downloads providers or changes drivers. CPU fallback is off
unless explicitly selected. Node attribution and compiler context must be kept
alongside results; a successful process exit proves neither accuracy nor serving
benefit.

Useful entry points:

```text
run_comparison.py --device cuda --capacity 8 --attention-mode grouped2d --pair-head ...
run_long_context.py --execute-root-owned --device cuda --compare-cpu-owner ...
export_context_onnx.py --precision both ...
prepare_context_fixture.py --execute-root-owned ...
run_context_ep.py --execute-root-owned --precision bf16_native ...
```

All programs require explicit checkpoint/config/output paths; see `--help`.
Numerical programs require a monitored owned-process execution window. The
latest hardware runs entered with 22 GiB physical/commit headroom and retained
18 GiB throughout, while the original Halogen server remained ready.

The exact executed source bytes and reports are retained here. The paired head
test reduced its isolated cost 24.82%; the 16K synthetic component test reduced
draft cost 42.72%. These are component costs, with finite checks and host ID copy,
and establish no Halogen token rate or target acceptance. Long-context logits
are not identical even though all three predicted IDs match the CPU oracle.
The measured mixed NPU/CPU one-row graph remains disabled because its cost and
source errors do not justify synchronous decode adoption.

See `docs/research/halogen0173-dflash-components-20261009.md` for scope and raw
evidence. Integration still needs owned native features, transport/fence
acknowledgments, causal scheduling and actual target verification. No target
acceptance or serving throughput was measured by these programs.
