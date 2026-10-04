# Retained-allocator execution result — 4 October 2026

**The separately authorized attempt failed at the first synthetic call.**
Session setup completed with OGA's separate allocator holder, but the first
call did not produce a validated result. There is no demonstrated repair or
NPU speed gain. The candidate is not qualified for production.

The user authorized the prepared single attempt with “freigabe erteilt”. Root
launched the frozen argument vector once through local PowerShell, after
checking live processes, completed agents, stopped controller/backend, zero
active requests, free ports 8731/8840, stopped WSL and small source/DLL pins.
The frozen guard verified the entire synthetic bank and sealed ORT stage.
The authorization allowed at most two synthetic calls, a 90-second child limit,
22-GiB initial and 18-GiB monitored physical/commit reserves. The nine-hour
optimization window and its heartbeat remained closed.

## What returned

The receipt directory is
`server/.local/optimization9h-20261004/qmoe-retained-admission-daf275ea3fd74e81a9990f37782612aa`.
Flushed native stages establish successful holder-session creation, allocator
acquisition and strict execution-session/tensor/binding setup. The requested
`Cpu / OrtDeviceAllocator / device0 / default` key returned
`RMM type=0 mem=0 device=0`. The holder graph was never run.

There is one `synthetic_call_0_invoke` marker, followed by a caught read access
violation. There is no returned-call marker, second invoke, native cleanup
marker or profile-completion marker. Native counters remain null because no
normal native receipt returned. No validated output, output hash or completed
call timing was received. Python cleanup and failure-report serialization
completed; native allocator/session/provider cleanup is unproved.

The collector captured `0xC0000005`, read address `0x0000045887cfeca0`, at
RIP `0x00007ffbdda2a541`. Its 56-module arm-time snapshot reports the faulting
module as unknown; it cannot identify later-loaded provider/XRT modules. The
child's terminal exit code was separately `3221226505 / 0xC0000409`. The
terminal code does not identify the AV's cause. The ORT profile file is empty,
so neither exclusive Light kernel attribution nor internal NPU placement is
established. The recorded 458.5002-ms failed native-admission host duration
includes setup and the failed invocation; it is not throughput or a completed-call
latency.

## Closure and remaining scope

The parent records `owned_job_closed=true`, `admission_latch_released=true`,
no closure error and successful final verification of the complete ORT stage.
Fresh process/port inspection found child PID36984 absent, no measurement
processes and no listeners on the owned ports. Monitored parent minima were
42.617 GiB physical and 198.352 GiB commit headroom; final values were
44.804 / 199.809 GiB. These are sampled observations, distinct from the child
report's narrower memory samples.

[Machine-readable evidence](halogen-qmoe-retained-allocator-admission-20261004.json)
contains the unchanged source/DLL pins, fault and stage evidence, closure
result, authorization scope and hashes of the raw receipt files. Historical
build and previous failed-attempt receipts remain preserved. An independent
agent reviewed the same raw evidence without hardware execution or edits.

No unchanged retry or real-bank conversion followed. Full Flash-Next MTP,
real-weight execution/residency, quality, acceptance improvement and throughput
gain remain unproved. Matched stock 8K PP-only remains 1661.0181 tok/s; the
separate PP8192/TG128 MTP cohort remains 1584.5019 prefill / 47.0600 decode
tok/s and 60% acceptance. This attempt adds no new engine benchmark result.
