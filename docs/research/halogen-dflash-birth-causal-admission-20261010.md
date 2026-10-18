# DFlash birth diagnostic: request not admitted

Session **17990** is terminal (exit 1). The instrumented Halogen 0.17.3 candidate became ready at context capacity 32,768, but the 22/22 GiB request-entry check rejected the diagnostic **before submission**. The candidate-ready snapshot recorded 23,438,061,568 bytes (**21.828396 GiB**) of physical reserve. The exact subsequent rejecting frame was not separately retained.

The requested workload remained the frozen natural 16,384-token prefix and 128 output tokens. There is no completed diagnostic prefill, decode, acceptance or first-birth predicate observation from this attempt. The native terminal receipt records two startup GEN seams, **zero owned births and zero feature exports/ingestions**. Startup smoke activity is separate from the diagnostic.

The candidate was cleaned up and the normal server restored. Root verified controller **23288**, backend **23140** and visible console **34828** ready at context capacity **262,144**, with no active request. That verification is copied into the completed trial as `normal-preserved-after-terminal.json`. Seventeen runtime files and the terminal checkpoint are retained. Capture retirement was unqualified; normal process cleanup and restoration succeeded.

This instrument-only build preserved the original birth-validation predicates and short-circuit order. It rebuilt only the caller object and retained the other 29 objects. No NPU producer or optional Ready substitution was enabled, and no throughput gain is claimed. The earlier actual request failure remains documented separately in [the head-constructor capture report](halogen-dflash-head-ctor-capture-20261010.md).

A distinct follow-up uses a **17,408-position diagnostic KV pool** with the same input/output workload. This is supported by the native pool requirement (at least context, a multiple of 256) and leaves 896 positions beyond the requested 16,512 input-plus-output positions. The retained entrypoint formula estimates 453,120,000 bytes, approximately **0.422 GiB**, less KV storage than the 32K pool. That is an estimate, not measured reclamation or proof of admission. Startup 35/131 GiB, request-entry 22/22 GiB and runtime 18/18 GiB floors remain unchanged. The colleague's restored profile remains at 262K.

Evidence directory:

```text
server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/
  dflash-root-birth-causal-capture-launch-20261010/trial/
```
