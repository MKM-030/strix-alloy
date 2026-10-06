# Additional acceleration mechanisms, 6 October 2026

The finite source and retained-data checks do not justify another hardware
cohort for the three mechanisms below. No live engine path was changed. The
normal stock instance remains ready/open; the full acceleration goal remains
unachieved.

## Final MTP head synchronization

The retained engine calls argmax at RVA `0x17dc123`, then checked
`hipDeviceSynchronize` at `0x17dc128`, followed by checked synchronous four-byte
D2H `hipMemcpy` at `0x17dc153`. It returns that host scalar immediately. Both
error branches are fatal; skipping the synchronization also changes that path.

The [pinned HIP copy implementation](https://raw.githubusercontent.com/ROCm/rocm-systems/2b22ab0195cc1461cd9abf3b969e9dd7c10af350/projects/clr/hipamd/src/hip_memory.cpp)
uses the legacy null stream and finishes the copy command. However,
[device synchronization](https://raw.githubusercontent.com/ROCm/rocm-systems/2b22ab0195cc1461cd9abf3b969e9dd7c10af350/projects/clr/hipamd/src/hip_device_runtime.cpp)
waits all streams. Its
[device implementation](https://raw.githubusercontent.com/ROCm/rocm-systems/2b22ab0195cc1461cd9abf3b969e9dd7c10af350/projects/clr/hipamd/src/hip_device.cpp)
also releases deferred pool memory; null-stream ordering excludes unjoined
nonblocking streams. These are different synchronization scopes.

All three direct retained `hipStreamCreateWithFlags` sites use nonblocking flag1:
`0x173ea77`, `0x17c5672`, and `0x182b2a8`. Local drains/event joins exist, but no
head-local predicate proves every other queue drained, no capture active, and no
deferred memory-release effect. The 73 recorded stream-zero count-one forwards
do not prove universal queue ownership. Their
[3.323555-ms complete-head bracket](halogen-mtp-full-head-event-timing-20261004.md)
does not isolate fence overhead and cannot become a predicted saving. Simple
elision is retired; a process-wide tracker is not justified by these costs.

Root independently checked the retained error-check/copy instructions and the
pinned official runtime implementations. The source audit was performed by
`/root/decode_submission_scope`. Retained host-text SHA256 is
`523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`.

## Exact-three-token continuation ranking

A bounded CPU policy could retain the last eight occurrences of each exact
three-token key, rank by additional left context up to sixteen tokens, and break
ties by recency. Root executed this causal offline policy against the hash-checked
full shifted 8,192-ID seed and all fifteen authoritative replay binaries. Across
37 labeled positions, including fifteen native round boundaries, there were
**zero earlier exact-three matches**. Both simulated latest-occurrence and
ranked policies therefore emit zero proposals. The missing original first prompt
token cannot add a match in those queries.

The [complete offline result](halogen-exact3-offline-policy-audit-20261006.json)
preserves input digests and every checked position. This is one retained family;
it does not measure native hash collisions, native eligibility, acceptance or
token rates. It supplies no basis for implementing a live ranking policy or a
new GPU/NPU cohort. `/root/proposal_lookup_scope` independently found the same
exclusion. The native hit-only private seam cannot supply no-hit proposals or
remove the lookup search; its limitations remain in the
[insertion scope](halogen-npu-native-pld-injection-scope-20261005.md).

## Larger Prefill chunks

The [completed upgrade screening](../benchmarks/halogen0162-upgrade-20261003.md)
already measured chunks16384/32768. Chunk16384 regressed both measured MTP wall
means; later stock confirmation removed apparent useful tuning gains. Those
comparisons retain sequential timing confounds and use the older arena/workload.
They are not a controlled delta against the present natural-text8192 arena.
Merely changing both limits now does not establish a new mechanism or justify
repeating the defeated parameter screen. Existing memory reserves are retained.

## Device assessment

GPU remains responsible for native projection/argmax and target verification.
CPU still needs the returned scalar; speculative ranking adds host work without
coverage in this retained family. NPU transport cannot remove that dependency,
and it has no demonstrated critical-cost advantage for this bounded host lookup.
Neither exact fence elimination nor identical arithmetic alone would improve
proposal quality. No new Prefill, Decode or native acceptance gain is qualified.
