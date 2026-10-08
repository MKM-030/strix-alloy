# Halogen 0.17.2 early-token publisher source

This default-off experiment observes an owned, frozen 16K request early enough
to investigate preparing the second 8192-token chunk while the GPU handles the
first. The reviewed callback-bound port compiled successfully on 8 October
2026. Root loaded it once for an owned 16K observation. That request failed at
`later-key-identity` and returned HTTP 502; it supplies no qualified performance
or token-release interval. Normal cleanup restored a clean 0.17.2 serving instance.
It does not run an NPU worker or substitute model results.

The source binds the exact 0.17.2 engine and function signatures in
`ple_engine_binding_0172.h`. Wrapper and Target forwarding use the observed void
ABI, once per native call. Selected admission requires the exact normal serving
callback manager/invoker. Completion checks preserve that pair and observe native
thread cleanup; structural completion alone is not inference success.

Source SHA256:
`83876d810498ae083ec172637c9b03d86c60af0140536aa1eb16673848005f03`.
Header SHA256:
`70fef9599dd6f9f4722ce73d73a11a5c92e4e790cc6ba505f5b176a0d6824681`.

The CPU-only build used `PLE_EARLY_BUILD_SHA` equal to the actual source hash,
`-Wall -Wextra -Werror`, and produced a 41,432-byte ELF64 x86-64 shared object.
Artifact SHA256:
`51e70a40b0251b040ceb5564c48dd1faba26f3b89abad1e0deab0dd9b0858aaf`.
The compiler exited zero and its owned job closed; no engine lifecycle, GPU or
NPU operation was performed. The private receipt is
`ple0172-host-build-490b932c16c64f14b777d4934ae31a2a/build.json` beneath the
0.17.2 preparation directory.

Root must issue fresh source/header/owner receipt pins before loading. The preserved
0.16.2 and original 0.17.2 preparation receipts cannot qualify this derivative.
Keep ordinary requests delegated, retain cancellation and unchanged numerical
tolerances, and use the normal lifecycle. Qualification requires owned HTTP
completion, exact token/chunk/generation evidence, an observed preparation lead,
and a measured benefit to the complete request. No NPU token-rate gain is claimed.

Private review, native ABI captures and post-fix preparation receipts are retained
under `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/`.
The live ServiceNow instance remains on the qualified stock 0.17.2 path.

The retained current stage has a native-prefetch helper-skip branch. The v1
observer required the later helper to run inside the second Target, which cannot
describe that path. A corrected observer must bind the actual prefetch caller
and second-chunk ownership; do not repeat v1 unchanged. Static extraction now
establishes exact PLE and default BF16 shader instruction identity with the old
validated kernels. Actual current input parity and NPU serving gain remain
unqualified. See [the current development status](../../../docs/research/halogen0172-prefill-overlap-20261008.md).

The new `ple_early_token_publish_0172_v2.c` and
`ple_engine_binding_0172_v2.h` bind the native CPU-prefetch launch, worker and
wait/join paths. They preserve native calls, raw input/carry ownership and
ordinary prefetch behavior. Worker observation supports the native default64
and maximum256; callback payload/TID reuse is allowed after return.
Root independently reviewed the correction and compiled it successfully with
`-Wall -Wextra -Werror`. The 47,064-byte ELF has SHA256
`8833bf7dd0424cb3b17027342ceed985fb86fe44dd8444b7a0592915842d0da5`.
Root loaded v2 once using its separately sealed launcher and manifest. The
owned 16,384-token request completed HTTP 200 with 128 output tokens; all 64
native workers returned and joined. Full request, suffix, carry and promoted
state bindings passed. The original Thinking-enabled 0.17.2 serving profile
was restored ready and open, with the observer removed.

The native second-chunk worker interval was 8647.885 ms, but most of that work
already overlaps GPU execution. The wait-to-join interval was 200.944 ms.
These intrusive observations are not throughput measurements. No NPU or result
substitution ran. The completed observation will not be repeated unchanged.

Follow-up implementation targets the ordinary first lookup and preserves the
existing second-chunk prefetch. Exact raw FP8 rows and original-order row IDs
are available from an archived CPU replay; native attachment and a serving
speedup remain unqualified. See the current development status linked above.
