# Configurable service validation - 29 September 2026

> Historical pre-fix record. Subsequent 126K startup, authentication and lifecycle
> checks are recorded in [the heartbeat-fix validation](validation-heartbeat-fix-20260929.md).

## Scope and status

This change adds the normal `Serve` launcher alongside the retained finite 4K
qualification profiles. Default context is 129024 positions (126 * 1024), with
one slot and `ServeSeconds=0` (no serving-duration cutoff). Context accepts
4096..262144; accepting this range does not qualify every configuration on hardware.
The new controller, ASGI authentication wrapper and container liveness supervisor
have **not completed a live model-start/serve/stop qualification** in this update.
The published earlier 4K live results apply to the old finite controller only.

## Executed source and fixture checks

- 47 backend tests passed, zero skips, in 2.337 seconds on the installed checkout.
- 10 shared selector/API-helper tests passed in 12.931 seconds.
- 16 PowerShell files parsed without errors.
- The new installed-entrypoint test verifies all four exact API invocation sites.
- ASGI fixtures reject missing, incorrect and duplicate Authorization headers,
  preserve streaming body chunks, protect the health/models/Responses/metrics
  routes, and exclude credentials and query strings from request log records.
- Parameter fixtures verify 129024/continuous defaults, explicit context values,
  both context and KV-pool settings, exact live-health expectations, scaled memory
  admission, stable-window waiting and timeout without lowering the thresholds.
- Command tests verify loopback-only publication, one slot, retained cgroup
  limits, disabled automatic restart, log rotation and a liveness lease rather
  than a fixed container lifetime. Stale/wrong-identity lease cases are tested.
- Source hashes and prior installed engine/bridge/probe identities passed their
  existing tests. No engine or upstream API binary/source file was modified.

These are source/fixture checks. They are not evidence of live authenticated
inference, maximum-context correctness, long-running stability or live recovery
of the newly introduced service supervisor.

## Actual launch attempts

The Windows launcher initially encountered a PowerShell app-alias versus resolved
MSIX-path difference. It now preserves the recorded PowerShell directory in the
child process's PATH only, after resolving Python. The exact installed-machine
comparison remains enabled. An incorrect initial count of API invocation sites
was corrected against the pinned entrypoint and covered by a regression test.

Later launches refused BEFORE Docker container creation/model allocation:

| Requested context | Required free physical / commit GiB | Sample at refusal |
|---|---|---|
| 129024 | 47 / 121 | 45.89 / 202.36 |
| 129024 | 47 / 121 | 46.14 / 202.66 |
| 129024, after a stable window | 47 / 121 | 46.18 / 202.69 at immediate recheck |
| 65536, explicit smaller test | 45 / 119 | 44.87 / 201.17 at immediate recheck |

The desktop's available-memory readings varied. A read-only inspection measured
about 50 GiB before a Docker/WSL invocation and 46.3 GiB after it. No user
applications were closed and no memory guard was relaxed to make a test pass.
Read-only model-file cache advice and one transient WSL page-cache reclamation
were attempted while no containers were running. They did not establish adequate
stable headroom. Model files and persistent host settings were not changed.

The final attempt is `26a407b5c57f479fa95031efcdbfbd48`; it requested 65536, not
the default 129024. Its outcome is failed inference admission, with cleanup and
recovery recorded true. That does NOT mean an engine loaded successfully: no
model container was created. All attempts and refusal logs remain in ignored
`.local/services/`. No live service remains running after this work.

## Authentication and logging

The launcher generated a local 256-bit random token in ignored `.local/api-token.txt`
and restricted its Windows file access to the user and SYSTEM. The token is not
in source, environment arguments, manifests or this validation record. The ASGI
wrapper has passed fixtures, but real authenticated requests could not be tested
because the model did not start. The endpoint is configured as
`http://127.0.0.1:8731/v1`, not claimed to be currently ready.

Service/engine logs and host telemetry rotate locally. Normal serving has no
fixed 300/600-second cutoff, but memory failure, startup timeout or a stale
controller/guard lease can stop the owned engine. Longer-than-300-second live
serving, end-to-end streaming and a near-full-context request remain untested.

## Publication boundary

This belongs on the existing source-integration branch, not as a validated runtime
release or a main-branch upgrade. The default and parameter behavior are implemented;
the new runtime lifecycle still needs a successful controlled hardware run when
memory admission passes. Original dirty research/native installations and the
0.13.8 compatibility package are not replaced.
