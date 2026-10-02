# Windows heartbeat replacement fix - 29 September 2026

## Incident and cause

The reported failed run was `f370cd32681945999ba9da5be217bfd1`. Its independent
guard failed while replacing `lease.json`: Windows returned `WinError 5 / Access
is denied` from `os.replace`. The guard then stopped its owned container; the
controller displayed only `independent guard missing/stale/dead`. The engine
was still loading weights, not serving requests.

This was not the earlier memory-admission refusal. All 57 retained host frames
remained above the 12 GiB runtime floors: the minimum available physical memory
was 44.595 GiB and the minimum commit headroom was 168.940 GiB. Docker reported
`OOMKilled=false`, `Running=false`, PID 0 and an empty state error.
The exact process holding the transient file handle is not established by these
logs. A real Windows open-reader test reproduces the same rename denial.
Microsoft documents that an open handle without `FILE_SHARE_DELETE` can prevent
rename/deletion: https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew

## Correction

Atomic JSON publication retries Windows errors 5, 32 and 33 for at most a
2-second retry budget. Each retry uses the same fully written temporary file
and original timestamp. The live file is never truncated, removed first, or
replaced with an incomplete JSON document. Permanent errors still fail closed;
disk-full and other unrelated errors are not retried. The retry budget does not
bound a blocking operating-system syscall. The independent guard and container
lease remain responsible for loss-of-supervision shutdown.

The controller now includes the saved guard cause in its error rather than
only the generic stale/dead message. Failure to write the guard diagnostic file
can no longer skip the attempted identity-verified container stop.

The requested defaults are unchanged: 129024 context positions, one slot,
`ServeSeconds=0`, 900-second startup timeout. The 47 GiB physical/121 GiB commit
admission calculation, 12 GiB runtime floors, 44 GiB cgroup, exact ownership,
loopback-only port 8731 and bearer authentication remain in force.
The existing 45-second lease age and 12-second guard-freshness checks were not
relaxed. No model, engine, driver, BIOS or WSL configuration was changed.

## Regression and source checks

Seven new tests cover transient sharing errors, a real Windows reader blocking
rename, bounded permanent failure, unrelated I/O errors, serialization failure,
propagation of the root guard cause and shutdown despite diagnostic-write failure.
The original implementation failed the regression run; the corrected one passed
all seven. The timestamp is not refreshed to mask unsuccessful publication.

All 54 backend tests and all 10 shared helper tests passed on the installed
checkout. In a fresh indexed checkout with no installed runtime/assets, 51 backend
tests passed and three installed-asset tests were skipped. Its ten shared tests
also passed. All 16 PowerShell files parsed without errors.
The targeted source scan found no matching credential patterns; it is not an
exhaustive security audit. Models, installed binaries and credentials remain
excluded from Git.

## Recovery of the previously failed run

The previous lock was archived only after confirming its exact run ID, no old
controller/service process, the exact container already terminal, and the saved
baseline-relative recovery predicate. The original failure logs and outcome
were preserved byte-for-byte. Reconciliation evidence is retained locally under
`.local/repairs/lease-20260929-135627/`; the failed run was not relabeled a pass.

## Live validation

Run `9ec4490ddf0b41b2a8e71f7955534960` reached READY on the same machine with API and
engine version 0.14.2. `/health` confirmed context, slot context and KV pool
all at 129024, with exactly one slot. The startup checks returned `42` and the
correct German colour answer. The negative-token startup check passed.

A separate request without a token returned HTTP 401. The repository PowerShell
API helper returned exactly `OK`, including another successful request observed
317.4 seconds after READY. The configured serving duration was zero: the server
did not stop at the former 300-second limit. It was then stopped deliberately
with `Start.ps1 -Stop`, not by a duration cutoff or guard failure.

The final outcome recorded ready=true, cleanup=true, recovery=true and error=null.
The exact container was terminal, PID 0, OOMKilled=false. The guard exit
acknowledgement was present, no guard-failure record existed, and the run lock
was released normally. All 459 guard samples and the unchanged validated source
hashes were retained. The test server is stopped after validation.

[Compact evidence and file hashes](validation-heartbeat-fix-20260929.json) identify
the precise run and results. Full local logs remain in `.local/services/`.

## Limits

This validates this startup, short authenticated requests, survival beyond
five minutes after readiness and one clean stop/recovery on the existing host.
It does not establish days-long stability, near-full-126K prompt quality,
other context sizes, concurrent slots or GUFO/native integration. Real SSE
streaming was not separately exercised in this run; its existing automated
ASGI streaming tests passed. No public tunnel, network exposure, release tag or
main-branch promotion was configured.
