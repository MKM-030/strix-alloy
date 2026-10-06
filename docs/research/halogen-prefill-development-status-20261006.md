# GPU, CPU and NPU development status, 6 October 2026

No new serving Prefill, Decode or native MTP acceptance improvement is qualified.
The normal stock server is restored, ready and open on port8840. The
[evidence](halogen-prefill-development-status-20261006.json) records terminal
attempts, source hashes, checks and the successful restoration receipts.

The compact-Q8 two-row GPU MTP kernel measured133.050µs against130.425µs for the
original in the [completed component screen](halogen-gpu-hidden-q8-rows2-screen-20261006.md).
Its mean component latency is2.012% higher; it remains disabled. These are
component timings, not measured serving token rates or acceptance deltas.

| Candidate | GPU | CPU | NPU | Possible serving effect |
|---|---|---|---|---|
| Native packed HT Prefill pipeline | Failed exact captured output | Submission and validation | No qualified packed consumer/interface | Retired before measured cohort |
| Selected50MiB original-W cache | Exact outputs, 1.5208% higher mean component latency | Immutable binding and lifetime | No useful producer or extra storage established | Disabled; no serving comparison justified |
| Compact two-row MTP kernel | Slower in completed component comparison | No demonstrated offload benefit | No demonstrated offload benefit | No gain adopted |

Exact arithmetic can preserve proposals while reducing computation time. Higher
acceptance requires better proposals; it does not follow from a faster kernel.
The [selection policy](halogen-accelerator-selection-policy.md) requires all three
processor placements and actual serving outcomes to be assessed after every
development. The cache [design](halogen-selective-original-weight-cache-design-20261006.md)
retains original packed weights and is conditional on component correctness,
useful savings and later serving qualification.

The [finite Prefill component comparison](halogen-prefill-ht-component-screen-20261006.md)
completed arithmetic. Cached original weights measured 23.2392 ms against
22.8911 ms stock over eight balanced pairs, with all original output bytes
preserved. Native HT failed exact output qualification. Neither path establishes
a Prefill, Decode or acceptance gain, and neither proceeds to serving integration.
Startup attempts previously failed at memory admission, constructor activation
on a CLI probe, a modified pinned README, and a transient Windows status read.
Their failure receipts remain failed. No warmup or failed attempt is presented
as a post value.

The constructor now activates only exact serving argv1`--ck`, with five actual
CPU probe cases passing against the compiled adapter. Restoration accepts only
exactly linked terminal cleanup/recovery. The private observer reuses the normal
bounded Windows reader, continues the same verified process on transient access
errors, and durably retains pending identities when snapshots remain unavailable.
The actual Windows sharing error and recovery were exercised without an engine;
the pending snapshot helper was also checked. The
[independent review](halogen-prefill-ht-replay-independent-review-20261006.md)
records their scope. Global production/lifecycle files are unchanged.

The last failed startup's engine and all owned Windows processes were confirmed
terminal; Docker ownership, closed ports and original-baseline memory recovery
were independently proved before the exact lock was archived. This supplemental
closure preserves the failed normal cleanup evidence. A stock-only normal
restoration then passed with no errors and closed its owned WSL hold job.

The completed component run encountered a separate export directory collision.
Its failed coordinator receipt remains preserved. Root exported and validated
the five small inventory-hashed files from the exact stopped container without
repeating arithmetic. Normal stock restoration completed in that same run and
its final ready receipt passed. The export now uses a distinct exclusive results
directory; the actual filesystem regression reproduced the old collision and
passed after the correction. An independent source review released the fix.
No NPU producer, synchronous offload, driver or global WSL change was introduced.
