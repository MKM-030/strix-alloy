# BN64 device validation aggregation: source design

Date: 2026-10-09. Status at this source handoff: **unbuilt and unrun**.

This root-owned synthetic component prepares one narrowly scoped change: replace
the eight validation D2H copies with two 32-byte status readbacks. It retains every
acceptance predicate and both host decision fences. `validator.hip`, `oracle.c`,
and this record are source artifacts only; root owns `build.py`, `host.c`, all
compilation/execution, hardware access, and any later integration. No engine
adapter, production configuration, lifecycle, or diagnostic cohort is changed by
this package. There is no speed forecast or engine qualification claim.

The semantic reference is
`scripts/benchmarks/experimental/halogen0173_bulk_bn64_engine/bulk-bn64-engine-candidate-v2-resident-fix/adapter.c`:
`histogram()` at line 192, `guards()` at line 214, `rollback()` at line 225, the
post-item decision at line 284, and fold commit ownership at line 308.

## ABI and launch contract

`#define BN64_VALIDATION_ABI_ONLY` includes the C11-compatible declarations in
`validator.hip` without the HIP device code. `oracle.c` uses that include mode.
Root can define `BN64_ORACLE_LIBRARY` and include `oracle.c` in `host.c` to use its
static oracle and fixture APIs without its standalone `main()`.

Each kernel must launch with grid `(1,1,1)`, block `(256,1,1)`, dynamic shared
memory `0`, and the original `NULL` stream. The device checks grid/block geometry;
**the host must enforce shared-memory and stream arguments**. Invalid geometry
publishes `BN64_BAD_SHAPE` through the first thread when the output is valid.
There are no host launches or runtime initialization calls in `validator.hip`.

The exported C kernel names and positional arguments are:

```c
bn64_validate_histogram(
    const int32_t *raw, const int32_t *ids, const int32_t *prefix,
    uint64_t epoch, Bn64ValidationResult *out);

bn64_validate_post(
    const int32_t *counts, int32_t expected_gu, int32_t expected_dn,
    const unsigned char *gu_lead, const unsigned char *gu_trail,
    const unsigned char *dn_lead, const unsigned char *dn_trail,
    uint64_t epoch, Bn64ValidationResult *out);
```

`Bn64ValidationResult` is a naturally aligned, 32-byte record:

| Byte offset | Type | Field | Meaning |
|---:|---|---|---|
|0|`uint64_t`|`epoch`|Exact caller-owned invocation cookie|
|8|`uint32_t`|`stage`|Histogram 1 or post-items 2|
|12|`uint32_t`|`failures`|OR of failure bits; zero is necessary for acceptance|
|16|`uint32_t`|`segments`|Segment count; diagnostic sanitized count on histogram failure|
|20|`uint32_t`|`expected_gu`|`5 * segments` for accepted histogram, otherwise 0|
|24|`uint32_t`|`expected_dn`|`10 * segments` for accepted histogram, otherwise 0|
|28|`uint32_t`|`magic`|`0x42363456`|

The caller owns a writable device output of at least 32 bytes with alignment
suitable for this record, poisons it before **each** invocation, and uses a fresh
epoch. All launch, synchronization, and copy return codes must succeed before the
host accepts the result. Acceptance also requires exact expected epoch, stage,
magic, and `failures == 0`; a zero mask alone cannot reuse a previous success.
Stage two accepts expected counts derived only from the accepted stage-one
result. Output poisoning and freshness checks also apply to a reused allocation.

## Acceptance predicates

The translation preserves accepted versus rejected finite inputs within the
readable-allocation domain below. Aggregate diagnostic masks and evaluation order
need not match legacy short-circuit failure reporting.

