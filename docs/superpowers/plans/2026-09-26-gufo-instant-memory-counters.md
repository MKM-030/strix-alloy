# GUFO instantaneous memory counters implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development and test-driven-development. This is a telemetry performance correction, not a new safety policy.

**Goal:** Remove Get-Counter's measured one-second sampling overhead without relaxing the two-second collector deadline.

**Architecture:** Keep the existing hidden, bounded PowerShell probe and DXGI enumeration. Replace only the counter collection with synchronous native PDH collection of the same host gauges and adapter aggregate gauges. Native raw and formatted values, status, counter type and timestamps must agree; preserve wildcard topology visibility.

**Tech Stack:** Windows PowerShell 5.1, C# P/Invoke, existing Python standard-library normalization and unittest.

## Global Constraints

- Workspace C:\Projects\strix-alloy-research\integration, codex/gufo-native-integration.
- At least49GiB available physical before launch;24GiB runtime stop floor;12GiB commit reserve. Query duration and final age<=2s; runtime sample age<=5s. No overlapping queries; starts>=1s apart.
- No model, GPU operator, WSL, server, persistent system change, reboot, qualification creation, latch disposition, attempt reset or public push by implementer.
- Existing incomplete16k-v2 latch and every historical result remain untouched. Guardian timeout/cleanup semantics remain unchanged.
- Preserve adapter-global and host-global scopes, exact English path/LUID/physical-node identity, missing/duplicate/status/raw-cooked/time checks, complete fresh process inventory and DXGI identity. No per-process budget substitution or cached memory sample.
- No added dependencies or downloads. Apply_patch for source edits. Commit only owned files.

## Evidence and native contracts

Actual16k-v2 query took2.125s and correctly stopped the owned model. Existing collector is terminal, but its violated deadline permanently prevents recovery certification. This task does not override that behavior.

Read-only timing: cold whole probe1.655s, warm whole1.030s; isolated Get-Counter1.221,1.008,1.011s. Existing Get-Counter sleeps to collect its default sample. Memory counters are instantaneous gauges; do not apply this replacement to rate counters.

Microsoft references:
- https://learn.microsoft.com/en-us/windows/win32/perfctrs/collecting-performance-data
- https://learn.microsoft.com/en-us/windows/win32/api/pdh/nf-pdh-pdhcollectquerydata
- https://learn.microsoft.com/en-us/windows/win32/api/pdh/nf-pdh-pdhgetrawcountervalue
- https://learn.microsoft.com/en-us/windows/win32/api/pdh/ns-pdh-pdh_raw_counter

### Task 1: Native single-sample byte gauges

**Owned files:** scripts/gufo_control/windows_probe.ps1; new scripts/gufo_control/windows_counters.cs if needed for focused responsibility; scripts/gufo_control/telemetry.py; scripts/gufo_control/operator_policy.py; tests/gufo/test_telemetry.py; new tests/gufo/test_windows_counters.py. No other production files.

**Interfaces:** collect_snapshot() still returns the same normalized dictionary. Historical provider PDH/Get-Counter;DXGI/EnumAdapters1 remains recognized for immutable evidence. New live provider is PDH/native-gauges;DXGI/EnumAdapters1. Collect_snapshot must require the new provider from its actual subprocess; pure normalization/policy can validate both explicitly allowlisted providers. Never silently relabel old readings.

- [ ] RED: Add provider/collection regression tests first, including new provider accepted, arbitrary provider refused, actual subprocess old-provider output refused, and existing normalizer error cases unchanged. New native implementation tests must exercise gauge/status/type/timestamp validation and query release through an injectable narrow native-call seam or an equivalent real C# test harness. Native call structure layouts must have assertions.
- [ ] Run the focused test modules and record the expected failures before implementation.
- [ ] Implement bounded native query ownership: PdhOpenQueryW, PdhAddEnglishCounterW, PdhCollectQueryData, PdhGetRawCounterValue/PdhGetFormattedCounterValue (or matching array forms for wildcard gauges), PdhCloseQuery in finally. Use Unicode paths and pointer-width handles. Return-call success does not replace CStatus validation (only0/1 are valid). Require gauge types PERF_COUNTER_RAWCOUNT/PERF_COUNTER_LARGE_RAWCOUNT as appropriate; reject rate counters. Compare formatted byte count to raw FirstValue and reject negative/overflow/nonfinite values. Use provider sample timestamp with correctly documented FILETIME conversion, not a timestamp fabricated after work finishes. Preserve UTC age checks in normalization.
- [ ] Preserve the six path families exactly:

```text
\Memory\Available Bytes
\Memory\Committed Bytes
\Memory\Commit Limit
\GPU Adapter Memory(*)\Dedicated Usage
\GPU Adapter Memory(*)\Shared Usage
\GPU Adapter Memory(*)\Total Committed
```

Wildcard collection/expansion must retain all observed physical-node instances so the existing normalizer still refuses unsupported target topology. Do not simply hardcode target phys_0 and hide other nodes. Bound expansion/buffer allocation and retry count; only documented more-data sizing retries, no collection retry or cached fallback. Preserve canonical machine-qualified English paths and exact instance names; unexpected identities fail closed.

- [ ] Keep the existing collect_snapshot subprocess timeout5s, hidden window, output2MiB cap and independent guardian2s deadline. Do not change Query or guardian cleanup. The C# helper may be compiled through existing Add-Type; no persistent binaries or services. Fresh process inventory and DXGI enumeration still occur every query.
- [ ] GREEN: focused tests pass. Read-only real telemetry is authorized only after notifying parent so probes cannot overlap. Compare normalized identity/scopes/counters with the existing Get-Counter mechanism in sequential samples; memory values can legitimately vary, so prove valid byte gauges/status/types and matching adapter identity rather than demanding byte equality across time. Record cold total duration over several nonoverlapping samples, each >=1s apart, and preserve raw data outside immutable prior runs.
- [ ] Run full offline suite once with absolute PYTHONPATH, then commit owned files. Python: C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe. PYTHONPATH: C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo. Command: python.exe -m unittest discover -s tests/gufo. Report all failures/skips honestly.
- [ ] Independent task review must approve provider compatibility, PDH semantics, timestamp conversion, wildcard topology, resource cleanup and test evidence before a real launch is considered. Parent separately handles failed-run recovery disposition and a new explicitly identified benchmark attempt. This task alone grants neither.
