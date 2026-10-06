# Multiple draft sources for higher Halogen throughput

The useful objective is more authoritative output tokens per second at unchanged
target verification. Several genuinely different draft sources can improve
continuation coverage. They do not guarantee 100% acceptance, and extra work can
reduce decode throughput even when more drafts match. No ensemble model was
trained, installed or benchmarked in this assessment.

## What 60% establishes

The retained 8,192-input cohort accepted 207 of 345 native drafts: 60%. This is
workload-specific accepted/drafted accounting, not a per-position independent
probability. The retained natural long-input cohorts have different acceptance.
It supplies no measured forecast for a second drafter.

Two hypothetical independent 60%-correct candidates at one token have 84%
at-least-one coverage; three have 93.6%. These are illustrative oracle coverage,
not achievable measured acceptance. Real errors correlate, identical
deterministic copies add no diversity, and a router cannot know the correct
candidate without information or target verification. Discarded proposals and
verification cost must remain visible in the accounting.

For a continuing greedy round with a linear chain of m drafts, expected committed
length is 1 + sum over j=1..m of P(the first j drafts all match). Actual stops and
truncation require actual committed counts. Compare committed tokens against
total cycle time, including private draft preparation, transfer, capture,
verification, replay/commit, missed deadlines and stock fallbacks. Aggregate
acceptance alone is insufficient to infer that survival curve or throughput.

## Existing consumer boundary

The current native seam consumes one contiguous block of at most three custom
IDs and verifies one linear continuation. It retains a native opening check.
There is no parent/branch index, tree attention, per-branch recurrent/KV state,
selected-branch commit or branch outcome protocol. Multiple sources could
privately select one timely chain; they cannot make this verifier evaluate and
choose among alternative branches for free.

The research direction is established: [Medusa](https://arxiv.org/html/2401.10774v3)
uses trained additional heads and tree verification;
[EAGLE-2](https://arxiv.org/html/2406.16858v1) adapts draft trees using confidence.
Those designs require model/engine integration. Their published gains are not
Halogen measurements. Quality-preserving typical acceptance is not proof of
unchanged target sampling. Our current bounded native route is greedy; sampling
would require a separately correct proposal/acceptance/residual algorithm.

Domain-specialized trained heads or models are plausible. Arbitrary subsets of
Qwen weights or MoE experts are not complete token predictors. A valid predictor
needs its trained feature path, tokenization and vocabulary head; an auxiliary
head may also require the target's actual hidden features.

## Recommended bounded direction

Keep native GPU MTP and assess one complementary inexpensive proposer first.
Strata's token-only CPU suffix/source selector is a concrete source candidate,
but it must demonstrate incremental useful hits after Halogen's existing lookup
before it earns a serving cohort. Both perform lookup, so zero additional yield
is possible. The [pinned Strata assessment](strata0140-halogen-source-assessment-20261006.md)
identifies source locations and the larger neural dependencies.

CPU suits owned-token indexing, routing and publication. A token-only NPU model
with its own canonical state could avoid a target-hidden-state transfer, but
training, accuracy, deadline readiness and total serving benefit remain unknown.
An NPU auxiliary head using target features adds publication and transfer costs.
A GPU drafter shares execution and memory bandwidth with the target. Several
full draft models also increase memory/bandwidth demand on this UMA system.

Speculative drafting primarily targets decode. It does not replace target
prompt evaluation, so a higher acceptance rate supplies no direct Prefill gain.
Assess Strata's separate gfx1151 prompt and decode kernels independently, with
native shapes, formats and unchanged tolerances established before substitution.

Decision: one complementary ready source before a larger multi-branch redesign.
No new Prefill, Decode, acceptance or NPU serving values follow from this study.