| Legacy condition | Aggregate implementation and retained host gate |
|---|---|
|Six nonnull bindings: `ids`, `prefix`, `raw`, native `gu_items`, native `dn_items`, `counts`|All six remain host gates before launch. The histogram kernel additionally rejects null pointers for its three inputs.|
|`1 <= active <= 512`; `total == 81920`|Read signed `raw[512]` and `raw[513]`, set active/total bits.|
|Every signed expert row lies in `[0,81920]`|Check all 512 rows. Invalid rows set `BN64_BAD_ROWS` and contribute 0 to safe diagnostic arithmetic.|
|For each positive expert, `index < active` and `ids[index] == expert`|Parallel active-rank scan gives the compact index; validate bounds before reading active ID/prefix entries.|
|Positive expert index increases strictly (`expert > previous`)|Retained logically: experts are visited in ascending order and exact ID equality enforces that sequence. The separate legacy comparison is redundant on this domain.|
|For each positive expert, `prefix[index] == preceding row sum`|Parallel inclusive `uint64_t` row scan minus the current row gives the exclusive sum. Compare to the signed prefix without overflowing signed32-bit arithmetic.|
|At every expert, `sum <= 81920 - rows`|Check every sanitized inclusive sum against 81920. With valid nonnegative rows this is the same bound.|
|Final sum 81920, compact index count equals `active`, terminal prefix 81920|Check the final scans and `prefix[active]` only after active-range validation.|
|`segments = sum(ceil(rows/64)) <= 1792`|Sum safe segment contributions and check the same capacity. Publish GU/DN expectations only on a zero failure mask.|
|Two signed native counts equal accepted expected GU/DN counts|Check `counts[0]` and `counts[1]` after the item producer on the same stream.|
|All four 4096-byte guards consist of `0xa5`|Scan every byte of GU lead/trail and DN lead/trail, OR all four diagnostics.|

The histogram kernel uses two experts per thread, inclusive scans of `uint64_t`
rows and `uint32_t` active ranks, then an OR/sum reduction. Each scan level reads
all old values before a barrier, writes the new values, and reaches a second
barrier before the next level. Sanitized sums cannot overflow `uint64_t`; even
512 valid 81920-row entries fit the published diagnostic segment field. The
aggregate continues after malformed values to report additional bits; the legacy
oracle preserves the original early-return order.

Neither path validates item payload contents. `ids[active..511]` and
`prefix[active+1..512]` are semantically ignored. The post kernel checks an
additional invocation invariant (`expected_gu` is a positive multiple of 5 no
larger than `5 * 1792`, and DN is twice GU). Every accepted histogram satisfies
it. **Post-stage acceptance equivalence is claimed only for those accepted
histogram outputs**, not arbitrary externally supplied expected-count arguments.

The valid segment maximum is 1784, below the retained 1792 capacity:
`floor((81920 + 63 * 512) / 64) = 1784`. Consequently, capacity rejection cannot
occur independently after all other histogram predicates have passed. It is
still checked, and the combined invalid-sum/capacity fixture exercises its bit.

## Host phases and error handling

The proposed integration sequence retains both blocking decisions:

1. Before starting a replacement transaction, retain all existing host gates.
   Enqueue `bn64_validate_histogram` after the native histogram producers on
   `NULL`. Retain `hipStreamSynchronize(NULL)`, then perform one synchronous
   32-byte D2H status copy and the complete host acceptance check. Failure takes
   the original stock path without beginning replacement work.
2. After successfully submitting native64 item generation, enqueue
   `bn64_validate_post` on that same stream. Retain the second
   `hipStreamSynchronize(NULL)`, then the second synchronous 32-byte result copy
   and acceptance check. GU64 must not be submitted before that check succeeds.
3. Any failure after transaction start retains the original rollback contract:
   regenerate native128 items/counts, replay the already attempted GU/DN prefix
   according to recorded phase, and synchronize before stock continuation.
   Rollback failure remains fail-closed. The existing phase-before-submission
   recording, saved arguments, thread/stream restrictions, and interruption
   handling remain unchanged.
4. The original fold remains the commit boundary after successful submission.
   This component adds no deferred decision, conditional projection launch,
   post-fold fence, or different commit owner.

HIP errors are rejected regardless of output contents. This source package does
not establish that a failed kernel launch, a GPU fault, or a failed result copy
can recover through the legacy rollback path on a live engine. Any later
integration must qualify error handling independently. The synthetic harness
must never continue into a GPU stage after a failed predecessor or stale status.

## Allocation lifetime and extent limits

Synthetic inputs and outputs are owned readable allocations. Required native
input extents are raw 514 signed 32-bit entries (2056 bytes), IDs 512 entries
(2048 bytes), prefixes 513 entries (2052 bytes), and counts 2 entries (8 bytes).
The kernel accesses active ID/prefix entries only, but future native integration
must establish lifetime and fixed reference extents for **all three histogram
input allocations** through the corresponding decision completion. Nonnull
values do not establish ownership, readability, extent, or lifetime.

