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

## Baseline API observations

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

The subsequent paired 2048 / 8192 / 2048 study completed all six RAW/QPC
cohorts and restored the normal server. At paired 8192, actual 8192-token input
achieved 1526.01 prefill tok/s, 43.99 observed decode tok/s and API head
192/312 = 61.54%. Actual 16384-token input achieved 1380.48 prefill tok/s,
45.18 observed decode tok/s and API head 180/324 = 55.56%. Prefill exceeds both
controls by 17.95–26.22% at 8K and 4.58–13.17% at 16K. Changed output hashes
leave causal decode comparisons open. The online profile uses paired 2048
while development continues toward higher prefill and decode together.
[Complete prefill study](../benchmarks/halogen0201-prefill8192-20261111.md).

The following paired 2048 / 4096 / 2048 comparison completed all six cohorts
on 11 November. At 8K, candidate prefill reached 1314.53 tok/s, with observed
decode of 42.90 tok/s and API head acceptance of 174/330 = 52.73%. At 16K,
the corresponding values were 1368.08 tok/s, 41.98 tok/s and 174/339 = 51.33%.
Prefill exceeded both controls by 11.94–13.91% and 9.82–12.00%. Candidate
outputs differ from their controls, leaving causal decode comparisons open.
API acceptance retains its source-derived scope and independent reconstruction
remains open. All 26 focused CPU tests pass. The current online server uses
the exact paired-2048 normal profile.
[Complete 4096 comparison](../benchmarks/halogen0201-prefill4096-20261111.md).

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
V5 has now completed all six cohorts and restored the exact normal profile.
At 8K, cost increases API head acceptance from 59.43% to 64.95%, while RAW
decode falls to 42.54 tok/s against gate controls of 46.82 and 45.38.
At 16K, cost reaches 44.19 tok/s against 42.71 and 39.09, with API head
acceptance rising from 50.46% to 58.16%. Stock controls drift materially,
and all phase rates include observer/trace overhead. The general serving
profile retains the gate rule. Independent reconstruction of the full API
accepted count remains open. [Complete results and restoration evidence](../benchmarks/halogen0201-mtp-cost-gate-20261110.md).
Previous slower NPU consumers remain disabled. GPU kernel and alternative-draft
ideas are prioritized with their transfer limits in the
[current opportunity review](halogen0201-opportunities-20261110.md).

