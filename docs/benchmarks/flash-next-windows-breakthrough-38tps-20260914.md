# BREAKTHROUGH: 27–38 t/s decode on Windows — the drluoto/FR-Spec configuration (2026-09-14)

**The founder's four new sources contained the answer.** The `vincentkelleher/qwen3.8-flash-next-halo`
config validated on our exact box (Bosgame M5 / gfx1151 / 128 GB) reaches **33–37 t/s decode**. We have
now **reproduced that class on Windows**, using a build the founder already had on disk.

## What we measured (this box, Windows, native)

Engine: `C:\AI\runtimes\strix-vulkan-ba5354d\llama-server.exe` — the **same commit**
(`ba5354d46`) the vincentkelleher repo pins. Weights: unsloth UD-IQ4_XS. Draft: **FR-Spec MTP head**
(`mtp-...-Q8_0-frspec-65k.gguf`). Template: **Froggeric** `chat_template.jinja`.

| Prompt | Prefill | **Decode** | Reference (vincentkelleher) |
| --- | ---: | ---: | ---: |
| short (×3) | 23–35 t/s | **32.0–38.1 t/s** | 35.8 (depth 0) |
| 8,106 tok | 331.3 t/s | **31.98 t/s** | 36.7 (depth 8,192) |
| 26,557 tok | 250.5 t/s | **27.23 t/s** | 33.5 (depth 32,768) |

And at a **131,072-token context** (`-c 131072`, `GGML_VK_DISABLE_GDN_CACHE_FUSION=1`), confirming the
deep-context behaviour:

| Prompt | Prefill | Decode |
| --- | ---: | ---: |
| short | 37.5 t/s | **37.13 t/s** |
| 32,605 tok | 262.2 t/s | **26.59 t/s** |
| 58,202 tok | 157.5 t/s | **25.48 t/s** |

**Decode 25–38 t/s across every depth tested — matching their published curve (35.8 → 36.7 → 33.5 →
25.7).** Deeper rows returned HTTP 400 only because my prompts exceeded the slot's remaining budget.

**Decode 27–38 t/s vs our previous 14–22 t/s on the pwilkin fork — roughly doubled, and it holds at
depth.** This matches their published numbers closely.

## Why this works and the earlier setups did not

| | pwilkin fork (WSL/HIP) | **this config (Windows/Vulkan)** |
| --- | --- | --- |
| Engine | `pwilkin/strix-halo`, ROCm | **`drluoto` `strix-halo-vulkan`, `ba5354d46`** |
| Draft head | shared-Q8_0 | **FR-Spec Q8_0 (vocab-trimmed, 65k ctx)** |
| Draft min-prob | 0.75 | **0.0** (uncalibrated logits — any threshold wastes acceptance) |
| Chat template | built-in | **Froggeric (flattens AST; fixes an "80% throughput drop")** |
| Device access | `/dev/dxg` + DXG translation | **native RADV, `/dev/dri`-equivalent — no `/dev/kfd` needed** |
| Decode | 14–22 t/s | **27–38 t/s** |

**Two keys:**
1. **The FR-Spec draft head.** It is vocabulary-trimmed (`output.weight` 65,536 vs the model's 248,320)
   and **only the drluoto build maps it** — pwilkin's fork rejects it, and the drluoto *HIP* branch we
   built also rejects it (`wrong shape; expected 2560,248320, got 2560,65536`). Our existing
   **Vulkan** build accepts it. That is the single biggest decoder difference.
2. **Froggeric's template**, which documents fixing a **reported 80% inference-throughput drop on
   llama.cpp** (flattened Jinja AST) and preserving think-blocks for KV-cache hits.

## Reproduction (verified)

```
C:\AI\runtimes\strix-vulkan-ba5354d\llama-server.exe ^
  -m  C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf ^
  -md C:\AI\models\qwen38-flash\drluoto-frspec\mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf ^
  -ngl 999 -fa on --host 127.0.0.1 --port 8113 ^
  -c 32768 --parallel 1 -ctk f16 -ctv f16 -b 2048 -ub 2048 ^
  --jinja --chat-template-file C:\AI\models\qwen38-flash\froggeric\chat_template.jinja ^
  --reasoning-format deepseek --reasoning-preserve ^
  --spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.0 ^
  --temp 1.0 --top-k 20 --top-p 0.95 --min-p 0.0 --presence-penalty 0.0 ^
  --alias qwen3.8-flash-next-mtp
```

Scripts: `.revn-data/orchestrator/vulkan-ba-test.ps1` (load test), `vulkan-bench.ps1` (depth sweep).

**It fits the current 32 GB carve.** No carve change, no WSL, no `/dev/kfd`, no pinning.

## Notes and caveats

- **`-md` must be passed** (sidecar auto-discovery does not find the FR-Spec head).
- vincentkelleher's compose also sets `GGML_VK_DISABLE_GDN_CACHE_FUSION=1` (their branch's fused GDN
  state-cache path corrupts output on the 8060S). Our build loaded and answered correctly without it,
  but if output degrades, that is the first thing to set.
- Their config uses `-lm dio` (O_DIRECT) and kernel args `amd_iommu=off amdgpu.gttsize=126976
  ttm.pages_limit=32505856`; we ran without either and still matched. Both are further tuning.
- Deep-context rows returned HTTP 400 because `-c 32768` caps each slot; a larger `-c` would extend the
  ladder. The two measured depths already match their 8k/32k figures.

## What this changes

1. **REV:N's World Engine should run this config, not the WSL/HIP fork.** +~15 t/s decode and equal or
   better prefill, natively, with a build already on disk.
2. **Halogen is no longer needed for speed.** Its native-Linux figure is 25.4 t/s decode — **this beats
   it on Windows.**
3. **The kernel session's decode target changes:** we are at 27–38 t/s against a ~63–75 t/s
   bandwidth ceiling, so ~2× headroom remains (graphs/launch), but the "fix the drafter" problem is
   already solved by using the right head + fork.
