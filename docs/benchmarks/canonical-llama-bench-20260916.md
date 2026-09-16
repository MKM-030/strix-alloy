# Canonical llama-bench numbers (2026-09-16)

`llama-bench` is llama.cpp's own benchmark tool and the number everyone quotes. Its defaults are
**`-p 512 -n 128`**, reported as **`pp512`** (prefill of a 512-token prompt) and **`tg128`** (text generation,
128 tokens). Two properties make it the right cross-engine yardstick:

- it is the same tool upstream, ilintar, olliehm and the Reddit threads all report, so the numbers are
  comparable without translation;
- **it cannot drive a drafter** — there is no speculative/MTP flag in the build — so `tg128` is *plain serial
  decode*. That is precisely what makes it fair: it measures the engine, not the acceptance rate, which we have
  shown is heavily content-dependent (27–47 t/s with MTP).

## Measured on this box (Windows, native HIP, PROJFIX IQ4_NL, 96 GB carve)

| test | n_batch / n_ubatch | t/s | notes |
| --- | --- | ---: | --- |
| `pp512` | 2048 / 512 (defaults) | **761.30 ± 38.24** | canonical default pair |
| `tg128` | 2048 / 512 (defaults) | **31.49 ± 0.17** | serial decode, no drafter |
| `pp16384` | 16384 / 16384 | **892.59 ± 22.50** | ilintar's protocol |
| `tg128` | 16384 / 16384 | **30.16 ± 1.00** | ilintar's protocol |
| `pp16384` | 16384 / 16384, `-r 8` | 827.74 ± 23.50 | more reps do **not** climb → not a warm-up artifact |

Command (from `build-therock\bin`):

```
llama-bench.exe -m <model> -dev ROCm0 -ngl 99 -fa on -lm none -p 512 -n 128 -r 5
llama-bench.exe -m <model> -dev ROCm0 -ngl 99 -fa on -lm none -p 16384 -n 128 -b 16384 -ub 16384 -r 3
```

## Direct comparison with the published reference (same tool, same protocol)

| metric | **this repo (Windows HIP)** | ilintar (`pwilkin/strix-halo`, Linux) | ratio |
| --- | ---: | ---: | ---: |
| prefill `pp16384` | 892.59 | **1204.31 ± 2.31** | **0.74× (−26%)** |
| decode `tg128` | **30.16** | 26.28 ± 0.29 | **1.15× (+15%)** |

Read honestly: **we are 26% behind on prefill and 15% ahead on serial decode.** The prefill gap matches the
earlier rebase finding (our ~1040 server-measured vs their 1204); the decode lead is new and is the more
interesting one, because serial decode is the cleanest engine-vs-engine number available — no drafter, no
acceptance variance.

Their figures are their own published ones (`r/StrixHalo/1weo5s3`, `pwilkin.github.io/strix-halo`), taken on
Linux with the retained-PM4 runtime, which we do not have.

## One discrepancy to state plainly: canonical harness vs server

The same 16k prefill measures **~830–890 t/s under `llama-bench`** but **926–1043 t/s via the server's own
`prompt_per_second`** (across `base-96g`, `post-port-prod` and the earlier ladder: 926, 986, 1032, 1043). The
canonical harness is the conservative one and the one a third party can reproduce, so **the README's headline
prefill figure should be the `llama-bench` number, not the server peak.** The gap is ~10–15% and is not
explained yet; candidate causes are context size (`llama-bench` uses `n_prompt + n_gen`, the server runs
`-c 32768`) and a harness-side fixed overhead. Not worth chasing for a published figure — report the number
that replicates.

**Recommendation for the README:** quote `llama-bench` — `pp512 761` / `tg128 31.5`, and `pp16384 893` /
`tg128 30.2` for the long-prompt case — and keep the MTP decode figures clearly labelled as
*server-measured, content-dependent* (27–47 t/s). Mixing a server peak with a benchmark-harness number is what
made our earlier table confusing.
