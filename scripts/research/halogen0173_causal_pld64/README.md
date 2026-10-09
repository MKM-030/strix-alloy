# Frozen causal PLD suffix64 tail selection

One CPU-only fixed policy screen found a small useful difference on current
0.17.3 stock frontiers. Across 96 complete width-three PLD rows, 14 had a
compatible historical match longer than three IDs. Only one proposed tail
changed. On 94 reconstructible future raw-ID labels, stock exact prefix total
was 235 and candidate total was 237: wire request 15, round 44 changed prefix
1 to 3. No scored frontier worsened. Wires 9/round 37 and 13/round 54 have no
complete future raw-ID reconstruction and remain unscored.

This is one offline stock-trajectory result, with no timing, changed native
rollout, realized acceptance denominator, or Prefill/Decode gain. A changed
tail can change later frontiers and costs. This result supports a bounded CPU
provider implementation; it does not justify a hardware or serving cohort.

`longmatch64.h` now preserves a compact allocation-free C++ version with copied
suffix length at most 64 and fixed stock width three. It has no native hook,
owner, model, lifetime or OS/device operation. The freestanding CPU test DLL
has entry point zero, no imports and one function export. A single matching
pass reproduced all 96 frozen Python proposals and their match/index/position
metadata exactly, with all openings unchanged. `cpp-match.json` preserves
that CPU-only result. No future-label evaluator was rerun by this check.

## Exact frozen policy

The predictor consumes only the copied pre-Begin committed suffix (64 IDs),
the actual stock width-three offer, and the frozen ordinary-ID set derived
from the exact tokenizer file. For each earlier position whose preceding
three IDs equal the current trailing three, require a complete already
committed three-ID continuation and the same stock opening. Reject undefined
or special IDs. Compare backward context, choose greatest match length,
newest position on a tie, and require length greater than three. Preserve
stock width and opening, changing only tail slots 1 and 2. Otherwise return
all original stock IDs. No policy sweep, fitting, threshold retune, external
corpus, native model call, or future-label input is used.

Only the last 64 committed IDs are searched; full prompt history and older
occurrences are deliberately outside this policy. At width three there are
at most 59 prior positions, with bounded comparisons. A future native CPU
provider can use copied arrays and a preallocated ordinary-ID bitmap, with
no index, allocation, worker, model, wait, NPU, or extra device readback in
the callback. No runtime cost was measured here.

## Preservation of the first evaluation

`executed-inline-screen.py` is the exact Python body recovered from the first
executed tool call. It contains both the frozen predictor and the separate
future-label evaluator. All 96 proposals were serialized and hashed in
memory before the evaluator accessed later rows. They were rehashed after
scoring. The original prediction hash is
`be54505c785271d76f1808b27f72618df9f2a0b82e6730c0a7b2d37488157c62`.
`initial-result.json` preserves that first tool result semantically.

Source and durable files were saved after that initial evaluation. They
were not disk-sealed before it. `recover_predictions.py` executes only the
recovered predictor definition and verifies all recovered proposal bytes
against the original pre-evaluator hash before saving them exclusively.
It never invokes the evaluator. There is exactly one scoring pass; recovery
does not supply another result, timing measurement, or independent rollout.

The evaluator reconstructs future IDs from later committed suffixes of the
same session, owner birth, slot cookie and epoch, with exact overlap. All 94
scorable stock prefix lengths match the recorded native accepted-prefix
outcomes. Future IDs enter only this evaluator after predictions freeze.
This uses the same overlap contract as the existing future-label oracle
generator; the proposed CPU predictor does not query an oracle ready list.

## Eligibility and integration prerequisites

The successful offline frontier has session nonce
`cf194e1fb733d624cdbf08fa47612ed3`, owner birth 13, slot cookie 1, slot epoch 49,
wire request 15, round 44, Begin 1409 and Outcome 1410. Its native allowance
and stock width are both three, model position is 740, context total is 741,
and cached opening equals unchanged stock proposal zero. All 96 PLD rows
have cached openings; 94 equal proposal zero. The policy cannot rescue an
opening mismatch and must retain the normal native opening check.

The observed collector copies request+0x1a0 as cached opening and marks PLD
rows censored when request+0x240 has constraint state. It checks request to
record, wire ID, slot and owner epoch before Begin. These complete rows
therefore support this constrained offline scope. A new implementation still
needs the current synchronous lexical owner's guarded tail transaction at
0x17413ff, original RSP+0x6a0 and count RBX, with width/opening preserved.

The existing `halogen0173_pld_tail/tail_adapter.h` is the consumer reference.
Bind each ready candidate to all copied frontier values, current session,
model/tokenizer identities, birth, slot cookie/epoch, round, wire ID, target
position, transported count, suffix length/content, stock offer and allowance.
Recheck native same-owner/slot/loss/input after provider return; expire every
borrow at return and drain relays before storage release. Keep reset,
release, cancellation, destruction, opening gate, native linear verification,
consecutive prefix comparison, correction/bonus commit, replay and stop/EOS
native. The observer lock alone cannot serialize concurrent model mutation.

The generic consumer currently has stock and future-label ready-list
providers. No real occurrence-ranking CPU provider has been integrated or
live-qualified. An implementation should retain default-off operation and
the existing narrow greedy/unconstrained complete-hit restrictions. No
engine recommendation follows before provider overhead and complete owned
transaction correctness are established; even then one positive offline
frontier gives limited quality evidence.

## Evidence and other route disposition

Input decoded journal:
`docs/research/halogen0173-selector-pilot-20261009/native-capture/decoded.json`,
SHA256 `6e4036db6dc008c206badac7101c28fcf46cda90033f5a44723a00668751bd67`.
Exact tokenizer JSON:
`C:/AI/models/halogen-flashnext/tokenizer/tokenizer.json`, SHA256
`0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3`.
Engine SHA256 is
`af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7`.
These are token metadata reads; no HGN tensor payload was copied or published.

The older Strata complement/follow-up reports explicitly retain longer
backward match at a real PLD hit. Their fifteen-case no-hit family had zero
candidates and could not score it. Current positive PLD rows are the changed
evidence. Full vocabulary/Q8, depth/PLD sweeps, token-hash MLP, no-hit self
lookup, short-key/count backoff and external-corpus thirds stay closed.

The separate MoE follow-up is rejected on present evidence: H128 requires
all 128 folded rows, so independent 32-row blocks cannot preserve its
single-launch scratch-free contract. A full-strip two-expert group needs
1024 threads and still only 20*N workgroups; extra LDS output storage or
pairwise publication/reuse barriers trade against speculative parallelism.
Owner512 already has no spills, and no measured removable stall proves that
these costs can beat native FL. Its original 13.31% slower result remains
unchanged. No new MoE component or engine cohort is proposed.

Only this fresh private directory was written. No hardware, API/engine
requests, WSL/lifecycle, profile, model, shared STATE, public files or Git
state was changed.
