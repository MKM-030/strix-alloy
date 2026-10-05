# Offline PLD proposal packet and stock-preserving selection

5 October 2026 scope. **A default-off, finite CPU packet/selection adapter is
implemented.** Its three focused synthetic tests pass. This prepares a bounded
token-only contract for the retained PLD-hit seam; it implements no native shim,
trained proposer, transport, model load, NPU execution or engine integration.
Native acceptance, token throughput and engine gain remain unqualified.

Source: [codec and selector](../../scripts/benchmarks/halogen_pld_proposal_wire.py),
[three focused CPU tests](../../scripts/benchmarks/test_halogen_pld_proposal_wire.py).
The implementation follows the
[private insertion scope](halogen-npu-native-pld-injection-scope-20261005.md) and
[compact proposer plan](halogen-npu-compact-pld-proposer-plan-20261005.md), while
borrowing immutable dataclasses, fixed little-endian framing and whole-packet
validation patterns from the existing FC wire. That existing wire is unchanged.
This author created only these three files and ran only the named CPU tests;
no hardware, runtime/model probing, compiler build, WSL/server/lifecycle action,
continuation edit or commit was performed.

## Packet contract

`encode_proposal` receives an immutable binding and a tuple of one to three
independently supplied IDs. It returns one privately owned immutable byte frame:
**192-byte header + 4*n ID bytes + 32-byte HMAC-SHA256**, exactly 228–236 bytes.
Fields use little-endian integers; IDs/current token are nonnegative signed
int32 values. No pointer or retained native address appears in this protocol.

| Header offset | Bytes | Field |
| --- | ---: | --- |
| 0 | 8 | Magic `HGNPLDP1` |
| 8 | 4 | Version 1 |
| 12 | 4 | Proposal count, 1–3 |
| 16 | 16 | Integrity key ID |
| 32 | 32 | Model binding |
| 64 | 32 | Tokenizer binding |
| 96 | 16 | Request-initialization nonce |
| 112 | 16 | One-shot round ID |
| 128 | 32 | Authoritative committed-prefix fingerprint |
| 160 | 8 | Committed-prefix length |
| 168 | 8 | Target position |
| 176 | 4 | Current token |
| 180 | 8 | Committed context-window origin |
| 188 | 4 | Window count, exactly prefix length minus origin |

The binding requires exact immutable byte fields, nonzero nonce/round/trust
values, positive committed-prefix length and target position, and a window of
1–512 committed tokens. Target position and prefix length are separate supplied
values: this offline format invents no native equality between them. A caller
should fingerprint the authoritative canonical committed IDs, for example with
SHA256 over their little-endian int32 representation. The adapter receives that
truth; it does not reconstruct a native context or read future target rows.

The 32-byte caller-owned integrity key authenticates the complete header and
ID body. The selector owns a copied, bounded trusted key map; unknown key IDs
decline. HMAC protects the frame and does not prove model/tokenizer compatibility
or native context freshness. Trusted model and tokenizer bindings must match
exactly both the caller's current snapshot and the packet. These trust values
are explicit fixture/configuration inputs, not model-file verification performed
by this module. The real target/proposer tokenizer comparison remains a separate
gate in the plan; their raw file SHA values differ.

## Selection and unchanged stock fallback

The caller supplies `SelectionContext(binding, stock_ids, native_allowance,
constraints_present=False)`. Stock IDs must be the original immutable int32
tuple; its count is `len(stock_ids)`. The adapter copies no borrowed native
pointer and never changes this tuple, caller context, or the caller's key map.
Configuration/context construction errors raise `ValueError`; this trusted API
boundary is separate from rejecting an untrusted reply.

`ProposalSelector` defaults to `enabled=False`. Enabled selection requires two
explicit caller truth predicates:

- `token_is_defined(ID)` answers from the trusted tokenizer's defined IDs.
  A head-range check alone is insufficient because some head IDs may be undefined.
