# Halogen NPU bridge research — 2 October 2026

## Verified local facts

- FastFlowLM 1.0.7 NPU runtime validates on the BOSGAME Ryzen AI Max+ 395.
- A live `qwen3:0.6b` NPU2 sidecar was started on port 8877.
- The pinned Halogen 0.15.1 `flash_serve` was extracted from the release image;
  SHA-256 is `81a5f68fe418358b8684cdd520651fa14217d586409fcc1a0e8a81bb5e3ec4af`,
  matching the repository pin.
- The old analysis binary and the pinned 0.15.1 binary are different. The old
  binary exposes `--drafter-taps` / `--drafter-hidden`; 0.15.1 does not.
  0.15.1 does contain internal `HALOGEN_TAP_FROM_SCAN`,
  `HALOGEN_MTP_PREFILL`, `state_segs` and `state_segs_src` paths. Static
  xref inspection shows the first two default enabled; they are not IPC hooks.
- The exact w4b checkpoint was inspected through Halogen's own 0.15.1 inspector.

## Flash-Next MTP geometry

The checkpoint carries 31 `mtp.*` tensors:
- 21 q4c tensors, 1,476,636,384 bytes.
- 10 bf16 tensors, 2,710,016 bytes.
- hidden size 2560; hyperconnection state width 10240 (4 streams).
- 512 routed experts, top-10 per token, expert intermediate size 640.
- The two routed expert matrices account for ~1.426 GiB of the head, but one
  token touches only ten experts. From the stored tensor sizes, the selected
  routed expert payload is ~27.85 MB per draft step before dense attention,
  shared-expert, mixer and lm-head work.

This sparsity is why an NPU draft head remains worth prototyping: the whole
1.48-GB head need not be streamed per token.

## FastFlowLM comparison

The shipped FastFlowLM 1.0.7 `qwen3_8mtp_npu.dll` is a real NPU implementation.
Its release binary contains `speculate_npu`, `npu_mtp_layer`,
`MTP_layer.xclbin`, NPU lm-heads and exported `mtp_draft()`. It explicitly
reports no host fallback for the 64 decoder layers / draft head in this build.

It cannot be used directly for Flash-Next:
- Qwen3.8-27B hidden width is 5120, Flash-Next is 2560 + four 10240-wide
  hyperconnection streams.
- 27B's MTP layer is dense; Flash-Next's MTP layer is a 512-expert top-10 MoE.
- Flash-Next has hyperconnection mixers absent from the 27B head.

FastFlowLM's Qwen3.6-MoE DLL does contain NPU expert-prefill machinery and MoE
routing, so the practical implementation path is to reuse design/components,
not the existing Qwen3.8-27B bitstream verbatim.

## Decode design

Target design:

Halogen target GPU -> 10240-wide target state -> Flash-Next-specific NPU MTP
graph -> draft token(s) -> Halogen GPU verifier.

The target verifier remains authoritative. Rejection must restore the exact
Halogen target/drafter state. A sidecar whole model is not part of this path.

The online blocker is Halogen 0.15.1: it has no supported external state export
or draft-import endpoint. A new binary/source seam is required. Until that seam
exists, no standalone NPU process can replace Halogen's internal MTP work.

## Prefill design

A second model prefilling on the NPU does not accelerate Halogen because its
KV/DeltaNet/hyperconnection state is not interchangeable. The first viable
prefill offload is therefore a contiguous Halogen subgraph with state handoff.

The highest-value first candidate is MTP priming, not target prefill:
`HALOGEN_MTP_PREFILL` already identifies a separate draft-head prompt phase.
Moving that phase to the same future Flash-Next NPU MTP graph can reduce first
decode latency without requiring all 48 target layers to move.

Full target-prefill offload remains behind the state-import/export seam and must
beat the already measured ~1.5k tok/s Halogen PP8192 path end-to-end.

## NPU coexistence control

Earlier measured Halogen-v2 coexistence showed continuous independent NPU work
reduced GPU decode by roughly 6.5–7.6%; throttling with 4-second gaps reduced
the loss to roughly 2–3%. Therefore independent continuous sidecar work is not
promoted as a Halogen speedup. The checked-in A/B harness fails closed above a
1% GPU regression.

## Current artifacts

- `scripts/benchmarks/halogen_npu_scheduler.py`
- `scripts/benchmarks/halogen_npu_ab.py`
- `scripts/benchmarks/halogen_npu_seam.py`
- `scripts/benchmarks/halogen_npu_bridge_probe.py`
- `docs/research/halogen-npu-seam-20261002.json`
- `docs/research/halogen-mtp-geometry-20261002.json`
- `docs/research/halogen-npu-bridge-probe-20261002.json`
- `docs/research/halogen-w4b-inspect-20261002.json`

The large inspector JSON is evidence only; no model weights are copied into Git.

## New microbench evidence

The machine's own XRT validation was run with no FLM workload active:

- NPU GEMM validation: **51.3 TOPS**, PASS.
- NPU latency validation: **87.0 us average**, PASS.
- NPU throughput validation: **54,778 op/s**, PASS.

The HGN v2 container format is now parsed directly by
`scripts/benchmarks/hgn_extract_mtp.py`, using the public HGN 1.0.1 container
and q4c storage specification. The parser reproduced the inspector's 31 MTP
tensors and 1,479,346,400 payload bytes.

`hgn_q4c_slice.py` decodes arbitrary q4c-v2 row ranges without expanding the
whole 1.48-GB head. Expert 0 was decoded successfully:

- gate/up: [1280, 2560], finite, range -0.1582 .. 0.2264.
- down: [2560, 640], finite, range -0.3006 .. 0.2617.

A real one-expert ONNX graph was generated from those weights:
`gate_up -> SiLU(gate) * up -> down`. With weights resident, Windows ML's CPU
EP measured 100 iterations at mean 0.1019 ms, median 0.0981 ms, minimum
0.0836 ms and p95 0.1370 ms.

This changes the NPU partition recommendation. Individual expert dispatch is too
fine-grained: its dispatch overhead could be comparable to useful work. The NPU
candidate must fuse/batch all top-10 selected experts and, ideally, keep the
attention/shared-expert/lm-head portions in the same persistent graph.

A Windows-ML/VitisAI path is being prepared for exactly that microbenchmark.
The Python Windows ML runtime installed successfully, but the VitisAI EP was
reported as NOT_PRESENT and its automatic provider acquisition had not completed
at the time of this evidence snapshot. No NPU ONNX latency is therefore claimed.

## Weight conversion path

The implementation now has three reversible stages:

1. Parse HGN metadata and payload offsets without loading the trunk.
2. Decode only required q4c-v2 rows (including one selected expert) into a
   reference FP32 representation.
3. Generate a standalone ONNX expert graph for CPU/NPU numerical and latency A/B.

These tools are independent of the Halogen server and do not modify model files.
They are the basis for converting the complete top-10 MTP sparse path once the
NPU execution provider is available.
