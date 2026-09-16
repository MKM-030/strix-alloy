# Halogen Flash-Next on this machine: fit analysis (2026-09-12)

Founder question: given the 32 GB RAM / 96 GB GPU-carve-out split, would the real Flash-Next weights
(~118 GiB) even fit? If yes, load them; if no, find another way (IQ4 → `.hgn` conversion, or some way
to run the w4b file under WSL/Windows).

**Answer: No — two independent blockers, and the fix for the RAM one is the opposite of intuition.**
The download was deliberately **not** started.

> **ADDENDUM, 2026-09-12 evening (this section supersedes the two blockers below).** The founder
> resolved the carve-out first: the BIOS/UMA setting is now at **minimum (512 MiB)** — Windows sees
> **127.1 GB** and the disk has **723 GB free**, so *both* blockers in §2/§3 are gone. The founder
> then authorized the download ("im Zweifel gehe ich auch auf 32 gb carve out"), so it is running:
> base 124.07 GB + overlay + overlay-speed + vision (all four LFS-sha256-verified sizes known), via
> `aria2c` (HF throttles this account to a flat ~7.8 MiB/s regardless of connection count). WSL is
> raised to `memory=110GB`. Prerequisites were verified end-to-end before the base finished:
> `flash_serve` links cleanly under the Ciru ROCm-10 `LD_LIBRARY_PATH`; the tokenizer loads and
> returns the same ids as the 27B `halogen` test; the OpenAI front-end `tools/serve_api.py` (extracted
> from the 0.6.1 image) runs. **The correct posture for this engine is the minimum carve-out, exactly
> as this analysis predicted.** Verified harnesses: `.revn-data/orchestrator/run-flash-next.sh`
> (engine 8730 + front-end 8731, `HALOGEN_FLASH_PIN_TRUNK=0`, checkpoint staged on WSL ext4 so the
> 47.7 GiB n-gram table is not paged over 9p) and `flash-next-watch-and-run.ps1` (sha256 + restart +
> auto-run). What remains is simply the ~4 h transfer.

## 1. The model's actual requirements (from the model card + the engine's own strings)

| Requirement | Value |
| --- | --- |
| Checkpoint | `qwen38-flash-next-w4b.hgn` — **115.55 GiB** (1198 tensors) |
| Quality sidecar | `…w4b.overlay.hgn` — **2.4 GiB** (do not skip: 5–9% perplexity) |
| Total download | **~118 GiB ≈ 127 GB** (decimal) |
| **Resident need** | **~68 GiB** ("the model needs ~68 GiB resident") |
| n-gram table | **47.7 GiB**, FP8, **paged through the host page cache on every request** |
| Host the card assumes | "holds most of a 128 GB host" |

## 2. Blocker A — RAM: 31.6 GB host vs 68 GiB resident

This host, with the current split: **Windows sees 31.6 GB**; the rest (~96 GB) is firmware-carved for
the iGPU. `flash_serve` itself warns about exactly this configuration:

> "WARNING … GiB of RAM is carved out for the iGPU in firmware, and this model reads a … GiB lookup
> table through the host file cache on every request. A carve-out that large competes directly with
> that cache, and the symptom is a server that starts, answers short prompts, and then crawls on a
> long one with the disk busy and a process in uninterruptible sleep."

> "You are already paying for it even if nothing has thrashed yet: the KV pool sizes itself from
> MemTotal, which the carve-out has made smaller …"

The weights it needs resident (68 GiB) **alone exceed the 31.6 GB the host can see.** No engine knob
can create 68 GiB out of 31.6 GB.

### The counterintuitive fix (the engine states it outright)

> "This engine does not need dedicated VRAM: it drives the GPU through **GTT** and allocates from the
> same unified memory either way. **Set the BIOS UMA or dedicated-graphics-memory option back to Auto
> or its minimum, which reports about 512 MiB here, and the carved RAM returns to the host.**"

So for **this** engine the correct posture is the opposite of the 32/96 we use for Ciru:

