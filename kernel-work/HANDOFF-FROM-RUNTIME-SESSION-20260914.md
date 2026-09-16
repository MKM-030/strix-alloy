# HANDOFF → Kernel/Fork/Quantization session — Windows-Vulkan/FR-Spec breakthrough (2026-09-14)

**From:** the Windows/Flash-Next runtime session.
**To:** the kernel-work session (`C:\Projects\REV-N-ornith-eval-20260911\kernel-work\`).
**Founder note:** "Das wirkt langsamer als der andere Fork." — I checked that before handing over; the
honest comparison is below. Short version: **decode is clearly faster, prefill is comparable, and the
one config that beats everything uses a build the founder already had on disk.**

---

## 1. The finding you need first: a working Windows/Vulkan stack at 25–38 t/s decode

**Engine:** `C:\AI\runtimes\strix-vulkan-ba5354d\llama-server.exe` — the **same commit `ba5354d46`** the
`vincentkelleher/qwen3.8-flash-next-halo` repo pins (drluoto `strix-halo-vulkan`, Vulkan/RADV).

**Weights:** unsloth UD-IQ4_XS (3 shards, the file you inventoried).
**Draft:** `mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf` (**FR-Spec**, 3.64 GiB).
**Template:** `froggeric/Qwen-Fixed-Chat-Templates/chat_template.jinja`.

**Measured on this box, Windows, native (no WSL, no `/dev/kfd`, current 32 GB carve):**

| Prompt | Prefill | Decode |
| --- | ---: | ---: |
| short (×3) | 23–37 t/s | **32.0–38.1 t/s** |
| 8,106 tok | 331.3 t/s | **31.98 t/s** |
| 26,557 tok | 250.5 t/s | **27.23 t/s** |
| 32,605 tok (@c=131072) | 262.2 t/s | **26.59 t/s** |
| 58,202 tok (@c=131072) | 157.5 t/s | **25.48 t/s** |

Reference (vincentkelleher, same box, Vulkan): 35.8 / 36.7 / 33.5 / 25.7 t/s → **we match it.**

## 2. Your numbers vs mine — the honest comparison (this is the "feels slower" question)

| | pwilkin `strix-halo` (HIP, your session) | **drluoto `strix-halo-vulkan` + FR-Spec** |
| --- | --- | --- |
| Decode | 13.8–22 t/s (`fn-ramp`/`fn-boundary`) | **25.5–38.1 t/s** |
| Prefill 8k | 308 t/s | 331 t/s |
| Prefill ~26k | 269 t/s @31.8k | 250 t/s @26.6k |
| Prefill ~58k | not measured | 157 t/s |

**Decode: clearly faster (roughly doubled). Prefill: comparable at 8k, modestly lower in my 26k/58k
rows — but those rows also had a bigger KV pool and `dio` loading, so this is not a clean A/B.**
Your `531 t/s @25291` row was from a run where I later proved the prompt was mis-sized (word counts,
not tokens) — do not treat 531 as the pwilkin baseline for that depth. **A clean, token-exact
prefill A/B at 8k/32k/64k/128k is exactly what this handoff asks you to produce.**

**Your weight-only ceiling calc is the target: ~28–34 ms/token ≈ 29–35 t/s.** We are already inside it
at short context and just under it at depth — so the remaining headroom is **at depth** and in **prefill**,
not in the base decode rate.

## 3. Three axes to work (the founder wants all three benchmarked)

The founder's instruction names three ways. My reading of what they are:

- **Way 1 — the new one (Vulkan/FR-Spec).** `strix-vulkan-ba5354d` + FR-Spec head + Froggeric template +
  `--spec-draft-p-min 0.0`, `-ngc`, etc. **This is the one currently at 25–38 t/s.**
- **Way 2 — your pwilkin `strix-halo` HIP build** (`/home/revn/strix-llama`, `f5daaa3c`), the one you
  have instrumented (expA, graph A/B, op microbench).
- **Way 3 — the drluoto **HIP** branch** `strix-halo-flash-next` @ `590ac45`. **I cloned and built it**
  at `/home/revn/drluoto-llama/build-hip/` (ROCm/gfx1151, builds clean). **Caveat found:** it **rejects
  the FR-Spec head** — `check_tensor_dims: tensor 'output.weight' has wrong shape; expected 2560,248320,
  got 2560,65536`. FR-Spec is a vocabulary-trimmed head (`t2d`/`d2t`) that **only the Vulkan branch
  maps**. So on way 3 you must use the **plain** `mtp-Qwen3.8-Flash-Next-Q8_0.gguf` (4.14 GB), or port
  the vocab-mapping. **This is a concrete, checkable lead.**

## 4. What I already established (don't redo)

1. **`--spec-draft-p-min 0.0` is correct.** The FR-Spec draft logits are uncalibrated; any threshold
   throws away acceptance for nothing (vincentkelleher's compose says this explicitly).
2. **`-md` must be passed** — sidecar auto-discovery does not search the `MTP/` subfolder.
3. **`--load-mode dio`** (O_DIRECT) is what the validated config uses.
4. **`GGML_VK_DISABLE_GDN_CACHE_FUSION=1`** — vincentkelleher's compose sets this because the branch's
   fused GDN state-cache path **corrupts output on the 8060S**. I ran with it at 131k and it was clean.
5. **Froggeric's template fixes a reported "80 % inference throughput drop on llama.cpp"** (flattened
   Jinja AST) and preserves think-blocks for KV-cache hits. It also defaults reasoning to **medium**
   instead of `xhigh`.
6. **The 0 %-acceptance rows we both saw were a prompt-cache artifact**, not a depth property — and my
   first two explanations (depth, first-request) were both wrong. Do not build on them.
7. **The `per_layer_token_embd` / PLE table is paged, not resident** — your inventory: 26.82 GiB,
   IQ4_NL, 320M rows. This is why RAM does not grow with context on the Vulkan path.

## 5. Concrete targets and ideas for the 10-hour run

**Prefill:**
- Clean token-exact A/B at **8k / 32k / 64k / 128k** for all three ways, same prompts, same box, one
  engine at a time. Use `/tokenize` to size prompts (my "~8k" bug is what made earlier tables wrong).
- Test **`-b/-ub` sweep** (the validated config uses 2048/2048; the Dimaginar post uses 2048/1024;
  pwilkin used 4096/4096). Prefill is usually batch-sensitive — this is cheap and likely real.
- **Graphs**: your expA (graphs on/off) is directly relevant — if graphs engage on the Vulkan path too,
  that is a shared win.

**Decode:**
- **MTP depth sweep** (`--spec-draft-n-max` 2/3/4/5) and **acceptance logging** at each depth.
- **Draft head variants**: FR-Spec-65k (vocab-trimmed), plain Q8_0, bf16, and **Q4_K_M** (smaller, faster
  to read). Available/known:
  - `C:\AI\models\qwen38-flash\drluoto-frspec\mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf` — present, 3.64 GB
  - `C:\AI\models\qwen38-flash\drluoto-frspec\mtp-Qwen3.8-Flash-Next-Q8_0.gguf` — present, 4.14 GB
  - `C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\MTP\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf` — present, 2.60 GB
  - `mtp-Qwen3.8-Flash-Next-Q4_K_M.gguf` — **⚠️ only a 15-byte LFS pointer on disk; download from
    `drluoto/Qwen3.8-Flash-Next-MTP-GGUF` on HF before using it.**
- **Train/produce your own MTP head** if the off-the-shelf ones plateau — the founder explicitly
  authorizes this. `drluoto/Qwen3.8-Flash-Next-MTP-GGUF` on HF is the reference recipe; the head is
  small (3–4 GB) so it is tractable.
- **The ~2× gap to the ceiling at depth** is where the real work is: check whether acceptance falls at
  depth, whether the PLE paging stalls, and whether graphs amortize launch overhead.

**Quantization:**
- The custom IQ4_NL "PROJFIX" set (`/home/revn/models/flash-next-strix`, 95.8 GiB) **does not fit** the
  32 GB carve (needs ~79 GiB resident + compute). Note it, don't sink time into it at this carve.
- Compare **UD-IQ4_XS vs UD-Q3_K_XL vs Q4_K_XL** on the Vulkan path for prefill/decode/quality tradeoffs.

## 6. Exact reproduction of the breakthrough

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

Scripts (mine): `.revn-data/orchestrator/vulkan-ba-test.ps1`, `vulkan-bench.ps1`, `vulkan-bigctx.ps1`.
My documents: `docs/benchmarks/flash-next-windows-breakthrough-38tps-20260914.md`,
`new-sources-synthesis-20260914.md`.

## 7. Guardrails (both sessions share one box)

- **One Flash-Next instance per box, ever** (your own runbook rule — it caught me twice).
- **WSL cap 88 GB max**, one heavy job at a time; a 90 GB cap + parallel jobs hard-restarted the PC.
- **Load models from `/mnt/c`, not WSL ext4** (ext4 ballooning starves Windows; Windows fell to 86 MB).
- Vulkan runs **natively on Windows** — it does not need WSL, so it can run **while WSL is doing other
  work**, but memory is shared; check `Available MBytes` before starting.
- Crash-dump cleanup is automated (`REVN-WSL-CrashDump-Cleanup`, daily 12:30).

---

## 8. THE PROMPT TO RUN (verbatim from the founder)

```
continues working on the prefill and tok/s no matter what you Need to do to get closer to the ceiling. work Not only on this proposed model / way but your two other alternative ways and Benchmark all of then incl tok/s and prefill on multiple Context Sizes. Continue Autononously the Next 10 hours until you have good results. Leverage Parameter Tuning, Research and Download MTPs or Sidecars or even create your own MTP to increase the tok/s. your goal is to have better results than the Official benchmarks we already know
```

Deliverable expected: for each of the three ways, a token-exact table of **prefill and decode at
multiple context sizes**, the MTP/parameter configuration that produced the best numbers, and a clear
statement of how each compares to the official published benchmarks (vincentkelleher 25.7–36.7 t/s;
Halogen 25.4 t/s serial; peonist prefill figures).
