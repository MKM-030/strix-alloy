# Occupied depth costs ~7–9%, then flattens (2026-09-15)

Codex Step 2b. With the capacity effect refuted (`capacity-penalty-refuted-20260915.md`), the remaining
question was whether processing a chunk against a long **occupied** history costs more than processing
the same chunk at depth 0.

## Method

`kernel-work/chunk-depth-bench.py` + `depth-chunk.ps1`. `-c 262144` (capacity fixed), then prime the KV
to depth D and append a **fixed 8192-token chunk**, measuring only that chunk's prefill. The script
verifies the measurement is the chunk alone: it asserts `processed_tokens == 8192` for every row
(`cache_n` confirms the prefix was actually reused). So this is not an average over a long prompt.

## Result

| occupied depth | chunk prefill t/s | cache reused |
| ---: | ---: | ---: |
| 0 | **642.8** | 0 |
| 32,768 | **586.4** | 32,768 |
| 131,072 | **598.4** | 131,072 |

## Reading

- **Depth 0 → 32k costs ~9%** (642.8 → 586.4). That is the real, if modest, "history" cost: attention
  and the QSA indexer genuinely do more work against 32k occupied keys than against a fresh chunk.
- **32k → 131k is flat** (586.4 → 598.4, within noise). Quadrupling the occupied history adds nothing
  further. This is consistent with the QSA indexer capping attention at `top_k = 2048` blocks — beyond
  the cap, more history does not increase per-token attention work, it only changes *which* keys.
- **Combined with Step 2a, the prefill shape is now fully attributed:**
  - capacity: **no effect** (1026–1033 t/s at 0.75–6 GiB KV)
  - occupied depth: **~7–9%, one-time, then flat**
  - the whole-prompt curve (862→984→907→856→809) is therefore mostly **amortisation/measurement**, not
    a growing per-token cost.

## Consequence

Prefill optimisation at depth is **not** a promising direction: the per-token cost against long
history is within ~9% of the fresh-chunk cost and saturating. This removes prefill-depth work from the
plan and leaves the decode efficiency (shapebench) as the single live target.

## Caveats

- Single rep per depth (the prime to 131k dominates the runtime). The 0→32k step (9%) is larger than
  would be expected from noise, but n=1; a repeat is cheap if this becomes load-bearing.
- The corpus prefix is shared across depths by design (that is what enables prefix reuse), so content
  is not independent across rows — yet the *appended chunk* differs, which is what is measured.

## Artifacts

`kernel-work/chunk-depth-bench.py`, `depth-chunk.ps1`; `results/dch-depth-chunk.{json,log}`.
