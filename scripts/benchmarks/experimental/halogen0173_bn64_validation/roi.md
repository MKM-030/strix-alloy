# BN64 device validator: independent ROI and scope assessment

9 October 2026. **Recommendation: defer a new live BN64 device-validator
candidate.** The component establishes a finite validation improvement, but its
optimistic measured-pattern budget is about 37.376 ms per request against a
340.733 ms measured prefill deficit. It does not make beating stock plausible
enough to justify the remaining allocation-proof and integration work. Keep the
BN64 adapter disabled. This mechanism has no identified matching cost to remove
from the tracked NORMAL serving path.

This assessment reads root's retained engine and component results. It performs
arithmetic and local source inspection only. No hardware access, engine request,
source fetch, build, lifecycle, STATE, Git, or source change was performed. The
only authored file for this assessment is this `roi.md`.

## Qualified engine latency deficit

Inputs are `docs/research/halogen0173-bulk-bn64-engine-20261009.{md,json}`. Use the
qualified v2 candidate/before comparison only. V2-before reuses v1-after; it is
not a new independent baseline. Exclude each arm's warmup, and average the three
recorded native API phase durations directly: `timings.prompt_ms` and
`timings.predicted_ms`. These are the per-run phase milliseconds, not inverses of
mean token rates and not reconstructed wall times. No clock normalization is
applied. V2-after and pooled comparisons remain unqualified because their clock
scaling differs.

| Arm | Measured prefill phase ms | Measured decode phase ms |
|---|---|---|
|Before|6668.0, 6600.8, 6645.0|2950.8, 2832.7, 2859.3|
|Candidate|6917.5, 6945.7, 7072.8|2844.0, 2924.8, 2911.2|

| Native phase | Before mean ms | Candidate mean ms | Candidate deficit ms |
|---|---:|---:|---:|
|Prefill|6637.933333|6978.666667|340.733333|
|Decode|2880.933333|2893.333333|12.400000|
|Sum of native phases|9518.866667|9872.000000|353.133333|

The latency increase is 5.133124% for prefill and 3.709825% for the sum of phases.
Those differ from the report's mean-rate percentages because the calculation
uses means of recorded durations. Three measured requests remain a bounded
screen, not a confidence claim or a general workload result. Output and native
MTP+PLD accounting match in the qualified pair.

## Observed transaction exposure

The v2 candidate audit contains 192 contiguous `committed_native64_bulk` records,
ending at started/committed 192/192 with zero rollbacks and failures. The
candidate arm has four requests: one warmup and three measurements. Thus the
**observed window average is 192 / 4 = 48 completed transactions per request**.
Dividing by three measured requests would incorrectly charge the warmup's
transactions to the measured requests.

The audit records have no timestamp or request ID, and there are only window
before/after snapshots. These retained records do not independently establish
exactly 48 transactions in each individual request or isolate 144 measured-run
transactions. This assessment uses the observed request average for its budget,
with that attribution limit explicit. The repeated request shape and outputs do
not turn aggregate counters into per-request logs.

The adapter requires rows 81920 before replacement at `adapter.c:280`, and its
complete fold requires tokens 8192 at `adapter.c:305`. These are fixed bulk
operations. The favorable prefill budget below allocates the entire observed
average to prefill; the retained audit supplies no phase timestamps. The
cumulative 158167 rejected launches include initialization, are stock forwards,
and are not additional successful transactions or validation opportunities.

Audit input:
`server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/bulk-bn64-engine-comparison-v2-resident-fix/candidate-audit-after.jsonl`.

## Upper component savings budget, not an engine forecast

Root's `result.json` reports 50 correctness fixtures passed and 256 timed pairs:
64 pairs for each of four accepted shapes, with eight excluded warmup pairs per
shape. Recomputing each mean from the integer `legacy_ns`/`aggregate_ns` rows
gives:

| Pattern | Legacy mean ms | Aggregate mean ms | Mean saving ms | Saving x 48 ms |
|---|---:|---:|---:|---:|
|Uniform|2.204969437500|1.426302796875|0.778666640625|37.37599875|
|Sparse boundaries|2.029195734375|1.310959671875|0.718236062500|34.47533100|
|Maximum segment skew|2.057462875000|1.355791609375|0.701671265625|33.68022075|
|Single final expert|2.206802796875|1.482008093750|0.724794703125|34.79014575|

The **upper measured-pattern savings budget** uses the greatest of these four
mean savings for every one of the 48 observed average transactions:
`48 * 0.778666640625 = 37.37599875 ms/request`. It assumes every hit transfers
the best observed component mean saving to the engine, with no new integration
overhead and no losses from producer/consumer ordering. It is a favorable
bookkeeping scenario, **not a statistical upper bound on unmeasured engine
behavior, a measured engine saving, or a latency forecast**. No component
milliseconds are converted to tok/s.

This budget covers 10.969282% of the prefill deficit and 10.584104% of the
combined-phase deficit. Even granting it in full leaves 303.357335 ms of prefill
deficit and 315.757335 ms of combined-phase deficit. Prefill break-even would
require 7.098611 ms saved per average transaction; combined-phase break-even
would require 7.356944 ms. Those are about 9.12 and 9.45 times the best measured
mean saving, before requiring any positive advantage over stock.

