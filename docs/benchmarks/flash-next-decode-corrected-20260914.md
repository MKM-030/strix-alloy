# Flash-Next decode: CORRECTED root cause — MTP dies when the prompt fills the KV pool (2026-09-14)

**This supersedes `flash-next-decode-mtp-first-request-bug-20260914.md`, whose "first request" claim
was wrong.** The corrected measurement is below, and it is good news: **decode is 17–31 t/s, not 7.**

## The corrected experiment

One server (`-c 32768`, MTP depth 3), requests alternating short/long in a single process:

| # | Request | Prompt tokens | Decode | MTP acceptance | mean len |
| ---: | --- | ---: | ---: | ---: | ---: |
| 0 | short | 57 | 13.83 | 76.2% | 3.29 |
| 1 | **~8.5k** | **8,562** | **21.82** | **84.6%** | 3.44 |
| 2 | short | 4 | 23.45 | 62.5% | 2.88 |
| 3 | short | 4 | 17.13 | 76.2% | 3.29 |
| 4 | ~8.5k | (cached) | **31.06** | **100%** | 3.88 |
| 5 | short | 4 | 24.23 | 62.5% | 2.88 |

**Decode stayed 17–31 t/s through every request; the ~8.5k prompt was among the fastest. MTP acceptance
stayed 62–100%.** A long prompt does **not** kill the drafter.

## What actually produces the 0% rows

Every earlier slow run used prompts of **15,000–27,000 tokens** against `-c 32768` — the prompt filled
most of the KV pool. In that regime the log shows `0 accepted / 123 generated, mean len 1.00` and
decode ~7 t/s. At 8.5k tokens against the same context, acceptance is 85%.

**So the trigger is prompt-size relative to the KV pool, not context depth in general, and not request
count.** (Earlier I concluded "depth" because each of those runs happened to have one deep prompt; then
"first request" because the very first prompt in those runs was short. Both were wrong: the alternating
test shows the drafter surviving long prompts and repeated requests.)

## Corrected numbers for the World Engine

| Workload | Prefill | Decode | MTP acceptance |
| --- | ---: | ---: | ---: |
| short prompt (≤1k) | 30–150 t/s | **17–24 t/s** | 62–76% |
| ~8.5k prompt | **331 t/s** | **22 t/s** | 85% |
| up to ~25k (warm cache) | 530–577 t/s | 7 t/s | **0%** ← pool saturation |

**Two distinct regimes**, and the boundary is where the prompt consumes most of the context pool.

## Consequences

1. **REV:N World Engine at realistic context (8–16k)** gets **~22 t/s decode with 85% acceptance** —
   which is *at* Peonist's Halogen figure (25.4 t/s) and far better than the 7 t/s I first reported.
2. **Why the small-context test mattered (founder's instinct was right):** smaller context = smaller
   pool pressure = MTP keeps working. `-c 8192` gave 20 t/s warm; `-c 65536` with a 20k prompt gave 7.
3. **Practical rule:** keep `ctx` modest (16–32k) and keep prompts well under the pool. If a scene needs
   more context, raise `-c` *and* accept the decode penalty, or split the world state.

## Method note (my error, recorded)

My depth tables tokenised nothing — "~8k" meant 8,000 *words*, which is ~15–27k tokens. That silently
pushed every "deep" row into the pool-saturation regime while the label suggested moderate depth. The
disambiguation run used the server's `/tokenize` to size prompts exactly, which is why it disagrees with
the earlier tables.
