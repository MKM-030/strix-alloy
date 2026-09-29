# Startup reliability investigation - 29 September 2026

## Scope

This change retains Halogen 0.14.2, the existing engine and all compatibility
binaries, a 129024-position context and pool, one slot, bearer authentication,
continuous serving, exact container ownership and all existing memory floors.
It changes startup file-cache scheduling and makes guard failures measurable.

## Reported failure

Run `1eef2c3809be43ddb41954ffb42b6e37` completed both registration phases and
was stopped while preparing weights. The guard reported only
`missing/stale/unsafe direct Windows memory frame`. Its last five saved samples
fell from 15.985 to 12.289 GiB available physical memory. The rejected sample
was not saved by the old implementation, so its exact value and whether its
age also contributed cannot be reconstructed. Docker reported no OOM kill.
The earlier clock and file-replacement defects are distinct and their fixes
remain enabled. This run is preserved as a failure.

The successful earlier 126K run and the reported failure have identical model
launch environments. The failed run's observed physical-memory decline was
36.123 GiB, versus 24.747 GiB in the earlier successful run. No model, backend,
context, slot count or driver substitution explains that difference.

## Why the controller needed another change

The old main startup loop made a blocking HTTP health request before doing
model-file cache advice. A slow/non-listening API delayed the next advice.
There was no independent record of Linux cache occupancy or advice timing.
This creates avoidable coupling between API readiness and memory housekeeping.

The new startup-only helper runs inside the owned container, advises only the
two already-mounted, read-only HGN files, and records guest/cgroup memory
before and after each attempt. The host monitors its progress independently.
The helper must stop, exit successfully and acknowledge shutdown before the
first smoke request or client-ready announcement. It never performs global
`drop_caches`, changes registered model mappings, or advises client caches
during serving. A startup deadline and container ownership still apply.

`POSIX_FADV_DONTNEED` is advisory, not a promise of immediately returned Windows
RAM. Microsoft explains that Linux page cache can retain WSL host memory until
Linux releases it. These facts motivate measurement rather than assuming that
an advice call guarantees reclaim.

The guard now logs the actual sample before evaluating it. A failure records
physical/commit values and sample duration; pressure, stale measurements and
malformed data have distinct messages. Engine-exit reports include a recorded
guard cause when available. The 12/12 GiB safety floor was NOT lowered.

## Windows memory-compression experiment

During the first instrumented start, Windows' Memory Compression process had
an observed 8113405952-byte working set and later 14630699008 bytes (13.626 GiB).
The file-cache worker alone reached READY, but its lowest free-physical sample
was only 12.339 GiB. That narrow margin is not sufficient evidence of robust
startup across desktop activity.

For the next controlled start, only `MemoryCompression` was disabled with the
Microsoft MMAgent cmdlet after the prior server stopped and recovered. The
original value was true; PageCombining, prefetch, prelaunch, OperationAPI and
SysMain were left unchanged. There was no reboot, driver, BIOS, pagefile, clock,
WSL or security change. The next run reached READY and its observed minimum
free physical memory was 16.532 GiB. This is a measured configuration comparison,
not proof that compression was the sole cause: OS state and file-cache warmth
were not identical. A third run with the same disabled setting still had a
large Memory Compression working set and a 12.285 GiB minimum. The apparent
improvement did not repeat, so disabling this setting is NOT the repair. Compression also normally serves a useful purpose, so this
is not an unconditional recommendation for other machines.

The diagnostic change was reversed and all five inspected MMAgent settings
were verified equal to their original values. The final verification run uses
the restored original host settings. No installer or launcher changes MMAgent
settings automatically. No reboot was performed during this experiment.
To restore the original setting, after stopping inference, use Administrator
PowerShell: `Enable-MMAgent -MemoryCompression`. The saved before/after records
and local diagnostic scripts are not distributed as auto-executing setup.

## References used in the investigation

- Microsoft WSL memory reclaim: https://devblogs.microsoft.com/commandline/memory-reclaim-in-the-windows-subsystem-for-linux-2/
- Linux posix_fadvise: https://www.man7.org/linux/man-pages/man2/posix_fadvise.2.html
- Windows available physical memory: https://learn.microsoft.com/windows/win32/api/sysinfoapi/ns-sysinfoapi-memorystatusex
- WSL configuration: https://learn.microsoft.com/windows/wsl/wsl-config
- Disable-MMAgent: https://learn.microsoft.com/powershell/module/mmagent/disable-mmagent
- Enable-MMAgent: https://learn.microsoft.com/powershell/module/mmagent/enable-mmagent

