# Bounded cancellation polling in the independent PLE producer

The separate default-off v2 worker completed one full M8192 preparation in
2.541773 seconds for the external guard process, excluding native PowerShell
startup. Worker wall was 2.203000 seconds, sampled before ready-receipt
publication. Root compared every byte of the 40 MiB BF16 input with the
original GPU input, and every byte of the 80 MiB FLOAT widening with its frozen
reference. Both are identical. Row IDs, preceding/final history, LUT, output
digests, read plan and all 431,407,104 payload bytes match v1.

V2 replaces per-boundary cancellation-file probes with a 10 ms cooperative
cadence. Deadline checks remain at every existing boundary and run again
after a filesystem probe. Request entry forces a fresh probe; final ready
publication forces another after receipt fsync immediately before atomic
rename. A canceled task cannot publish ready. A blocking read, fsync, file
probe or scheduling delay can postpone a cooperative boundary, so 10 ms is
not a hard end-to-end cancellation bound. The 170-second worker deadline and
180-second outer owned-process lifetime remain unchanged.

The narrow real-file behavior validation failed on v1's uncadenced 5,000
checks inside a controlled 5 ms interval, while entry cancellation, deadline
and canceled publication passed. All four cases passed with v2. The clock was
controlled only for deterministic boundary testing; these are behavior checks,
not speed measurements. Independent source review found no functional blocker.

| Actual v2 component scope | Seconds |
|---|---:|
| Complete external CPU guard | 2.541773 |
| Worker, excluding ready-receipt publication | 2.203000 |
| Inclusive table-read phase | 0.596349 |
| Payload seek and read inside that phase | 0.462854 |
| Row scatter | 0.794080 |
| Payload read hashing | 0.204365 |
| Output persistence | 0.068771 |
| All finalized filesystem cancellation probes | 0.003977 |

The ready receipt snapshots 363,379 gate checks, 363,512 deadline checks and
133 filesystem probes before publication. Process stdout records finalized
counts after the final forced probe: 363,380 / 363,514 / 134. The extra probe
is excluded from already serialized ready metrics; no receipt is rewritten.
The seek/read timer includes the operating-system filesystem/cache path, and
does not measure physical SSD device latency alone. It is nested inside the
inclusive table-read timer and must not be added to it as a separate stage.

The earlier v1 window took 24.955329 seconds externally. Both windows used
the same input and ranges, but cache state was not controlled. The observed
wall difference is therefore not a qualified old/new speedup attributable to
cancellation polling. No cold-cache claim or speedup percentage is reported.
Neither terminal worker will be repeated unchanged for another diagnostic.

The child and guard exited zero, errors were empty and the owned job closed.
Minimum physical reserve was 26,395,676,672 bytes (24.58 GiB), with commit
headroom 122,708,430,848 bytes (114.28 GiB). Admission remained 22/22 GiB;
runtime floors remained 18/18 GiB. Source, helper, input, constants and table
pins were checked again after completion. The worker accessed no accelerator,
provider, old sparse atlas, expected native input or live mapping.

The measured preparation cost supports further work on a lookahead producer,
but this remains chunk-zero fixture validation. It does not prove later-chunk
request/history ownership, live Windows publication, a real readiness lead,
persistent NPU feeding, output packing/transport, consumer quality or serving
gain. The separate strict CPU projection mismatch remains unresolved. The
next mechanism is a small request-owned raw-token publication before Target,
so the next complete 8K chunk can be prepared independently while the current
chunk executes. Its actual timing and ownership must be demonstrated.

The original server remains ready/open on port 8840 with context capacity
262144. No server lifecycle change or GPU/NPU call occurred in this window.
There are no new Prefill tok/s, Decode tok/s, native MTP acceptance or NPU-on/off
throughput results. The full acceleration goal remains active and unachieved;
the automation remains paused.

Evidence: [full audit JSON](halogen-ple-independent-input-v2-20261008.json).
Baseline input proof: [v1 report](halogen-ple-independent-input-20261008.md).
