# DFlash context-window startup failure — 10 October 2026

The v1 worker held during cold loading, before request submission: `Actual complete resident CUDA BF16 head required`. No warmup, shadow anchors, acceptance or token-rate measurements were produced.

Source review found a lifetime-unsafe relocation memo and duplicate traversal of shared context/head modules. A freed CPU layout-index object can have its Python id reused by a GPU head object; a later shared-module visit can then select the stale index destination. This explains a possible route to the head invariant failure, but actual object-id reuse was not recorded. The repair retains source objects strongly and visits each module once while preserving exact buffers and dtype.

The actual tool ended with exit 1. Owned candidate resources were cleaned and normal lifecycle recovery completed. Diagnostic native/worker retirement remains explicitly unqualified because no completed request existed. The normal 262,144-context server was restored ready/open; its actual identities and retained terminal/runtime evidence are pinned in the JSON.

The success reporting helper and failed v1 evidence remain intact. A distinct v2 package must validate the structural repair before any new measurement. No serving gain is claimed.