As a deliberately generous check on the missing request attribution, charging
all 192 commits to only the three measured requests gives 64 per measured
request and a 49.834665 ms budget. That is not the observed window average and
discards the warmup's share; even this allocation leaves 290.898668 ms of the
prefill deficit. The count-attribution limitation does not change the decision.

For another favorable component-scale sanity check, erasing the entire largest
observed legacy validation mean at zero replacement cost gives only
`48 * 2.206802796875 = 105.92653425 ms/request`, still below the prefill deficit.
This is also a synthetic-component envelope, not a universal live-cost bound.

The measured candidate includes two 32-byte H2D poison uploads, two scan launches,
two explicit decision waits, two 32-byte D2H status copies, and host acceptance
decisions. Legacy includes eight D2H copies totaling 22548 bytes and the same two
waits. `host.c:64-86`, `:111-140`, and `:172-179` establish these timed boundaries;
the summary repeats their accounting. Allocation, fixture uploads, and module
loading are outside those intervals. This component generates no native items,
GU/DN/fold work, engine inference, or restart.

Both paths ran on owned synthetic buffers with otherwise empty component queues.
The old full-engine receipt did not time the adapter's copies/fences separately.
Real queued native work must complete at the two retained decision boundaries;
it cannot be booked as removed synchronization work. Hence the component benefit
does not causally explain the engine deficit or support an extrapolated gain.

## Native lifetime proof and added overhead

The component does not close the native histogram-input proof gap. Before the
first GPU scan can replace `histogram()`'s fixed D2H reads, future integration
must establish readable live extents for raw 2056 bytes, IDs 2048 bytes, and
prefixes 2052 bytes, and keep their allocation identity valid through the first
decision completion. Keep all six original nonnull gates. An allocation-range
answer alone does not prevent a concurrent free/reuse; an outer arena range also
does not by itself establish the producer's logical subspan. GPU faults from
unreadable inputs do not have qualified legacy-copy error or rollback semantics.
Private guard allocations are owned and do not solve this three-input gap.

Three runtime range checks per transaction would mean 144 extra checks per
observed average request, plus their resolution/dispatch, error handling, and
lifetime coordination. Their latency is unmeasured and must not be assumed zero
or assigned a guessed value. A registry could avoid repeated HIP queries, but
requires complete native allocation/free/reuse coverage, correct interior-range
arithmetic, publication/locking, and safe lifetime through completion. Its hot
lookups and maintenance also have positive cost and would reduce the 37.376 ms
favorable budget. Neither approach currently has a completed native proof or
measured overhead in this component.

The existing normal hybrid `copies[4096]` (`hip-register-hybrid.c:66`) tracks
immutable registered model-weight copies (`:157`, `:402`), and translates those
host addresses at `:487-508`; unregister owns their release at `:511-539`. The
private shim's `registered[4096]` and registration/unregistration functions track
host registration/protection (`hip-register-private-rw.c:25`, `:90`, `:152`).
Neither retained source is a general native scratch-device allocation/free
registry. Those records cannot be assumed to prove raw/ID/prefix arena lifetime.

## NORMAL path applicability

`backends/halogen-wsl2-0.17.3/scripts/service.py:294-301` configures normal v2
serving with this chain:

```text
/candidate/libhalogen0173-v2-preflight.so:/candidate/hip-register-private-rw.so
```

The preflight library is built from the hybrid planner, bridge, and trampoline;
the second DSO is the private mapping/registration shim. These four tracked
sources contain no `hipLaunchKernel`/`hipModuleLaunchKernel` interposer, BN64
validator, `histogram()` transaction check, or four-private-guard scan. Normal
registration/planning checks are model admission work, not these eight
per-transaction validation readbacks.

Only the separate experimental launcher appends `libbulk-bn64.so` and sets
`ALLOY_BULK_BN64_ENABLE=1` (`bulk-bn64-engine-comparison-v2-resident-fix/launch.py:90-93`).
The adapter constructor requires that opt-in at `adapter.c:130-134`. Its
`histogram()`/`guards()`/post-items sites (`:192`, `:214`, `:284`) create the
copy work that the new component aggregates. Stock windows explicitly require
the BN64 manifest/environment keys absent. The public engine report retains the
candidate-off disposition.

Therefore this package could improve the disabled BN64 experiment's validation
overhead, but it removes no identified matching work from NORMAL stock serving.
Adding a normal launch wrapper and validator would introduce work to that
tracked path. This finding does not claim absence of all copies, validation, or
internal resolution inside the closed native engine/vendor runtime. No distinct
normal eight-copy validation mechanism is evidenced here. The byte-identical
0.17.2/0.17.3 native GPU object (`portable-source-notes.md:5`) does not create such
a normal-path opportunity.

The finite component result is worth preserving. It does not justify another
live BN64 implementation/cohort under the present goal. Reconsideration needs
independent evidence of substantially more removable cost or a different
mechanism with adequate budget, plus the native input lifetime contract; this
assessment requests no additional diagnostic cohort.

## Evidence identities at assessment

| Input | SHA256 |
|---|---|
|Engine report Markdown|`36BCD3E089E09E95A59D3EA6C8CE667F17B90ABF837F3493EB3DF36D46CD6F8A`|
|Engine report JSON|`A105FA1FB1757AA12389400F4E1CCB7B325DA050E34DE638A91D4470B01F09E5`|
|Component `result.json`|`7A156B7F19FB26D5214E87386AA72CF4990CD43FE0FCF8CA0A04B1B7172E005B`|
