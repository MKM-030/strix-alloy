# GUFO MTP on Halogen's ten prompts — 27 September 2026

**Measured native Windows decode: 41.93 tok/s across all 30 responses.**
All 36 requests, including warmup, calibration and PP, completed. Owned shutdown
and memory recovery passed. This is a throughput result, not a quality pass or
a persistent-service qualification.

| Measurement | Result |
|---|---:|
| Ten-prompt engine decode, arithmetic mean of 30 requests | **41.93 tok/s** |
| Three full-corpus repetition means | 41.81 / 41.98 / 41.98 tok/s |
| Between-repetition sample SD | 0.10 tok/s |
| Across-request SD / observed range (includes content differences) | 6.38 / 32.43–51.68 tok/s |
| PP2048 HTTP, actual 2,047 input / 1 output, n=3 | **796.08 ± 21.98 tok/s** |
| PP2048 engine, same three requests | **831.69 ± 22.95 tok/s** |
| MTP acceptance, corpus responses only | **4,323 / 5,841 = 74.01%** |
| Corpus engine TTFT, mean ± sample SD | 441.51 ± 31.63 ms |

Decode is native completion tokens / native decode seconds. The arithmetic
mean is the Halogen-style headline; the pooled 7,632 tokens / 186.079 decode
seconds is **41.01 tok/s**, a different statistic. The same 7,632 tokens over
199.940 seconds of complete HTTP requests yields **38.17 output tok/s**,
including prefill and transport. It is not concurrent throughput. Non-streaming
corpus responses do not measure client-visible first-token arrival.

HTTP PP includes request preparation/transport and one output token. Engine PP
uses prefill tokens / native prefill time. PP requests had no cache hits; their
one-token decode rates are excluded from decode claims. MTP was enabled, but
these one-output PP requests proposed zero draft tokens.

## Per-prompt results

All cells retain three repetitions; engine decode mean ± sample SD. Every
prompt produced byte-identical text and identical token counts across repeats.

| Prompt | Actual input / output tokens | Decode tok/s | Finish |
|---|---:|---:|---|
| code_a | 31 / 256 | 51.59 ± 0.08 | Length limit |
| code_b | 41 / 256 | 46.23 ± 0.23 | Length limit |
| proof_a | 24 / 256 | 49.83 ± 0.44 | Length limit |
| proof_b | 22 / 256 | 47.19 ± 0.30 | Length limit |
| proc_a | 27 / 256 | 42.28 ± 0.78 | Length limit |
| proc_b | 30 / 256 | 34.50 ± 0.08 | Length limit |
| chat_a | 26 / 240 | 36.70 ± 0.29 | Natural stop |
| chat_b | 24 / 256 | 37.69 ± 0.20 | Length limit |
| prose_a | 36 / 256 | 32.55 ± 0.18 | Length limit |
| prose_b | 28 / 256 | 40.71 ± 0.27 | Length limit |

Manual quality review: **27/30 responses hit the output limit**. Code functions
and proofs are incomplete; SSH instructions stop during setup, the speculative
decoding explanation omits when it ceases helping, and several answers stop
mid-sentence. The RAID answer additionally reverses a hot-swap/power-off safety
condition and is unsuitable as operational guidance. The unified-memory answer
also overstates prefill as the bandwidth bottleneck. Only the laundry chat
finishes naturally. No generated code or operational instruction was executed.
The raw suite's `quality_failed=0` means no automated response-contract failure;
it is **not** semantic certification. No same-corpus AR control was run here,
so neither quality differences nor a causal MTP speedup can be established.

## Comparison, with protocol differences retained

| Halogen ten-prompt MTP decode | Mean tok/s | Evidence |
|---|---:|---|
| Our native GUFO, this run | **41.93** | 30 locally recorded responses |
| Our Halogen 0.13.8 through WSL2 | **41.20** | Historical 30-response MTP suite |
| Community GUFO Windows port | **43.0** | Contributor-reported, Q4_K_XL |
| Wordweaver native Windows HIP fork | **47.6** | Author-reported, IQ4_XS |

