# Native vector H: stop before live integration

5 October 2026. Source/text and retained-receipt review only. No hardware,
WSL, compiler, tests, imports, engine lifecycle actions, or pinned-source edits.

**Do not schedule a live vector-H cohort or another timing run merely to expand
the gates.** The current native path has no demonstrated mechanism that could
beat the original GPU dependency. Its fastest retained complete sample is
355.6 µs, already about 2.24 times the original H device bracket, before the
required GPU capture, Windows bridge and GPU publication.

| Retained result | Time | Actual scope |
| --- | ---: | --- |
| Original H mean | 158.707124 µs | M4, resident normalized BF16 input/output; GPU events; copies excluded |
| Original E→H host mean | 487.170063 µs | Both M1 and M4 enqueue/event-wait; not an H-only budget |
| Vector H call 0 | 2969.9 µs | Host transpose, poison/sync, native launch/wait, output sync/readback |
| Vector H call 1 | 355.6 µs | Same complete scope; native launch/wait alone 348.5 µs |

The GPU receipt has four warmup pairs and sixteen measured balanced A/B pairs;
H ranges from 150.858 to 174.740 µs. The vector receipt has two distinct A/B
calls, zero warmups, all 20,480 checked values inside the frozen NPU tolerance,
one differing BF16 word and maximum absolute error 0.000488. Initialization is
525500.6 µs. Two samples do not establish steady state. These scopes are not a
matched full transport measurement, so they do not prove universal infeasibility;
they do supply a negative case for spending another live window on this path.

Evidence: [GPU summary](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/alloy-fc-timing-f7c3c720f88f4edfaa0a1adcee68a56d/gpu-timing-summary.json),
[GPU receipt](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/alloy-fc-timing-f7c3c720f88f4edfaa0a1adcee68a56d/native/timing.json),
[GPU timing source](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen0162_fc_timing.c:372),
[vector receipt](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/native-hidden-vector-stopped-component-2dbd6aa0ac934e52ab923c794c607256/native-result.json),
[vector complete timer](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen_npu_native_hidden_vector/host.cpp:281).

The original H input is the whole-row 10,240-element RMS result on the GPU,
viewed as four 2560-element streams. H writes GPU scratch at global 0x18db228;
the native seed-add reads that pointer on the same default stream. The retained
D path goes from H at 0x17db65e to seed setup at 0x17db9bd and launch at
0x17dbb91 without an explicit H-to-seed host fence or copy. Stream ordering
already makes the output available to the consumer. Adding a GPU host wait or
readback to the original arm would create an artificial offload opportunity.

The candidate instead synchronizes before capturing 20,480 bytes to host,
round-trips the H wire through the Windows native backend, copies 20,480 bytes
back into the original GPU output and synchronizes publication. The native
355.6-µs timer includes none of those bridge or HIP operations. The hook's
`readiness_to_visibility_ns` encompasses them, but no retained measurement of
that field was found in this review. Its source-only existence is not a gain.

Evidence: [native pointers and stream](C:/Projects/strix-alloy-clean/docs/research/halogen-native-d-fc-dispatch-20261004.md:79),
[retained H/seed instructions](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/mtp-route-static-20261004/host-text-disassembly.txt:192325),
[candidate capture/publication](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen0162_mtp_h_native_replace.c:402),
[candidate timer field](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen0162_mtp_h_native_replace.c:544).

The earlier prepared-row consumer cannot hide this cost. It accepts one
token-keyed 5120-byte embedding projection and keeps native H. Vector H returns
20,480 bytes from the changing target/head residual, available only after the
late whole-row RMS. This is a different operation and readiness point. An
embedding precompute or hit cannot consume the full H result or establish lead
time for it. See the [embedding consumer contract](C:/Projects/strix-alloy-clean/docs/research/halogen-npu-local-memory-path-20261005.md:25).

If a later concrete implementation changes this negative case, the one useful
finite comparison is identical frozen A/B H inputs **ready on the GPU → H output
usable by the original GPU seed consumer**. Keep original H asynchronous on its
default stream; collect timing events later without adding a per-H host wait,
host copy or transport. The NPU arm includes readiness/capture, framing and
validation, the real resident bridge, transpose, all streamed weights and native
compute, readback, GPU upload and publication. Use a finite cap of four warmup
pairs plus sixteen measured pairs, balancing A/B and arm order; initialization
and first call remain separate. This conditional
comparison is not recommended for the current implementation.

The next distinct mechanism worth source design is an independent compact
token-block drafter: consume committed Qwen token context, keep private draft
state resident, and propose several token IDs for authoritative GPU target
verification. It can reduce repeated target work instead of replacing this
late 158.7-µs component. A token-only design avoids assuming an available target
feature export. First establish the concrete external proposal, verification,
accepted-prefix commit and rejected-suffix discard transaction. The inspected
public Halogen contract exposes builtin `serial`/`mtp`, not those external
operations; private native helper addresses do not constitute a qualified API.
No compatible trained NPU drafter or measured gain exists here. See the
[verified integration limitation](C:/Projects/strix-alloy-clean/docs/research/halogen-laya-jev-sidecar-feasibility-20261004.md:56)
and [private state/rollback gap](C:/Projects/strix-alloy-clean/docs/research/halogen-mtp-full-head-state-abi-20261004.md:65).
