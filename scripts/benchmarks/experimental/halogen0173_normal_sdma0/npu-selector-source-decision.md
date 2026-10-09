# NPU confidence selector over native MTP/PLD offers

Source-only decision, 9 October 2026. **An independently trained token-only
selector could choose a native offer width without new GPU readback or changing
the target model weights. The preserved server has no supported per-round
callback that can apply that decision. No current NPU implementation or hardware
candidate is justified.** This is a different mechanism from generating draft
IDs, replacing a vocabulary head, or sweeping startup controls.

The missing interface is specific: an owned, current-version decision transaction
before native drafting/verification, coupled to authoritative round outcomes and
request birth/reset/cancellation/slot-generation ownership. Static instruction
locations identify where such an adapter would act; they do not implement it.
There is also no frozen trained selector, aligned native round ledger, qualified
NPU export, or complete transport/placement cost evidence. No Decode, acceptance,
Prefill, or tok/s forecast follows from this note.

Only this directory's source excerpts, receipt, decision and references were
written. The two preserved ELF files were read as inert data; the existing Windows
LLVM decoder disassembled finite functions and every retained instruction byte
was checked against the current file. No accelerator, driver, API, WSL, engine,
build, source fetch, lifecycle, profile, STATE, Git or model-weight payload action
was performed. A delegated source review independently checked the counters.

## Selector versus draft generator

A selector returns a source/width decision over stock IDs or chooses the number
of native neural predictions to request. It produces no replacement token ID and
requires no output-vocabulary matrix. A generator predicts new token IDs. The
previous delayed-correction predictor and the retained 0.8B autoregressive model
are generators; their missing assets and measured generation costs do not measure
or disprove a tiny selector. Neither is reopened here.

The concrete distinct policy is an independently trained classifier of
**consecutive prefix survival**, using only owned host inputs. For a copied
offer of width `n`, predict `q_j = P(first j stock drafts survive | available
host features)` for `j=1..n`. It may keep a shorter leading prefix. For an early
neural-depth decision, a separate input mode uses the committed prefix and prior
outcomes before later draft IDs exist. A compact feature vector and a quantized
small dense classifier are conceivable NPU assets; no graph, size, latency or
accuracy is claimed to exist.

This policy cannot increase native capacity, manufacture a PLD hit, reorder a
chain, select a later draft after a failed earlier draft, or use future verifier
IDs as confidence. Token-only learned confidence is a prediction of survival,
not the native draft probability or an acceptance guarantee.

## Actual public and startup controls

The preserved 0.17.3 `serve_api.py.data` has request-level `drafter` fields
(lines1487,1518,1698). Its mapping is `serial=0`, `mtp=1`, `dflash2=2`
(lines1889-1890); validation is at2201-2216. `Engine.generate` writes that choice
once in `GEN` (1063-1097). There is no depth, PLD-width, proposal packet,
confidence, or per-round selector result field in that path. The `ctl` passed
alongside the stream carries a stop flag and sends cancellation `X`, not a
drafting decision (1003-1059,1108-1111,2361-2370).

`INFO` parses `spec_rows`, `pld_n`, `pld_k` and drafter capability
(912-938). Health describes prompt lookup as applying to greedy MTP requests
(3200-3204). These are capability/settings reports, not an offer callback.
The optional `--npu` route sends requests naming its models to a separate NPU
decision engine (4205-4214); it does not interpose in native MTP verification.
Greedy/top-logprob scoring is limited to `max_tokens=1` (2167-2175), and the
`T`-line parser reports emitted target-token logprobs (503-511,1142-1146).
Neither supplies draft confidence before the next verifier round.

The backend launcher sets `HALOGEN_MTP_DEPTH` in the process environment
(`service.py:305`) and applies bounded stock/off speculation policies. Its
`speculation_policy.py` docstring still names0.16.2; it is a wrapper constraint,
not proof of a new dynamic native API. Current0.17.3 instructions independently
show PLD parsing at `0x172d3fa..0x172d42c`, SPEC_ADAPT parsing at
`0x172da71..0x172daa8`, and MTP depth/high-depth parsing at
`0x172dafc..0x172dbe5`, all in the startup function. Missing MTP depth defaults
to2; omission of depth and high-depth derives high3, whereas an explicit depth
with no high-depth sets high0. These are native startup choices. Changing the
parent environment cannot submit a new decision to an already-running round.

Current native adaptive depth already keeps a host acceptance EMA: after a neural
round, `0x17518ed..0x1751951` uses accepted-prefix/attempted-width, smoothing
factor1/32, and0.68/0.75 hysteresis. The handler reads the resulting byte and
low/high depths at request+`0x1b0`, +`0x138`, +`0x13c`
(`0x1740844..0x1740857`). A learned conditional selector is distinct from that
existing recent-acceptance heuristic; another static knob sweep would not create
the proposed mechanism. The retained0.17.2 adaptive comparison reported unchanged
combined acceptance and a2.85% Decode regression against its fixed2 bookend
mean. It supplies no current0.17.3 selector labels or gain.

