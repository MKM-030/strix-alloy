# Multiple draft sources for higher Halogen throughput

The useful objective is more authoritative output tokens per second at unchanged
target verification. Several genuinely different draft sources can improve
continuation coverage. They do not guarantee 100% acceptance, and extra work can
reduce decode throughput even when more drafts match. No ensemble model was
trained, installed or benchmarked in this assessment.

**Executed decision:** the separate full-device GPU drafter now has exact
incremental-state parity, but the available opening-only selection rule adds
zero retained label coverage over stock. Its 26.05545 ms/round component cost
therefore supplies no case for a synchronous added-work serving path. Preserve
the state result and retire this realization as a serving-promotion argument
under the current consumer restrictions.

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

## Observed complementary proposals and a causal selection rule

The [full-device result](halogen-device-full-snapshot-results-20261006.md) and
its [JSON](halogen-device-full-snapshot-results-20261006.json) retain actual
three-ID proposals for 15 frozen stock prefixes in one family. A separate
evaluator owns the workload's `expected_next_ids`; these labels cannot select
the live source. There are 45 predicted IDs and 44 scored label positions, with
the final third ID unscored.

The [fresh causal-screen receipt](halogen-multi-draft-causal-screen-20261006.json)
independently reads the hash-verified raw GPU proposals and original workload
labels, reproducing the stock, opening-rule and oracle counts below.

| Offline rescoring of the same frozen cases | Leading label positions |
| --- | ---: |
| Retained stock accepted-prefix counts | 22/44 |
| Independent proposal alone, before opening restriction | 22/44 |
| Select independent on opening equality, otherwise stock | 22/44 |
| Same opening-only rule with a two-ID replacement cap | 19/44 |
| Hindsight maximum of stock and independent | 28/44 |
| Hindsight maximum with independent opening equality required | 25/44 |

The opening-only rule can use already available first-head equality after an
independent proposal has been recorded; it does not inspect future labels.
The table optimistically assumes every packet is ready and a three-ID consumer
is available. In its ten opening-equal cases, independent and stock each score
19 labels. Gains of one label in rounds 4, 9, and 13 are cancelled by losses of
one in rounds 2, 5, and 11. Stock fallback in the other five cases contributes
three, leaving the original 22. A two-ID cap removes all three gains.

The 25-label oracle chooses only the three winning cases using hindsight. No
trained or qualified causal router makes that selection. Round 12 supplies the
other three labels in the 28-label unrestricted oracle: independent first ID
17739 matches the next target label, but differs from native opening ID 7963,
so the preserved opening check rejects it. It rescues one of three native-head
mismatches only in the unrestricted offline comparison.

These are frozen-prefix scores, not live accepted tokens: changing a round's
committed length changes subsequent prefixes and proposal boundaries. Even
the observed unrestricted oracle covers only 28/44 label positions. Additional
sources do not guarantee 100% acceptance, and 100% exact state-row agreement
does not establish 100% prediction acceptance.

## Complete cost, native timing, and missing consumption opportunities

The measured full-device core is `31.8703 + 204.0217 + 154.9398 = 390.8318 ms`:
one seed plus every proposal/save and complete clear/restore/replay resolution,
or 26.05545 ms/round. The 37.0657 ms measured diagnostic writes are separate.
Startup, transport/authentication, publication, late replies, and contention
also need their own integrated accounting. No unmeasured overlap makes this
work free. With zero incremental coverage and unchanged stock work, any
positive unhidden added cost defeats the opening-only rule's benefit case.

At the existing hit-only replacement seam, native lookup and the native first
head remain; target verification, commit, output, and native accepted-prefix
replay also remain. A separately integrated no-hit chain could displace later
builtin speculative-chain generation, but no such savings were measured and
the first-head/replay obligations cannot be subtracted wholesale. The retained
count-one complete-head event mean, 3.323555 ms over 73 instrumented calls,
is a component bracket, not a stock round duration or a per-round saving.

No actual duration for the 15 native rounds is retained. The pinned
[raw trace](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/mtp-tap-resume-d20a7077972049538940fe6b95bf62c7/trace/trace.jsonl)
has call counts, positions and entry/exit state, with no timestamp fields. Its
[response](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/mtp-tap-resume-d20a7077972049538940fe6b95bf62c7/response.json)
retains 4219.3 ms for the whole intrusive 128-output decode, explicitly outside
throughput qualification. The unobserved stock
[raw cohort](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/stock8k-final-no-observer-1/cold/samples.jsonl)
retains whole-request decode fields of 2924.0, 2930.6 and 3026.3 ms in its three
measured MTP repetitions, with clock-calibration records. It supplies no
per-round timestamps or mapping of removed versus retained work for these 15
cases. Those aggregate fields and the older generous four-output-per-round
planning ceiling cannot price the three oracle extensions or prove net gain.

The hit-only selector caps at `min(stock_n, 3, native_allowance)` and declines
when stock is empty. The retained
[exact-three audit](halogen-exact3-offline-policy-audit-20261006.json) has zero
causal lookup opportunities across all 37 retained output positions; actual
native hit/count/readiness fields remain unobserved. The
[no-hit contract](halogen-pld-nohit-contract-status-20261006.md) preserves opening
and one-chain verification but is default off and absent from engine call
sites. Early ready publication, transport, and complete authoritative-output
handoff are not qualified. A structural insertion candidate is not a current
consumption opportunity.

The full report already labels its union calculation as hindsight, and the
[benefit audit](halogen-independent-proposer-benefit-20261006.md) labels its
cost ceiling as a planning bound. Neither supplies a usable source selector.
Do not promote the 25/44 or 28/44 maxima, the old cost ceiling, or component
milliseconds into native acceptance or serving tokens/s.

## Recommended bounded direction

Keep native GPU MTP. Reopen an added proposer only with a causal one-chain
selector that improves held-out coverage after opening/count restrictions and
with a useful ready consumer whose saved and added work are explicitly priced.
The completed full-device pass needs no repeat; its correct state mechanism
remains reusable evidence. This family and the current synchronous GPU
addition do not justify another serving cohort or a native audit.

Strata's token-only CPU suffix/source selector was already screened on the
retained family: normal and pending-MTP lookup each supplied zero candidates
in 15 cases. The unchanged same-history mechanism is retired for this family;
an independently useful corpus or different mechanism would need new evidence.
The [follow-up](halogen-strata-followup-status-20261006.md) retains those results.
The [pinned Strata assessment](strata0140-halogen-source-assessment-20261006.md)
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

Decision: retain exact-state evidence, reject the current added-work gain claim,
and require useful causal ready-source evidence before a larger branch redesign.
No new Prefill, Decode, acceptance or NPU serving values follow from this study.

Source/evidence check: the raw trace, seed and all 15 authoritative replay files
match the workload pins; the stock raw cohort matches SHA-256
`feca0b78387099ea732406d94b10a2baa0c62c3cac494237b88f787db662ae27`.
The reviewed root full-result JSON is SHA-256
`225efa047f80a8901df84918792b13b6232f5898091207d8c3a6c1bc243299e8`;
the count-one event statistics retain SHA-256
`4898ed5ba2dcbbef1ffdd95166bd95277e7b69e8e821dbcadeb32f159aec0a0d`.
This update used retained data reads and CPU arithmetic only. No hardware,
runtime, WSL, controller/lifecycle action, repeated test, or existing-script edit
was performed. The source-review agent changed this document only; root added
the independent causal-screen JSON and corrected the completed lookup status.
