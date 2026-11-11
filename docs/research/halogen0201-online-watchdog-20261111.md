# Latest Halogen online, 11 November 2026

The fresh official check confirms **[Halogen v0.20.1](https://github.com/peonist-ai/halogen-flash-server/releases/tag/v0.20.1)** remains latest. Both OCI tags `0.20.1` and `latest` resolve to the installed immutable image `sha256:66dac8dac25bf15f2b63a684bbe3953036045172d881525600ea41d45e5acc73`. The annotated tag is dated 9 November 2026, 15:11:59 UTC; there is no separate formal GitHub release publication time.

The normal public server was stopped once and restarted through its existing lifecycle. Authenticated health, model discovery and an actual chat response of `READY` pass. It remains online with a visible request/response console on port **8840**, request model **`halogen-v2`**. Both API and engine report 0.20.1. Context/pool is 32768, one slot/concurrency one, paired prefill 8192, gate 0.90, PLD `3,3`, prefetch zero and Cache/Thinking/Vision Off. Existing ServiceNow credentials are retained. [Exact snapshot and evidence hashes](halogen0201-online-watchdog-20261111.json).

## Watchdog reliability correction

Only the elapsed-time source changes from three wall-clock reads to integer Linux `/proc/uptime` seconds. The exact upstream/WSL script guards and selected 120-second timeout, 30-second PING, 15-second polling, 900-second compaction deferral, D-state handling and owned cleanup remain. The generated live service entrypoint matches the reviewed preview SHA256 `9f088ea42992f9ebf44301c153c72f1f8267289e9626a49c2abfac91d79f8ab0`.

The regression reproduces an original false shutdown after 15 seconds plus a 136-second forward clock jump. All 16 canonical Git Bash CPU tests now pass, including real timeout, forward/backward clock shifts, PONG reset and 915-second virtual D-state coverage. One earlier run hit the test runner's 10-second deadline during model startup; it is preserved. The final 30-second runner allowance changes no virtual timing, assertion or production limit. Seven startup-inspection and 19 backend CPU tests also pass; eight WSL/GCC tests are explicitly skipped.

The older server incident's precise cause remains unproved. Fixing the wall-clock defect does not establish that a clock jump caused that particular shutdown. GPU kernels, models, drivers and global WSL settings are unchanged.

The first post-start 22-GiB smoke-entry check briefly failed before sending inference. The same ready controller and backend were verified again; the subsequent unchanged admission passed and `READY` succeeded, with no second engine launch. Startup 30/131, entry 22/22 and runtime 18/18 GiB limits are retained. Exact old files and terminal cleanup receipts are preserved for rollback.

## Subsequent availability

The earlier server snapshot was later stopped by the 18-GiB runtime memory guard
after additional Voice-model allocation. One exactly identified owned TTS model
was unloaded under the existing authorization. The new normal launch passed
unchanged 30/131 start admission and later 22/22 request entry, returning an
authenticated `READY`. Controller/backend runs
`54495bb566554fe8a4be00be80f129d5` / `693717e5bba9420f8f1e791ec4adff31`
replace the historical snapshot identities. Original failed recovery evidence is
preserved; fresh five-frame recovery was proven before its owned lock was
reclaimed. The [subsequent stateful NPU component](../benchmarks/halogen0201-stateful-npu-20261111.md)
ends with this recovered server still online and unchanged during both jobs.

## Performance scope

This is a serving/reliability update, **not a new throughput benchmark**. The [last normal serving observations](../benchmarks/halogen0201-normal8192-20261111.md) remain 1475.04 prefill / 47.52 decode tok/s and 61.54% API neural-head acceptance at 8192 inputs; 1447.23 / 45.07 and 55.56% at 16384 inputs. Their phase-clock and acceptance limitations remain unchanged. No NPU producer is enabled; the completed [bulk NPU experiment](../benchmarks/halogen0201-bulk-npu-20261111.md) is rejected for both numerical failure and higher cost. The full acceleration goal remains open.

## Latest online verification, 11:19 UTC

The official package check at 11:07:18 UTC still identifies 0.20.1 and the same
installed OCI digest. After the finite scalar catch-up comparison, the normal
server was restored through its existing lifecycle. Fresh authenticated model
discovery and a 17-input/2-output-token chat request returned `READY`; this
functional check is not a throughput measurement. All 47 normal source members
match manifest `b73f5fa60d47b911a2c3d15caef2aaa1fdc55c50baeb7434544f4bf4500c38f8`.

The current controller/backend runs are
`28f99c01e114418dbf103148e5bdec5b` / `4504311ca2714c209abf1d6608ec3420`,
with exact process identities recorded in the appended
[`latest_online_verification` snapshot](halogen0201-online-watchdog-20261111.json).
These replace the historical identities above. The visible console, existing
ServiceNow credential, `halogen-v2` alias, port 8840 and paired-8192 one-slot
32K configuration remain available. The NPU helper has exited and its four
native contexts are closed; the normal profile does not enable it.

The [subsequent finite NPU comparison](../benchmarks/halogen0201-real-npu-catchup-20261111.md)
completed three measured stock and three measured NPU requests, but its final
stock arm stopped after an excluded warmup when request-entry memory remained
below 22 GiB. No complete bracket or NPU speed gain is qualified. The normal
server was left online; the full optimization goal remains unachieved.
