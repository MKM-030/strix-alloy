Title: Qwen3.8-Flash-Next on my Windows Strix Halo: Halogen 0.16.2, GUFO and PROJFIX

Measured on 3 October 2026: eleven valid timing cells and one PROJFIX reserve failure.

I tried the long-chat layout from [deepu105's comparison](https://www.reddit.com/r/LocalLLM/comments/1wu0m53/benchmarks_best_engine_for_qwen_38flashnext_on/) on my BOSGAME Ryzen AI Max+ 395 / Radeon 8060S: 128 GiB installed memory, Windows 11 Pro, driver 32.0.32015.2008. I didn't record a fixed wattage.

GUFO and PROJFIX run natively on Windows; Halogen uses Ubuntu 24.04 WSL2/Docker with DXG. The weights differ: v2 HGN, Unsloth UD-IQ4_XS, and IQ4_NL-PROJFIX. This compares those setups on my machine; it doesn't isolate engine, quantization or OS effects from the reference post.

Halogen's v2 HGN checkpoint averages **4.16 bits per weight**: 4-bit experts and other weights, 6-bit mixing layers, and 8-bit dense MTP projections. Its separate n-gram lookup table is FP8. These are the [published v2 quantization details](https://github.com/peonist-ai/halogen-flash-server/blob/main/docs/QUANT.md#the-v2-checkpoint-015-on); IQ4_XS is the GUFO quantization.

Each cell is two three-turn conversations at temperature 1 / top-p .95 / top-k 20, low-effort thinking requested, and a 1536-token answer limit. I used twelve pinned LlamaStash code files plus exact-value fixtures, with ungraded implementation/review follow-ups. 3-turn time is the normalized sum of `TTFT + 1000/decode t/s` per turn, averaged across both conversations. Prefill covers initial requests; regular sampled decode is weighted across all six answers, including reasoning tokens. MTP accept is accepted/proposed draft tokens. Actual wall times and counts are in the report.

**64K capacity, 32K initial input — 50% filled**

| Engine | Weights | 3-turn time | Prefill t/s | Sampled decode t/s | MTP accept | Retrieval |
|---|---|---:|---:|---:|---:|---:|
| Halogen 0.16.2 / WSL2 | v2 HGN + lookup source | 2.17 min | 1010.3 | 30.55 | 83.9% | 14/14 |
| GUFO / Windows | UD-IQ4_XS + Q8_0 MTP | 2.01 min | 715.7 | 39.63 | 79.8% | 14/14 |
| PROJFIX / Windows, cache0 | IQ4_NL-PROJFIX + Q8_0 MTP | 3.70 min | 241.7 | 35.51 | 85.2% | 14/14 |

**128K capacity, 64K initial input — 50% filled**

| Engine | Weights | 3-turn time | Prefill t/s | Sampled decode t/s | MTP accept | Retrieval |
|---|---|---:|---:|---:|---:|---:|
| Halogen 0.16.2 / WSL2 | v2 HGN + lookup source | 2.44 min | 1011.7 | 37.25 | 85.1% | 16/16 |
| GUFO / Windows | UD-IQ4_XS + Q8_0 MTP | 2.94 min | 673.3 | 37.23 | 76.7% | 16/16 |
| PROJFIX / Windows, cache0 | IQ4_NL-PROJFIX + Q8_0 MTP | 5.33 min | 287.1 | 34.13 | 83.7% | 16/16 |

**128K capacity, 96K initial input — 75% filled**

| Engine | Weights | 3-turn time | Prefill t/s | Sampled decode t/s | MTP accept | Retrieval |
|---|---|---:|---:|---:|---:|---:|
| Halogen 0.16.2 / WSL2 | v2 HGN + lookup source | 2.49 min | 1398.7 | 36.72 | 83.6% | 16/16 |
| GUFO / Windows | UD-IQ4_XS + Q8_0 MTP | 4.04 min | 632.8 | 33.94 | 73.1% | 16/16 |
| PROJFIX / Windows, cache0 | IQ4_NL-PROJFIX + Q8_0 MTP | 4.72 min | 507.0 | 34.54 | 85.0% | 16/16 |

**256K capacity, 128K initial input — 50% filled**

| Engine | Weights | 3-turn time | Prefill t/s | Sampled decode t/s | MTP accept | Retrieval |
|---|---|---:|---:|---:|---:|---:|
| Halogen 0.16.2 / WSL2 | v2 HGN + lookup source | 3.25 min | 1248.2 | 33.90 | 85.0% | 16/16 |
| GUFO / Windows | UD-IQ4_XS + Q8_0 MTP | 5.10 min | 611.1 | 32.45 | 73.1% | 16/16 |
| PROJFIX / Windows, cache0 | IQ4_NL-PROJFIX + Q8_0 MTP | Reserve failure | — | — | — | Not scored |

GUFO is quicker at 32K input; Halogen has the shorter conversation at larger inputs among completed results. Every completed cell retrieved all its exact values. Halogen's 37.25 t/s row uses approximately 65536 input tokens; its 1398.7 prefill / 36.72 decode / 83.6% acceptance row uses approximately 98304 input tokens. The last Halogen row is **131099 actual input tokens in a 262144-capacity engine**, measuring 1248.2 prefill / 33.90 decode / 85.0% acceptance. That 3 October comparison did not measure 260K actual input; a separate 5 October greedy measurement is below.

Halogen used stock compute and Exact cache. Its startup MTP depth was 2, but the sampled path proposes one token per round regardless of that setting; depth tuning applies to greedy requests. GUFO used proposal cap 3/full vocabulary/length policy, prefill 2048, without prompt lookup; PROJFIX used MTP-host depth 1 / `--cache-ram 0`. Initial requests were cold and follow-ups reused history in every completed cell. [Halogen sampled-depth evidence](https://github.com/MKM-030/strix-alloy/blob/main/docs/research/halogen-sampled-mtp-depth-20261004.md).

GUFO hit the answer cap once at 128K/50% and once at 256K/50%; PROJFIX hit it three times at 64K/50%, once at 128K/50% and once in the partial 256K/50% run. Halogen had no cap hits. Truncated answers stay in the recorded data.

The selected PROJFIX rerun adds only `--cache-ram 0`. At 256K/50%, it crossed the 18 GiB physical reserve during request 4, after one conversation. Cleanup succeeded; that partial cell is unscored. The earlier 256K cancellation is documented separately.

**Separate coding pass/time check**

| Engine | First-attempt passes | Final passes (up to two attempts) | Actual suite time |
|---|---:|---:|---:|
| Halogen 0.16.2 / WSL2 | 5/10 | 7/10 | 27.59 min |
| GUFO / Windows | 5/10 | 6/10 | 36.23 min |
| PROJFIX / Windows, cache0 | — | Unscored reserve stop | 5.26 min (partial) |

This uses ten disclosed Aider polyglot Python exercises, a read/write tool agent, up to two attempts, a 4096-token call cap and pristine official tests. Halogen hit that cap once; GUFO three times; PROJFIX's two recorded calls had no caps. Its loop/subset differs from the author's Pi run. Coding time is actual suite elapsed.

PROJFIX coding had a transport abort, then a retry after a gateway timeout fix with the 600-second API limit unchanged. It passed affine-cipher, then hit the physical reserve; the partial suite is unscored.

My earlier approximately 65 tok/s result used predictable synthetic output; it stays in the separate [long-context report](https://github.com/MKM-030/strix-alloy/blob/main/docs/benchmarks/halogen0162-long-context-20261003.md).

[Code and setup](https://github.com/MKM-030/strix-alloy) · [Method, counts, build and failure details](https://github.com/MKM-030/strix-alloy/blob/main/docs/benchmarks/strix-alloy-article-comparison-20261003.md) · [Sanitized evidence](https://github.com/MKM-030/strix-alloy/blob/main/docs/benchmarks/strix-alloy-article-comparison-20261003.json)

Thanks to Peonist AI, GUFO and the llama.cpp fork maintainers for the engine work. Alloy supplies the local Windows/WSL integration and measurement wrapper.

**4 October update: native WSL lookup file**

I also moved Halogen's n-gram feature lookup file from the Windows-backed mount to WSL ext4 and ran stock → native → stock with the same answers and token counts. This was a separate 64K-capacity / 32K-input run with cache Off; the tables above use Exact cache.

Initial prefill was 1441 t/s with the native file, versus 989 and 1109 t/s for the stock bookends. Each of the two initial requests was 28–32% faster than the later stock control. Draft acceptance stayed at **2156/2539 = 84.92%** in all three cells. Decode varied too much between the stock controls to claim a gain. The native run's RAM recovery also required a separate later check, which is retained in the evidence. [Result and counts](https://github.com/MKM-030/strix-alloy/blob/main/docs/benchmarks/halogen0162-native-lookup-20261004.md).

**Separate 8K greedy check after reboot**

On 4 October, with 8192 input tokens, 128 output tokens, cache Off and MTP depth2, the first fresh stock control averaged **1866.537 t/s prefill and 48.4236 t/s regular greedy MTP decode** across three paired requests. The second stock control averaged **1885.854 t/s prefill and 48.2804 t/s decode** across three paired requests. Each control had **207/345 = 60% draft acceptance**. Separate serial PP8192/TG1 was 1873–1924 t/s; serial decode was 36.73–37.03 t/s. Turning prompt lookup off gave 48.23 t/s and the same acceptance, so I kept stock. All answers and token counts matched. This is an 8K-input check in a 262144-capacity engine, separate from the sampled long-chat tables above. [Full comparison](https://github.com/MKM-030/strix-alloy/blob/main/docs/benchmarks/halogen0162-pld-stock8k-20261004.md).

The older late pristine stock control on 3 October used **16384 input / 128 output tokens** and averaged **1647.279 t/s prefill and 45.3427 t/s regular greedy MTP decode** across three paired requests, with **56.3025% draft acceptance**, cache Off and MTP depth2 at the same 262144 capacity. This 16K control was **not rerun after the reboot**. Its separate serial PP16384/TG1 mean was 1680.803 t/s. [Retained 16K evidence](https://github.com/MKM-030/strix-alloy/blob/main/docs/benchmarks/halogen0162-upgrade-20261003-evidence.json).

**5 October update: actual 128K and 260K inputs**

I reran Halogen with exact 131072 and 260000 input tokens, rather than using the context capacity as the input length. These are once-only War and Peace prefixes followed by the same story-writing task. The output is ordinary prose, with no repeated blocks.

| Actual input tokens | Prefill t/s | MTP decode t/s | Draft acceptance |
|---:|---:|---:|---:|
| 131072 | 1177.60 | 36.67 | 47.33% (186/393) |
| 260000 | 1104.87 | 36.81 | 51.20% (192/375) |

Each row is the mean of three runs after one excluded warmup: 128 output tokens, greedy temperature0/seed1, thinking off, prompt cache Off, MTP depth2 and PLD3,3. The native acceptance counters cover that configured draft path. Both sizes ran on the same 262144-capacity instance with `HALOGEN_MAX_TOK=8192` and `HALOGEN_PREFILL_CHUNK=8192`. The engine reported 5.6 GiB of working memory, versus 12.3 GiB for the earlier 32768 arena.

These use different prompts and sampling settings from the long-chat tables, so they are separate results, not an optimization delta. The earlier 48.42 t/s remains an **8K-input** result. The NPU was off: no full-engine NPU speedup has been demonstrated. [Runs, warmups and evidence](https://github.com/MKM-030/strix-alloy/blob/main/docs/benchmarks/halogen0162-natural-long-20261005.md).