## Current0.17.3 native map, not a rebase

Current ELF:26,188,824 bytes, SHA256
`af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7`.
Previous0.17.2 ELF:26,178,504 bytes, SHA256
`ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913`.
Unique fixed prologues identified the new functions; existing ELF unwind records
bounded them, and actual current calls/loads established the map below. The GPU
code object's retained identity does not establish host ABI identity.

| Role | Previous0.17.2 | Byte-checked current0.17.3 contract |
|---|---|---|
| Neural controller | `0x1750470` | `0x1751770`; request inRDI, selected width inESI. Host proposals are complete at `0x1751803`, in controllerRSP+`0x10`; request isRBX and width isR13/EBP. |
| Early greedy neural depth | `0x173f542..0x173f59f` | `0x1740833..0x174088e` selects/clamps depth and calls the controller at `0x174152a`. Width below2 follows the separate single-draft path, rather than entering the controller loop. |
| PLD lookup/copy | `0x173ef7c..0x173f144` | `0x17401dc..0x17403a4` searches the native host history map, reads continuation index at node+`0x10`, and setsRBX to `min(available suffix,native allowance)`. Misses go to `0x173fd73` without a PLD offer. |
| PLD hit-only join | `0x17400ff` | `0x17413ff`; copied int32 IDs at handlerRSP+`0x6a0`, stock countRBX, request atRSP+`0x10`. Constraint pointer is now request+`0x240`; null constraints pass count throughR13 at `0x17414ce`. |
| PLD native opening check | `0x173eb62..0x173eb79` | `0x173fdbf..0x173fddd`, missing-opening sibling `0x17403a9..0x17403cf`. Cached opening is request+`0x1a0`, current ID+`0x19c`, model+`0x108`. First PLD ID must equal the native opening. |
| PLD verifier | `0x173ebd0 -> 0x17f7980` | `0x173fe32 -> 0x17fa0e0`, with `[current,drafts...]` at handlerRSP+`0xa00` and count `n+1`. |
| Neural verifier | `0x1750534 -> 0x17f7980` | `0x1751834 -> 0x17fa0e0`, with `[current,drafts...]` at controllerRSP+`0x50` and count `n+1`. |
| Accepted prefix/correction | PLD `0x173ebe0..0x173ec32`; neural `0x1750550..0x1750599` | PLD `0x173fe40..0x173fe92`; neural `0x1751850..0x1751899`. Consecutive comparisons stop at the first mismatch; accepted IDs plus authoritative correction/bonus are assembled on the host. |
| Commit/replay | Commit `0x17f9c00`; replay `0x17f7630` | Commit `0x17fc360` at PLD `0x173fea0` and neural `0x17518a3`; continuing neural replay calls `0x17f9c60` at `0x1751d89`. |

PLD allowance at `0x173fcfd..0x173fd37` is bounded by model+`0x14` minus1,
request+`0x120`, remaining model capacity using model+`0x118` and position
model+`0x2e8`, and positive request+`0x228` minus1. The historical cap remains
at most `min(stock_n,3,native_allowance)` for a first bounded selector.
Model/request offsets changed; old0.17.2 hooks cannot simply be loaded or rebased.

Native offers are **not a menu of simultaneously prepared PLD and MTP chains**.
PLD lookup precedes neural fallback. At its hit join the PLD IDs exist, but the
alternative complete neural chain generally does not. Rejecting that offer may
lead to native MTP work; it does not select an already-free alternative. At
`0x1751803`, all chosen-depth neural IDs exist, but their drafting and chosen-ID
readbacks have already been paid. Truncating there could affect verifier/replay
work and useful yield, but cannot claim to save the skipped neural generation.
Actual draft-cache/replay parity for truncation is unqualified.

## Inputs that require no new GPU readback

Available inside native host control flow: committed history IDs, actual native
PLD IDs/count/allowance after a hit, host neural IDs after each wrapper return,
cached opening/current ID, previous accepted-prefix counts, correction/bonus IDs,
and native aggregate/adaptive state. An adapter could copy a bounded immutable
snapshot for an independent token-only policy. The existing API token stream
does not bind these values to an upcoming native round or distinguish accepted
drafts from its correction/bonus; API receipt timing is not a safe pre-round
callback.

Native MTP query/confidence is different. At current `0x17f4298 -> 0x17f46b0`,
the query is device pointer `model[+0xd78]+(count-1)*5120`, corresponding to
BF16[2560]. The reduced consumer produces selected FLOAT logits and scatters
them into full device output `model+0xd80`. Selection follows at
`0x17f42bd -> 0x17f4b90`, device synchronization at `0x17f42c2`, and a
four-byte chosen-ID D2H copy at `0x17f42ed` (return `0x17f42f2`). The wrapper
returns that integer ID, not an owned host logit vector, margin or probability.
The current producer and consumer pointers were checked; BF16 interpretation
also rests on the retained exact identical GPU kernel instructions.

