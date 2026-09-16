# llama-bench workload identity: the `rand()` defect is real, its throughput impact is not (2026-09-16)

External review raised a specific comparability defect in using `llama-bench` for the cross-platform
comparison, and ranked it high. Two experiments below test it. **The defect is confirmed as real; it is
measured to be immaterial to throughput on this model.** That is a useful split — the workload identity
concern stands, the throughput explanation does not.

## The defect, confirmed on our exact toolchain

`tools/llama-bench/llama-bench.cpp` feeds the model with:

```cpp
token = std::rand() % n_vocab;
```

Compiled with the MSVC/UCRT toolchain we use, `RAND_MAX` is 32767 (`rand-check.c`, built with the same
`vcvars64` the engine uses):

```
RAND_MAX                  = 32767
n_vocab (Qwen3.8-FN)      = 248320
max token id seen in 2e6 draws = 32767  (13.2% of vocab reachable)
draws below 32768: 100.00%   at/above: 0.00%
```

Our binaries link `api-ms-win-crt-runtime-l1-1-0.dll` (UCRT), so the cap applies. On Linux/glibc
`RAND_MAX` is 2^31-1 and the full vocabulary is reachable. **So the two platforms' `llama-bench` runs do
not feed the same token distribution, and a matching seed cannot fix it across different C libraries.**
`test_prompt()` fills the prompt this way and `test_gen()` supplies a fresh pseudorandom token after every
single-token step, so neither phase is normal generation.

## Experiment 1 — does the ID *range* change throughput? No.

Same server, same engine, same length, varying only which IDs are in the prompt (`token-distribution-ab.ps1`):

| prompt stream | max id | 8k prefill | 16k prefill |
| --- | ---: | ---: | ---: |
| `natural` — real prose, full vocab | 248,076 | 971.8 | 1007.7 |
| `low-only` — filtered real ids < 32768 | 32,767 | 939.5 | 966.3 |
| `unif-full` — uniform over full vocab (glibc-like) | 248,301 | 876.1 | 871.9 |
| `unif-low` — uniform over [0, 32768) (UCRT-like) | 32,765 | 863.9 | 870.2 |

**The UCRT-vs-glibc comparison is `unif-low` vs `unif-full`: −1.4% at 8k, −0.2% at 16k.** Restricting the
reachable vocabulary to 13% of its range does **not** materially change prefill throughput on this model.

## Experiment 2 — is it PLE n-gram locality? No.

A plausible mechanism specific to this architecture: `src/models/qwen4exp.cpp:1725,1787` gathers `ple_n_heads`
rows of a ~27 GiB table per token, indexed by a hash of the **local n-gram**, so a random stream makes every
n-gram unique (cold gathers) while prose repeats n-grams (cached). If that were the cause, throughput would
track *repetitiveness*, not the ID range.

Tested by holding IDs and length fixed and varying only repetitiveness (`ple-locality-ab.ps1`):

| stream | distinct trigrams in 8256 tokens | 8k prefill (warm median) |
| --- | ---: | ---: |
| fresh-random | 8,254 (essentially all unique) | **952.1** |
| repeated-block (512-id cycle) | 512 | 904.4 |
| prose | 7,103 | 964.2 |

**Refuted.** The stream with the *most* unique n-grams was the **fastest**, 5.3% ahead of the maximally
repetitive one. PLE n-gram gather locality is not what makes random tokens slower, so it is not an
explanation for the harness difference.

## What this leaves

1. **The `rand()` defect is real** and the two platforms are not measuring the same workload. Report it as a
   workload-identity defect, and label `llama-bench` figures as synthetic.
2. **It is not the throughput explanation.** Restricting the range costs ≈0–1.4%; n-gram locality moves the
   wrong way. So the 26% prefill gap to ilintar is *not* explained by the token stream.
3. **A caveat I now have to take seriously: the server's own numbers move between runs.** The same
   `unif-full` 8k shape measured a 876.1 median in one server session and 952.1 in another (fresh-random,
   same construction) — a ~9% spread for what should be the same experiment. Combined with the
   sequence-to-sequence spread seen here, the server's prefill figures are only good to roughly ±5–10% for
   random-token prompts.

Point 3 means the "4–17% harness gap" against `llama-bench` **cannot be separated from server-side spread
with the data collected so far.** The reviewer's §3 objection was right: the two are not a controlled
comparison. Establishing one would need the same stored token array fed through both entry points, timing the
same backend operation — which is the experiment to run next, not another throughput sample.

## Reproduce

```bash
cl /nologo /O2 rand-check.c /Fe:rand-check.exe && rand-check.exe          # the RAND_MAX cap
powershell -File token-distribution-ab.ps1 -Sizes '8192,16384' -Repeats 3  # experiment 1
powershell -File ple-locality-ab.ps1 -Sizes '8192' -Repeats 3              # experiment 2
```
