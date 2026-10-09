# Halogen 0.17.3: isolated BN64 device validation

The GPU validator passes the 50 fixed CPU/GPU fixtures. Its complete synthetic
validation cost is 33–35% lower than the legacy validation path in 256 paired
measurements. This is an isolated component result. No engine Prefill/Decode
rates, MTP acceptance, NPU execution, or serving speed gain were measured here.
The normal Halogen 0.17.3 server remained open and idle throughout; no inference
request or lifecycle change occurred. The full acceleration goal is unachieved.

| Owned fixture | Legacy mean ms | Aggregate mean ms | Cost change | Lower-cost pairs |
| --- | ---: | ---: | ---: | ---: |
| uniform-512x160 | 2.204969 | 1.426303 | -35.31% | 64/64 |
| sparse-tail-boundaries | 2.029196 | 1.310960 | -35.40% | 64/64 |
| max-segments-skew | 2.057463 | 1.355792 | -34.10% | 64/64 |
| single-expert-511 | 2.206803 | 1.482008 | -32.84% | 61/64 |

Each shape has 8 excluded warmup pairs and 64 measured pairs. Order alternates,
with 32 pairs per shape placing each arm first. Timing uses CLOCK_MONOTONIC_RAW.
Both arms include two NULL-stream waits and all validation decisions. Legacy
copies 22548 bytes through 8 D2H calls; aggregate performs 2 GPU kernels, 2 D2H
status copies totaling 64 bytes, and 2 included H2D output-poison uploads totaling
64 bytes. Allocation/module/symbol loading and fixture construction/upload are
outside timing. There is no queued native item, projection, or fold work in this
helper. Device allocations total 452660 bytes. These fixture loops are validation
microbenchmarks, not language-model prompt workloads.

Every GPU histogram result, and every eligible post result, matches the
32-byte CPU oracle exactly, including epoch/stage/magic and diagnostic fields.
Invalid histograms suppress post execution. The legacy acceptance predicates
remain represented by the independent CPU oracle. Guard corruption fixtures
cover first/middle/last positions, not every byte position. The capacity case
also violates the histogram sum; it is not an independent valid-sum overflow.

Native input lifetime and allocation extents are still unproved for a future
live adapter. Owned-fixture correctness cannot establish HIP pointer-fault or
rollback equivalence. Any real integration must include allocation validation
and lifetime costs and preserve the existing transaction recovery contract.
Component milliseconds are not converted into engine token rates.

The first preparation attempt compiled the host and passed its 50 CPU fixtures,
then stopped before GPU execution because the coordinator wrongly required an
optional LD_LIBRARY_PATH manifest field. That failed receipt is retained. A
single corrected continuation reused the sealed preparation and completed the
GPU test. No failed GPU cohort or unchanged experiment was repeated.

Protected health stayed completed 4/cancelled 0 with active_requests 0. All owned
Windows jobs and Linux helpers are closed. Tracked sampled minimum physical/commit headroom was
23.052/110.535 GiB.
GPU load counters were valid and idle; no League/Riot process was present.

The source inspection records concern source only. Actual compilation and
execution were performed by root after that handoff. The normal configuration
and NPU placement remain unchanged. Evidence contains exact paired raw rows and
source/receipt hashes; no credentials, model data, native binaries, prompts or
generated answers are published.

[Evidence](halogen0173-bn64-device-validation-20261009.json) ·
[Source archive](../../scripts/benchmarks/experimental/halogen0173_bn64_validation/README.md)

## Scope and next-step decision

This validator belongs to the disabled BN64 adapter. The normal preflight and
private-registration preload path contains no equivalent eight-copy validator.
Replacing this component therefore does not remove work from normal serving.

The existing qualified v2 before/candidate requests report mean native prefill
times of 6637.933/6978.667 ms
and decode times of 2880.933/2893.333 ms.
The measured candidate deficits are 340.733 ms prefill and
12.400 ms decode. No phase rates were reconstructed or normalized.

The audit has 192 complete transactions over four requests including warmup:
48 transactions per request as an observed average. It does not log exact
individual request boundaries. Multiplying that average by the largest observed
component mean saving gives 37.376 ms as an optimistic illustration,
about 11.0% of the existing prefill deficit.
This is not a measured engine saving, guaranteed bound, or tok/s prediction.
Live allocation/lifetime checks and recovery remain additional unqualified costs.
The evidence does not justify attaching this validator to BN64 for another
engine cohort. Both the adapter and NPU production remain disabled. A future
candidate needs a separate mechanism that actually removes normal serving work.

## Independent evidence review

The ratio of pooled mean times shows a 34.399% reduction;
253/256 individual pairs favor aggregate. Both balanced
order groups favor aggregate, with per-shape/order reductions of 22.440–44.123%.
The headline per-shape means therefore do not assert order-independent cost.
Memory values are minima of tracked samples, not continuous observations or
minima over the additional checked admission/idle frames.

The historical failing preparation coordinator source was overwritten and is
retained as hash-only provenance. The exact successful coordinator and build
control are now versioned as text beside the source archive. The completed
control is retired: its dormant OwnedProcess-constructor error.owner recovery
path needs repair before future reuse. That error did not occur in this run;
actual terminal helper closure and server readiness were independently confirmed.

[Independent evidence review](../../scripts/benchmarks/experimental/halogen0173_bn64_validation/evidence-review.md) ·
[Independent ROI assessment](../../scripts/benchmarks/experimental/halogen0173_bn64_validation/roi.md)
