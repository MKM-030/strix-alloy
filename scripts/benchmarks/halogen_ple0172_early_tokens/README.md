# Halogen 0.17.2 early-token publisher source

This default-off experiment observes an owned, frozen 16K request early enough
to investigate preparing the second 8192-token chunk while the GPU handles the
first. The reviewed callback-bound port compiled successfully on 8 October
2026. It has **not been loaded or benchmarked**.
It does not run an NPU worker, substitute model results or change the live server.

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
