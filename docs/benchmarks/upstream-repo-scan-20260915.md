# Upstream repo scan — actionable deltas since 2026-09-11 (2026-09-15)

Full sweep of every source the founder named, checked live (`gh` API + HF API) against a
2026-09-11T00:00Z cutoff. Only *actionable* deltas that touch gfx1151 kernels, quant formats, decode,
prefill, or the MTP head. Sources with nothing new are listed at the end so the omission is honest.

## The three that matter most

### 1. `llama.cpp` PR #28941 — Vulkan only, and **CLOSED as a dead end** (corrected below)

**CORRECTION (verified 2026-09-15):** the first pass of this scan listed #28941 as "open". It is
**closed and unmerged**, and the author closed it *because it does not work*: reviewer `jeffbolznv`
noted `SHMEM_STRIDE_PAD=6` is not 16-byte aligned (invalid per the cooperative-matrix extension), and
the author then tested `{0,4,8,12}` and **"did not find any gains… closing this PR as this looks like a
dead end."** So there is **no Vulkan prefill win to cherry-pick**. The lesson stands: verify a PR's state
before building on its headline number.

More importantly, **it was Vulkan anyway** — and our gap is not Vulkan. Our fast path is native-Windows
**HIP** (1057 t/s vs ilintar's 1204), so a Vulkan-only change could not have closed it regardless. That
makes ilintar's `40a9f4d0` (HIP) the real lever, which is what we rebased onto (§2).

### 2. `pwilkin/llama.cpp` `strix-halo` branch moved to `40a9f4d01` (2026-09-15) — newer than our fork base

Our fork `win-native` is based on **`d67d5883`**. ilintar's branch has **five commits on top of it**:

| commit | date | what |
| --- | --- | --- |
| `40a9f4d01` | 09-15 | extend MMB quants + **fuse Flash-Next F32 PLE** |
| `d67d58836` | 09-14 | **sparse QSA decode + incremental indexer state** (this is our base) |
| `0f2950198` | 09-13 | skip unused HIP decode indexer work |
| `ac1ebb4e0` | 09-13 | **compile in the tuned defaults, drop 53 `LLAMA_*` env gates** |
| `40c0b9c38` | 09-13 | QSA maskless-path determinism fix (10/10 → 1/10 distinct greedy outputs) |

`d67d58836`'s own numbers: sparse decode 25.85→28.82 t/s at depth 40k, 31.17→35.57 t/s on a 40 680-token
first request, **32.69→39.10 t/s on repeated requests** — with **1,986,560 bit-identical logits** as the
correctness gate. `ac1ebb4e0` re-measured **pp16384 = 1223 t/s, tg32 = 30.05 t/s with no env vars at all**.

**Why:** our whole gate apparatus (`gates-test.sh`, 35 env vars, `LLAMA_MMB_HC16=0`) is these commits'
*predecessor*. Rebasing onto `40a9f4d01` would (a) remove the fragile env block, (b) fuse the PLE cast we
pay in decode, (c) carry a determinism fix for long sessions. This is a rebase + rebuild, not new kernel
work. **Action: rebase `win-native` onto `40a9f4d01`, re-verify HC16 behavior (it may be fixed upstream),
re-run the ladder.**

### 3. `llama.cpp` PR #28243 — the upstream MTP speedup (open, still unmerged)

`models: Qwen3.8-Flash-Next MTP` (danielhanchen), advertised **"1.3–2× faster MTP"**, shared MTP modules
that reuse `embed_tokens` (saves disk/VRAM). The matching sidecar already exists on HF
(ilintar `mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf` — **the head we already run**).

**Why:** this is the upstream version of the MTP path we hand-rolled. When it lands (or if we cherry-pick),
it is the intended, maintained implementation of our decode lever. **Action: track it; do not duplicate.**

## New engines with gfx1151 numbers to beat

### EngramHalo (`Aristo94/EngramHalo.cpp`, `strix-halo-qwen4exp`) — 2026-09-12

- MTP draft head + mtp-only sidecar; QSA decode gathers top-k KV rows instead of dense masking; chunked
  GDN prefill kernel; skip fully-masked FA vec warp slices + head-256 RDNA tuning; lazy row prefetch +
  IQ4_NL `get_rows`; mmap page-cache drop behind uploaded tensors.
- Advertised (builds `Herotek-AI/EngramHalo-BUILDER` b1005–b1008, gfx1151): **QSA sparse gather 91→192 t/s
  at 131K (2× deep prefill); MTP 24.4→39.3 t/s**; SSD-backed 27 GiB engram table, ~1 GiB RAM at 262K.
- **Why:** the **39.3 t/s MTP** claim overlaps exactly our decode number, and "gather top-k KV rows instead
  of dense masking" is our own QSA decode question. **Action: read their QSA-decode kernel; it is a concrete
  cross-check on our sparse path.**

### ROCmFPX-BUILDER b1045 (2026-09-14) — gfx1151 ROCmFP4

- `b1045`: kingjones30/ROCmFPX @ `dfeacaf`, incl. `qwen4exp`. `b1044`/`b1042` ("q38rocm"):
  **ROCmFP4_FAST 4.26 bpw: 30.56–36.04 tok/s with MTP**; FP8 18.96 tok/s; **Asymmetric TurboQuant KV cuts
  262K ctx from 61.4 GB → 20.08 GB**.
- New quant: **`agentionai/Qwen3.8-Flash-Next-ROCmFP4-FAST-imatrix-v2`** + a `PLE16` variant (2026-09-13).
- **Why:** 30.56–36.04 t/s with MTP is our band, and the KV halving is a real memory lever at depth.
  **Action: note the KV-compression result; the FP4 quant itself needs an FP4 kernel we have not built.**

### Ciru (`ciru-ai/ornith-ciru-halo-agent`) — vLLM-side Strix Halo

- Runtime **1.0.2 (09-15)** native tool schemas + image support; **1.0.1 (09-14)** convolution +
  accepted-state correctness fixes; **1.0.0 (09-13)** hybrid graph replay + Qwen tool contracts.
- `ciru-ai/Qwen3.8-Flash-CIRU-STRIX-IU4`: IO32 runtime **v4.1 (09-14)**.
- **Why:** "accepted-state correctness fix" and "hybrid graph replay" are the same mechanisms we debug on
  the HIP side. **Action: read their accepted-state fix — it may be a known-bug reference for our MTP.**

### Halogen `0.10.2` (2026-09-15) — now on 0.9/0.10

- `0.10.0` (09-15) **on-disk prompt cache** `HALOGEN_CACHE_DIR` + decode-table correction.
- `0.9.1` (09-15) `HALOGEN_INDEXER_BUDGET` — sparse-attention budget, raisable at startup.
- `0.9.0` (09-14) composable context. `0.6.0` (09-12) **prompt lookup beside the MTP head** + draft-head
  projections at 8 bits in the sidecar. `0.6.3` the 47.7 GiB n-gram table read 64 rows at a time.
- **README: native Linux only — WSL2 is not a supported host; requires kernel 7.0+.**
- **Why:** (a) confirms PLD/n-gram is shipped and tuned beside MTP, matching what the author said on Reddit;
  (b) **WSL2 non-support** closes the door on running Halogen under our WSL path — it is a native-Linux or
  bare-metal proposition. **Action: treat Halogen as a native comparison target only.**

## Correctness hazards and closed-but-relevant items

- **`llama.cpp` PR #25863 closed UNMERGED** — "avoid direct ROCm_Host compute on HIP integrated GPUs".
  The APU host-buffer corruption regression it fixed is **still open upstream**; pwilkin carries the fix,
  mainline does not. **Why: a live gfx1151 correctness hazard that our fork's base may still have.**
- **Open gfx1151 bugs:** #24437 (ROCWMMA_FATTN prefill regression up to −41% at long ctx on gfx1151),
  #28211 (gfx1151 wrong logits when prompt > n_ubatch), #28933 (qwen4exp host RSS+swap growth on 128 GB
  UMA), #28734 (qwen4exp CUDA decode slows linearly with ctx). **Why: #28211 and #28933 are directly about
  our model/box.**