- `context_is_current(context)` answers from authoritative committed state and
  current request/round readiness. It must decline stale, retired, cancelled,
  reset or late replies. It must not inspect future target predictions or
  manufacture the native opening-token match.

Both predicates must return the literal boolean `True`; missing, failing or
raising callbacks decline. The wire range bound and token definition predicate
apply to candidate IDs; the current token must also fit the trusted range and
definition map. These callbacks are explicit caller obligations, not a proof
that an engine observation is truthful or synchronized.

The eligible reply count must satisfy:

```text
1 <= candidate_count <= min(len(original_stock_ids), 3, native_allowance)
```

A reply exceeding the cap is rejected whole, without truncation or enlargement
of the native count/buffer. A constraint object declines this first adapter.
An empty stock block or zero allowance returns stock, supplying **no no-hit
coverage**. Disabled, unknown-key, malformed-length/count, tampered, out-of-range
or undefined-ID, mismatched/stale binding and caller-unavailable cases likewise
return `Selection(original_stock_ids, False, reason)`. The returned stock tuple
is the same object; original values and count stay intact.

Only a fully validated selection consumes `(request_nonce, round_id)` in the
selector's owned set. A replay of a consumed round declines even if the packet
is still otherwise valid. Each selector permits four successful rounds by
default, configurable to 1–64; exhaustion declines. Rejections spend no valid
round or success budget, allowing a corrected fresh reply for that same unused
round. A local lock makes this consumption atomic between adapter calls.

`used_proposal=True` means the offline selector returned a replacement tuple.
It does not mean a native stack was overwritten or that the target accepted an
ID. The retained seam lies before native constraint/opening-head/verification
handling: any later qualified shim must preserve those native gates, target
accepted-prefix/correction handling, replay and stock fallback. This module
neither calls that machinery nor synthesizes a matching first token.

## Focused CPU validation

The new test file was first run before the module existed and failed with the
expected missing-module error. After implementation, the explicit root-venv
command passed exactly **3 test methods**:

```powershell
& 'C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe' -B `
  'C:\Projects\strix-alloy-clean\scripts\benchmarks\test_halogen_pld_proposal_wire.py'
```

The tests exercise fresh one-shot selection/replay and finite exhaustion;
stale/tampered or wrong/unknown bindings retaining the same stock tuple and
subsequent valid round; and native/stock/three-ID bounds, malformed frames,
undefined/out-of-range IDs, constraints and default-off fallback. Expected
proposal/stock IDs are literal synthetic fixtures. No fixture contains a model
prediction, tokenizer qualification, future answer, or native acceptance result.
`-B` avoids bytecode writes; no optimization flag, broader test suite, model,
compiler or live probe was used.

## What this enables and what remains missing

The small owned frame makes identity, integrity, count, stock preservation and
finite one-shot behavior reviewable independently of a future producer. Keeping
caller truth explicit avoids treating an object pointer or position as a native
epoch. The design declines uncertainty instead of borrowing native request
vectors or claiming reset/cancellation safety from constructor/destructor anchors.

The local lock does not cover native request destruction/reset, cancellation,
slot transitions or the gap between a truth callback and actual engine use.
An eventual caller must prove serialization/ownership across that boundary,
retire birth nonces and outstanding work, and apply results before their native
state can change. External proposer accepted-prefix/correction synchronization,
rejected-suffix discard or committed-window rebuild also remain unimplemented.
No private ABI, live-register preservation, trampoline, transport or asynchronous
feed is qualified here.

The current seam is PLD-hit-only: it retains stock lookup and cannot add no-hit
proposals. A genuine tokenizer-compatible independently trained producer and
raw-ID state adapter are still required. Its useful comparison must include all
proposal generation, transport/checking, native opening/verification/commit/replay,
rejection and fallback, window rebuilds and actually committed output tokens.
These CPU tests establish only the offline protocol behavior.
