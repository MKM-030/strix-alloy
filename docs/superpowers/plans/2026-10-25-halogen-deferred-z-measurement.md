# Halogen 0.18.15: original-kernel overlap and comparable measurements

The user authorizes continued implementation and necessary server restarts until
prefill and decode approach the original results. Keep one large engine only;
leave the serving instance online afterward. Preserve the existing 35-GiB base
startup admission, Vision increment, 18-GiB physical/commit runtime reserves and
22-GiB entry reserve. Preserve other applications and models outside the explicit
resource-unload authorization. Root exclusively owns hardware work.

The retained 8K A/A' control is 47.56 native decode tok/s and 66.04% head acceptance;
prefill is 1189.59 native tok/s. Phase clocks remain independently unqualified.
Whole HTTP time and output/count parity are the independent comparison evidence.
The former 1925.16 PP1 and 48.42 MTP128 came from separate requests. Do not merge
them into a new measured operating point. Do not select only the fastest prompt.

## Current diagnosis

- Current and historical core weights use the same real HIP allocation/copy
  policy. No new placement regression has been demonstrated by that comparison.
- A runtime update report about another GPU does not establish a local cause;
  the 10.0/10.1 mapping-flags ABI needs a complete caller/provider match.
- The original 0.18.15 server stopped at 21:20 UTC after available physical memory
  crossed its 18-GiB floor. Exact previous owners and normal cleanup are retained.
- The human authorization “Ja – andere Modelle entladen und Halogen danach
  online lassen; Voice pausiert” covers Qwen-ASR and Qwen-TTS. The earlier
  separate ASR approval question unnecessarily narrowed that authorization.
  The retained `authorized-voice-window.json` receipt confirms both models were
  unloaded successfully on 2026-10-25 at 22:18:38 UTC. Root owns any further
  lifecycle work.

## Chosen bounded candidate

Test a default-off deferred-Z schedule derived from the reviewed Gufo overlap
idea. Preserve the original QKV, alpha, beta, Z, convolution and fused recurrence
kernels and their arithmetic. Complete all native FC operations that share
workspace before forking the deferred Z operation. Use a private nonblocking
stream and private events; never borrow model-owned prefetch streams or events.
Join before every native Z consumer and before buffer reuse or error cleanup.

This is selected for investigation because it can overlap independent work
without approximate target state. A new NPU proposer has no trained compatible
weights or proven timely consumer; swapping a lone runtime library has no proven
ABI safety or expected gain. Neither alternative is a measurement candidate yet.

## Work and verification

An independent profile-only candidate reduces **both** prefill_chunk and
max_prefill_tokens from8192 to4096. The earlier0.18.5 natural16K report measured
1849.54/1856.12 native prefill tok/s at4096/4096. That historical association is
not a causal prediction for0.18.15. Its CPU-validated collector is under
server/.local/halogen-update-20261025/continuation-2110/arena4096; it delegates to
the unchanged current collector and admits only these two coupled profile
fields. It preserves the exact current requests and all output/cache/reserve
rules. Measure this separately from the stream adapter; never bundle their
changes into a single claimed improvement.

1. Finish the pinned native control-flow and buffer-range review. Independently
   implement/test stream ownership and scoped redirection. If live allocations
   or all consumers cannot be bounded, leave the candidate disabled and record
   the missing contract; do not invent successful overlap.
2. Restore the existing normal server as soon as normal admission passes, using
   current terminal owners rather than stale PIDs. Persist fresh ready identities.
3. Compile the candidate with the existing toolchain only after static review.
   Use a current stream/provider binding and prove callback scope. CPU fake-HIP
   schedule tests cover event generation, workspace ownership, errors and reuse;
   they are not numerical or performance qualification.
4. Root runs a fixed request control, then candidate, then control bookend. Each
   case uses one excluded warmup and three measured repetitions, cache no_store,
   temperature 0, seed 1, unchanged output budget and identical request bytes.
   Preserve actual input/output counts, hashes, draft counts and whole HTTP QPC.
   A single warmup or failed cohort is not a post result. Stop on output or
   invariant mismatch. Do not repeatedly restart a live observation handle.
5. Accept only a repeatable elapsed-time improvement, with intact output/count
   parity and no lost prefill/decode behavior. Native phase observations remain
   labeled until independently clock-qualified. Restore the faster qualified
   serving configuration, leave it open, and save exact current identities.

## Review focus

The scoped FC must not redirect alpha/beta or later layer operations; every
early return must join side work; host-failure cleanup must drain both streams;
scratch must survive asynchronous completion; native decode-prefetch ownership
must remain independent. A CPU stub's success proves none of the actual device
allocation ranges or numerical output parity.

The full speed objective remains unachieved until measured evidence satisfies it.