| Setting | Host RAM | Result for Flash-Next |
| --- | --- | --- |
| 32 / 96 (current) | 31.6 GB | **cannot run** (68 GiB needed) |
| Auto / min (~512 MiB carve-out) | ~124 GB | **feasible** — weights + page cache fit; GPU reads via GTT/DXG |

Then set the WSL VM accordingly (`.wslconfig` `memory=110GB+`) and run with `HALOGEN_FLASH_PIN_TRUNK`
per taste. This is a **real tradeoff the founder must decide**, because changing the carve-out affects
the other engines (Ciru C1 currently allocates ~88 GB and worked *with* the 96 GB carve-out).

Engine knobs that help *after* the carve-out is lowered (all confirmed present in the binary):
`HALOGEN_FLASH_PIN_TRUNK=0` (run unpinned — the engine calls this "a last resort, several times the
decode speed"), `HALOGEN_HOST_RESERVE_GIB`, `HALOGEN_KV_POOL_POSITIONS` / `HALOGEN_KV_POOL_FIT`,
`HALOGEN_UMA_CARVEOUT_GIB`, `HALOGEN_QSA_STRIP_MB`.

## 3. Blocker B — disk: 108 GB free vs ~127 GB needed

```
C:  free 108 GB / 1907 GB     ← the only filesystem
WSL /dev/sdd 1007 GB, 867 GB free   ← but this is a VHDX that lives on C:
```

~118 GiB ≈ **127 GB** does not fit in 108 GB. And the WSL "free" is inside a sparse VHDX on the same
C:, so downloading there still consumes C:. **Freeing ~25–30 GB or adding a drive is a prerequisite.**

## 4. Can an IQ4 quant be converted into `.hgn`? No.

- The only converter is `chlorine-server`'s `hgn-convert.py`, and it supports **bf16 / f32 / f16 /
  i32 / i64**, plus a **simple** `fp8r` and **simple** `q4c`. It does **not** emit `i4l`, does not
  reproduce the NVFP4-derived `q4c` layout, and knows nothing of the Flash-Next MoE + n-gram
  structure. It is a writer for chlorine's own verification, not a path to Peonist quality.
- The engine only decodes **its own** layouts. llama.cpp's IQ4 is a different block encoding
  (codebook + per-16 scales) with no loader in `flash_serve`.
- Even with a perfect converter it would not be faster: **speed comes from the engine's kernels**
  (and its MoE/ngram/MTP handling), not from the quant level. Our own data: Flash-Next UD-IQ4_XS on
  llama.cpp ≈ 303 tok/s prefill @32K, vs halogen's published 1,287 tok/s @64K.

## 5. What was checked to be sure

- Model card + file list via HF API and the rendered page (115.55 GiB + 2.4 GiB; "~68 GiB resident").
- `flash_serve` binary extracted from `ghcr.io/peonist-ai/halogen-flash-server:0.6.1`; it links the
  same ROCm 10 libs as the 27B engine, and **has a built-in `Pin::None` mode** (`checkpoint: mapped …
  NOT pinned (Pin::None)`), so the `hipshim` used for the 27B would not even be needed.
- All 168 `HALOGEN_*` env vars enumerated from the binary.
- Host RAM split and disk free space measured directly.

## 6. Recommendation (in order)

1. **Decide the carve-out question first.** For Flash-Next, lower the iGPU carve-out to Auto/minimum
   (≈512 MiB) → host gets ~124 GB → WSL `memory≈110GB` → the engine runs. That is the engine's own
   documented configuration. If Ciru must stay on 96/… , these two engines want opposite splits and
   cannot be resident at the same time.
2. **Free ~30 GB on C:** (or add a drive) before any download.
3. **Then** download base + overlay (~118 GiB) and run:
   `flash_serve --ck qwen38-flash-next-w4b.hgn --port 8731` (overlay auto-loads beside it).
4. **Do not** attempt an IQ4 → `.hgn` conversion: not supported, and not the source of halogen's speed.
