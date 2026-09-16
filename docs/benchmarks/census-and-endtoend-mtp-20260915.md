# End-to-end MTP economics + tensor census (2026-09-15)

Two results that correct my earlier framing. Both were prompted by the frontier-model review.

## 1. The tensor census: 4.25 GB, not 4.61 and not 3.75

Measured from the **actual PROJFIX GGUF** (`pf-census.py`), counting dense matrices fully, routed
experts at k/512, and embedding tables by rows gathered:

| family | GiB | GB | note |
| --- | ---: | ---: | --- |
| dense / other (full read every token) | 2.726 | 2.927 | 1078 tensors: attention, GDN, hyper-connections, **output head Q6_K 497 MiB**, routers, PLE projections |
| routed experts (k=10 of 512) | 1.236 | **1.327** | exactly the review's figure |
| PLE n-gram table (rows gathered) | ~0 | ~0 | ~1440 B/token logical; paged from disk |
| input embedding (1 row) | ~0 | ~0 | gather |
| **TOTAL active weight payload per token** | **3.962** | **4.254** | |

So my 4.61 GB was ~8% high (it double-counted some small tensors) and the review's 3.75 GB was 12% low —
the difference is ours: **our output head is Q6_K (497 MiB), not IQ4_NL** (the 65k-trimmed amount they
assumed), plus the hyper-connection and PLE projections that were not itemised.

**Revised serial ceiling**: 200 GB/s → **47.0 t/s**, 220 → 51.7, 240 → 56.4, 256 → 60.2.
At our measured 28.8 t/s we are at **133 GB/s = 52–61% of the practical ceiling**, i.e. serial decode
does have headroom, but the ceiling is ~47–56 t/s, not 43–52.

## 2. MTP now works with the large prefill batch — and the ub-8192 failure was a clang-21 artifact

The most consequential thing the review said: our MTP config *lost* on full requests, because attaching
`-md` forced `ub 16384 → 2048`, paying ~11 s of prefill to save ~1 s of generation.

**Tested on the clang 24 build: the conflict is gone.** MTP loads and runs at `ub 16384`.

| depth | prefill | decode |
| ---: | ---: | ---: |
| 1024 | 466 | 34.6 |
| 16384 | 974 | 30.3 |
| 32768 | 964 | 31.1 |

Full-request latency, 32,768 in + 256 out:

| config | prefill | decode | total |
| --- | ---: | ---: | ---: |
| no draft, ub 16384 | 1035 | 28.8 | **40.55 s** |
| MTP + ub 2048 (old) | 767 | 32.5 | 50.60 s |
| **MTP + ub 16384 (new)** | 964 | 31.1 | **42.22 s** |

So MTP went from **+10 s worse** to **+1.7 s worse** on a short output; the crossover dropped from
**2,798 to 908 output tokens**. It is no longer a misconfiguration — it is now simply a
workload-dependent trade (MTP wins on long generations, loses on short ones).

Two notes worth keeping:
- `ub 2048` is a **capacity setting, not the decode row count**; the review is right that I conflated them.
- The MTP advantage *shrinks* as ubatch grows (34.6 t/s at ub 2048 vs 31.1 at ub 16384), because a bigger
  verify batch does more work per round. The decode-optimal ub and the prefill-optimal ub genuinely differ
  — but they are no longer *incompatible*, which is what mattered.

## 3. What this changes

- The "two configurations, pick one" problem is resolved: **one configuration runs both well**.
- The decode ceiling is ~47–56 t/s serial; we are at 52–61% of it. The remaining gap is genuinely open
  (per the review: "unattributed mixed bottleneck" — dequant, occupancy, dispatch, small-matrix cost).
- Only ~1.7 s of the 40 s end-to-end request is attributable to prefix/decode trade, so further decode
  tuning is worth **≤4% end-to-end** for this workload; the review's point that prefill/prep dominates is
  correct for ingest-heavy requests.
