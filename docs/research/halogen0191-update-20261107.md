# Halogen 0.19.1 update, 7 November 2026

The PowerShell 5.1 launcher selects Halogen **0.19.1 CurrentText32K** by default.
The latest Voice configuration explicitly selects two 32K slots, a 65536-position
KV pool, two concurrent requests and a paired 2048-token prefill chunk and arena.
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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentText32K -Slots 2 -KvPoolPositions 65536 -Concurrency 2 -PrefillTokens 2048 -ConsoleTrace
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
The explicit capacity profile retains startup admission of at least 30/131 GiB,
runtime guards of 18/18 GiB and request-entry admission of 22/22 GiB.

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
observation confirmed the restored normal two-slot 2048 profile ready, with
request-entry admission ready. The final controller and backend runs are
`c0f914b3674d46ff8e22e5059d84900e` and
`df10d3939eb84bb28088fc93c2ce2b67`. The profile SHA256 remains the same.
That observation is retained at
`server/.local/halogen-update-20261107/primary0191/final-ready-20261107T130414824304Z.json`.

The frozen 8K/16K cohort completed one excluded warmup and three measurements
per input. Its API-reported prefill/decode means are 1191.85/46.62 tok/s at 8K
and 1125.72/48.98 tok/s at 16K. Complete-request QPC means are 9.666991 and
17.241034 seconds. Every reported phase sum fits its corresponding whole HTTP
interval. Independent RAW phase-clock qualification remains pending.
The OEM operating-mode readback was unavailable to the non-elevated process.
[Fresh 0.19.1 observations](../benchmarks/halogen0191-natural-8k16k-20261107.md).

The retained 0.18.22 and earlier benchmark quantities describe their original
runs. [Historical 0.18.22 phase measurements](../benchmarks/halogen01822-raw-8k16k-20261101.md).
