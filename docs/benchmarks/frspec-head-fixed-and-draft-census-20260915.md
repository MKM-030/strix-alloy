# FR-Spec head: root cause fixed, A/B measured, draft-head census (2026-09-15)

## Headline

**The FR-Spec 65k-vocab draft head now runs.** The fault was never in the HIP kernel — it was a
**6-byte alignment bug in my own converter** that corrupted the `d2t` map, whose garbage indices then
drove an out-of-bounds `ggml_set_rows` scatter and surfaced as `ROCm error: unspecified launch failure`.
One-line fix. The head loads, runs, and reaches **71% acceptance** — but in a clean A/B it is only
**~+2% decode at n-max 2 and −4% at n-max 1**, because the MTP operating point is not bandwidth-bound.

## 1. Root cause of the fault (this is the "a" that was owed)

The reader and the converter disagreed about where GGUF tensor data begins:

- **Reader** (`d2t-inspect.py` / `gguf_inventory.py`): `data_start = align_up(hdr_end, 32)`. Correct.
- **Converter** (`convert-frspec-head.py`): `f.seek(hdr_end)` — read the data section from the *unaligned*
  header end.

The original FR-Spec head's metadata ends at offset **10946906**, which is **6 bytes short of its
32-aligned data start (10946912)**. So every tensor the converter copied was shifted **6 bytes early**,
and the `d2t` int64 array read as garbage (`84551612818363, 281474976710656, …`, 0/65536 in range)
instead of `0,1,2,3,…` (65536/65536 in range).

Downstream, the fork takes the `d2t` branch (`d2t->ne[0] = 65536 ≠ 248320`) and scatters the compressed
logits into full-vocab shape with `ggml_set_rows`. Garbage indices → out-of-bounds writes → launch failure
at the first graph warmup (before any decode).

**Fix** (`convert-frspec-head.py`):
```python
f.seek((hdr_end + align - 1) // align * align)   # was: f.seek(hdr_end)
```

**Verification** (`verify-converted.py`, new): all **35/35** carried tensors are byte-identical to the
source, the synthesized `eh_proj = row-concat(fc_embd, fc_hidden)` is exact, and `d2t` is 65536/65536
in range. Loader confirmation:

```
0.45.202.835 I srv  llama_server: model loaded
0.54.833.179 I slot print_timing: id 0 | task 0 | graphs reused =         13
0.54.833.195 I slot print_timing: id 0 | task 0 | draft acceptance = 0.62963 (17 accepted / 27 generated), mean len = 2.21
```

No shape error, no fault, graphs reused.

## 2. Draft-head tensor census (the artifact the review asked for)

| tensor | shared Q8_0 head | FR-Spec 65k head |
| --- | ---: | ---: |
| `ffn_gate_exps` [2560,640,512] Q8_0 | 891.3 MB | 891.3 MB |
| `ffn_up_exps` [2560,640,512] Q8_0 | 891.3 MB | 891.3 MB |
| `ffn_down_exps` [640,2560,512] Q8_0 | 891.3 MB | 891.3 MB |
| `token_embd.weight` | **absent** (borrows trunk) | 675.4 MB [2560,248320] |
| `output.weight` (draft LM head) | **absent** (borrows trunk) | **178.3 MB** [2560,65536] |
| `attn_q` [2560,12288] | 33.4 MB | 33.4 MB |
| `attn_output` [6144,2560] | 16.7 MB | 16.7 MB |
| `nextn.eh_proj` [5120,2560] | 13.9 MB | 13.9 MB |
| `d2t` I64 [65536] | — | 0.5 MB |
| **total payload** | **2.776 GB** | **3.628 GB** |

Two structural facts fall out:

1. **The draft head is a full MoE layer** — its own 512-expert FFN is 2.67 GB of the payload. Per draft
   *step* only top-k of those are read (≈52 MB at k=10), so the experts are not the step cost.
2. **The shared head borrows the trunk's LM head.** The trunk `output.weight` is **Q6_K [2560,248320] =
   521.5 MB**. So every shared-head draft step reads a **521 MB** projection, while the FR-Spec head reads
   its own **178 MB** one — a 3× smaller draft head, exactly what FR-Spec exists for.

Implication for the cost model: the draft LM-head projection is the *dominant* per-draft-step weight read
(521 MB vs ≈52 MB of experts), so a smaller head *should* matter. §3 shows how much it actually does.

