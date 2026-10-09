# Halogen 0.17.3: bounded next-route assessment

The normal server stays available. This assessment adds no serving change and
establishes no Prefill, Decode or NPU speed gain. The separately qualified
[natural 16K result](../benchmarks/halogen0173-natural16k-raw-20261009.md) remains
1,833.70 Prefill tok/s, 43.05 Decode tok/s and 180/399 = 45.11% combined
MTP+PLD acceptance. None of the observations below replaces that result.

## Actual retained handoff intervals

The closed selector pilot contains 797 complete rows and 1,714 valid cost
records. Its 96 complete PLD rows all have a complete preceding same-owner
round: 41 neural and 55 PLD. Sixty censored native pairs remain excluded.
The pilot uses 550–734 actual input tokens, not the separate natural 16K input.

| RAW sample interval, 96 pairs | Minimum | Median | Nearest-rank p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Previous Outcome to next PLD Begin | 10.321 µs | 16.881 µs | 42.193 µs | 221.725 µs |
| Previous Begin to next PLD Begin | 49.168002 ms | 54.616168 ms | 70.922119 ms | 89.892871 ms |

Each match includes session nonce, owner birth, slot cookie, slot epoch and
round minus one. Cost records also match native event kind, sequence, wire ID
and source. The [audit output](halogen0173-pld-gap-audit-20261009.json) binds the
exact retained inputs and all 96 pairs. Root independently reproduced the
source agent's calculation with the [offline audit](../../scripts/research/halogen0173_pld_gap_audit.py).

Samples use CLOCK_MONOTONIC_RAW after ownership admission and before snapshot
work. The short interval includes the preceding Outcome snapshot and later
host/native/observer transit. It is not a measured producer launch interval,
a hard deadline, or a natural-16K timing. The earlier interval includes the
entire preceding stock round; it cannot be called isolated verification or
available overlap for a predictor whose next authoritative input does not yet
exist. Neither interval supplies a ready NPU result or a serving rate.

The prepared tail consumer accepts only an immediately ready result. A real
asynchronous producer with correct state, timely causal predictions and useful
coverage is still missing. Do not start another NPU handoff diagnostic merely
to add protocol checks. The earlier 1.850 ms NPU versus 0.487 ms GPU projection
also remains a separate negative component result, not a current tok/s delta.

## Unsupported adaptive 1-to-2 control

The exact current engine SHA256 is
`af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7`.
Startup at `0x172dbd4..0x172dbe5` retains high depth only when low is at least
two and high exceeds low. Otherwise high becomes zero. Setting low one and
high two therefore selects fixed one, not an adaptive one-to-two policy.
Root independently checked the retained instructions. The unchanged fixed-two
deployment remains selected; another flag sweep is not justified by this idea.

Native reduced logits exist on the GPU, but the ordinary selection path returns
only a four-byte chosen ID to the host. No aligned probability, top-two margin
or entropy corpus is retained. A new scalar reduction would add work and need
a decision seam between heads; it cannot skip a first head already executed.
This remains an unqualified mechanism, not a reason to launch a capture.

## Small causal CPU prototype

One fixed longer-match policy over only 64 already committed IDs changes one of
96 retained PLD offers. Among 94 reconstructible frontiers its exact-prefix
total is 237, versus stock 235; one improves and none worsens. Proposals were
sealed before the future-label evaluator, and the allocation-free C++ version
matches all 96 proposals. The [separate report](halogen0173-causal-pld64-20261009.md)
preserves the first result, source, limited scope and missing integration.
This is a causal proposal prototype, not an oracle predictor, but its one
positive frontier does not justify a serving-gain or NPU claim. No new cohort
was launched solely for this result.

## GPU follow-up disposition

The authentic N=3 scratch-free FL candidate stays disabled after its measured
13.31% latency regression. Its H128 normalization mixes all 128 rows in one
strip, so independent 32-row workgroups cannot preserve the single-launch
operation. Two parallel experts over all 128 rows require 1,024 threads and
still only 60 workgroups for N=3. Additional LDS storage or publication/reuse
barriers have no measured saving to offset their costs. The compiled owner512
candidate already has no spills. No revised GPU component was run.

The source findings and small causal CPU proposal study are independent of
the corrected phase-clock measurement. A higher offline prefix count must not
be converted into native acceptance, a changed-trajectory result, or tok/s.

## Scope

Root and two agents used retained source/evidence and bounded CPU work. No
new inference request, GPU/NPU operation, lifecycle restart, profile change,
driver installation or global setting change occurred during this assessment.
The broader acceleration goal remains active and unachieved.
