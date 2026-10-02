# Repeat qualification — 24 September 2026

**Assessment: share the completed benchmark with caveats; repeat-start
inference and an installable release are not yet qualified.**

These attempts followed the completed original Halogen serving and size
benchmarks. They are separate observations, not extra repetitions folded into
the original averages. All use the same pinned Halogen 0.13.8 image, model,
working DXG bridge and adapters, with a 32,768-position pool, one slot, a
2,048-token arena/chunk, 28 GiB copy cap, ROUTE_GEMM=0, SDMA=1, cache=0 and
selective copied-weight reclaim enabled.

| Attempt | Startup deadline | Readiness | Outcome |
|---|---:|---:|---|
| Original complete-suite run | 240 s | 136.875 s | All 60 serving and 86 size-sweep requests completed |
| Repeat 1 | 240 s | Not reached | Guard timed out at 240.656 s while API was starting; no inference |
| Repeat 2 | 360 s | 265.328 s | WSL distribution powered off after readiness; no inference |
| Repeat 3 | 360 s | 166.250 s | Attached lifetime observer held the server alive; first answer request timed out |

## Bounded startup deadline

The only guard-code change between repeats 1 and 2 was a 360-second startup
deadline, including API readiness. All memory protections remained unchanged:
startup abort below 20 GiB, stable readiness and runtime floor 24 GiB; at most
one startup cache-advice operation, never during timed inference. Twenty-seven
unit tests pass and a scoped independent review approved the deadline change.
This does not fix slow file reads or guarantee a physical RAM reserve.

Original guard SHA256:
`4864bfd19d0a0ea4c696bda7533177b881b86b6757e83bfd9c73cd2cca7aa4f9`.
New guard SHA256:
`d3095dd8c5f182dc8afee73736954a29988fd1fed82238365e835502c841baaa`.

## WSL lifetime finding

Repeat 2 reached readiness at 19:56:39 UTC. At 19:56:52 UTC the Linux system
journal recorded power-off and termination of Docker, followed by Halogen
shutdown. The container ended at 19:56:57 UTC, exit 1, OOMKilled=false. Its
runtime guard could not complete initial inspection, and the answer-check
client failed its initial health request; no inference POST was sent.

The original successful run had a host-attached log observer; repeat 2 did
not. [Microsoft documents that systemd services alone do not keep WSL
alive](https://learn.microsoft.com/en-us/windows/wsl/systemd). The timeline
supports an idle-lifecycle explanation; the internal WSL idle event was not
separately traced. The WSL kernel/VM remaining alive did not mean the Linux
distribution and Docker remained alive. A DXG allocation-destruction warning
was observed during shutdown and is not established as its initiating cause.

Repeat 3 added a Windows-attached, read-only wait for that exact container,
bounded to 900 seconds. Docker remained running across readiness and the full
request timeout; the observer ended when the test container was deliberately
stopped. No WSL service/configuration, driver, BIOS or Windows setting changed.
This experiment is not yet a portable supervised-launcher implementation.

## First-request performance failure

Repeat 3 used the existing draft comparison harness: public prose, code and
verbatim-lookup inputs; serial/MTP, two alternating repetitions, temperature 0,
thinking off, up to 512 output tokens. It stopped on the **first** serial prose
request after the 180-second client timeout. The planned twelve-request suite
was not completed. No MTP comparison or text-identity pass exists for this run.
The [exact public request and failure record](repeat3-request-20260924.json)
is included. The 700-word instruction exceeds the 512-token output budget;
the expected output was a budget-limited fragment, not a complete 700-word essay.

The engine logged progress (310 tokens at 123.4 decode seconds, then 482 at
153.6 seconds). The API logged 488 generated tokens discarded when the client
disconnected and cancelled. These partial progress counters are not a delivered
response or a completed-request throughput measurement. There is no full
answer or final prefill/decode timing pair to publish for this attempt.

Two process snapshots showed a file-page fault/read wait; read-byte counters
advanced between them. This is evidence of file-I/O waiting, not a diagnosis
of a particular physical disk, and not proof of a GPU arithmetic failure.
API health remained OK throughout, so a health check alone is insufficient
as an inference-readiness test. Further cold/warm latency work remains open.

## Windows memory and teardown

| Attempt | Minimum available during startup, bytes | Available at readiness, bytes |
|---|---:|---:|
| Repeat 1 | 29,090,938,880 | Not reached |
| Repeat 2 | 29,101,506,560 | 29,592,473,600 |
| Repeat 3 | 22,556,626,944 | 29,200,605,184 |

Repeat 3's runtime minimum was 28,568,846,336 bytes (28.57 GB; 26.61 GiB),
with no pressure-triggered stop or runtime cache advice. The container was
deliberately stopped after the failed request and ended PID 0, exit 137,
OOMKilled=false. The guard's later container-exit event belongs to this planned
teardown, not to a preceding pressure abort. Windows subsequently recovered
above 81 GB available and device-wide GPU usage fell below 0.6 GB.
All [76 device/Windows memory samples](repeat3-memory-20260924.csv) are included
without private adapter identifiers. They span baseline, loading, runtime and
cleanup; the guarded runtime minimum is from the finer one-second guard log.

## What can be claimed

The original full-suite numbers are supported by their archived data. These
subsequent failures must accompany them. Do not claim stable first-request
speed, a minimum throughput guarantee, all-start success, or clean installation.
The separately requested [fresh 256k capacity test](256k-20260924.md) failed
before readiness and caused severe memory pressure during delayed cleanup.
No occupied-256k throughput was measured; this must not be inferred from 32k.