## Confirmed-unchanged (no action)

| source | status |
| --- | --- |
| `drluoto/llama.cpp` (branches `strix-halo-vulkan`, `strix-halo-flash-next`) | last push 2026-09-06; **the names are branches, not repos** |
| `drluoto/Qwen3.8-Flash-Next-MTP-GGUF` (HF) | last modified 2026-09-06 |
| `unsloth/Qwen3.8-Flash-Next-GGUF` (UD-IQ4_XS) | last modified 2026-09-02 — **the head and quant we run are unchanged** |
| `windowsxp811203` abliterated GGUF | last modified 2026-08-27 |
| `Heretek-AI/chlorine-server` | last commit 2026-09-10, nothing since cutoff |
| `MakazhanAlpamys/Soup` | active (v0.75, 09-14/15) but **nothing touching kernels/quant/decode** |
| `pwilkin/rocm-systems` `ilintar-experiments` | head re-committed 2026-09-12 but no new functional content after 09-05 |
| AMD TheRock | newest Windows tarball **`10.2.0a20260915`**, toolchain **clang 24.0.0git** — confirms our build; no compiler bump |
| `ROCmFPX/ROCmFPX` | exists but stale since 2026-09-06 (active work moved to `Heretek-AI/ROCmFPX-BUILDER`) |

**404 / absent:** `drluoto/strix-halo`, `drluoto/strix-halo-vulkan` (branches, not repos); `pwilkin/llm.c`
(does not exist); `MorezMartin/engramhalo-rocm10` (HF 401, gated).
