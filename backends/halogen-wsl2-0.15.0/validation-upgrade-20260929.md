# Halogen 0.15.0 upgrade validation - 29 September 2026

## Scope and provenance

The source integration starts at `60e5b885e4007901f421de4a9764e8f07ab2d205`.
The existing 0.14.2 backend is retained unchanged as a separate rollback package.
Upstream main was inspected at `f9efa0ddad12a94699132dc9ed28292096c0f758`.
Both GHCR `latest` and `0.15.0` resolved to the same manifest digest:
`sha256:28ef278ab621a67b02550d1f1bfecfe641552803b96dae588018425fcfe38f36`.
The complete official image was pulled and inspected. Its engine, entrypoint,
API and HIP header hashes were independently checked against the extracted files.

The old w4b checkpoint, overlay and tokenizer are reused without conversion.
Both checkpoint and overlay environment paths are explicit; the image's newer
v2 model default cannot silently change the workload. V2 weights are not supplied
or qualified by this update. Source references are the upstream CHANGELOG and
entrypoint at the recorded commit, plus the immutable official registry manifest.

## Compatibility adaptation

The new engine is pinned to SHA256
`a7c096afa6c882cc8ee5fadae1311f49826c047ecf7731a5339efa3b7a413181`.
The compatibility site's file offset is `0x116d750` and RVA `0x116e750`.
Its unique instruction signature, ELF layout and enclosing function hash are
verified by the version-specific adapter before installation is admitted.
The enclosing function is not byte-identical across releases. The relocation-aware
inspection and actual trace are not presented as a proof of full engine equivalence.
The API file and checked HIP header are byte-identical to the prior image.

All three interoperability components were rebuilt with GCC 13.3 and verified by
hash during a separate installation. The new package does not reuse unverified
binaries from the working old installation. The engine itself is not redistributed
or modified on disk. Original adapter source and notices remain in the repository.
The live pre-registration trace passed the exact 252-range model plan and verified
owned-container shutdown/recovery before normal serving was attempted.

## Old-service transition

Public Funnel forwarding was paused before stopping 0.14.2. Its model process
terminated correctly, but its original 180-second baseline-relative recovery check
timed out while desktop memory use had changed. That recorded failure was retained.
A separate check later confirmed the exact old container remained terminal and
five fresh memory frames met the original recovery predicate; only then was its
lock archived and the new diagnostic started. No user application was terminated
and no memory floor or OS setting was changed to force a pass.

## Retained service behavior

Default context and KV pool are 129024 positions, with one slot. Normal serving
has no fixed lifetime. Startup cache scheduling, exact ownership, sequence-based
liveness, Windows atomic-publication retries, bearer authentication and rotating
logs are retained from the repaired 0.14.2 service. The old API token was explicitly
copied locally for continuity and is not present in the source or this report.
The service refuses a health response reporting the previous engine/API version.

The upstream 0.15.0 API reads its version from the pinned image environment.
The shared API source being unchanged does not excuse accepting a 0.14.2 engine;
actual health/version and immutable image identity are checked separately.

## Executed test coverage

| Check | Result |
|---|---|
| Installed 0.15.0 Windows backend suite | 93 discovered: 77 passed, 16 Linux-only skips |
| Fresh indexed checkout without installed assets | 93 discovered: 74 passed, 19 explicit skips |
| Shared selector, API helper and parser regression tests | 13 passed in both checkouts |
| PowerShell syntax | All 20 source files parsed in both checkouts |
| Linux bridge/ABI fixtures | 12 passed with compiled production and fixture libraries |
| Linux startup-cache fixtures | 10 passed, including read-only file advice |
| Linux supervisor subprocess fixtures | 3 passed, including child termination on lease loss |

The initial copied tests correctly exposed an old image expectation and a UTF-8
round-trip mistake in a smoke-answer string. The runner was reconstructed from
its original UTF-8 source and the exact new image expectation was corrected before
live testing. The copied production-bridge test's old engine SHA expectation was
also changed to the pinned new engine; its no-bypass checks remain enabled.

The new version tests require the exact 0.15.0 image and explicit legacy checkpoint
and overlay paths. They reject a 0.14.2 health response and retain the 126K,
continuous-serving defaults and memory floors. Source hashes match in a fresh
checkout exported with `core.autocrlf=true`. Version-local attributes preserve
pinned source bytes, including intentional inherited Windows line endings.
The byte-pinned telemetry helper's original final blank line is preserved.
Models, extracted binaries, headers, credentials and local telemetry are excluded
from the staged source; a targeted scan is not an exhaustive security audit.

## Live results

Both complete service starts reported engine and API 0.15.0, with actual context,
slot context and KV pool at 129024 and one slot. Missing and incorrect tokens
returned HTTP 401. Short-answer and arithmetic requests passed. Each run processed
120024 prompt tokens and returned the expected answer. Each also delivered genuine
SSE chunks ending in [DONE]. These repetitive prompts verify that workload, not
broad semantic quality or a performance advantage over the prior version.

| Run | Long prompt tokens | Seconds for controlled long request | SSE | End state |
|---|---:|---:|---|---|
| e6bddf6d | 120024 | 100.953 | Passed | Clean stop, guard exit and memory recovery |
| 07ba7a91 | 120024 | 101.156 | Passed | Left serving |

The first service stopped deliberately with its exact owned container terminal,
no OOM kill, confirmed memory recovery, normal guard exit and lock release. The
second run is intentionally left running; no second terminal result is claimed.
No runtime code or source pins changed between these two service runs.

## HTTPS restoration and limits

The original Tailscale Funnel route was restored only after local authentication
and new-version checks passed. HTTPS tests through the existing hostname returned
401 for missing/incorrect tokens, reported engine/API 0.15.0 and context 129024,
answered an authenticated chat request, and delivered SSE through [DONE]. These
requests originated on the Windows PC, not in the user's external cloud instance.
The API token and route were retained. No NAS/router, driver, BIOS, WSL, pagefile,
Windows memory-compression or global memory policy setting was changed.

This is a version-pinned update on the integration branch, not a main-branch merge,
combined runtime ZIP or an upstream WSL-support claim. Existing 0.14.2 and 0.13.8
packages are byte-preserved. No v2-model, multi-slot, days-long stability or arbitrary
other-context guarantee follows from these tests. New model assets require their
own memory/compatibility validation rather than reusing this w4b qualification.

[Compact evidence](validation-upgrade-20260929.json) contains image/component pins,
actual run IDs, test scopes, response usage, observed guard minima and public HTTPS
results. Full local logs and the pre-upgrade source archive remain ignored locally.

The first HTTPS probe immediately after enabling Funnel encountered a transport EOF; a subsequent probe succeeded after the route became reachable. TLS verification and authentication were not disabled.
