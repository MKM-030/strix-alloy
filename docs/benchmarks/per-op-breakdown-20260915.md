# Per-op composition: what is measured, what is not, and the one number that IS solid (2026-09-15)

## Status: composition still not reliably measured

Three attempts, and the honest summary is that **we do not yet have a trustworthy per-op breakdown**.

| attempt | config | result | verdict |
| --- | --- | --- | --- |
| 1 | `LLAMA_OP_TIMING=2`, graphs ON | CPPY 20.3%, CONT 16.6%, MUL_MAT 15.6% — **but** the aggregate path ran without its required `GGML_CUDA_DISABLE_GRAPHS=1`, and both arms **crashed** with `GET_ROWS failed` | **INVALID — retracted** |
| 2 | `LLAMA_OP_TIMING=2`, graphs ON | the in-graph path (`_IG`) reported **`tracked total 0.0 ms/replay`** on all 15 summaries | **broken on this build** |
| 3 | `LLAMA_OP_TIMING=1` + `GGML_CUDA_DISABLE_GRAPHS=1` | passed the validation gate (32 summaries, 0 zero-rows, 0 errors): MUL_MAT 56.1%, SCALE 11.5%, RMS_NORM 10.2%, GET_ROWS 8.8%, CONT 6.1%, CPY 4.4% | **valid run, but see below** |

**Attempt 3 disagrees with attempt 1 by a factor of ~3.6 on the MUL_MAT share (56.1% vs 15.6%).** I cannot
explain the gap, so I am not going to quote either as *the* composition. The plausible reason the graphs-off
figure is inflated is that with graphs disabled each op is launched separately and the event pair spans the
launch gap as well as the kernel — so the aggregate path over-attributes, especially to whichever op is
most numerous. But that is a hypothesis, not a demonstration.

## What IS solid, and it is important

**Decode throughput with graphs ON vs OFF, same model, same box, same session:**

| config | decode | ms/token |
| --- | ---: | ---: |
| graphs **ON** (our normal path) | **35 t/s** | 28.6 ms |
| graphs **OFF** (attempt 3) | **10.7 t/s** | 93.5 ms |

**Graphs are worth ~65 ms/token — about 70% of the graphs-off time.** This is the single most useful thing
to come out of these runs, and it is a clean A/B.

The consequence matters for everything we have been discussing: **the graphs-on path is already
dispatch-free.** So the ~80% "target verify" time we measured earlier is **genuine GPU execution**, not
launch overhead. That kills the "maybe it is all dispatch overhead" hypothesis for the production path, and
it means the remaining lever really is the work the kernels do — which brings us back to needing a real
composition measurement.

## What is *consistently* true across both attempts

Despite the MUL_MAT disagreement, both runs agree on the *shape* of the non-matmul cost:

| | attempt 1 (graphs on) | attempt 3 (graphs off) |
| --- | ---: | ---: |
| SCALE + RMS_NORM + GET_ROWS + CONT + CPY + CONCAT | **~50%** | **~40%** |
| calls per op type | 200–1200 | **9 400–19 200** |
| average cost per call | 11–50 µs | **3.8–7.7 µs** |

**Roughly 40–50% of measured GPU time is non-matmul elementwise/layout work, spread over tens of thousands
of sub-10-µs calls.** That ordering held in both configurations even though the MUL_MAT share did not. It is
also consistent with the earlier phase finding (draft step ~70% fixed overhead) and the model's structure
(48 layers × per-layer norms, scales, gathers, concats).

I am labelling that **"strongly indicated, not yet proven"** — it is the kind of claim I should have made
about attempt 1 before I stated it as fact.

## Where the composition measurement stands

The in-graph timer is the right tool and it returns **zero on this build**. Fixing it is a contained job
(the code is ~100 lines in `ggml-cuda.cu`) and would give composition *with graphs on*, which is the only
configuration whose numbers matter. That is the correct next step for this line of work — not more runs of
the graphs-off path, which cannot answer a graphs-on question.

**Practical gate for whoever picks this up:** validate before quoting — non-zero summary, no error lines,
and for the graphs-on case confirm the `_IG` path produced rows at all.

## Cleanup state

- `ggml-cuda.cu` reverted to the pre-instrumentation backup (0 op-timing refs) and **rebuilt clean**;
  verified healthy (`model loaded`, `listening on`, no `cudaMemGetInfo` failure).
- The instrumented binary **crashed under load** (`GET_ROWS failed` → `ROCm error`) and must not be used
  for benchmarks. It is no longer on disk.
- Baseline throughput restored: 35 t/s decode, ~1025 t/s prefill @16k.
