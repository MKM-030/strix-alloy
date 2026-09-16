# QSA indexer width: the handover's #1 hypothesis is CONFIRMED structurally (2026-09-15 late)

The handover's top correctness hypothesis was that speculative verification crosses an indexer
matrix-vector dispatch threshold because the indexer's **flattened** width is `4 × tokens`, not because of
token count. Verified against our model and our code. **It is true.**

## Evidence chain (all from our own model + our own source)

**1. Our indexer has 4 heads** — read from the PROJFIX GGUF metadata:
```
qwen4exp.attention.indexer.head_count   = 4
qwen4exp.attention.indexer.key_length   = 128
qwen4exp.attention.indexer.top_k        = 2048
qwen4exp.attention.head_count           = 24
qwen4exp.attention.head_count_kv        = 2
```

**2. The scoring op's second operand is `[idx_dim, n_idx_h × n_query, n_stream]`** — from
`build_qsa_top_k` in `src/models/qwen4exp.cpp`:
```cpp
ggml_mult(ctx0, score_keys,
    ggml_view_3d(ctx0, q, idx_dim, n_idx_h*n_query, n_stream, ...))
```
So the mul_mat's `ne11` (= number of destination columns, i.e. the effective batch) is
**`4 × n_query`**, exactly as the handover described.

**3. The dispatch threshold is 8 on this GPU.** `MMVF_MAX_BATCH_SIZE = 8`
(`ggml/src/ggml-cuda/mmvf.cuh:3`), and `ggml_cuda_should_use_mmvf()` gates on:
```cpp
} else if (GGML_CUDA_CC_IS_AMD(cc)) {
    if (fp32_mma_hardware_available(cc)) { return ne11 <= 3; }
    return ne11 <= 8;
}
```
and `fp32_mma_hardware_available()` returns **`GGML_CUDA_CC_IS_CDNA(cc)`** — CDNA only. gfx1151 is
RDNA3.5, so **the gate is `ne11 <= 8`**.

## The consequence — a kernel-family switch at our production operating point

| configuration | token rows | indexer `ne11` = 4 × rows | kernel family |
| --- | ---: | ---: | --- |
| serial decode | 1 | **4** | MMVF (vector) |
| MTP n-max 1 (verify) | 2 | **8** | MMVF (vector) — at the cap |
| **MTP n-max 2 (our production)** | **3** | **12** | **NOT MMVF** — falls through to MMF/MMVQ/MMB/MMQ or cuBLAS |

**Serial decode and our production decode run *different kernel families* for indexer scoring.** The
handover's claimed mechanism is not merely plausible on our stack — it is structural.

Note also that n-max 1 sits exactly *at* the cap (8 ≤ 8) while n-max 2 is the first width to cross it.
That predicts a **discontinuity between n-max 1 and n-max 2 specifically**, not a gradual trend — which is
testable and is what the running comparator measures.

## What this does and does not establish

**Established:** the width/node-shape relationship and the dispatch boundary, from our model and our source.

**NOT established:** that the kernel swap *changes the selected indexer rows or the logits*. A different
kernel computing the same reduction order would be numerically identical. This is a **lead**, not a
demonstrated defect — exactly as the handover frames it.

## The test now running

`verify-width-equivalence.ps1` + `verify-width-equivalence.py`:
- Same byte-identical prompt, `temperature 0`, `top_k 1`, seed 1234, `cache_prompt false`
- **Arm A** — no drafter → serial greedy tokens = reference
- **Arm B** — `-md <shared head> --spec-draft-n-max 2` → speculative greedy tokens

Speculative decoding is defined to be **output-equivalent to serial greedy decoding**. Any divergence is a
correctness signal. Per the handover I record the **first divergence position** and the surrounding token
context, not just a boolean — a near-tie float difference and a changed attention semantics are different
findings, and the token context is what separates them.

Two arms, run strictly serially (never two 177B instances).

## Also from the preflight audit

- **`HIP_LAUNCH_BLOCKING` is NOT set at any scope**, and no SDK file sets it. The handover flagged this as a
  potential large benchmark confound — **ruled out**, so all our timings stand.
- Machine-level `HIP_PATH` points at the old `C:\Program Files\AMD\ROCm\7.2\`, not our TheRock SDK. Our
  launch scripts override it, and the SDK DLLs now win the loader order (the `amdhip64_7.dll` shadow fix),
  so this is inert — but worth noting as a latent trap for any script that forgets the override.
- GPU driver `32.0.31041.1004` unchanged; NPU `OK`; no competing heavy work on the box.
- Pinned binary hashes for the record: `llama-server.exe BE4E66A8BDA811DF`, `llama.dll 69D1A62C51CFB053`,
  `ggml-hip.dll 3C834F4ADD6DF769`.
