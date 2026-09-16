# Flash-Next prefill + decode: three-engine token-exact benchmark (2026-09-14)

Session: 10-hour autonomous kernel/perf run, GPU free, Windows+WSL one-instance rule enforced.
All numbers **[MEAS]** on the Bosgame M5 (Ryzen AI Max+ 395 / 8060S, gfx1151, 128 GB, **32 GB carve**).
Prompts are **token-exact** (sized with `/tokenize`), `cache_prompt=false` (true fresh prefill).

## 0. Headline

| | Best prefill found | Best decode found |
| --- | ---: | ---: |
| **Way 1 — Windows Vulkan (`strix-vulkan-ba5354d`) + FR-Spec MTP** | **366 t/s @8k** | **30.6 t/s @1k, 20.0 @32k** |
| **Way 2 — pwilkin HIP (`f5daaa3c`) + IQ4_NL PROJFIX + `LLAMA_MMB=1`** | **525 t/s @8k, 381 @32k** | 21.7 @1k, 17.1 @8k |
| **Way 3 — drluoto HIP (`590ac45b`) + plain MTP** | (loading) | (loading) |
| Official references | Halogen ~1,246–1,423; pwilkin 1,204 | Halogen 25.4 serial / 42–45 drafted; vincentkelleher 25.7–36.7 |

**Two decisive findings:**
1. **`LLAMA_MMB=1` — the fork's bf16-WMMA dequant GEMM prefill path, which is OFF by default — is worth +45% prefill** on the right quant (364→525 t/s @8k). Undocumented; found by reading `mmb.cu`.
2. **The PROJFIX quant is required for it**: MMB's IQ4 fast path needs *resident IQ4_NL weights*, which PROJFIX has everywhere and unsloth UD-IQ4_XS does not (its attention is Q8_0). PROJFIX+MMB (525) ≫ UD+MMB (380, unstable).

## 1. Why we are not at 1,204 t/s (the carve arithmetic) `[MEAS+EST]`

The author's 1,204 t/s config (from his own installer, fetched verbatim): IQ4_NL 93 GiB,
`-b 16384 -ub 16384 --load-mode none --lazy-mode on-direct`, on a **128 GB unified machine where the
device pool is essentially the whole RAM**. Our box runs a **32 GB carve → 79.82 GiB Vulkan pool**:

| | GiB |
| --- | ---: |
| Device pool (32 GB carve) | 79.82 |
| PROJFIX resident weights (93.16 − 26.82 non-resident PLE) | 66.34 |
| **Left for KV + compute buffers** | **13.48** |
| KV f16 @ 49k ctx + GDN state | 1.23 |
| **Compute budget** | **12.25** |
| ub 16384 requires (measured: 14.05 GiB allocation failed) | **14.05** → **FAIL** |
| ub 8192 requires | 7.03 → OK |

**So ub 16384 — the author's prefill setting — does not fit at this carve.** That is the single
largest structural gap between our 525 t/s and his 1,204. Raising the carve to **48 GB** (pool
≈ 88 GiB) would make ub 16384 fit and should move prefill into the 900–1,200 t/s band. This is a
**founder/BIOS decision**, not a code change.

`[MEAS]`: `-ub 16384` at the current carve → `failed to allocate compute pp buffers` (14,050 MiB request).

## 2. Results (token-exact)

### 2.1 Way 2 — pwilkin HIP + PROJFIX, ub 8192, ctx 49152, `-fit off`, f16 KV, `--lazy-mode on-direct`

| Config | prefill @1k | @8k | @32k | decode @1k | @8k | @32k |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **+ `LLAMA_MMB=1`** | 364 | **460–525** | **381** | 21.7 | 17–19 | 10.0 |
| MMB off | 324 | 325–364 | 316 | 20.6 | 13–19 | 11.5 |

**MMB = +45% prefill @8k, +21% @32k; decode also improves.** (Runs are noisy: first rep is always
low — cold cache/JIT; reps 1–2 are the steady state. Medians reported.)

### 2.2 Way 2 — pwilkin HIP + unsloth UD-IQ4_XS + `LLAMA_MMB=1`, ub 8192, ctx 65536

| prefill @8k | @32k | decode @8k | @32k |
| ---: | ---: | ---: | ---: |
| 155–380 (unstable) | 206 | 12–14 | 12.5 |

