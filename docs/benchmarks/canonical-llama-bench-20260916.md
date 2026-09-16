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

Read honestly: **we are 26% behind on prefill and 15% ahead on serial decode.** The decode lead is the more
interesting one, because serial decode is the cleanest engine-vs-engine number available — no drafter, no
acceptance variance.

**These are two separately published results, not a controlled cross-platform A/B, and the cause of the prefill
difference is unresolved.** I previously implied it was the retained-PM4 runtime; that is **contradicted by the
reference itself**. Ilintar's own page states that HIP graphs **do not engage during the Flash-Next prefill**
work (each chunk shape occurs once per request) and that retained PM4 pays off in *decode*. Our own notes from
2026-09-14 record the same thing — "PM4 does not engage during prefill measurement; prefill wins are kernel"
work. So PM4 cannot be the explanation for a prefill gap. Do not repeat that attribution.

Candidate explanations that remain open, none tested: their single-batch shape (`-b/-ub 16384` with the whole
prompt in one batch), their sparse-indexer path, kernel-set differences, loading mode, and the possibility that
`llama-bench` and `llama-server` are not measuring identical work (see the next section).

Their figures are their own published ones (`r/StrixHalo/1weo5s3`, `pwilkin.github.io/strix-halo`), taken on
Linux. Their configuration also differs (`--load-mode none --lazy-mode on-direct`, `ub = b = 16384`), and
ilintar explicitly cautions against simple rankings across unlike configurations.

## Two discrepancies to state plainly: harness vs server, and what `llama-bench` actually feeds the model

### (a) `llama-bench` vs `llama-server` for the same shape

The same 16k prefill measures **827–893 t/s under `llama-bench`** but **926–1043 t/s via the server's own
`prompt_per_second`** (across `base-96g` and `post-port-prod`: 926, 986, 1032, 1043). That is a **3.7–16.9%
range, not one measured 15% effect**, and the two are not controlled comparisons: they differ in context size
(`llama-bench` uses `n_prompt + n_gen`, the server ran `-c 32768/262144`), in preparation state, and possibly in
what the harness times.

I also cannot claim "warm-up is ruled out because eight reps do not climb": the `-r 8` run reported
**827.74 ± 23.50**, about 7.3% below the `-r 3` run's 892.59, and an aggregate mean does not show whether
individual reps warmed, slowed, or varied with input. The `±` printed by `llama-bench` is a **sample standard
deviation**, not a confidence interval.

**Neither number is "the honest one" — they measure different things.** The defensible move is to publish both,
labelled, and to stop treating them as interchangeable. To actually locate the difference, feed the **same stored
token array** through both entry points and time the same backend operation at the same boundaries; that is not
done here.

### (b) `llama-bench` is synthetic single-token evaluation, and its token stream may differ on Windows

The reviewer raised a specific, checkable point worth recording. In this tree, `llama-bench` does not perform
normal autoregressive generation: `test_prompt()` fills the prompt with pseudorandom token IDs and `test_gen()`
supplies another pseudorandom token after each single-token forward pass:

```cpp
token = std::rand() % n_vocab;
```

On the Microsoft CRT `RAND_MAX` is 32767, so against a 248,320-token vocabulary that expression can only select
the **first 32,768 IDs (~13%)**, and a matching seed does not produce a matching sequence across different C
libraries. For an MoE with hashed PLE lookups, a different token distribution can change routing, cache
behaviour and preparation work.

**I have not verified the actual token trace of our binary**, so this is a concrete comparability defect to test,
not a proven explanation of the cross-platform difference. Until it is measured:

- treat `pp512`/`tg128` as **synthetic single-token evaluation throughput** — useful, but not a serving or
  quality benchmark, and not automatically comparable to a Linux binary built against a different CRT;
- label every figure with its harness, its engine revision and its settings;
- do not rely on "same tool, same seed" for a cross-platform claim.

**Recommendation for the README:** quote `llama-bench` — `pp512 761` / `tg128 31.5`, and `pp16384 893` /
`tg128 30.2` for the long-prompt case — with the harness named, and keep the MTP decode figures clearly labelled
as *server-measured, content-dependent* (27–47 t/s). Mixing a server peak with a benchmark-harness number is what
made our earlier table confusing.
