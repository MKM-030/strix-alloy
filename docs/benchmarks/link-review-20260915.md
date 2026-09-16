# Link review (2026-09-15): ilintar GGUF, Windows abliterated GGUF, Soup

## 1. `ilintar/qwen3.8-flash-next-gguf-strix-halo` — **we are already running this**

File listing:

```
Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-0000{1..9}-of-00009.gguf   (9 shards, 93.16 GiB)
mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf                      (2.6 GiB draft head)
```

This **is the "PROJFIX" quant** — the same files we copied to
`C:\AI\models\qwen38-flash\projfix\` and benchmarked at **1,057 t/s prefill / 33.7 t/s decode**. It is
the author's own quant, the one his 1204 t/s figure was measured on, and it is the fastest we have found
(25% faster prefill and ~90% faster decode than unsloth UD-IQ4_XS *on this fork*, because the fork's MMB
kernels are written around resident IQ4_NL).

**Action: nothing to download — no faster quant exists in this repo.** The only difference from what we
run is the head: they ship the **shared** Q8_0 head, which is what we use.

## 2. `windowsxp811203/Qwen3.8-Flash-Next-Abliterated-GGUF` — will load, but not for speed

Files: `BF16`, `Q4_K_M`, `Q5_K_M`, `Q6_K`, `Q8_0` (abliterated = refusal directions removed).

**Would it load?** The **Q4_K_M** would be **refused by this fork**: `Q4_K` is a K-quant, and the fork's
GGUF reader accepts only the IQ4_NL / IQ4_XS / IQ3_S / Q4_0 families (Halogen's changelog documents the
same restriction, and it is why PROJFIX exists at all). `Q5_K_M` and `Q6_K` are likewise K-quants.
**Q8_0 would load** (Q8_0 is accepted), but at ~8.25 bpw it is roughly **2× the bytes per token** of
PROJFIX — expect decode around **15–18 t/s**, i.e. worse, not better.

**Does it make sense?** For *speed*, no. For *content*, it is a different model (abliterated, and built
from a different base — `base_model:windowsxp811203/Qwen3.8-Flash-Next-Abliterated`), so it is a
**product/model-selection question**, not a performance one, and per the REV:N rules that is a
`DECISION_REQUIRED` rather than something to pick here. Note the *name* "Windows" refers to the uploader,
not to a Windows-optimized build — there is no such thing in that repo.

**If the founder wants it:** the only loadable variant is **Q8_0**, at ~2× bytes/token, so it would be
slower than PROJFIX but still work. It would be worth having on disk as a fallback/alternative content
model, not as a speed source.

## 3. `MakazhanAlpamys/Soup` — a training tool, not an inference win; useful later, not now

It is a **fine-tuning / post-training CLI** (SFT, DPO, GRPO/PPO, KTO, ORPO, SimPO, IPO, BCO, distillation,
tool-calling) with PEFT (LoRA/DoRA/GaLore/…), QLoRA/4-bit, QAT, FP8/NVFP4, plus `train|infer|chat|serve|
ui|merge|export|eval`. Its headline feature is **layer streaming** (keep the frozen base out of VRAM,
feed one decoder layer at a time) — demonstrated as "Llama-3.1-8B + NF4 at 119.6 tok/s, 3.32 GB peak on a
4 GB RTX 3050", bit-exact against a resident run.

**Relevance to us, honestly:**

- **Not an inference accelerator.** It does not change how the GGUF runs; our 1,057/33.7 comes from the
  fork's kernels and the toolchain.
- **CUDA-centric.** It targets transformers/Unsloth/MLX; Unsloth is CUDA. On gfx1151 the practical route
  is stock `transformers` + ROCm, and "Python 3.10–3.12 only" matters (our venv is 3.14).
- **Where it could genuinely help, later:** (a) training a **better MTP draft head** — ours is unsloth's
  shared head at ~61% acceptance; a head fitted to *this quant and this domain* is the most promising
  route to higher acceptance, which is exactly what caps our decode; (b) **task-specific LoRA** for the
  World Engine (e.g. dialogue style) if quality work starts; (c) layer streaming would let us fine-tune a
  large model on this box at all.

**Decision: keep it on the list for the fine-tuning phase; do not pursue now.** The immediate
decode levers are the n-max sweep, the FR-Spec trimmed-vocab head, and (if they pan out) a custom-trained
draft head.
