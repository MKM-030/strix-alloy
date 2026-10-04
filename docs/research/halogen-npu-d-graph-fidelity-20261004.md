# Count1 D graph fidelity and actual NPU compiler failure

The immutable D preparation graph was attempted on the NPU after a separate
CPU-ORT graph-fidelity check. NPU inference did not execute: the actual compiler
failed to place `SinglePassRMSNorm` buffers in L1. CPU fallback was disabled and
the failed session was closed. This is a concrete placement failure, with no
speed or acceptance result.

The new [graph probe](../../scripts/benchmarks/halogen_npu_v2_d_graph_probe.py)
has source SHA256
`43eeebe26cbc0312832dd65a756c030380e13c964e47363c31f5598cb6a2697f`.
It introduces an explicitly named `ORT-graph-output` oracle containing the
retained stable original CPU-ORT seed words. The [original failed NumPy
screen](halogen-npu-d-prepare-20261004.md), its outputs and frozen tolerances
remain intact. That separate screen continues to fail. Matching the ORT graph
cannot establish native full-D arithmetic parity.

The original model SHA256 is
`3dd6940b38d788643b709837959d36ab16d1b926e548121b6f6efcc554147518`;
its build receipt SHA256 is
`06bba1a8bb9658047ce12292becf7bbee9d639498a345aaf3019af4540bcfd99`.
No original graph, external data or weights were modified. The new probe
verifies source, graph, data, fixture and baseline identities. NPU initialization
requires a successful CPU receipt from the same new probe and identical inputs.

| Window | Sessions / completed calls | Result | Minimum physical / commit headroom |
|---|---:|---|---:|
| `d-graph-cpu-c2cb59db863b488ba8f429f8b86655e0` | 1 / 12 | Exact retained CPU-ORT seed bit parity; 348 CPU node events | 47.012 / 201.771 GiB |
| `d-graph-npu-ac1c53d5240d4e068f912e89078dc290` | 1 attempted / 0 | Compiler L1 failure; fallback rejected | 46.729 / 201.443 GiB |

Raw evidence is under `server/.local/optimization9h-20261004/` in those two
exclusive windows. The successful CPU receipt SHA256 is
`8e3cf1010335d1274ebe727900fccb72828ebd3c60cf5149ca449e1a2b9f4700`;
the frozen original failed CPU baseline is
`6d140e5abd82b9fa1b90db80b10bf8eb43b5bc4858d9a9bdae47f2dd65b5fb3d`.
Both owned jobs closed, both memory monitors stopped and neither window has
cleanup pending. The actual provider copy was
`C:\AI\halogen-mtp-npu\npu-ep-1.8.75-20261004`.

The compiler identifies `SinglePassRMSNormTGTiling(e_square_Duplicated_1)` and
reports that total L1 buffers exceed capacity. No returned NPU output exists.
The next candidate splits the whole-row sum into fixed 256-element tiles,
preserves the original norm/product/BF16 and FC boundaries, and exposes partial
sums to prevent losing the intermediate reduction boundary. Its changed FP32
summation order requires fresh numerical checks. Compiler support and useful
end-to-end latency remain to be measured; source construction alone proves
neither.

The [actual original GPU RMS replay](halogen-hidden-rms-standalone-replay-20261004.md)
now establishes exact NumPy RMS agreement on the two frozen hidden inputs. It
does not establish complete FC/seed, head state, verifier or acceptance parity.

## Fixed256 candidate execution

The new [transformer](../../scripts/benchmarks/halogen_npu_v2_d_tiled_graph.py)
and [probe](../../scripts/benchmarks/halogen_npu_v2_d_tiled_probe.py) were reviewed
and root executed one build and one CPU window. The transformer has SHA256
`52f8bb4f9546135d1d85c5786468cf65ade68cdeda1cd16ffd7efc276ce56485`;
probe SHA256 is
`08bbb8078ff1bda1ed0d06f2455b1844d1395831e05dc9333ef5ed13a1660bca`.
The original graph, 52,480,000-byte external data, gamma, epsilon, FC matrices
and BF16 boundaries remain unchanged. The candidate changes FP32 reduction
order and returns partial sums and norm diagnostics in addition to the seed.

Candidate graph SHA256 is
`5f9c711ed7b2554d63fa393e7dda249b45f305f5d5717f7b94880a5aa956eb00`.
It is retained beside the original external data as
`C:\AI\halogen-mtp-npu\v2-d-prepare-20261004\d-prepare-tile256-c51427b7d56e41188e6b7d7426e306bb.onnx`.
The owned build passed and closed, with physical/commit minima
50.905/207.860 GiB.

| Input | Hidden RMS vs actual native words | Seed vs original ORT words / outside tolerance | Seed vs NumPy words / outside tolerance |
|---|---:|---:|---:|
| A | 0 | 107 / 73 | 2 / 1 |
| B | 0 | 76 / 55 | 0 / 0 |

Each column compares 10,240 BF16-widened values per input. The original CPU
tolerances remain `rtol=0.002, atol=0.0002`. A's seed maximum absolute error
against NumPy is 0.00048828125. Its maximum error against original ORT is
0.00390625; B's is 0.0078125. The original failed ORT-vs-NumPy evidence stays
separate. Native agreement here is for hidden RMS only; the native FC/seed
result has not been replayed.

All twelve balanced CPU calls completed with stable finite outputs on the
required BF16 lattice and distinct A/B hashes for all five observable outputs.
The profile proves 444 CPU-only node events. The overall seed gate failed,
therefore **no tiled NPU session was started** and compiler fusion avoidance
remains unqualified. No timing, speed or acceptance result is promoted.

The raw window is
`server/.local/optimization9h-20261004/d-tiled-cpu-ca80a5b5fead40a7bcb0c10f2875060a`;
its CPU receipt SHA256 is
`15a8b999391dd4e3a9bc342f3809180e956ab65150025949ef89630459668cc6`.
The child exited 1 for the preserved numerical failure, while the owned job
closed normally, the reserve monitor stopped and cleanup is not pending.
The outer physical/commit minima were 49.492/205.921 GiB; the inner guard
observed 49.455/205.880 GiB, above the 18-GiB reserve.

The next arithmetic gate is the original native FC/seed computation on the
same frozen normalized inputs. The matching hidden RMS is useful progress,
but does not justify changing the seed tolerance or calling the NPU path
integrated. Complete head/history/verifier work and useful throughput remain
open.