Each private guard pointer names exactly 4096 readable bytes. GU item storage is
143360 bytes between its guards and DN item storage is 286720 bytes between its
guards. These private allocations must stay live through post-validation and
the existing transaction/rollback lifetime. The output must stay live through
its synchronous readback.

A stale or unreadable histogram pointer can produce a GPU dereference fault or
poison device execution, whereas the reference's `hipMemcpy` may return a copy
error. Full-array D2H copying and GPU active-entry reads also have different
memory-access footprints. No equivalence for arbitrary pointer values,
allocation errors, HIP error behavior, or live native lifetimes is claimed.
Future integration needs concrete proof for the native three-input allocation
lifetime/extent, possibly from an existing allocation registry; it cannot assume
that the six nonnull checks supply that proof.

## Fixtures and source review

`BN64_FIXTURE_COUNT` is 50. `bn64_fixture_init()` constructs each fixture;
`bn64_legacy_histogram()`/`bn64_legacy_post()` preserve the original CPU
predicates; `bn64_oracle_histogram()`/`bn64_oracle_post()` provide the full
aggregate result. `bn64_oracle_selftest()` checks fixture expectations and
accepted/rejected agreement when root executes it. No such execution is claimed
at this source handoff.

| Accepted fixture | Rows | Segments | GU | DN |
|---|---|---:|---:|---:|
|Uniform|512 experts x 160|1536|7680|15360|
|Sparse boundaries|Experts `{0,3,9,16,255,510,511}` with rows `{63,64,65,127,128,129,81344}`|1282|6410|12820|
|Maximum valid segment skew|248 experts x 193 plus 264 experts x 129|1784|8920|17840|
|Single final expert|Expert 511 x 81920|1280|6400|12800|

The remaining factory cases cover ignored ID/prefix tails, malformed active and
total fields, negative/out-of-range signed rows (including `INT_MIN`/`INT_MAX`),
low/high sums, active-count mismatch, first/middle/last and duplicate/reversed
IDs, malformed prefixes, counts, first/middle/last bytes in each guard, all four
guards corrupt, and ignored item payload. The sum/capacity case uses 512 x 193:
sum 98816 and segments 2048, so both predicates fail. Guard corruption fixtures
cover boundaries; they do not exhaust all 16384 possible corruption positions or
all 256 thread residues. The source loop itself visits every guard byte.

An independent read-only review found no source compile blocker, scan/reduction
race, mask discrepancy, fixture-name mismatch, or ABI defect. It confirmed the
four accepted counts above and the combined sum/capacity limitation. This was
inspection, with no builds, execution, or writes. The reviewer emphasized the
stage-two expectation domain, host enforcement of shared 0/stream NULL, and the
limited guard-fixture position coverage documented here.

## Complete cost accounting

| Boundary | Reference synchronous D2H copies | Bytes | Aggregate status copies | Bytes |
|---|---:|---:|---:|---:|
|Histogram|3: raw 2056 + IDs 2048 + prefixes 2052|6156|1|32|
|Post-items|5: counts 8 + four 4096-byte guards|16392|1|32|
|Both decisions|8|22548|2|64|

The root harness includes a 32-byte H2D status poison before each kernel inside
the measured candidate path: **two additional H2D copies, 64 bytes total**.
The candidate also adds **two GPU scan launches**, their argument/submission
costs, device input/guard reads, shared-memory use, scan/reduction barriers, and
32-byte output writes. Timing events, if enabled, have positive recording and
query costs and must be accounted for. The same two decision waits remain.
Reducing transfer bytes and copy calls alone does not establish lower latency.

Root measurement must account for both boundaries together: launch/copy costs,
both waits, both status-poison uploads, and host decision/predicate costs, with
per-boundary observations when useful. Initialization, input uploads, allocation,
and fixture construction performed outside a steady-state interval must be reported
separately; excluded setup must not be described as free or silently folded into
an engine benefit. Any timing events and their inclusion/exclusion also need
explicit reporting. The GPU scans cannot be subtracted from candidate totals.

An empty synthetic queue cannot attribute native work that a real engine has
already queued before either decision wait. Producer/consumer ordering must
therefore remain correct even if a synthetic measurement shows inexpensive
fences. Component measurements do not imply tok/s, prefill latency, decode
latency, or a recovered live-engine speed gain. There is no such extrapolation
in this design.
