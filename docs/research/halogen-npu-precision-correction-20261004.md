# NPU precision correction and useful placement — 4 October 2026

The stable-high correction passes the unchanged NPU development tolerances on
both frozen native-GPU FC input sets: zero embedding or hidden elements outside
`rtol=.03, atol=.003` across all twelve alternating calls. Strict compiler
context coverage of all eighteen dynamic outputs and the VitisAI execution
profile also pass, with CPU fallback disabled. This is a component diagnostic,
not full-head parity, a live engine replacement, or a token throughput result.

The corrected path is slower than the original GPU path. Prefill and native
MTP remain on the GPU, and the colleague's current server remains open.

## What changed

The original projection candidate reduced BF16 operands through the provider's
BFP16 arithmetic and failed its numerical screen. The generic correction
splits each activation and weight into a high part and a residual, evaluates
all four matrix products, and retains the original final BF16 boundaries.
Static weight preparation happens once; activation preparation happens per
call. The source operands, native-GPU oracles and tolerances remain unchanged.

Two concrete issues were diagnosed and corrected:

1. ORT fused six MatMul/Add pairs into Gemm operations. The default session's
   CPU profile proves those exact six fusions. The compiler context then lacked
   their original partial-product names. The diagnostic now explicitly uses
   `ORT_DISABLE_ALL` for both CPU and NPU; its receipt and cache identity bind
   that setting. All eighteen placement requirements remain intact.
2. Applying the documented BFP quantizer again changed some one-pass high
   parts. The final sibling iterates the same generic quantizer until applying
   it again is bit-exactly stable. A fixed eight-check limit rejects
   nonconvergence. Iteration histories, reconstruction, residuals and an
   independent final quantization check are retained. There are no
   oracle-selected operand values or per-element fixes.

Both one-pass and stable candidates are preserved separately. The stable
candidate's high parts converge, reconstruct the original operands numerically
with their residuals, and have zero high-part requantization mismatches on the
retained weights and inputs.

## Frozen native-GPU numerical screen

Each paired-FC measurement uses four warmups and eight measured calls,
alternating A/B. Embedding output has 2,560 elements and hidden output has
10,240. The table counts elements outside the original NPU tolerance in one
representative call of each stable input set; all repeats have identical hashes.

| Candidate on actual NPU | Embedding A / B failures | Hidden A / B failures | Placement and profile |
|---|---:|---:|---|
| Original paired FC | 0 / 1 | 882 / 962 | Pass |
| One-pass high/residual, explicit ORT optimization disabled | 0 / 0 | 6 / 8 | Pass |
| Stable-high/residual, explicit ORT optimization disabled | 0 / 0 | 0 / 0 | Pass |

Passing tolerance does not mean identical BF16 words. Stable NPU hidden outputs
still differ in 3,648 / 3,614 words; maximum absolute hidden error is 0.015625,
within the declared relative-plus-absolute test for the affected values.
No logits, generated proposals or end-to-end acceptance were tested with these
outputs substituted into Halogen.

The one-pass CPU candidate passes its distinct `.002/.0002` screen after
disabling fusion. The stable CPU candidate still fails one B-hidden element
out of 10,240, differing by one BF16 ULP, 0.00048828125. This failed CPU receipt
is preserved and admitted only for the standalone diagnostic. Normal service
admission remains closed; no production gate was bypassed.

## Timing and placement decision

| Original or corrected paired FC | Mean time | Scope |
|---|---:|---|
| Original GPU | 0.311702 ms | Resident paired-kernel GPU event bracket |
| Original GPU | 0.487170 ms | Host enqueue and wait, same original replay |
| Stable NPU | 1.850025 ms | `session.run`, excluding preparation/diagnostics and compilation |
| Stable NPU | 3.539513 ms | Per-call high/residual preparation and diagnostics, copies and `session.run` |

The NPU session alone is about 3.80 times the instrumented GPU host bracket.
The complete diagnostic call is about 7.27 times that bracket, including
diagnostic preparation overhead that a future optimized implementation could
reduce. Even excluding all preparation, no useful synchronous replacement is
demonstrated. Windows/WSL transport, upload and live engine scheduling are not
included. GPU timing excludes setup, input/output copies, validation and file
I/O. These component brackets are not a matched engine A/B benchmark.

The decision is to keep the original GPU FCs, trunk prefill and native MTP.
There is no measured NPU-induced prefill/decode tok/s delta or acceptance gain.
The earlier static expert NPU prototype was also slower than its matched CPU
run. An asynchronous embedding projection cache remains a
[separate source-only feasibility design](halogen-mtp-embedding-cache-feasibility-20261004.md),
with no established NPU advantage over native GPU memoization.

## Existing regular engine measurement

| Actual input | Output | Prefill tok/s | MTP decode tok/s | Acceptance |
|---:|---:|---:|---:|---:|
| 8,192 | 128 | 1,239.198392 | 42.150412 | 60.0% (207 / 345) |

This retained run uses nonrepetitive greedy prose, one warmup, three measured
requests with identical output hashes, cache Off, MTP depth2 and PLD3,3.
The model is Halogen 0.16.2's native v2 checkpoint. Context capacity is 262144;
the row measures 8192 occupied input tokens. It predates this precision work,
and has no NPU output substitution. Historical 48.423621 decode is a separate
retained result and is not relabeled as this current profile's measurement.

## Evidence and state

[Sanitized precision receipts and timings](halogen-npu-precision-correction-20261004.json)
bind both earlier failures, the one-pass measurements, the final stable CPU/NPU
measurements, original GPU budget and regular engine result. Raw outputs,
compiler contexts, profiles and owned-process receipts remain in ignored local
evidence directories. Sources were independently reviewed by the two component
authors; actual builder and provider execution was performed only by the root.

All owned jobs closed, all monitors stopped and no cleanup remains pending.
The final NPU window maintained at least 27.151180 GiB physical reserve and
119.531128 GiB commit headroom, exceeding the continuous 18-GiB reserve. The
colleague controller run `c4b3c8be6b584d4c901b43e54cc6e8d8`, PID 28488, backend
PID 2504, profile hash `39faa5d1c98289be76d76a396aafd6ae4fe44cba673e61354a8d63f4540b3de7`
remained ready and idle at 21:51 UTC. Models, original weights, drivers, BIOS,
voltages and global WSL settings were preserved. No live NPU offload is enabled.

The full optimization goal remains open: passing this frozen NPU screen does
not establish full head correctness or useful engine acceleration. The
[21:38 update checkpoint](halogen-update-checkpoint-20261004-2138.json) records
the separate official release and driver-channel check; no installation was
performed.
