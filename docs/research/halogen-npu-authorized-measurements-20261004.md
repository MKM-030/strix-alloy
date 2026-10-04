# Authorized NPU measurements — 4 October 2026

Four previously unmeasured runnable cuts were executed on the actual NPU between
20:47 and 21:03 UTC. No candidate is integrated into the colleague's Halogen
instance. These are component milliseconds, not generated tokens per second.

| Fresh component | CPU host mean | NPU host mean | Measured calls | Numerical result |
|---|---:|---:|---:|---|
| Native-oriented embedding + hidden FC, BF16-rounded weights | 1.123738 ms | 0.684275 ms | 8 each, after 4 warmups | CPU B-hidden fails 2/10240; NPU hidden A/B fail 882/962 of 10240 |
| Fixed256 D normalization + FC + seed | 1.451075 ms | 1.027963 ms | 8 each, after 4 warmups | NPU seed A/B fail 879/985 of 10240 against retained ORT seed |
| Static expert0, older w4b lineage | 0.227671 ms | 0.496503 ms | 100 each, after 1 warmup | Both pass their declared prototype tolerances; NPU slower |
| Original-FP32 normalized FC + seed suffix | 1.376713 ms | 0.727863 ms | 8 each, after 4 warmups | CPU exact retained ORT seed parity; NPU A/B fail 842/953 of 10240 |

CPU and NPU tolerances retain their original distinct values. The three
projection/seed NPU gates use `rtol=.03, atol=.003`. Native-oriented FC CPU
screening uses `.002/.0002`; no failed field or reference was rewritten. The
fixed256 CPU run predates its NPU run. Expert0 and the FP32 suffix use fresh
sequential CPU/NPU windows. None of these CPU ratios establishes a benefit over
Halogen's original GPU kernels.

The NPU session-run/copy means respectively are 0.676613/0.007663 ms for paired
FC, 1.019063/0.008900 ms for fixed256 D, and 0.718875/0.008988 ms for the FP32
suffix. Session initialization is excluded from all call means. Expert0's NPU
initialization, including compilation, took 18.714985 seconds; its maximum
absolute output error was 0.000623541. Its replay covers one synthetic input,
not live v2 routes.

All four NPU profiles attribute executed Nodes to VitisAI, with CPU fallback
disabled. The FC/D/suffix compiler receipts pass the original required-output
hardware-partition checks. Expert0's retained context names one VAIML/stx/hw
partition with constant weights and output `y`. Internal device-cycle profiling
is unavailable: the provider's own profiler emits a no-event error, while the
ORT Node profiles remain retained. Fixed256 D now compiles and executes despite
the original whole-row RMS graph's earlier L1 compiler failure; its numerical
seed gate still fails.

All owned measurement jobs closed and monitors stopped, including the suffix
child that exited 1 for its arithmetic failure. No cleanup remains pending.
Physical headroom stayed above 27.18 GiB and commit headroom above 118.76 GiB,
exceeding the continuous 18-GiB reserve. Models, original external weights,
drivers, BIOS and global WSL configuration were preserved.

The fresh regular Halogen result is **1239.198392 prefill tok/s,
42.150412 MTP decode tok/s, 60% acceptance (207/345)**. It uses actual 8192 input
tokens and 128 output tokens, greedy prose, one warmup and three measured
requests, cache Off, MTP depth2, PLD3,3, and **262144 context capacity**.
It does not measure 262144 occupied input tokens. The server remains ready at
`http://127.0.0.1:8840/v1` for the colleague, with native MTP and no NPU swap.
There is no measured NPU-versus-GPU prefill/decode delta or acceptance gain.

[Sanitized measurements and receipt hashes](halogen-npu-authorized-measurements-20261004.json)
bind the raw windows. [Earlier candidate inventory](halogen-npu-candidate-inventory-20261004.md)
keeps previous successes, placement failures, provider crashes and absent
implementations separate from these new results.

The original-GPU paired-FC timing budget is now measured in a separate small
replay while the colleague server is idle: sixteen measured A/B pairs after four
warmups average **0.311702 ms** in the GPU event bracket (embedding 0.152995 ms,
hidden 0.158707 ms), with **0.487170 ms** monotonic host enqueue/wait time.
Every timing output byte-matches the four frozen original outputs. Setup,
copies, comparisons and file I/O are outside the brackets; event overhead and
host enqueue gaps remain inside. This is resident component timing, with no
live-engine cache/transport/end-to-end qualification. The owned job and small
container closed and were removed; the colleague server stayed ready.

The existing failed paired-FC NPU host call is already about 2.20 times this
instrumented GPU bracket and 1.40 times the host enqueue/wait bracket, before
cross-WSL copies and transport. The current shadow path additionally runs the
original FCs first, so it cannot establish useful FC skipping. No live NPU FC
offload is enabled.

A generic
high/residual precision correction adds arithmetic and needs its own fixed
numerical/placement gate. Production NPU use requires both passing outputs and
a measured useful replacement/overlap, followed by the same regular Halogen
workload with and without NPU. The full optimization goal remains open.
