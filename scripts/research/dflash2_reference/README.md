# DFlash2 numerical reference components

This package implements real components of the pretrained
`incoai/Qwen3.8-Flash-Next-DFlash2` architecture. It contains no checkpoint
weights, complete trained proposer, target feature exporter, native engine hook
or device backend. Synthetic fixtures establish arithmetic
against pinned upstream source; they establish no learned quality, acceptance
or serving speed.

Importing `contract`, `math_ops` or `source_oracle` imports no tensor runtime,
selects no device, downloads nothing and performs no inference. Numerical work
starts only when an operator is explicitly called with caller-owned tensors.
This stage is tested on CPU only. Do not interpret the upstream SGLang
`is_npu` branch as an AMD Windows XDNA implementation.

Repository-root imports use the namespace package, for example
`from scripts.research.dflash2_reference import math_ops`. Internal package
imports are relative, so an unrelated top-level `contract` or `source_oracle`
module cannot supply their bindings. Standalone test-file execution is also
supported. Both forms retain passive imports.

`contract.verify_saved_contract()` uses only the standard library. It checks
the actual model config and exact81 BF16 tensor names/shapes/contiguous header
extents:603,065,600 parameters. It never opens tensor payloads. Target features
must eventually be the completed-layer means of four raw HC streams at layers
5,15,25,35,45; old Pixel normalized HC taps are incompatible. Target embeddings
and the full output head remain external dependencies.

The implemented convolution uses width2560, group width16,160 groups, two taps,
projection[640,2560] and base[input/output,2,2560]. `prepare_convolution` returns
the input convolution and the output coefficients computed from that same
input. `finish_convolution` reuses those coefficients with the output-side
base. The predecessor shift resets independently at block4/block8 boundaries.
FP32 and BF16 outputs preserve upstream operation/materialization order;
compatible strided inputs are accepted. Invalid scoped geometry, shapes and
dtypes are rejected. No inplace writes are introduced.

`score_edges` takes *already projected* rank256 hidden rows, top16 candidate
IDs and FP32 unary logits. It computes the upstream pairwise lattice, with the
verified anchor as every predecessor at the first edge. `follow_maps` follows
precomputed successor indices. These functions do not compute the vocabulary
head/top-k, hidden projection, sampled proposal distribution or verification
correction. Table bounds alone do not establish tokenizer-defined IDs.

`source_oracle` independently AST-extracts `_grouped_conv`, `_score_edges`,
`_follow_maps` and the actual `DFlashGroupedConv` class from the full retained
SGLang source. It verifies the source SHA before compiling only those
definitions. Arithmetic bodies remain unchanged; only compilation decorators
and `torch._dynamo.mark_static` statements are removed. SGLang, FlashInfer,
Triton and distributed code are not imported or executed.

Run the passive plan with any Python interpreter:

```powershell
python -B scripts/research/dflash2_reference/test_math_ops.py
```

Explicit CPU test run using the existing PyTorch interpreter:

```powershell
& 'C:/Users/Marcel/AppData/Local/Programs/Python/Python312/python.exe' -B `
  scripts/research/dflash2_reference/test_math_ops.py --run-cpu
```

The tests set intra-op/inter-op threads to1, disable gradients and explicitly
allocate CPU tensors. The largest fixture parameter is640×2560 FP32 (6.25MiB);
selector fixtures use32 table rows with the real rank256/top16 dimensions,
rather than allocating a complete248,320-row vocabulary. No model tensor data,
accelerator API, download, compilation backend or inference engine is used.
The test module's own default is passive; it requires `--run-cpu` to execute.

`context_kv.py` implements the actual17-tensor context partition: target feature
projection, hidden normalization, five independent K/V projections and K
normalization/RoPE. It returns private owned CPU tensors. Selection copies only
verified input rows (anchor plus accepted proposals); the correction/bonus
token has no computed hidden row yet. Caller metadata assertions are not native
lifecycle authority. The BF16 arithmetic is checked at zero tolerance against
the hash-pinned original native/sequential RMSNorm and RoPE methods. It differs
from the fused GPU path, whose intermediate rounding needs its own validation.

`attention.py` implements the author's actual block layout and common
block-end window: every query sees keys in
`[max(0,prefix+block-2048),prefix+block)`, including future query rows, while its
own RoPE position stays `prefix+row`. This is the model-card TRT backend's
expanded single-token-decode layout, realized here using CPU SDPA. A generic
per-query causal window or SGLang TorchNative's normal encoder-extend path
would implement a different mask. No GPU kernel identity is claimed.

`backbone.py` connects real query QKV/norm/RoPE/attention/output projection,
two learned grouped-convolution wrappers, residual normalization, MLP and final
normalization across five layers. It consumes actual caller-owned embeddings
and per-layer committed context KV. Tests compare FP32/BF16 block4/block8 with
the original AST decoder/norm/activation methods. They use synthetic weights,
not model parameters or target hidden states. There is no target embedding/head
sharing, native feature publication or token acceptance implementation in this
backbone.

`proposal.py` completes the dense TP1 CPU top16 and learned rank256 greedy
selector arithmetic. It discards each query block's anchor hidden row exactly
as the original worker does, casts predicted hidden rows to the supplied full
head's dtype, crops to the explicit original vocabulary prefix, and follows
predecessor-dependent selector maps. Greedy probabilities are point masses.
The independent AST oracle executes the actual DFlash classes and whole worker
sampler. CPU tests use synthetic32/64-row vocabularies with real2560/256/16
dimensions; they do not establish full-head-scale performance, actual defined
tokens, learned quality or FlashInfer/GPU top-k tie behavior. The full pinned
worker source is bundled; no ignored local path is required by this component.

The additional explicit CPU checks are:

```powershell
& 'C:/Users/Marcel/AppData/Local/Programs/Python/Python312/python.exe' -B scripts/research/dflash2_reference/test_context_kv.py --run-cpu
& 'C:/Users/Marcel/AppData/Local/Programs/Python/Python312/python.exe' -B scripts/research/dflash2_reference/test_attention.py --run-cpu
& 'C:/Users/Marcel/AppData/Local/Programs/Python/Python312/python.exe' -B scripts/research/dflash2_reference/test_backbone.py --run-cpu
& 'C:/Users/Marcel/AppData/Local/Programs/Python/Python312/python.exe' -B scripts/research/dflash2_reference/test_proposal.py --run-cpu
```

These CPU components produce no measured serving Prefill, Decode or acceptance
values. They must not be enabled in the normal server or represented as an NPU
speedup before actual native data/ownership and end-to-end qualification.

Source/provenance and Apache-2.0 attribution are in `provenance.json`,
`NOTICE` and `sources/SGLANG_LICENSE`. The original full source is preserved
under `sources/sglang_dflash.py` for audit only and must not be imported.