These are the same ten prompt texts, **not identical engine configurations or
complete benchmark protocols**. This GUFO adaptation is greedy, seed 42,
thinking off, max output 256, cache bypass, 4,096 context capacity, IQ4_XS plus
Q8_0 MTP, full vocabulary, length policy, draft cap three. It executes all ten
cases per repetition after a warmup and PP. Historical Halogen used HGN w4b,
thinking enabled with low effort (closed at token one), 50–69 input tokens,
serial/MTP interleaving, and a different carve and runtime. Wordweaver's full
fork/configuration and raw repeats are unavailable. Thus the GUFO headline is
numerically close to our WSL2 result, but neither parity nor superiority is
established. Its 35.99 tok/s earlier runbook result was a different corpus.

[Historical WSL2 measurement](C:/Projects/strix-alloy-wsl2/docs/benchmarks/upstream-20260924.md),
[Wordweaver post and contributor comparison](https://www.reddit.com/r/StrixHalo/comments/1wqsv03/yet_another_windows_strix_halo_q38fn_attempt/).
The author's post still says no repository is available. A fresh check of
the post, profile, replies and GitHub found no attributable public download.
No unrelated Windows fork was substituted.

For no-MTP PP2048/8192 use the separate [completed AR measurements](gufo-pp-20260927.md):
877.40 / 928.00 HTTP tok/s. Do not combine those AR rates with this MTP decode
into an implied single configuration. This MTP run did not measure PP8192.

## Memory, lifecycle and reproducibility

Same pinned engine `cff564964e8506c0abb3e530cecb55332187ac6c`, TheRock 10.2,
gfx1151, Unsloth UD-IQ4_XS revision `38bb39ee97821de2c9009abb7e93950eec396e66`,
shared Q8_0 sidecar, existing 64 GiB carve. Engine SHA256:
`E7F5B899C54C747EE5038C0598016394D2A70F25EE69AFBB1E02859FD223D943`.
Halogen corpus SHA256: `23DF9FEB5EC2B343F675BB08DC6C0C2286E17DD6D73ACF4E7D363D0C0C49922B`.

- Load: **25.564 seconds**; engine device use **67,701 MiB = 66.114 GiB / 70.99 GB**.
- 235 serving samples: available Windows RAM minimum **48.199 GiB**;
  adapter total commitment maximum **67.355 GiB**, shared maximum **4.110 GiB**.
  These overlap and must not be summed; sampled peaks are lower bounds.
- Minimum system commit headroom **142.914 GiB**. All 49/24/12 GiB floors and
  the separately reviewed d3 allocation envelope remained unchanged.
- 255/255 telemetry queries completed, slowest **0.344 seconds**, largest sample
  gap **1.047 seconds**. Five recovery samples: **54.023–54.094 GiB** RAM free,
  adapter commitment **0.628 GiB**. Exit 0; owned PID 5852 and port 8836 absent.
- No system-setting changes, reboot, new unit tests, push or publication.

The fixed recipe, exact launch arguments, raw responses, native counters,
memory samples, review and one-use approval are retained. The adapter is
intentionally consumed and must not be blindly rerun or have its marker erased.
Historical failures remain unchanged. Runtime qualification is retained under
an explicitly labelled historical reference, not relabelled as the new workload.

Raw directory:
`C:\Projects\strix-alloy-research\reports\halogen-ten-mtp-d3-20260927-v1-runs\20260927T173323Z-57ca3e581dda4a57a9cb39a178f4c9e4`

Result SHA256: `30B4E7B45848F16526F579A9288C7ACB0325D291B583CC94CFF79A73144BFDF8`.
All 36 response artifact hashes/sizes and recorded metrics were checked. All
35 non-streaming raw responses were reconciled to their counters and timings;
the streaming warmup is retained separately. Broad performance optimization,
sampled/cached comparisons, long context and concurrency remain unfinished.