## 3. Clean A/B: shared head vs FR-Spec head (rep1, same trunk, serial)

Trunk = PROJFIX, ctx 32768, b/ub 2048, gen 256, native Windows clang 24. rep0 is page-cache-warming
contaminated (96 GB mmap off disk); **rep1 is the clean number.**

| head | n-max | prefill 1k | 8k | 16k | decode 1k | 8k | 16k | acc @1k |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| shared | 1 | 458 | 791 | 779 | 34.16 | 29.77 | 31.12 | 74.7% |
| **frspec** | 1 | 497 | 772 | 786 | 31.89 | 27.93 | 31.37 | 71.1% |
| shared | 2 | 653 | 798 | 784 | 35.45 | 29.99 | 32.80 | 62.1% |
| **frspec** | 2 | 625 | 799 | 782 | **35.78** | **30.49** | **33.88** | 59.9% |

Decode delta (frspec − shared):

| n-max | 1k | 8k | 16k |
| ---: | ---: | ---: | ---: |
| 1 | **−6.6%** | **−6.2%** | +0.8% |
| 2 | +0.9% | +1.6% | **+3.3%** |

**Reading:** the cheaper head is a real but small win **only at n-max 2**, and a net loss at n-max 1.
The mechanism is consistent with the forward-pass mix:

- Per speculative round, the ratio of draft forwards to target forwards is **k : 1** (n-max k).
  At k=1 the draft is 1/2 of forwards; at k=2 it is 2/3.
- The byte saving is `k·Δ` per round but spreads over `1+acceptance` tokens, so it scales roughly with
  `k/(1+acc)`: ≈0.57·Δ/token at n-max 1 vs ≈0.83·Δ/token at n-max 2 — the cheaper head should help ~1.5×
  more at n-max 2, which is what we see.
- At n-max 1 that small saving is outweighed by the **acceptance penalty** (71.1% vs 74.7%): the FR-Spec
  head can only propose tokens inside its 65,536-row frequency-ranked sub-vocabulary, so any target token
  outside it is a forced draft miss.

**Why the win is far below the byte model.** A pure-byte estimate (draft step 570→230 MB) predicts ~12%
at n-max 2; we measure ~2%. That confirms the earlier finding — at the MTP operating point we are at only
**24–29% of the bandwidth ceiling**, so MTP decode is **overhead/acceptance-bound, not bytes-bound.**

The draft/target cost ratio was fitted at **r ≈ 0.47**, but **direct phase timing superseded it**: draft is
only ~16% of the decode wall and target verify + host is ~84%, so the cheaper-draft route cannot reach
42 t/s alone. See `review-corrections-and-round-timing-20260915.md`.

## 4. What this changes

- **FR-Spec is not the decode lever.** It is now correctly wired and reproducible, but its round-trip is
  a wash. Keep it as a *cheaper-draft* building block for a higher-`k` regime, not as a standalone win.
- **Acceptance is the wall.** Shared head tops out at 74.7% (n-max 1) / 62.1% (n-max 2). Everything that
  multiplies decode (draft depth, cheaper head, lookups) is gated by it.
- **The draft head is trained for someone else's trunk.** That is the remaining headroom, and it is a
  training problem, not a kernel or config problem — see the companion plan
  `draft-head-training-plan-20260915.md`.

## 5. Reproduction

```powershell
# 1. rebuild the converted head (idempotent; verifies itself)
wsl -e bash -lc "cd /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work && \
  python3 convert-frspec-head.py \
    /mnt/c/AI/models/qwen38-flash/drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf \
    /mnt/c/AI/models/qwen38-flash/projfix/mtp-frspec-65k-pwhead.gguf"
wsl -e bash -lc "cd /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work && python3 verify-converted.py"

# 2. smoke test (loads + runs the head; expect graphs reused, ~0.63 acceptance)
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Projects\REV-N-ornith-eval-20260911\kernel-work\smoke-frspec.ps1

# 3. the A/B
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Projects\REV-N-ornith-eval-20260911\kernel-work\ab-heads.ps1 -Nmax "1,2"
```

Scripts: `convert-frspec-head.py`, `verify-converted.py`, `head-census.py`, `smoke-frspec.ps1`,
`ab-heads.ps1`, `ab-summary.py`. Raw: `results/ab-{shared,frspec}-n{1,2}.json`.
