# Halogen 0.19.1 update, 7 November 2026

The PowerShell 5.1 launcher selects Halogen **0.19.1 CurrentText32K** by default.
The selected Voice configuration uses one 32K slot, a 32768-position
KV pool, serialized requests and a paired 2048-token prefill chunk and arena.
The public model is `halogen-v2` at `http://127.0.0.1:8840/v1`.

## Verified upstream release

The 7 November release audit selected official **0.19.1**, published on
6 November. The versioned image and `latest` resolved to the same immutable
image during that audit. The public source commit is
`47ceb439fd97ef4b62cc18042fda505113546567`. The image reports engine revision
`85b2b0c37d5d`. [Official package](https://github.com/peonist-ai/halogen-flash-server/pkgs/container/halogen-flash-server),
[pinned changelog](https://github.com/peonist-ai/halogen-flash-server/blob/47ceb439fd97ef4b62cc18042fda505113546567/CHANGELOG.md).

```text
ghcr.io/peonist-ai/halogen-flash-server@sha256:7ab5c3dfd77acb2387603f1807069cac3494e678f413c0670745ba2df74c0f0e
```

The registry config digest is
`sha256:e38fa4d382b9e6e9f88d602d917761a53bda90dbff063c93c899433b709426c9`.
The local package records the extracted engine, API, entrypoint and provider
identities. [Version-specific release pins](../../backends/halogen-wsl2-0.19.1/profiles/release.json).

The qualification flags in that release file retain the package's static
prequalification artifact metadata. Separate dated runtime and provider
observations establish the recorded live qualification described below.

The bounded source check completed at **15:13 UTC** again identified **0.19.1**
as the latest official tag and image. The `latest` and versioned image digests,
registry config and public source head matched the earlier audit. The official
AMD GPU driver, Ryzen AI and XRT release fields also retained their earlier
versions. [Official package](https://github.com/peonist-ai/halogen-flash-server/pkgs/container/halogen-flash-server),
[official tag](https://github.com/peonist-ai/halogen-flash-server/tree/v0.19.1),
[AMD driver](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html),
[Ryzen AI release notes](https://ryzenai.docs.amd.com/en/latest/relnotes.html),
[XRT releases](https://github.com/Xilinx/XRT/releases).

Direct Reddit access returned HTTP 403 and the web listings were cached, so
current subreddit freshness remained unverified. At that checkpoint, the next
bounded refresh was due at or after **17:13:05 UTC**. The private receipt is
`server/.local/halogen-update-20261107/source-refresh/refresh-20261107T151003Z/receipt.json`.

A narrow official release check at **16:39 UTC** again resolved both `latest`
and `0.19.1` to the image and config digests above. The official source head and
version tag still resolved to the pinned public commit. This check covered
Halogen release identity. The broader driver and community refresh retains
its separate schedule. [Official package](https://github.com/peonist-ai/halogen-flash-server/pkgs/container/halogen-flash-server),
[pinned source](https://github.com/peonist-ai/halogen-flash-server/commit/47ceb439fd97ef4b62cc18042fda505113546567).

The subsequent bounded refresh observed sources at **17:14:44–17:15:25 UTC**
and completed at **17:17:34 UTC**. Halogen source, tag, image and config
identities matched the retained pins. AMD GPU, Ryzen AI, XRT and WHIRL release
fields were unchanged. Reddit returned HTTP 403 and available web listings
were cached. Current community freshness remains unverified. The next bounded
refresh is due at or after **19:17:35 UTC**. Its receipt is
`server/.local/halogen-update-20261107/primary0191/completion-closure/source-refresh-1713/receipt.json`.

The refresh identified **libosmos 0.5.4**, published at **16:48:43 UTC**.
Its upstream report cites about **2.8% higher 16K prefill** from Qwen expert
table placement. Decode and the 2K/4K cases retained their earlier results.
These are upstream engine measurements. Local memory fit, compatibility and
a Halogen implementation of that layout remain unqualified.
[libosmos 0.5.4 release](https://github.com/mrsirg97-rgb/libosmos/releases/tag/v0.5.4).

## Manufacturer benchmark scope

The official **66.12 decode tok/s** row belongs to **0.18.20 v2**. The current
documented benchmark invokes `bench-serving.py serial,mtp 256 low 3` over ten
fixed prompts. It sends three repetitions per prompt and drafter, totaling
60 requests, and computes an equal-weight mean of per-case native rates.
Its short prompts, natural output stops and cache settings differ from the
local cold 8192/16384-token, fixed-128-output RAW cohorts. A direct parity
comparison requires a fresh replay of that exact protocol.
[Published performance row](https://github.com/peonist-ai/halogen-flash-server/blob/47ceb439fd97ef4b62cc18042fda505113546567/docs/performance.md#01820-against-01819),
[benchmark client](https://github.com/peonist-ai/halogen-flash-server/blob/47ceb439fd97ef4b62cc18042fda505113546567/tools/bench-serving.py),
[fixed prompts](https://github.com/peonist-ai/halogen-flash-server/blob/47ceb439fd97ef4b62cc18042fda505113546567/tools/eval-prompts.json).

The current 0.19.1 tokenizer and template render those ten prompts to
22–41 input tokens with Thinking Off. The `low` client argument sets reasoning
effort. Disabling thinking also requires the effective server default to be
false. No complete 0.19.1 replay of the official 60-call corpus has qualified.
The retained protocol audit is under
`server/.local/halogen-update-20261101/primary01822/vendor-protocol-audit/`.

## Changes relevant to ServiceNow and tools

- The 0.18.23 turn-ending fix stops a reply when the model ends its turn inside
  reasoning. This prevents an extra user message from being generated into the
  reply. Its tool parser also preserves argument strings containing the XML
  closing tags used by tool calls.
- Version 0.19.1 rejects malformed tool schemas with a named HTTP 400 error and
  releases generation slots on errors before generation. This addresses the
  failure where repeated invalid requests could occupy every slot.
- Whole-file edits receive upstream prompt-lookup improvements. Repeated
  completion prompts receive tokenization improvements. These benefits depend
  on the request shape.
- Concurrent speculative sampling follows the requested distribution more
  precisely. Seeded sampled replies can therefore change across this update.
  Upstream also adds a startup warmup and adjusts concurrent device-memory use.

These changes are described in the pinned upstream release notes. Local
performance measurements remain specific to their recorded version and workload.
[Changes since 0.18.22](https://github.com/peonist-ai/halogen-flash-server/blob/47ceb439fd97ef4b62cc18042fda505113546567/CHANGELOG.md).

## Reproduce the latest Voice profile

Run from `C:\Projects\strix-alloy-clean` in Windows PowerShell 5.1.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentText32K -Slots 1 -KvPoolPositions 32768 -Concurrency 1 -PrefillTokens 2048 -ConsoleTrace
```

The profile uses v2 weights, 32768 context positions per slot, Cache Off,
Vision Off, Thinking Off with low effort, adaptive MTP gate 0.90, PLD `3,3` and
prefetch 0. The context limit covers input plus output. `-ConsoleTrace` enables
request and response content in the foreground console. The normal Voice profile
keeps content tracing disabled.

The bare launcher uses the same current version with one slot, one concurrent
request and a 2048-token prefill chunk and arena. `FollowupText32K` retains the
historical measured **0.18.22** Flexible-cache profile. The integration guide
retains its comparison and older measurements. [ServiceNow integration guide](../integrations/halogen-servicenow.md).

The public credential remains `server/.local/servicenow-api-token.txt`. The
backend uses its separate version-specific token. Existing ServiceNow callers
continue to use the same public model, base URL and Authorization header.
Startup admission remains at least 30/131 GiB and runtime guards remain
18/18 GiB. The two-slot gateway separately requires 22/22 GiB at request
entry. The one-slot gateway reports `not_required` for that capacity guard.
The private benchmark collector independently enforces 22/22 GiB request entry.

## Local compatibility work

The update carries all 47 source members from the complete primary 0.18.22
package, including bounded capacity validation and the narrow CacheOff counter
correction. Fresh extracted 0.19.1 bytes were used to discover and verify the
memory-bridge seam, frame contract and direct transfers around the patch.
All four CPU products were rebuilt against the new image headers. The normal
installer reused the established complete-file model receipts after exact
file-identity checks.

Offline migration tests passed 4/4 and the new package's portable capacity tests
passed 15/15. An independent review verified the fresh ELF mapping, bridge source,
entrypoint transformation and API adaptation. The update retains the existing
managed lifecycle, authentication and console trace implementation.
The complete server suite passed 236 tests and the native Voice suite passed
1705 tests. `Start-SCCVoice.ps1 -CheckOnly` completed successfully with refreshed
source pins.

## Runtime qualification

The 7 November observation at **12:47 UTC** recorded both the normal controller
and backend ready, matching API and engine version **0.19.1**, two 32768-position
slots and a 65536-position KV pool. The selected profile retained concurrency
two and paired 2048 prefill settings. The active bridge identity and HIP
`gfx1151` preflight passed the fresh qualification.

Model discovery returned HTTP 401 without authentication and HTTP 200 with the
existing public credential, advertising `halogen-v2`. Request-entry admission
was ready. The normal Voice consumer's persistent selection was updated to the
verified 0.19.1 profile.

The recorded controller run is `f18c4e89b8ad41f6b1a25791f8a9d68b` and backend
run is `3103ec5ec2dc457c93ce99ebb50164b5`. The selected profile SHA256 is
`0d92158fe58e5ae278eba173aa4d40a0f4978cbc6d8e0bb5e5ca45c44c713cca`.
The local observation is retained at
`server/.local/halogen-update-20261107/primary0191/runtime-and-auth-qualified.json`.

After the separate one-slot workspace trial, an independent **13:04 UTC**
historical snapshot recorded the restored normal two-slot 2048 profile ready,
with request-entry admission ready. Its controller and backend runs were
`c0f914b3674d46ff8e22e5059d84900e` and
`df10d3939eb84bb28088fc93c2ce2b67`. The recorded profile SHA256 was the same.
That observation is retained at
`server/.local/halogen-update-20261107/primary0191/final-ready-20261107T130414824304Z.json`.

The earlier frozen cohort used synthetic prose at 8K and a contiguous novel
excerpt at 16K. It completed one excluded warmup and three measurements per
input. Its API-reported prefill/decode means are 1191.85/46.62 tok/s at 8K and
1125.72/48.98 tok/s at 16K. Complete-request QPC means are 9.666991 and
17.241034 seconds. Every reported phase sum fits its corresponding whole HTTP
interval. Independent RAW phase-clock qualification remains pending for that
earlier cohort.
The OEM operating-mode readback was unavailable to the non-elevated process.
[Fresh 0.19.1 observations](../benchmarks/halogen0191-natural-8k16k-20261107.md).

A later genuine **8192-token natural-text RAW cohort** completed one excluded
warmup and three measured requests in the two-slot, pool-65536, paired-2048
PLD `3,3` before arm. Its independent
RAW midpoint means were **1185.559992 prefill tok/s** and **48.802438 decode
tok/s**, with pooled native-head acceptance **207/327, or 63.30275%**. RAW bounds
include observer overhead. The API phase clocks remain unqualified.
[PLD RAW report](../benchmarks/halogen0191-pld34-raw-20261107.md).

The full PLD `3,3` to `3,4` to `3,3` comparison failed before a matched
three-arm result qualified. Its 16K case stopped after the excluded warmup,
and the code oracle failed.

The separate prefill comparison completed genuine natural 8K and 16K before
cohorts with **one slot, pool 32768, concurrency one and paired 2048 prefill
settings**. Each cohort excluded one warmup and included three measured
requests with 128 actual output tokens. RAW midpoint means were
**1143.700731/48.574773 tok/s** at 8K and **1124.357529/49.677162 tok/s** at 16K
for prefill/decode. Pooled native-head counts were **207/327 (63.30275%)** and
**210/321 (65.42056%)** respectively. These one-slot observations have their
own profile and request records.
[Prefill RAW report](../benchmarks/halogen0191-prefill4096-raw-20261107.md).

The one-slot paired-4096 candidate completed only its 8K excluded warmup before
failing the 22 GiB request-entry gate. The prefill campaign ended and restored
the normal two-slot/2048 profile. Qualified 4096-prefill gain, PLD speedup and
beneficial NPU contribution remain open. API phase clocks retain their
qualification limits.

## Copied-log performance study

The original frozen log task required 4934 UTF-8 bytes. Serial generation
returned 4933 bytes, omitting its final LF. That canonical task remains failed.
A separate prospectively registered performance study froze the exact recorded
serial response and retained the original request and sampler.
[Original pilot](../benchmarks/halogen0191-pld34log-raw-20261107.md),
[prospective plan](../benchmarks/halogen0191-log-serial-reference-plan-20261107.md).

The first reference attempt stopped after one measured response because a
post-response frame reported System PID 4 Copy utilization of 1%. Ownership
of that activity remains unresolved. The failed cohort stays unqualified.
[Retained GPU-gated attempt](../benchmarks/halogen0191-pld34log-reference-raw-20261107.md).

The separate `retry-1` attempt completed a PLD `3,3` before cohort with one
excluded warmup and three measurements. Each used 3539 input tokens, 1259
generated tokens and the exact frozen serial-visible output. RAW midpoint
means were **1161.93155 prefill / 105.333309 decode tok/s**. Pooled native-head
acceptance was **69/84 (82.14%)** and lookup acceptance was
**3228/3234 (99.81%)**. Mean complete-request QPC time was **15.023209 seconds**.
The result applies to this copied-log workload and profile.
[Qualified single-condition cohort](../benchmarks/halogen0191-pld34log-reference-retry1-raw-20261107.md).

The PLD `3,4` candidate generated zero responses. Its normal startup first
observed stable 30 GiB availability, then failed a subsequent admission check
at 29.99 GiB. The 30/131 GiB startup floors remained unchanged. The after arm
was unstarted and no three-arm speedup qualified. The campaign restored the
two-slot serving profile at **17:01:45 UTC**.

## Earlier functional check

The **7 November 15:31:03 UTC** observation recorded the restored normal
two-slot, pool-65536, concurrency-two, paired-2048 profile ready with matching
0.19.1 API and engine versions. Controller/backend PIDs were **25272/28248**,
with run IDs `a58f2a53c0b441079108b830b3531def` and
`35abd5bb406440d8b685073eb05fbeaa`. The selected profile SHA256 was
`0d92158fe58e5ae278eba173aa4d40a0f4978cbc6d8e0bb5e5ca45c44c713cca`.

Model discovery returned HTTP 401 without authentication and HTTP 200 with
authentication, advertising `halogen-v2`. Authenticated chat returned HTTP 200
and the reply `READY`. The same captured runtime identities were ready and
idle before and after that functional availability request. Its saved proof is
`server/.local/halogen-update-20261107/primary0191/final-functional-check/proof.json`.

The retained 0.18.22 and earlier benchmark quantities describe their original
runs. [Historical 0.18.22 phase measurements](../benchmarks/halogen01822-raw-8k16k-20261101.md).

## Final functional check

After restoration, the two-slot gateway reported `physical_low` with about
21.57 GiB free against its 22 GiB request-admission floor. Root selected the
existing supported one-slot capacity through the normal managed lifecycle.
The current profile retains 32768 context positions, pool 32768, paired 2048
prefill settings, PLD `3,3`, gate 0.90, Cache Off and Thinking Off. Requests
are serialized. The persistent Voice controller selection records that profile.

The **7 November 17:09:37 UTC** functional check recorded controller/backend
PIDs **28972/24440**, matching API and engine version **0.19.1**, and profile
SHA256 `69b91ddae6daa21b7c4d7666077847e4913fd9b59aedd149201c9d0ccd994b84`.
Model discovery returned HTTP 401 without authentication and HTTP 200 with
authentication. Authenticated chat returned HTTP 200 and `READY`. Both
captured runtime identities remained ready and idle across that request.
Observed free physical memory afterward was **22.56879 GiB**. The proof is
`server/.local/halogen-update-20261107/primary0191/completion-closure/final-functional/proof.json`.

Six additional idle launch windows were closed only after exact creation-time
identity, controller-exit and child-ownership checks. The original launcher
and current serving launcher were preserved. The baseline 50 source members
were checked and all three private observation additions were absent.

## Subsequent mechanism investigation

The later CPU audit established that every observed copied-log lookup chain
already reached the native seven-token ceiling. Its K4 chain-length premise
is closed. The libosmos routing change overlaps an existing parallel Halogen
planner, and the official NPU helper still lacks the Flash consumer needed
for a measured speed contribution. A separate existing Q8 draft-vocabulary
control has an inactive, tested source bundle and a prospectively frozen
natural-text comparison. Hardware admission remains pending.
[Mechanism evidence](halogen0191-mtp-next-mechanisms-20261107.md),
[Q8 study plan](../benchmarks/halogen0191-draft-vocab-q8-plan-20261107.md).

## Delivery verification at 18:57 UTC

The fresh official GitHub API and GHCR audit again identified **0.19.1** as
the newest published Halogen version. The current source head, version tag,
`latest` image, versioned image and config digest matched the installed pins
above. The running installation therefore already contains the latest
release observed during this audit.
[Official package](https://github.com/peonist-ai/halogen-flash-server/pkgs/container/halogen-flash-server),
[pinned release source](https://github.com/peonist-ai/halogen-flash-server/tree/v0.19.1).

Authenticated readiness verification recorded the same controller/backend
PIDs **28972/24440**, matching 0.19.1 API and engine versions, the selected
one-slot profile hash, an idle gateway and all **50** baseline files exact.
The three private RAW additions remained absent. The current server stayed
online throughout this verification. Stale active-handle aliases in the
private continuation record were archived and resealed to these identities.
The retained proofs are under
`server/.local/halogen-update-20261107/primary0191/completion-closure/user-final-20261107/`.

Fresh CPU verification completed at **19:01 UTC**. The server suite passed
236 tests. The installed backend suite passed 19 tests and skipped eight
POSIX/GCC vision fixtures on Windows. The coordinator, Q8, native-trace and
exporter suites passed another 96 tests. The documented one-slot launcher
command with `-ConsoleTrace -PrintOnly` passed under Windows PowerShell 5.1
and retained the existing session inventory. These checks qualify the tested
source and launcher paths. The live audit used authenticated metadata reads
and generated zero model requests.

Available physical memory was **20.48 GiB**, below the frozen Q8 comparison's
22 GiB entry requirement. The Q8 study remains prepared with zero model
requests. Its accuracy, acceptance and throughput effects remain unmeasured.
The earlier qualified benchmark quantities retain their original workloads
and clocks. The broader acceleration goal, including a beneficial NPU
contribution and a complete matched manufacturer-protocol comparison,
remains open.

## Subsequent optimization work

The pinned 0.18.22 and 0.19.1 engines contain 2,034 common named GPU
functions. CPU ELF inspection found 2,030 byte-identical functions, four
changed recurrent-row functions and six added QSU4 functions. Host dispatch,
current tensor state and execution times remain outside that byte comparison.
The retained natural 16K request is identical across the two versions, while
its prefill chunk and arena changed from 8192 to 2048. The older 8K fixture
also contains different text. These differences prevent a causal version
regression claim. Evidence is retained in
`primary0191/continuation-1904/prefill-source/assessment.json`.

A separate native MTP cost rule supplies a new low-memory test hypothesis.
It weighs calibrated joint-prefix survival against marginal drafting and
verification costs. The ordinary target verifier remains in its path.
The default retains the confidence gate, and the managed interface currently
lacks the internal `HALOGEN_MTP_GATE_RULE=cost` opt-in. This mechanism differs
from the earlier constant-threshold studies. Its throughput effect remains
unmeasured. Static reproduction passed 35 instruction assertions across 30
bounded captures. Evidence is retained in
`primary0191/continuation-1904/mtp-source/assessment.json`.

The inactive cost-rule bundle now contains 50 candidate files, 50 exact
rollback files and three changed package files. Ten focused CPU tests and
the cloned backend suite passed, with 19 backend passes and eight Windows
POSIX/GCC skips. Tests exercise ordinary controller validation and command
forwarding, real service options and manifest construction, canonical rule
values and persisted-environment consistency. The installed package, selected
profile and all 117 protected Q8 preparation files remain exact. The
gate/cost/gate profile projections are staged and unmeasured. Runtime
coordination and whole-engine qualification remain pending. Evidence is
retained in `primary0191/continuation-1904/cost-gate-candidate/receipt.json`.

Root prioritizes a fixed-Q4 cost-rule comparison when request headroom
returns, while preserving the independently frozen Q8 study. The cost rule
adds no model or KV reservation. The Q8 loader's shared 198,759-row pool
requires about 242.63 MiB more logical row storage at Q8. Those buffer-size
calculations establish neither the Windows physical-memory delta nor peak
allocation. The existing memory floors retain their values. This ordering
is a test-priority decision and supplies no measured speedup. Evidence is
retained in `primary0191/continuation-1904/q8-logical-storage.json`.

The existing manufacturer benchmark client and analyzer now have a private
0.19.1 source/profile adapter. Twelve CPU tests and independent review
verified all 60 historical request bodies and their order, cache-policy
compatibility and separate native-ledger, response-native and complete-HTTP
QPC summaries. The existing HTTP client and analyzer retain their exact
bytes. This preparation generated zero model requests. The current serving
profile remains selected. Evidence is retained in
`primary0191/continuation-1904/vendor-parity/receipt.json`.

The scheduled source refresh completed at **19:18:52 UTC**. Official driver,
Ryzen AI, XRT, WHIRL and libosmos release fields matched the earlier refresh.
The fresh **18:57 UTC** Halogen identity check was reused. Reddit direct
listings returned HTTP 403, and the web fallback retained incomplete current
coverage. The next broad refresh is due at or after **21:18:52 UTC**. Its
receipt is retained in
`primary0191/continuation-1904/source-refresh-1917/receipt.json`.

## Cost-rule comparison preparation and runtime recovery (21:29 UTC)

The finite cost-rule coordinator and saved-evidence exporter are now prepared.
The prospective [protocol](../benchmarks/halogen0191-mtp-cost-gate-plan-20261107.md)
and its [source pins](../benchmarks/halogen0191-mtp-cost-gate-plan-20261107.json)
freeze the two natural input workloads, gate/cost/gate order and fixed Q4
controls. The combined inactive package contains 53 candidate files and 50
rollback files. CPU verification passed 26 coordinator/trace tests and 74
exporter/historical tests. The final exporter reproduced 1,059 numeric leaves
across five earlier campaigns while preserving all ten published files.
A realistic restored-runtime fixture exposed a missing `match: true` version
field in the first exporter draft; the corrected source rejects missing or
false match markers. These are source/evidence checks, with zero cost-study
model requests and no measured performance gain.

The previously running server stopped at 21:00 UTC after physical memory
fell to 17.970 GiB, below the unchanged 18 GiB runtime floor. Its retained
outcome reports completed cleanup and memory recovery; the failed guard
left an ownership lock. An already-running normal recovery was observed
rather than duplicated. Authenticated reads at 21:28:37 UTC verified the
replacement server ready with API/engine 0.19.1, the exact selected profile,
one 32768-position slot/pool and paired 2048 prefill limits. It remains open
at port 8840. Available physical memory was approximately 25.29 GiB.
The read-only GPU admission snapshot at 21:29:10 UTC found no active GPU
engine counters and recorded RiotClientServices and RiotClientCrashHandler.
An initial interpretation incorrectly treated those services as a blocker.
Inspection of the effective call chain established that it records those
services but rejects actual games and nonzero GPU counters. Two fresh GPU
frames and authenticated idle/reserve checks passed at 21:33 UTC. The
registered cost comparison then started through the existing lifecycle;
Riot processes were preserved. No measured improvement is claimed until
the complete comparison terminates and normal serving is restored.

The source refresh completed at 21:25:20 UTC. Official Halogen remains
0.19.1; tracked AMD, Ryzen AI, XRT, WHIRL and libosmos fields were unchanged.
Reddit direct listings remained inaccessible (HTTP 403), so newest-post
coverage remains unverified. The next broad check is due at 23:25:20 UTC.
The broader acceleration goal remains unachieved. Private receipts are
retained in `primary0191/cost-gate-cohort-prep/`.