The bounded official source check at **00:49:28 UTC on 11 November** confirms
Halogen 0.20.1 as latest. Both image tags resolve to the installed immutable
digest. AMD still lists 26.10.2 Optional / 26.10.1 Recommended, and Ryzen AI
remains 1.9. The next source check is due no earlier than **02:49:28 UTC on
11 November**. The reviewed host driver installation remains recorded
separately. [Official Halogen changelog](https://github.com/peonist-ai/halogen-flash-server/blob/d2f4286fc97fd1f75cd765714dbc50524004356f/CHANGELOG.md).

After the completed comparison, fresh authenticated checks at **01:10 UTC on 11 November**
verify API and engine 0.20.1 and a successful `READY` chat response on port 8840.
The normal persistent console remains open, with model alias `halogen-v2` and
the existing ServiceNow credential.

## Startup observation repair and full-history cache study

The first complete-history cache attempt reached a Docker inspection timeout
during private startup. The existing startup exception path then cleaned up
the owned container. This attempt contains zero benchmark requests and its
terminal record confirms authenticated normal restoration.

The normal startup loop now catches that inspection's `TimeoutExpired`, checks
the cache worker and continues observing the same container within the original
startup deadline. Seven regressions exercise the actual source block, including
same-container recovery and fatal ownership, exit and worker errors. The source
manifest contains 47 verified members, with SHA256
`4b70963dcd8442206c5b775c757dcdab18cb68b2c7b40e5cadaa0cd475953da6`.

A controlled normal restart completed at 02:21 UTC. Authenticated discovery
confirms API/engine 0.20.1 on port 8840, with the paired-2048 normal profile and
visible console. The next 24-request Off/Flexible/Off comparison freezes each
full conversation from its before-arm answer and replays the identical history.
It records first-content and whole-request time together with actual full,
cached and newly processed token counts. This tests the combined follow-up
cache benefit. Incremental reply-end attribution requires further evidence.
[Prospective V2 protocol](../benchmarks/halogen0201-reply-end-cache-plan-20261111-v2.json).

The subsequent V3 comparison completed all 24 requests and restored normal
serving. Flexible reused 8160 of 8192 follow-up tokens and observed 0.243-second
first-content latency versus 6.136 / 6.235 seconds for the two cold controls.
One answer changes text and length, so a full output-matched speed claim remains
unqualified. Cold first-turn latency also increases by 5–7%. Cache Off remains
the serving default. [Complete V3 result and limitations](../benchmarks/halogen0201-reply-end-cache-20261111.md).

At **03:24 UTC on 11 November**, a fresh official tag check confirms 0.20.1
as latest. The normal server reports matching API/engine 0.20.1 and answers an
authenticated chat request with `READY`. Port 8840, model alias `halogen-v2`,
the existing ServiceNow credential and visible request/response console remain
available. Current controller/backend runs are `02e38955abb44f40be18b878c6768a63`
and `642221c86f6e4196b1f0ece635d80b59`; earlier run identities above are historical.

## Current serving profile, 11 November 04:00 UTC

The normal server now uses paired 8192 after the completed input-matched prefill
comparison. Both prefill fields change together; the original 2048 profile is
preserved for rollback. All 47 normal source members are restored, with no RAW
observer, external oracle or NPU producer enabled. The persistent public server
uses run `1c2b9c6595584f29a1001b3281b55b51`, context/pool 32768 and one slot.

The independent normal-serving confirmation completed one excluded warmup and
three measurements per size. At 8192 actual inputs it reports 1475.04 prefill,
47.52 decode tok/s and 61.54% API neural-head acceptance; at 16384 it reports
1447.23, 45.07 and 55.56%. These are reported API/native phase observations, with
separate HTTP QPC evidence, not a new RAW or controlled gain claim.
[Current numbers, limits and Windows PowerShell command](../benchmarks/halogen0201-normal8192-20261111.md).

A separate exact-output oracle experiment reaches 65.43 RAW decode tok/s against
46.46/43.82 stock controls. It supplies future exact target IDs and measures no
real NPU prediction. Its 100% lookup acceptance is distinct from neural-head MTP
acceptance. The mechanism motivates further asynchronous NPU proposer work and
remains disabled in normal serving.
[Complete consumer experiment](../benchmarks/halogen0201-external-oracle-20261111.md).

## Actual NPU component, 11 November

The new growing-context FLM 1.0.7 component passes exact sequential-reference
parity for all 32,001,030 BF16 values across 129 states. It seeds the last 512
prompt IDs once and appends 128 authoritative target IDs through context 640.
Offline next-ID agreement is 66/128 (51.56%), with a 425.10-ms seed and 22.39-ms
mean authoritative append through owned logits. These are component operation
times, including CPU copy/argmax; they are not measured Halogen tok/s or native
MTP acceptance. Actual loaded DLLs match the selected providers, both helpers
are closed, and the same GPU server remains online.
[Result, limits and published source](../benchmarks/halogen0201-growing-npu-20261111.md).

The existing future-trajectory oracle is unsuitable as an unchanged live
count-one protocol. Real proposals need prefix-bound replacement, immediate
fallback and demonstrated arrival before demand. Grouping already queued
authoritative tokens was subsequently tested and rejected: both vector-prefill
batch widths fail the unchanged exact BF16 criterion and are slower than
sequential forwarding for the same 128 target IDs. The measured append costs
are 7.36× and 3.72× the scalar reference. No live NPU producer is enabled.
Supported stateful lookahead remains a separate unmeasured candidate.
[Complete negative result](../benchmarks/halogen0201-bulk-npu-20261111.md).

The bounded official refresh completed at 04:57 UTC: Halogen 0.20.1, both image
tags and the checked AMD/Ryzen-AI/XRT release identities are unchanged. Reddit
returned older discussions, with no verified new actionable November material.
The next full source check is due at 06:57 UTC; no driver was installed.

## Latest online verification and watchdog activation

A direct official check at 05:49 UTC confirms 0.20.1 remains latest and both
image tags retain the installed digest. The reviewed monotonic watchdog clock
correction is now active after one normal restart. Authenticated health,
model discovery and an actual `READY` chat response pass; the normal server
remains online on port 8840 with its visible console. Earlier process identities
above are historical; the new sealed runs and exact generated script are in the
[current online snapshot](halogen0201-online-watchdog-20261111.md).
This reliability change establishes no new throughput gain.

## Stateful NPU component and current availability

The separate FLM 1.0.12 full-snapshot/always-restore component now passes all
32,001,030 BF16 comparisons exactly. State read/write calls average 2.82/5.04 ms;
normal authoritative NPU appends average 21.07 ms. These component timings and
66/128 offline next-ID matches establish no Halogen tok/s or native acceptance.
[Full measured result and source](../benchmarks/halogen0201-stateful-npu-20261111.md).

After the earlier online snapshot, the 18-GiB runtime guard stopped that server
under additional memory pressure. The exact owned TTS process was unloaded
under the existing Voice-pause authorization, and a fresh normal launch passed
the unchanged 30/131-GiB start and 22/22-GiB request-entry admission. Original
failure/cleanup evidence is retained. Authenticated health, discovery and `READY`
pass on the recovered server. Its controller/backend runs are
`54495bb566554fe8a4be00be80f129d5` / `693717e5bba9420f8f1e791ec4adff31`.
This same recovered server remains ready after both NPU component processes close.

The retained-prefix serial producer now also passes exact comparison of
32,001,030 BF16 values: 66 committed-prefix promotions reuse cached state and
62 corrections restore and forward the actual target suffix. Its
[source and qualification](../benchmarks/halogen0201-streaming-npu-qualification-20261111.md)
are published with 51 passing portable CPU tests. Live GPU arrival and whole-engine
speedup are separate outstanding measurements. A reproduced publisher-lock
contention bug is being corrected before that comparison; the normal server
remains unchanged.

At 08:40 UTC, the official tag and OCI latest digest still match the installed
0.20.1 image. Both live API and engine agree on 0.20.1; an authenticated chat
returns `READY`. The existing paired8192 profile and port 8840 remain online.
