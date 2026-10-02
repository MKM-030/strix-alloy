# Clock-independent container lease - 29 September 2026

## Failure and diagnosis

The failed run `62899697e0df4b948f70c763d282e6c1` stopped in the container
lease supervisor during model loading. Its Windows guard continued to publish
frames and exited normally during cleanup. There was no guard-failure file;
Docker recorded OOMKilled=false, and cleanup and recovery were confirmed.
The original evidence files are preserved, not relabeled as successful inference.

The old container check subtracted a Windows-produced UTC timestamp from the
WSL clock and accepted at most five seconds of future skew. Three bracketed
clock samples immediately after the report found Windows approximately 5.8
seconds ahead of WSL (warm-sample bounds 5.755..5.832 seconds). A current
Windows heartbeat can therefore be rejected as coming from the future despite
an active guard. The original generic lease message does not retain the exact
failed read or age, so no specific file-sharing process is attributed here.
This clock-domain defect independently reproduces the false rejection.

## Fix

The Windows guard now publishes schema 2 lease records with a monotonically
increasing sequence for the exact service run. It increments only after checking
the controller heartbeat, memory floors and periodic container ownership.
The timestamp remains diagnostic; the container never compares it with its clock.

The container first observes a baseline sequence and requires a subsequent
advance before starting the engine. A static stale file cannot authorize startup.
After startup, only a higher sequence renews the local deadline. Duplicate
sequences and changed UTC timestamps do not renew it. Invalid schema, a different
run ID, backwards sequence or expired lease fail closed. A late renewal cannot
revive an already expired deadline.

The production no-progress limit remains 45 seconds. Linux uses CLOCK_BOOTTIME
(including suspend); the portable fallback uses time.monotonic. The absolute
values of these clocks are never sent across the OS boundary. Brief read errors
consume the existing lease budget and cannot extend it; persistent read failures
still stop the owned process group. Diagnostic messages now distinguish missing
progress from invalid lease data.

The 126 * 1024 = 129024 context default, continuous serving, one slot, 47/121 GiB
admission, 12/12 GiB runtime floors, pinned engine, bearer authentication and
Windows atomic-replace retry fix are unchanged. No clock, driver, BIOS, registry
or Windows/WSL setting was changed.

## Tests

Ten new deterministic tests cover renewal before startup, large UTC offsets,
forwards/backwards UTC changes, duplicates, expiry, late renewal, backwards
sequence, malformed records and exact run identity. They also assert that the
consumer does not call wall-clock time to calculate its deadline. The saved old
source lacks the progress protocol and fails this regression suite; the updated
source passes it.

Three Linux CPU-only process fixtures exercise actual supervisor and child
processes: static-file startup refusal, operation with extreme timestamp offsets
followed by guard-writer loss and verified child termination, and recovery from a
brief missing lease file. The fixtures shorten the timeout only in their isolated
Python subprocess; production code offers no such override. No model, GPU or
Docker container is involved in these fixture tests. All three passed.

The first installed Windows run passed 64 backend tests and 10 shared-helper
tests, with all 16 PowerShell source files parsed. The Linux process fixtures are
separately executable and explicitly skipped on Windows.

## Runtime validation and exposure

Live model startup and Tailscale exposure are tracked separately from these
source/CPU checks. A refused memory-admission attempt is not a model-start pass.
Do not lower floors, kill user applications, or expose an unauthenticated older
profile to make this workflow complete. Runtime findings for this change are
recorded in the accompanying validation JSON.

## References

- Python clocks: https://docs.python.org/3/library/time.html#time.monotonic
- Tailscale Funnel: https://tailscale.com/docs/features/tailscale-funnel

### Actual attempt after the correction

Run `21cd229604f442fc9a61220152a93b3d` requested 129024 positions and continuous serving.
It refused before container creation: the immediate admission reading was
43.97 GiB free physical memory against the unchanged 47 GiB requirement.
Commit headroom was 197.92 GiB against 121 GiB required. Cleanup and recovery
completed and the lock was released. An active game and its client were observed;
no user applications were closed. This is not a live model-start validation of
the clock fix.

The fresh indexed checkout passed 61 backend tests (six explicit skips: three
installed-asset checks and three Linux-only process fixtures) and all ten shared
helper tests. PowerShell parsing passed in the working copy and fresh checkout.
The three Linux process fixtures were run separately and all passed.

Tailscale is now signed in on Windows. Funnel configuration is still empty.
No public forwarding was enabled because the new local server did not reach
READY; no authenticated public request or external streaming test is claimed.
After freeing sufficient memory, use the normal Start.ps1. Once READY and local
API authentication pass, the previously prepared local Enable-HalogenFunnel.ps1
can publish HTTPS. It must not be run against an unauthenticated legacy profile.

[Machine-neutral evidence summary](validation-clock-fix-20260929.json).
