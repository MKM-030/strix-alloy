# Halogen MTP MLP event timing seam — 4 October 2026

Separate research sources are prepared to measure the original layer-48,
count-one MLP with HIP events. No timing run was launched while preparing
them. The existing head and routing capture sources and receipts are frozen.

The [event tap](../../scripts/benchmarks/halogen0162_mtp_event_tap.c) retains
the exact engine/function identity and five-byte MLP trampoline used by the
routing seam. Original MLP execution occurs once on every path. The
[launcher](../../scripts/benchmarks/halogen0162_mtp_event_tap_launcher.py)
fixes v2, context 262144, prompt cache Off, MTP depth 2, one slot and the
18-GiB reserve; it changes only `service.build_manifest`, appending one
read-only SO to the original preload. The original controller owns admission,
memory guards, normal shutdown and RAM recovery.

## Stream qualification

The retained exact ELF has 77 direct MLP `__hipPushCallConfiguration` calls:
70 explicitly zero R9 (stream), and seven use the selector at `[rsp+0xb0]`.
Count one takes the branch at `0x17bd4ba` to `0x17bd5ba`, zeros EDX at
`0x17bd5c5`, and stores zero to `[rsp+0xdf]` at `0x17bd5c7`. The selector
at `0x17c56c0..0x17c56c8` consequently stays zero, disabling the optional
expert side stream. All six launch configurations in shared helper
`0x17ca200` also zero R9.

The optional hipblasLt router at `0x17bd737` calls helper `0x18c6c60`, which
uses cache lookup `0x18c4f60`, optional tuning `0x18c6290`, and execution
`0x18c6850`. The handle pointer at global `0x18db4d8` is assigned the global
object `0x18dce70` at `0x176e3be/0x176e3c5`. Its constructor zeroes the
16 bytes at offsets `0x40..0x4f` at `0x18c43ef`; offset `0x48` is the
stream field. Execution passes it as the final argument of
`hipblasLtMatmul` at `0x18c68cb/0x18c68e7` and
`0x18c69f9/0x18c6a18`. Tuning uses the same handle field for matmul,
stream synchronization and its own events. The apparent offset-`0x48`
stores at `0x18c5d48` and `0x18c6674` update separate descriptor/vector
ends, rather than the handle stream.

The new tap also checks the live handle field before/after each sampled
MLP and observes executed `hipLaunchKernel`, `hipblasLtMatmul`,
`hipMemcpyAsync` and `hipMemsetAsync` stream arguments. A nonzero stream,
changed model/handle or API failure disables timing while preserving original
execution. A sample must observe at least one kernel launch. The installed
ROCm 7.2.0 hipblasLt header confirms the 16-argument matmul ABI used by the
observer. Library internals rely on that API's explicit stream contract;
they have not been exhaustively disassembled. Live qualification remains
required before interpreting a result.

Read-only audit evidence:
`server/.local/optimization9h-20261004/mtp-event-static-20261004.json`,
SHA-256 `a85a364b0d5a2dc16f988b0cae11af66e417df8848130a11118aaf37c0ba354c`.

## Measurement and lifecycle

During the first unarmed ordinary MLP call, the tap creates 128 pairs of
timing-enabled events (flags 0). The coordinator checks this completed pool
after its existing 8K prompt calibration and before publishing the exclusive
arm file. Each eligible call records start on stream 0, runs the original
MLP, and records end on stream 0. CPU duration covers the original host call
and launch observation. Metadata and counters stay in a fixed array. There
is no injected per-call synchronization, copy, allocation or file write.

After receiving the complete matched 8192-input / 128-output response, the
coordinator publishes the exclusive harvest trigger. The worker freezes the
array, waits once on the final recorded end event, reads elapsed times and
destroys the pool. It exports six regular files under a 256-KiB bound before
requesting normal service stop. The coordinator requires the historic prompt,
request and stock output hashes, validates every timing row and stream
observation, and retains ordinary cleanup/recovery evidence. A hard 128-call
cap remains independent of the request.

The prepared coordinator is
`server/.local/optimization9h-20261004/run_mtp_event_timing.py`. Its
`--prepare-only` mode and the launcher's `--print-only` mode start no engine.
The C build passed `-O2 -Wall -Wextra -Werror`, and both previews passed.

These measurements are instrumented stream brackets. They include GPU waits,
CPU enqueue gaps and launch-observer overhead, and exclude earlier work
ordered before the start event. They are not sums of kernel busy time, exact
uninstrumented latency, accepted-token timings or an NPU speedup. They can
establish a component cost to compare with a future complete NPU MLP path,
including its required data movement and scheduling costs.

## Completed root-owned timing

The guarded run captured 73 original MTP MLP calls with the historical 8K/128
request and stock output SHA-256 unchanged. All observed executed streams were
zero. It observed 584 kernel launches (eight per call), no hipblasLt calls, and
no original asynchronous copies or sets. There was one final-event wait after
the response, no injected per-call wait/copy/write, and all 256 events were
destroyed. Original owned shutdown and RAM recovery passed.

| Instrumented MLP GPU bracket | Milliseconds |
| --- | ---: |
| Mean | .404611973 |
| Median | .390228987 |
| p95, nearest rank | .487067997 |
| Minimum / maximum | .347234011 / .679159999 |
| Sum over 73 calls | 29.536674023 |

Mean original host enqueue duration was .018300178 ms. Physical/commit headroom
minima were 24,495,058,944 / 122,672,996,352 bytes, above the 18-GiB floor.
The event brackets retain the scope restrictions above. These numbers do not
establish a complete NPU or end-to-end comparison. The earlier synthetic fixed
expert NPU replay at about 1.5 ms uses different fixtures and only a subgraph;
it supplies no demonstrated advantage over this native complete MLP.

Retained run:
`server/.local/optimization9h-20261004/mtp-event-timing-b3437ba2bb1f4e5697a02e266fd5952a`.

| Receipt | SHA-256 |
| --- | --- |
| Terminal result | `eee7b6f12dd2cb4718f77b521d3bfebd5fc388a2adff09a64f47cb8624ed4757` |
| Event statistics | `2b923accfab79f3f34bd77e8056e622f587c4aee02c7d15d0797c6bacbfe2da8` |
| Original cleanup/recovery | `49482e37b72cb7c3c3f142ebdd08b9b24c2073269347c23a1c9d4bb5bb99bc9e` |
