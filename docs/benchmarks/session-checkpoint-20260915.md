# Session checkpoint: decode levers, results and state (2026-09-15)

Machine: 96 GB carve, device pool 111.8 GiB, Windows 31.6 GB RAM, WSL shut down for all runs.

## Best measured results (native Windows, clang 24 / TheRock 10.2 build)

| configuration | prefill @1k | @8k | @16k | @32k | decode @1k | @8k | @16k | @32k |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **PROJFIX, ub 16384** (prefill) | 710 | 1021 | **1057** | **1035** | 30.1 | 28.9 | 29.2 | 28.8 |
| **PROJFIX, ub 2048 + MTP n-max 1** | 385 | 548 | 536 | — | **34.6** | 28.4 | 29.4 | — |
| **PROJFIX, ub 2048 + MTP n-max 2** | 290 | 563 | 513 | — | 34.1 | **28.5** | **30.3** | — |
| PROJFIX, ub 8192 | 705 | 1024 | 1019 | 998 | 29.8 | 28.4 | 29.2 | 28.9 |
| UD-IQ4_XS, ub 8192 (reference) | 695 | — | 1000 | — | 24.3 | — | 23.2 | — |

Binary: `C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe`.
Setup: `C:\AI\sdk\therock1151` on PATH; PROJFIX shards + shared MTP head in
`C:\AI\models\qwen38-flash\projfix\`; WSL shut down.

## Levers tested, with verdicts

| lever | verdict |
| --- | --- |
| clang 21 → **clang 24** (TheRock 10.2 Windows SDK) | **+60–71% prefill**, +1% decode. The single biggest win found. |
| UD-IQ4_XS → **PROJFIX** | **+25% prefill, +90% decode** (layout, not bits: PROJFIX is *bigger*) |
| `--spec-draft-n-max` **1–2** | **optimal**; 3→8 monotonically worse (acceptance 86%→32%) |
| n-gram lookup ahead of MTP (cascade) | **worse**: acceptance 62%→42%; the lookup wins first refusal with a worse draft |
| PR #28118 device-resident spec checkpoints | **0%**: branch already uses `rs_rollback` (`n_rs_seq>0`, QWEN4EXP supported) |
| `--spec-draft-p-min 0.75` | **0%**: identical acceptance |
| standalone vs shared MTP head | **0%**: both ~61% |
| `--lazy-mode on-direct` | **0%** on decode (it is a PLE-paging flag) |
| FR-Spec 65k-vocab head | **fixed and running**; net **≈ a wash** — +2% decode at n-max 2, −4% at n-max 1 (see below) |

## FR-Spec head: what was done and where it stands

The `ilintar` repo's head uses drluoto's tensor naming. I wrote two tools and made it load on the fork:

1. `convert-frspec-head.py` — mechanical GGUF rewrite, **no requantization**:
   - rename `nextn.hc_norm/hc_down/hc_up` → `nextn.hc_head_*` (identical shapes)
   - **concatenate** `nextn.fc_embd [2560,2560]` + `fc_hidden [2560,2560]` → `nextn.eh_proj [5120,2560]`
     (row-wise, block-exact for Q8_0's 32-element blocks)
   - keep `d2t` (I64, 65536) and `output.weight` (Q8_0, [2560,65536]) as the vocab trim
2. `apply-d2t-to-winnative.sh` — ports the 84-line `d2t`/`t2d` vocab-trim support into `win-native`
   (it existed only on the older `op-timing` branch).

Result: **the head loads and runs.** The fault was **not** in the kernel — it was a **6-byte alignment
bug in `convert-frspec-head.py`**: the converter read the data section from `hdr_end` while GGUF tensor
offsets are relative to `align_up(hdr_end, 32)` (the original header ends 6 bytes short of its aligned
data start). Every copied blob was shifted 6 bytes early, so `d2t` read as garbage and its huge indices
drove an out-of-bounds `ggml_set_rows` scatter → `unspecified launch failure` at graph warmup. One-line
fix; `verify-converted.py` now proves 35/35 tensors byte-identical and `d2t` 65536/65536 in range.

A clean A/B (same trunk, same ctx/b/ub, serial) shows the FR-Spec head is **≈ a wash**: decode
+0.9/+1.6/+3.3% at n-max 2 (1k/8k/16k) but −6.6/−6.2/+0.8% at n-max 1, because it loses ~4 points of
acceptance (71% vs 75%). The cheaper draft head is real but the MTP point is overhead/acceptance-bound,
not bytes-bound. Full write-up: `frspec-head-fixed-and-draft-census-20260915.md`.

## Where the decode ceiling actually is

Bandwidth arithmetic (active weight bytes for PROJFIX at k=10 = 4.61 GB):
- serial decode 28.8 t/s → 133 GB/s = **55–66%** of the 200–240 GB/s ceiling → serial is bandwidth-bound
  (ceiling 43–52 t/s).
- MTP decode 32.9 t/s → 58 GB/s = **24–29%** → the MTP point is **overhead/acceptance-bound**, not bytes.
- KV read with QSA ≈ 50 MB/token = **~1%** of weight traffic, constant with depth.

So the remaining decode levers are (a) draft quality/acceptance, (b) whatever overhead the verify round
carries, (c) the FR-Spec cheaper-draft path if the fault is fixed. Halogen sits at 42–45 t/s with two
drafters on their own trunk.

## Source state

- Fork `win-native`: upstream `d67d5883` + `_WIN32` `prefetch()` stub + PR #28118 (6 ON_DEVICE sites)
  + the d2t/t2d vocab trim (19 refs). All committed except the last two, which are staged in the working
  tree and synced into `C:\AI\build\strix-llama-win` by `build-win-therock.ps1` (which now syncs
  `qwen4exp.cpp` as well — a bug that silently discarded the d2t patch for two builds).
- No upstream updates available: fork at `d67d5883`, drluoto at `ba5354d46`, TheRock newest Windows
  artifact is `gfx1151-10.2.0a20260915` (what we use).

## Links reviewed

- `ilintar/qwen3.8-flash-next-gguf-strix-halo` = **the PROJFIX quant we already run** (nothing to download).
- `windowsxp811203/...-Abliterated-GGUF` — only **Q8_0** loads on this fork (K-quants are refused); at 8.25 bpw
  it is ~2× bytes/token, so slower. A content-selection question for the project owner, not a speed source.
- `MakazhanAlpamys/Soup` — a fine-tuning CLI (SFT/DPO/GRPO/LoRA/QLoRA, layer streaming). **Not an inference
  accelerator.** Its real relevance: training a **better MTP draft head** (our acceptance is the decode
  limiter), which is the most promising remaining decode lever.