## Tests and evidence boundaries

The initial installed Windows suite discovered 77 tests: 73 passed, four
Linux-only checks skipped. The ten shared helper tests passed. All ten new
startup-cache tests, including a real readonly file-advice check, passed in
Linux. Sixteen PowerShell files parsed without errors. These fixture results
are separate from the live runs and do not certify every failure path.

The live validator checks actual 129024 context/slot/pool, exact 0.14.2 API/engine
versions, missing/incorrect-token HTTP 401, short arithmetic, a 22524-token prompt
and genuine SSE chunks ending in [DONE]. The third run additionally processed
120024 prompt tokens inside the 129024-position window. The prompt is a controlled
repetitive workload; this is not a broad model-quality or semantic-retrieval test. No speed superiority is claimed.

The original incident evidence is unchanged. Any final snapshot and subsequent
public endpoint check are recorded separately rather than inherited from an old
successful build. No binaries, models or credentials are included in this source
change; native and GUFO backends are not newly qualified by it.

## Repeated live results and final host state

| Run | Windows compression setting | Minimum free physical GiB | Long prompt tokens | SSE | End state |
|---|---|---:|---:|---|---|
| dd576496 | Original/enabled | 12.339 | 22524 | Passed | Clean stop and recovery |
| 5cf071e3 | Temporary diagnostic disabled | 16.532 | 22524 | Passed | Clean stop and recovery |
| df1dff04 | Temporary diagnostic disabled | 12.285 | 120024 | Passed | Clean stop and recovery |
| ac78e241 | Original/enabled restored | 18.033 | 120024 | Passed | Left serving |

All four runs used the same final runtime source hashes, 129024 positions,
one slot and no fixed serving cutoff. Each verified the engine/API identity,
rejected missing and incorrect tokens with 401, answered the arithmetic and
short-answer probes correctly, and delivered genuine streaming content with
[DONE]. The two 120024-token probes completed in approximately 99 and 98 seconds;
these timings describe these repetitive serial tests only, not a new benchmark.

Three deliberate stops verified exact owned-container terminal state, memory
recovery, normal guard exit and lock release. The fourth run is intentionally
left running for the user, so no fourth terminal/cleanup result is claimed.
Its minimum free-memory figure is a snapshot, not a future stability guarantee.
The other runs demonstrate that startup margins can still vary with host state;
keep the guard enabled and do not assume simultaneous gaming is qualified.

MMAgent's five inspected settings were restored and verified against the original
snapshot before the final run. MemoryCompression is enabled again. The temporary
experiment is retained as an inconclusive hypothesis, not a required workaround.
There is no lasting BIOS, driver, WSL, pagefile, SysMain or memory-tuning change.
No unrelated user application was closed. Original failed evidence remains intact.

## Fresh-checkout test correction

The parser test initially excluded any absolute path containing `.local`, which
also hid real source files when a fresh checkout was placed below a diagnostics
folder of that name. It now excludes repository-relative generated paths only.
A deliberately broken backend fixture reproduces the old missed check; two new
regression tests cover both source detection and correct generated-file exclusion.
All 12 final shared tests pass. Both working and fresh checkouts parse all 16
PowerShell source files. The fresh backend suite has 70 passes and seven explicit
skips (three installed-asset and four Linux-only tests); none is counted as a pass.

[Compact run evidence and source hashes](validation-startup-reliability-20260929.json)
records all four runs and the distinct test scopes. Full operational logs and
before/after/restore snapshots remain local under the ignored repair directory.

## Tailscale follow-through

After the local service passed readiness and authentication checks, the existing
explicitly requested Funnel helper was executed. The account owner approved the
one-time Funnel setting. The CLI then confirmed HTTPS port 443 forwarding to
127.0.0.1:8731, with AllowFunnel enabled for this device only. Public DNS resolved
Funnel relay addresses and an HTTPS request from the Windows PC without a token
returned 401 and the expected authentication error. NAS and router settings were
not changed. The runtime API remains loopback-bound behind the TLS proxy.

Authenticated local requests and real local SSE were tested as above. A separate
external execution environment could not reach the endpoint from its restricted
network, and a separate authenticated public-relay probe was not completed. Do
not describe this as a test from the user's actual cloud instance. Its credential
remains local and was never added to this repository. Disable Funnel before ever
switching the exposed port to a legacy unauthenticated diagnostic profile.

Final recheck: the last server answered the repository API helper with exactly OK 754.3 seconds after READY (over twelve minutes). All 12 shared tests also passed from the final indexed checkout. The server was not stopped after this check.
