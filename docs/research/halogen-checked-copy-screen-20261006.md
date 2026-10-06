# Checked-copy GPU-row consumer screen — 6 October 2026

The new default-off CPU validation path built successfully and completed a
natural16K candidate window, but **the full serving comparison failed**. No
speed gain, complete hit coverage or NPU integration is qualified. The original
arena8192 server is ready, idle and open on port8840; all own measurement helpers
are terminal. Automation remains paused.

| Window | Prefill tok/s | Decode tok/s | Native acceptance | Status |
|---|---:|---:|---:|---|
| Stock before | 1204.70 | 35.90 |186/387=48.06%|Completed single stock window|
| Checked-copy candidate | 1211.14 | 36.63 |186/387=48.06%|Recorded rates; comparison unqualified|
| Stock after | — | — | — |Not measured; original restoration only|

Both completed windows used exactly16384 once-only natural input tokens and128
output tokens, capacity262144, temperature0/seed1, Thinking Off, Cache Off,
MTP2/PLD3,3, arena/chunk8192, one excluded warmup and three measured requests.
All four sample output hashes and accepted/drafted counts agree. Clock
calibration and zero prompt/disk restores passed. These values are separate
from the historical8K48.42 tok/s workload.

The observed candidate difference versus the first stock window was
+0.53% Prefill and
+2.03% Decode. **This is not
a qualified gain.** The runtime observer captured one2.778825% Copy-engine
sample attributed to Windows System PID4, at00:56:00UTC during the candidate
warmup. Its source is unresolved; it cannot be called another application or
proven to belong to Halogen. The observer rejected the window before the
after-counter read. No nonzero complete skip count was therefore retained,
and the last stock cohort was replaced by normal original restoration. No
samples were removed and the screen was not rerun merely to enlarge gates.

The earlier observer also rejected its own sole WSL VM worker as foreign
because Windows names it `vmwp`. That prior matrix is retained at
`C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004\checked-copy-natural16k-ed25fbc8025f42ab9c6f5aa5fc76818e`;
it never started a candidate engine. A still earlier preparation failed before
inference because the watcher executable path was relative. Both invalid
attempts remain excluded from this report's stock result.

GPU applicability: the consumer intends to skip original gather/RMS/M1 and
reuse immutable original GPU row bytes. CPU applicability: replace18 live
maps scans per hit with exact-length kernel-checked owned copies. NPU
applicability: a producer would add preparation/publication costs; it remains
deferred because this consumer has no qualified serving gain. Ordinary target
Prefill is outside this MTP branch. Exact replacement intends unchanged
proposals and acceptance. The separate GPU hidden-vector sibling was slower
(160.095 versus136.962 microseconds) and remains disabled; component latency
is not converted into measured tok/s.

Root's focused C host test passed, and both-gate shared-library compilation
passed with `-Wall -Wextra -Werror`. Fresh before/after input hashes sealed that
build. The independent source reviewer found no remaining actionable defect
after the null-token and completion-semantics corrections. Independent cohort
review led to request-accounting, per-sample acceptance, native engine-identity
and runtime-interference checks. Source/binary tests do not replace the missing
live coverage or complete stock bookends.

Raw evidence and the source-sealed lifecycle are in `C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004\checked-copy-natural16k-9d18432c19c447a29a2c7f6622d286ea`. The JSON companion
retains hashes, the exact observer incident and restored identities. The
minimum root runtime reserves were
30.466 GiB physical and
122.195 GiB commit.
Both startup admissions retained44/131 GiB stable60seconds; that does not
prove exact44 GiB sufficiency. The full acceleration goal remains unachieved.