No native logit-margin/entropy confidence scalar is exported in this ordinary
proposal path. Getting the final query or logits to the NPU would add GPU
completion/readback and transport, contrary to the requested boundary. GPU
device pointers cannot be dereferenced by the Windows selector, and pointer
identity cannot prove stable contents. The existing post-response query capture
is an owned offline corpus design; it is not a live confidence/lifetime API.

## Exact missing decision and lifetime transaction

For an early neural-depth policy, a new adapter must present copied committed
prefix/prior-outcome features before `0x1740844..0x174088e`, accept a bounded
width decision, and retain the native gates, capacity clamp and correct single-
versus multi-draft branch. For a PLD policy, it must present the copied hit at
`0x17413ff` and apply only a valid leading width before constraints/opening.
For post-draft MTP truncation, the distinct boundary is `0x1751803`, but a full
controller/replay contract is needed before reducing its effective width.
None of these sites contains an installed external decision callback.

Each snapshot/result needs request birth nonce, slot generation, round,
committed-prefix length/fingerprint, target position, model/tokenizer pins,
offer source/IDs and actual allowance. The native thread must retain authority
over mutation. Reset, cancellation, stop/EOS, slot replacement and request
destruction retire outstanding work; late or mismatched results keep stock
behavior without waiting for the NPU. No asynchronous job may retain raw native
request, model, stack, or logit pointers. Outcome delivery must follow the
authoritative continuing frontier, including scalar/cooldown paths, rather than
only successful multi-draft rounds. Existing source packet locks and sequential
capture head numbers do not supply this lifetime synchronization.

Thus: **no target-weight rebuild is intrinsically required, and no extra GPU
readback is intrinsically required for token-only features. A new current host
adapter and outcome feed are required.** The existing process environment,
request API and NPU frontend alone cannot realize the proposed selector.

## Acceptance denominator and decision objective

Native neural accounting adds full attemptedR13 width to request+`0x70` and
consecutive acceptedR15 prefix to+`0x78` (`0x17518d7..0x17518e9`). A first-ID
mismatch accepts0 while retaining the full attempted count. PLD similarly adds
one round to+`0x40`, accepted prefix to+`0x48`, and attemptedEBP to+`0x60`
(`0x173feaa..0x173fec9`). A later individually matching ID after the first
mismatch remains unaccepted and still counted as attempted.

The API parses explicit `head_drafted` from wire field26 (991), PLD fields
from12/13/14 (970-973), and computes (2594-2601):

```
head_a = commit - rounds - shared - pld_accepted
draft_n = head_drafted + pld_drafted
draft_n_accepted = max(0, head_a) + pld_accepted
```

When `head_drafted` is absent, it falls back to neural round count; it exposes
the aggregate only when PLD is off or explicit PLD attempted count exists.
The reported ratio combines MTP and PLD and excludes the per-round
correction/bonus contribution from its accepted numerator. Lowering width or
omitting difficult rounds can raise that ratio without improving completed
token yield or Decode. Acceptance multiplied by Decode is not throughput.

For an ordinary continuing greedy round, a chosen leading width `m` yields
expected commits `K_m = 1 + sum(q_j, j=1..m)`. Stop/output limits can censor
that identity. Evaluate complete time per committed token across the request:
`sum(round_time)/sum(authoritative_committed_tokens)`. Charge feature packing,
NPU dispatch/return, both directions of WSL/Windows transport, scheduling,
publication/ownership checks, changed target width, replay, fallback, discarded
jobs, initialization and any concurrent target slowdown. After-drafting
selection keeps the already-paid draft cost. No measured exposed cost or
positive scheduling lead exists for this selector, and a tiny graph alone does
not establish that NPU placement beats executing the same policy on the host.

Training needs an aligned causal round ledger: pre-decision host features,
actual offered IDs/source/width/allowance, authoritative prefix length and
correction, termination/invalidation, and complete cost labels. For prefix
position `j`, the survival label is `accepted_prefix >= j`; positions never
attempted are censored, not failed. Use document-separated training/evaluation
and a fixed policy on its own changed trajectory. Current aggregate counters,
weight-only rank64/top256 assets and final-query/top-ID captures do not supply
that ledger or independent selector training data. They cannot justify oracle
source choice or transfer a stock trajectory's later states after divergence.

## Disposition

Retain the learned token-only offer-width policy as the genuinely distinct
conditional mechanism. Its decisive next prerequisite is a qualified selector
asset with causal native offer/outcome supervision and complete-cost evidence,
plus the specifically identified current host transaction. These are absent.
Do not implement a live shim, launch a component, add a per-token confidence
readback, rebuild the native model, or reopen the previous generator/head/
startup-control experiments on this assessment. The delivered result is the
current0.17.3 ABI proof and a concrete infeasibility boundary for the existing
interfaces.

Exact source/evidence file hashes and retained byte-span hashes are in
`refs.json` and `native-source.json` in this directory.
