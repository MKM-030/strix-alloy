# Bug B resolved: the MTP acceptance cliff is `indexer.top_k`, and raising it is a working fix
# (2026-09-15)

## The finding

The MTP draft's acceptance collapses to exactly 0% past a depth that **tracks
`qwen4exp.attention.indexer.top_k`** — proven by varying that key alone with `--override-kv`:

| `indexer.top_k` | acceptance OK up to | collapses from |
| ---: | ---: | ---: |
| 512 | 1024 | **2048** |
| 2048 (model default) | 2048 | **4096** |
| 16384 | 8192 (69.6%) | only the 4096 row was anomalous |

The threshold is exactly `n_kv > indexer_top_k + ratio - 1` (with `ratio = 4`), the gate in
`qwen4exp_use_block_selection()` (src/models/qwen4exp.cpp:809). Above it, the QSA input switches to the
maskless/packed-key layout — and the **draft** was deliberately allowed into that path (the comment above
the gate says so: *"keeping it shut the draft out of block selection, and with it out of the
maskless/packed-key layout and the qsa3 attention kernel"*). Past the threshold the draft's attention
stops matching the target, so acceptance is exactly 0 and MTP costs more than it saves.

## The fix (works today, no source change)

Set the indexer budget **above the context length**, which keeps the draft on the dense path:

```
--override-kv qwen4exp.attention.indexer.top_k=int:<ctx + margin>
```

Three constraint facts were established by experiment (each cost a run to learn):

1. **`top_k` must exceed the actual context**, not the max context — `top_k=65536` with `ctx=131072`
   made the server fail at graph init with `GET_ROWS failed / ROCm error`.
2. **`top_k` must not be absurdly large either** — `top_k=65536` at `ctx=262144` failed the same way,
   because the indexer's per-query allocation scales with `top_k`.
3. **The working rule is `top_k ≈ ctx + margin`.** Measured to work at both 65536 and 131072 context.

Measured, same binary / quant (UD-IQ4_XS) / head (shared Q8_0) / `-b 2048 -ub 2048`, native Windows:

| config | depth | prefill t/s | decode t/s | acceptance |
| --- | ---: | ---: | ---: | ---: |
| **ctx 65536, top_k 69632** | 1024 | 206 | 23.3 | 72.7% |
| | 8192 | 326 | **21.7** | 43.8% |
| | 16384 | 377 | **21.2** | 41.5% |
| **ctx 131072, top_k 135168** | 1024 | 240 | 27.3 | 72.7% |
| | 8192 | 286 | **21.2** | 43.8% |
| | 16384 | 271 | 14.9 | 41.5% |
| ctx 32768, top_k 65536 (earlier) | 2048 | 358 | **30.5** | **81.9%** |
| | 8192 | 396 | **28.5** | **69.6%** |
| | 16384 | 375 | **20.9** | 43.8% |
| **default budget 2048 (broken)** | 8192 | 425 | **13.2** | **0.0%** |

So the fix turns MTP from *worse than serial* into **~21–30 t/s at depth (1.5–2× serial 14.5)**, and it
**scales** — the same override works at 131k context, which is the operating regime we care about.

Acceptance is lower at depth (41–44%) than at short context (73–82%), which is expected: the draft's own
prediction quality falls as history grows. It is still well above the ~30% break-even for depth 2.

## Root cause, precisely: the new sparse decode disagrees with the dense path past the threshold

Two code sites select attention for decode (`src/models/qwen4exp.cpp`):

- **target** — `graph::build_layer_attn` (~line 1420):
  ```cpp
  if (n_kv <= width) { build_qsa_store_k(...); } else { top_k = build_qsa_top_k(...); }
  ```
  i.e. sparse whenever `n_kv > indexer_top_k + r - 1`, **regardless of token count**.
- **draft** — `graph_mtp::graph_mtp` (~line 700): sparse when `n_tokens <= 8 && ...` (a decode step).

So at depth > 2051 the target's verify step also runs sparse. With `--override-kv top_k = ctx+margin`,
`n_kv <= width` holds and **both** are dense → acceptance returns. That is why the mitigation works.

**A draft-only fix does not work**, and I verified that the hard way: I patched only the draft's
`sparse_decode` to `false`, rebuilt, and measured **0% acceptance at 8192 tokens again** — because the
target's own sparse decode is the half that disagrees. Reverted.

**Conclusion: the newly added sparse-QSA decode (`d67d5883`) is not numerically consistent with the dense
path past `indexer_top_k + ratio - 1`.** The acceptance loop compares the draft's proposal against the
target's *decode* logits, and at that boundary the target's own attention changes behaviour, so the
comparison breaks. This is a precise, reportable bug against the newest upstream feature, with a one-line
repro and a known workaround.

## Practical settings that work today

| goal | settings |
| --- | --- |
| **max prefill** (no MTP) | `-b/-ub 8192`, default `top_k` — 452–472 t/s, serial decode 14.5 |
| **max decode** (MTP, dense) | `--override-kv qwen4exp.attention.indexer.top_k=int:<ctx+4096>` → 21–30 t/s at depth |
| **long context** | `ctx 131072` with `top_k 135168` verified working |
| ⚠️ never | `top_k` ≤ actual ctx with a big ctx (fails `GET_ROWS`), or ub 8192 with `-md` (Bug A) |

## Why Halogen's 0.9.1 change is directly relevant

Halogen 0.9.1 added **`HALOGEN_INDEXER_BUDGET`** — the same knob: *"The checkpoint attends the top 512
blocks (2,048 tokens) of the context per query; that value is the default... Set to 4096 (2,048–8,192) the
model attends a superset of what it was trained on"*. Their measured trade:

- budget 4096: retrieval **95/96** (vs 94/96 default), at **+4.5%/6.7% of prefill** (8k/32k) and ~2% of decode
- budget 8192: 96/96, "consistent perplexity cost", **19% of prefill**
- **speculative decoding stays byte-identical to serial at every budget**

That last line is the important one for us: Halogen explicitly validated that changing the indexer budget
does **not** perturb speculative output. Our finding is complementary: on the llama.cpp side the budget
also *gates whether the draft is sparse at all*, and raising it is what makes MTP usable at depth.

## Where each engine now stands (native Windows, 96 GB carve)

| | prefill | decode | note |
| --- | ---: | ---: | --- |
| native HIP serial | 452–472 | 14.5 | stable, best prefill we have |
| **native HIP + MTP + top_k fix** | 358–396 | **28–30** | needs the override; depth-limited only by budget |
| Vulkan + FR-Spec | 366 | 30 | best decode, but FR-Spec is Vulkan-only |
| Halogen 0.9.1 (native Linux) | ~1,250–1,400 | 25.4 serial / 42–45 drafted | closed; not runnable here |

## Carve status (confirmed)

The carve was raised to **96 GB**: device pool is now **114,507 MiB = 111.8 GiB** (was 79.8),
108.8 GiB free. Windows total RAM dropped to 31.6 GB, and **WSL now has only 30 GB** — so at this carve
**native Windows is the only viable engine** (the 87 GiB model cannot be staged in WSL). This is exactly
the configuration olliehm and the author use, and it is what makes ub 16384 + draft head + 262k ctx fit.
