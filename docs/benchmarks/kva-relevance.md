# kva-relevance.md — handover v2, Priority 4 / D (KVA / LLKVApprox triage)

**Question:** is KVA / LLKVApprox (PixelML) a usable prefill accelerator for this box?

**Verdict: NOT applicable to our model, and not a decode lever.** Keep it as bounded prefill research
only, and do not spend GPU time on it before the decode candidates in `source-manifest.md`.

## Why it does not fit

- **Architecture mismatch.** The PixelML KVA / LLKVApprox work targets a ~27B, 64-layer dense
  transformer family. Our target is **Qwen3.8-Flash-Next (qwen4exp)**: 48 layers, 512 routed experts
  (top-10) + 1 shared expert, 4 hyper-connection streams, 36 GDN + 12 full-attention layers, and a QSA
  lightning indexer. There is no layer-for-layer correspondence, no expert/MoE path in their kernel
  set, and no hyper-connection stream layout in it either.
- **It is a prefill technique.** KVA/LLKVApprox approximates attention keys/values to cut prefill
  cost. Our decode is **memory-bandwidth-bound on weight reads**, not compute-bound on attention; the
  bottleneck it attacks is not our bottleneck at the decode operating point we care about
  (34–35 t/s @1k, 30–33 t/s at depth). Even a perfect prefill win would not move decode.
- **We already have a prefill gap with a known, cheaper route.** Our prefill is 1035–1057 t/s @16k
  vs ilintar's published 1204 — a 16.4% gap — and the source-guided fixes for that live in the halo-box
  PR18 prefill set (RDNA3.5 MMQ tiles, register prefetch, D=256 WMMA FA), not in an approximation
  technique. See `source-manifest.md` items S9/S10.

## Relevance to the current priorities

- **P1 (MTP acceptance):** none. KVA does not touch draft quality or verify width.
- **P2 (shared-MTP / HIP):** none. Different subsystem.
- **P3 (virtualization):** none.
- **P4 (prefill research):** the only place it could live, and it is **blocked on a model/port**: it
  would need a qwen4exp-compatible implementation before it is even testable here.

## Recommendation

Record as `NOT_APPLICABLE_TO_CURRENT_MODEL` and leave it un-executed. If prefill is pursued after the
decode candidates, do it with the halo-box PR18 prefill patch set (real RDNA3.5 work for this exact
GPU) rather than an approximation kernel for a different architecture.

## Status vs the handover's own framing

The handover already flags PixelML as "27B/64-layer, NOT compatible with our 48-layer qwen4exp"; this
triage confirms that reading from the architecture side and adds that it is a prefill-only technique,
so it is doubly out of scope for the decode work currently in flight.