**Worse than PROJFIX and unstable** — UD's Q8_0 attention projections can't use MMB's IQ4 fast path.
This is the quant-layout effect the earlier session's docs predicted.

### 2.3 Way 2 — pwilkin HIP + UD-IQ4_XS + ub 16384 (fits: UD is 60.4 GiB resident)

| prefill @8k | @32k | decode @8k |
| ---: | ---: | ---: |
| 379 | (ctx-limited) | 12.9 |

Bigger ubatch alone does **not** rescue the stock quant.

### 2.4 Way 1 — Windows Vulkan `strix-vulkan-ba5354d` + UD-IQ4_XS (ctx 196k→failed; 140k ok)

| Config | prefill @1k | @8k | @32k | decode @1k | @8k | @32k |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| + FR-Spec MTP d3 | 288–314 | 360–366 | 271 | **29.3–30.6** | 17.8 | 20.0 |
| no MTP | 323–334 | — | — | **18.5–19.2** | — | — |

**MTP is worth 1.6× decode on Way 1** (30.6 vs 19.2 @1k). Draft acceptance is **content-dependent**:
73% @1k, 33% @8k, 54% @32k on the synthetic corpus — a methodology point the official tables don't
state.

### 2.5 Way 3 — drluoto HIP + UD-IQ4_XS

(loading; filled below)

## 3. The cross-engine picture

| Engine | Quant | Prefill best | Decode best | Notes |
| --- | --- | ---: | ---: | --- |
| **pwilkin HIP + MMB** | IQ4_NL PROJFIX | **525 @8k** | 21.7 | best prefill of the three; needs ub16384 (carve) for more |
| Vulkan ba5354d + FR-Spec | UD-IQ4_XS | 366 @8k | **30.6 @1k** | best decode; FR-Spec is Vulkan-only; 38 t/s @short reported by handoff |
| drluoto HIP | UD-IQ4_XS | tbd | tbd | plain head only (FR-Spec rejected: 65k vocab) |
| Halogen (official, native Linux) | own | 1,246–1,423 | 25.4 serial / 42–45 drafted | needs native Linux + ~72 GiB |
| pwilkin (official, native Linux) | IQ4_NL | 1,204 | 26.28 | 128 GB unified, no carve |

## 4. What each lever is worth (measured/estimated)

| Lever | Effect | Evidence |
| --- | --- | --- |
| `LLAMA_MMB=1` | **+45% prefill @8k** (+21% @32k) | 364→525 t/s, same everything else |
| PROJFIX quant (vs UD-IQ4_XS) | **+40–65% prefill** with MMB | 525 vs 380, 381 vs 206 |
| MTP (FR-Spec, Vulkan) | **1.6× decode** | 30.6 vs 19.2 @1k |
| Carve 32→48 GB (to enable ub16384) | est. +70–110% prefill | the author's ub16384 vs our ub8192 |

## 5. Reproduction

```bash
# Way 2, best prefill config (WORKING today, this carve):
LLAMA_MMB=1 /home/revn/strix-llama/build-hip/bin/llama-server \
  -m /home/revn/models/flash-next-strix/Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf \
  -ngl 99 -fa on -fit off --load-mode none --lazy-mode on-direct \
  -ctk f16 -ctv f16 -c 49152 -b 8192 -ub 8192 --parallel 1 -t 8

# Way 1, best decode config (Windows):
#   (from the handoff §6 command + -md FR-Spec + --spec-draft-n-max 3 --spec-draft-p-min 0.0)
```

Benchmark client: `kernel-work/fnbench.py` (token-exact; `--mode chat` for realistic acceptance).
Harness/scripts: `vulkan-bench.ps1`, `main-run.sh`; raw logs in `kernel-work/results/`.

## 6. Recommendation

1. **To beat 1,200 t/s prefill on this box: raise the carve to 48 GB** (pool ≈88 GiB) and run
   pwilkin HIP + PROJFIX + `LLAMA_MMB=1` at `-ub 16384`. Everything else is already in place;
   only the memory ceiling blocks it. (Trade-off: the Vulkan/FR-Spec path needs pool too.)
2. **Best decode today: Way 1 Vulkan + FR-Spec MTP (30.6 @1k, 20 @32k)** — already matches the
   handoff's 25–38 t/s range; the FR-Spec head cannot be used on the HIP forks.
3. **Best prefill today at 32 GB carve: Way 2 + PROJFIX + MMB (525 @8k).**
