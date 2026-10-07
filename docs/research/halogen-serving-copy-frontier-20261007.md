# Serving Copy and health frontier, 7 October 2026

The warmed-guest admission and exact-cgroup fixes remove the recorded bootstrap
failure. They do not establish exclusive Windows System Copy ownership or
qualify the incomplete checked-copy speed comparison. Retire the unchanged
identity-capture draft as the next acceleration experiment. The current normal
0.16.2 server remains ready and open; no lifecycle or hardware test was performed
for this review.

## Health polling is not an established performance candidate

The extracted matching 0.16.2 API source has SHA256
`8607cc429448b7eaa51c1bad68fe24c5c59f4bf8662eb28bbf21b130236ac4f1`.
Its `probe_live` opens a separate socket and sends PING/read PONG, caching the
completed probe result for one second, including failures. It neither invokes
generation nor acquires the engine slot
semaphore or engine socket write lock. The health handler checks the semaphore's
state without acquiring it. Cache enumeration is a separate route because it
does acquire the engine lock.

Gateway's monitor sends a serialized probe, then sleeps two seconds. Healthy
inference returns immediately from `ensure_ready` while its last observation is
less than ten seconds old. Public health requests perform a fresh probe. HTTP,
socket and JSON work have nonzero cost, but no retained evidence measures a
serving penalty or supplies a reason to remove these readiness safeguards.

Exact sources: [gateway](../../server/gateway.py), matching
[API extraction](../../server/.local/optimization9h-20261004/upstream-api-source-9b538f902be94004b711bf878a78219e/source-stdout.txt)
at `probe_live` lines 1107–1164 and `health` lines 4954–5359. The extraction
receipt establishes source retrieval, not a health timing experiment.

## Why fixed startup does not qualify checked-copy

The completed historical capture used
`run_serving_identity_capture_sealed40_rebound2_20261007.py`, SHA256
`a27845a1454c587ca9eab7479791cb9332bec0a1582ff100e858aeb2bd08029b`.
Its pre-readiness cgroup telemetry failure, cleanup and restoration remain
historical outcomes. Its pinned sources, process births, HistoricalStock restore
profile and 40-GiB admission are obsolete. Current8K uses 35/131 GiB startup,
18/18 GiB runtime and the exact original profile
`50e09bc549f1238a42ff1f68e3a6304ada380ef5eb418adf28f60315f55bf9c1`.
A normal successful load above 35 GiB does not prove sufficiency at exactly
35 GiB.

The newer after-ready draft has SHA256
`218bcc0fc28c7762f65503d8a6f3e4ced45eb7716e37ddec182885369268bbf4`.
It supplies no `pdh_intervals` to `analyze_records` at lines 274–277, so PDH
ownership is not requested. Its restoration helper also retains stale service,
controller, memory, launcher and source-manifest hashes and 40-GiB admission.
Do not silently reseal or run either historical draft against the current
instance. Any real future window needs reviewed current sources, fresh owned
process identities and exact Current8K restoration.

Those repairs would establish an identity-capture lifecycle, not exclusive
occupancy. The current [attribution evaluator](../../scripts/benchmarks/halogen_gpu_copy_attribution.py)
rejects supplied intervals when the captured trace contains allocation
transfer/reference or hardware packet records; these checks use whole-trace
counts, rather than records restricted to an individual interval. The retained
driver producer associates event50 with a DMA build
attempt before its HRESULT is checked; an insufficient-buffer retry can flush
previous commands. That association is not proof of successful fill membership
or which committed DMA executed during a measured interval. Seven retained
chains precede measured rows; 339 System Copy spans still lack exclusive
ownership. Header PID4, a captured guest name or an allocation association is
insufficient. No threshold or attribution condition was weakened.

The historical checked-copy observation of +2.168% Decode lacks its original
PDH integration interval, final candidate counters and stock-after samples. A
later capture cannot retroactively qualify it. Removing 18 host maps scans per
warmed hit remains a plausible CPU saving; accepting it requires a new complete
comparison only after the remaining execution-attribution uncertainty is
actually resolved. No connected evidence currently supplies that resolution.

## Device and metric decision

CPU owns these observers and checked reads. GPU retains the original compute;
neither identity capture nor health code changes proposal quality. NPU cannot
remove this ownership uncertainty or turn a failed comparison into a serving
gain. No new Prefill, Decode, acceptance or NPU-on/off tok/s delta was measured.
The full acceleration goal remains unachieved.

References: [Copy implementation](halogen-copy-attribution-implementation-20261007.md),
[historical recovery](halogen-serving-capture-current8k-recovery-20261007.md),
[strict inert-shell diagnostic](halogen-inert-shell-boundary-diagnostic-20261007.md),
[current startup promotion](halogen-warmed-startup35-20261007.md).
