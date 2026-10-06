# Original BF16 preparation sibling screen, 6 October 2026

The selected W16=0 GPU preparation is exact on the frozen original layer0 QKV
inputs but shows **no useful advantage** in the completed finite screen. Keep
it disabled. No complete preparation-plus-GEMM or serving cohort follows, and
no new Prefill, Decode or native acceptance result is claimed.

| Resident preparation | Original W16=1 | Candidate W16=0 |
|---|---:|---:|
| GPU-event mean | 0.872904 ms | 0.867690 ms |
| GPU-event median | 0.919884 ms | 0.910209 ms |
| Submission plus full completion mean | 1.239336 ms | 1.215513 ms |
| Submission plus full completion median | 1.219164 ms | 1.287583 ms |

The GPU paired mean candidate-minus-original is -5.214 microseconds, while
the paired median is +7.455 microseconds. Candidate wins 8 of 16 GPU pairs.
Order-group means are -11.060 microseconds when original goes first and
+0.632 when candidate goes first. Host paired means also reverse by order:
-165.349 versus +117.703 microseconds. All pairs/outliers are retained. These
small, mixed differences do not justify the conditional full-path comparison.
The marginal medians are not paired medians. This is no intrinsic slowdown or
speedup claim, and component milliseconds are not converted into token rates.

Two excluded qualifications matched every one of the 26,214,400 BF16 words
(50 MiB), with different original/candidate output poison bytes. The retained
full qualification outputs have identical SHA256
`6374bfe3b7c36c29cabeb631f125d4291bdf62735abbb0f5c177615d62d675a7`.
Four excluded warmup pairs and sixteen balanced AB/BA measured pairs followed;
all 42 launches completed and all complete output checks passed. GPU events
and host submission/full-completion durations are separate. Uploads, poisoning,
readback, full comparison/hash, artifact writes and cold initialization are
excluded. The two qualification durations remain unmeasured.

Both kernels are original exports from the pinned Halogen0.16.2 gfx1151 object.
The experiment changed only the 512/256-thread preparation decomposition for
N10240/K2560, mode4/PRE1/KFAST1, grid20x80, default stream and zero dynamic
shared bytes. It neither changed the original GEMM nor measured it. The normal
profile and production validator remain unchanged; no W16 serving switch was
enabled. See the [mechanism](halogen-next-prefill-mechanism-20261006.md),
[independent review](halogen-prefill-deq-independent-review-20261006.md), and
[source](../../scripts/benchmarks/halogen_prefill_deq/README.md).

GPU supplied the exact native preparation candidate. CPU supplied binding,
submission and checks. No compatible NPU prepared-weight consumer or useful
publication path was demonstrated, so no NPU run was added to this candidate.
No mathematically identical preparation change trains a better MTP predictor.

Two launcher failures are retained separately: the first used a Python without
the established controller dependencies and did not stop the server; the
second required an absent unversioned HIP symlink and exited before native/HIP
execution. The corrected launcher uses the existing server venv and the pinned
regular `libamdhip64.so.7`. A focused host regression reproduced the filename
failure before the fix and passed afterward; an independent correction review
checked the retained passed runtime receipt. Neither failed attempt supplied
a kernel measurement. The first restoration admission missed 60 stable seconds
within its bound and launched no controller; after admission changed, one
normal restoration succeeded. Its failed evidence is preserved.

The final qualified measurement's UUID-labelled no-model container, owned
Windows job and monitor are closed. Minimum physical/commit headroom in that
screen was 44.598/199.629 GiB. Normal stock was restored ready/open on port8840,
context262144, CacheOff, MTP2/PLD3,3, and both prefill limits8192. Final
identities, raw receipts, source/build bindings and complete output artifacts
are pinned in the [JSON report](halogen-prefill-deq-status-20261006.json).
The full acceleration goal remains unachieved. No unchanged repeat is planned.
