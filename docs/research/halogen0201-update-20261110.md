# Halogen 0.20.1: running and measured on 10 November 2026

Halogen **0.20.1** is installed and serving through the existing authenticated
ServiceNow endpoint on port **8840**. The API and native engine both report
0.20.1 with version agreement. An authenticated chat request returned `READY`.
The normal persistent console displays incoming requests and responses.

## Release and local integration

The [official pinned changelog](https://github.com/peonist-ai/halogen-flash-server/blob/d2f4286fc97fd1f75cd765714dbc50524004356f/CHANGELOG.md)
describes reply-end prompt caching for faster follow-up turns. Flash weights,
ROCm 10.1 runtime and GEMM tuning remain those of 0.20.0. This is not a claim
of higher cold-request decode throughput.

| Identity | Bound value |
| --- | --- |
| Public tag/main commit | `d2f4286fc97fd1f75cd765714dbc50524004356f` |
| Immutable image digest | `sha256:66dac8dac25bf15f2b63a684bbe3953036045172d881525600ea41d45e5acc73` |
| Image configuration digest | `sha256:b0973fd66e5aa886b54cfaf2e4ad976b8d56ad2a2640221beec8dc920ade6e37` |
| Native engine SHA256 | `7a72e138f0090008d171e41358a23f86a875fe92fadbcbc5daf2d3225e426577` |
| Image engine revision | `9f38fe7ba960` |

The changed native demand function and patch site were independently checked
against the fresh ELF. All 47 source members, four rebuilt local products,
image providers and 153 headers were verified. Live process maps and file
hashes confirm the actual HIP, crypto and C++ providers. The image SSL file
hash was checked separately; it is not mapped by the native engine and no
live SSL-provider binding is claimed. Static migration pins remain distinct
from these runtime observations.

Startup passed the unchanged **30 GiB physical / 131 GiB commit** admission.
The controller keeps the **18/18 GiB** runtime reserve. Measurements retained
**22/22 GiB** request-entry admission. No foreign program was stopped, driver
installed, BIOS/voltage changed or global WSL setting changed for this update.

## Current measurements

Both workloads contain contiguous, non-repeated War and Peace text, with exact
native input counts. Each size completed one excluded warmup and three measured
requests, generating 128 tokens at temperature 0 / seed 1. Cache and Thinking
were off. The profile uses v2, one 32K slot/pool, paired 2048-token prefill
chunk/arena, MTP gate 0.90, PLD `3,3`, Vision Off and prefetch 0.

| Actual input tokens | API-reported prefill tok/s | API-reported decode tok/s | API-reported MTP head accepted/drafted |
| ---: | ---: | ---: | ---: |
| 8192 | 1276.59 | 46.95 | 189/318 = 59.43% |
| 16384 | 1103.35 | 40.02 | 165/327 = 50.46% |

These phase clocks are **not independently RAW-qualified**. Complete HTTP
responses were timed separately with Windows QPC; means were 9.208794 and
18.110871 seconds. The [measurement report](../benchmarks/halogen0201-natural8k16k-20261110.md)
and [numeric evidence](../benchmarks/halogen0201-natural8k16k-20261110.json)
retain all eight samples, warmup labels, native counters and output hashes.
The previous peaks have not been reproduced by this cohort. New-release
outputs differ from older releases, so these observations alone do not isolate
a causal engine-version regression. No NPU speed gain is claimed.

## Start and follow-up option

The normal measured configuration, using Windows PowerShell 5.1:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentText32K -Slots 1 -KvPoolPositions 32768 -Concurrency 1 -PrefillTokens 2048 -ConsoleTrace
```

The new opt-in profile enables Flexible caching with otherwise matching
one-slot 32K / paired2048 text settings:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentCachedText32K -ConsoleTrace
```

The cached profile has **not** received a local performance comparison. Clients
must preserve the previous answer exactly in conversation history to use the
new reply-end reuse. Faster time to first token is separate from cold prefill
or decode tok/s. The existing `FollowupText32K` profile retains its historical
0.18.22 identity. Use the normal stop procedure before switching profiles.

The public model remains `halogen-v2`, API base
`http://127.0.0.1:8840/v1`, with the existing protected ServiceNow key. It is not
necessary to change request headers for the version update. See the
[integration guide](../integrations/halogen-servicenow.md).

## Remaining optimization work

The acceleration objective remains unachieved. A separate default-off native
[cost-aware MTP candidate](../../experiments/halogen0201-native-cost/README.md)
is implemented as an inert source patch at fixed Q4, with twelve portable tests
and independent finite native-source review. It must preserve target outputs
and improve a controlled whole-request comparison before deployment. Its fresh
RAW observer binding and version-specific campaign preparation remain separate
from the completed API cohort above.
The first prospective cost attempt stopped before its first cohort: an
inherited observer could not forward a C++ clock call from the HIP preflight
helper's local dependency scope. Cleanup and recovery passed, and the exact
normal profile was restored and authenticated. It produced no cost-rule rates.
An exact-image CPU regression reproduced the old failure and verified a repair
that removes the observer only for that helper, retaining both memory bridges.
The observer binary and its thirteen sources are unchanged. The corrected
[v2 prospective plan](../benchmarks/halogen0201-mtp-cost-gate-plan-20261110-v2.json)
is separately registered; fifty-six CPU checks cover its coordinator and
restoration behavior. These checks establish no throughput improvement.
V2 then captured two valid 8K RAW responses (excluded warmup plus one measured
request), but stopped before the next request when Windows reported 1% Copy
activity for System PID 4. Ownership was not established. No complete cohort
or cost comparison qualified; normal serving was restored again. The separate
[v3 plan](../benchmarks/halogen0201-mtp-cost-gate-plan-20261110-v3.json) adds a
bounded pre-request wait for two zero-GPU observations. It retains the zero-load
threshold, immediate post-request rejection, all memory reserves and prior
failure evidence. Waiting time is recorded separately from measured phases.
V3 stopped during preflight, before stopping the server, because the new
receipt writer lacked its parent directory. The narrowly corrected
[v4 plan](../benchmarks/halogen0201-mtp-cost-gate-plan-20261110-v4.json) adds
directory creation and a filesystem replay using the actual controller writer.
Seventy CPU tests and independent full receipt replay pass; that CPU preflight
now also runs before any server stop. Backend and observer bytes are unchanged.
V4 completed the four-response 8K reference phase cohort, then rejected equality
between native chain counters and API head counters. Fresh native source review
shows they have different scopes: the API also counts single-step head drafts.
Its drafted total is neural rounds minus chain rounds plus chain drafted.
Full accepted totals additionally use a native field absent from the trace.
No counter correction is applied. Subsequent work separates qualified phase
throughput from the still unavailable independent full-acceptance reconstruction.
The [V5 protocol](../benchmarks/halogen0201-mtp-cost-gate-plan-20261110-v5.json)
declares this separation prospectively. Its [counter-scope note](halogen0201-counter-scopes-20261110.md)
retains both original counters and the limitation, with no fixed correction or
unproved cross-scope bound. All timing, output and resource checks remain required.
Previous slower NPU consumers remain disabled. GPU kernel and alternative-draft
ideas are prioritized with their transfer limits in the
[current opportunity review](halogen0201-opportunities-20261110.md).

The bounded official source check at **20:36:38 UTC** found Halogen 0.20.1,
AMD 26.10.2 Optional / 26.10.1 Recommended and Ryzen AI 1.9 unchanged. Its next
check is due no earlier than **22:36:38 UTC**. Listed releases are not claims
that those host drivers were installed or qualified by this task.
