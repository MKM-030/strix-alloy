# Native owner connection: reviewed source and one compilation

The new default-off `native_owner_capture` source connects supplied actual native
byte spans to fixed owned copies, the unchanged layout decoder and the unchanged
outcome handoff with `packet=null`. The independent
[source review](../../scripts/benchmarks/halogen_pld_nohit/NATIVE_OWNER_CAPTURE_REVIEW.md)
found no remaining blocker within its documented upstream capability contract.
The acknowledged native slot is explicitly compared with the decoded slot.
Both capability issuers and the installed native read boundary remain absent.
This is source progress, not an observed engine connection or lifetime proof.

Root ran the [focused compile-only launcher](../../scripts/benchmarks/halogen_pld_nohit/run_native_owner_capture_compile.py)
once with C++20, `-O2 -Wall -Wextra -Werror`, exceptions/RTTI disabled and stack
usage emitted. The compilation returned zero with no errors. No test executable,
native entry, engine request, GPU or NPU job was run. Compiler-reported static
stack for `observe` is 400 bytes; this excludes its complete callback call tree
and does not qualify an installed stack/signal/unwind budget. The object and
stack report are pinned in the [machine-readable receipt](halogen-pld-native-owner-connection-status-20261006.json).
All retained Windows jobs closed. Linux work returned within its finite timeout;
escaping descendants and external cancellation closure are not claimed.

Private native byte buffers total 6,018 bytes and include at most 512 suffix IDs.
A separate complete-prefix acknowledgement must finish before the bound seam;
matching suffixes, lengths, fingerprints or generations do not acquire that proof.
No copying of proposals or real machine state back to native objects is present.
The existing relay, layout decoder, handoff and consumer sources were preserved.

| Placement | Serving assessment after this development |
|---|---|
| CPU | Appropriate for fixed bounded copies, layout checks and owner metadata. Added complete cost has not been measured. |
| GPU | Separate token proposal production remains possible; complete transfers, contention, synchronization and readiness must be demonstrated. |
| NPU | The same owned values can support a separate proposer; actual runtime state parity, integration and timely readiness remain required. |

The connector does not replace ordinary target Prefill. Faster Decode and higher
acceptance would require useful independently predicted tokens, a real installed
consumer and a frozen complete-server comparison. Exact arithmetic alone normally
preserves proposals and cannot establish higher acceptance. CPU capture latency,
GPU/NPU readiness, new Prefill/Decode tok/s, native acceptance and serving gains
remain **unmeasured**. The latest GPU H vector screen still establishes no advantage;
it is not repeated or adopted because this connector compiles.

Next use the concrete native serialization findings to acquire a real read/seed
and lifetime boundary. Source-private authority types do not implement that work.
Do not repeat the unchanged compile, prior relay checks or defeated device screens.
The original normal server remains open; full acceleration is unachieved.
