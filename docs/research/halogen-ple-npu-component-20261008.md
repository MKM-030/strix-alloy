# Actual PLE NPU component: full development-tolerance passage

One Root-owned PLE component run completed on 8 October 2026. It used the
unchanged original layer-1 key/value BF16 weights, the frozen native input for
8,192 token rows and the public Python FLOAT-return API. All 104,857,600 values
pass the existing NPU development tolerance `rtol=0.03, atol=0.003`. This does
not repair the stricter CPU result or establish bit-exact native equivalence.

| Output | Values compared | NPU tolerance failures | Different native BF16 words | Maximum absolute error |
|---|---:|---:|---:|---:|
| Key | 83,886,080 | 0 | 70,621,941 | 0.01171875 |
| Value | 20,971,520 | 0 | 17,951,048 | 0.00390625 |

Both complete outputs are finite and lie on the BF16-widened FLOAT lattice.
They were saved before profiling/comparison and independently rehashed after
the child exited. The 400 MiB returned pair reflects the public FLOAT API;
the corresponding native BF16 pair occupies 200 MiB. No weight modification,
oracle correction, graph rewrite or tolerance change occurred.

## Observed timings and attribution

| Observed interval | Milliseconds |
|---|---:|
| Session creation including first compilation | 26,610 |
| Input feed copy | 15 |
| Sole synchronous `session.run` and public return | 203 |
| ORT host `model_run` interval | 200.598 |
| VitisAI provider Node host interval | 200.452 |
| Binary output persistence | 485 |
| Complete output hash/oracle comparison | 2,906 |

These are separately observed component/host intervals. Persistence is an
evidence cost, not a measured production handoff. This single first call has
no warmup or repeated latency cohort; steady-state performance is unqualified.
No component milliseconds are converted into serving token rates.

The fresh compiler context has one VAIML `runnerType=hw`, `deviceName=stx`
partition covering all six required dynamic key/value accumulators, BF16 casts
and FLOAT widenings. Its constants are `key_W_T` and `value_W_T`. CPU fallback
was explicitly disabled. Exactly one VitisAI provider Node event lies inside
the sole ORT `model_run`; there are no CPU Node events. CPU appearing in the
registered provider list does not mean it executed a graph node.

The provider also emitted an EndProfiling error saying it supplied no events
to `OrtProfilingEventsContainer`. Independent NPU device events and clocks are
therefore unavailable. The retained ORT Node event is a host/provider interval,
not pure device compute. Internal provider host work is unobserved. Bridge,
NodeIndex and linker warnings remain preserved in the raw stderr; their cause
is not inferred.

The earlier intrusive native control observed 43.614605 ms for key FC and
11.138067 ms for value FC, plus 38.640195 ms for publishing retained results.
Different runtimes, observation costs and cache histories prevent treating
these as a matched production comparison. The 203 ms NPU call establishes no
synchronous-offload speed advantage. A useful future design would need an
independently available early input, a measured preparation lead and a complete
Windows-to-WSL publication path, followed by unchanged-workload engine results.

## Lifecycle and decision

One session and one public run were attempted, with zero retries. Child and
guard exited zero; the owned job closed, provider unregistered, DLL directory
closed and bootstrap shut down. No server lifecycle operation or inference
request was performed. The 22 GiB admission and continuous 18/18 GiB reserve
checks passed; minimum physical reserve was 23.707989 GiB and minimum commit
headroom 113.323551 GiB. The original visible ServiceNow server was freshly
verified ready and idle on port 8840 afterward.

The authorized v2 startup allowance remains 35 GiB physical / 131 GiB commit
for context 262144 in both backend source profiles. Runtime reserve remains
18/18 GiB. The component and server were observed above their limits; no claim
is made about startup sufficiency at exactly 35 GiB.

The prototype remains outside production. Prefill, Decode, native MTP acceptance
and their NPU-on/off deltas have not been measured for this component. The full
acceleration goal remains unachieved. Do not repeat this unchanged component
merely to add diagnostics. The companion JSON binds the source/config review,
full raw result, both binaries, context/profile, warnings, cleanup and final
server verification. Tool session 86361 is terminal with exit zero.
