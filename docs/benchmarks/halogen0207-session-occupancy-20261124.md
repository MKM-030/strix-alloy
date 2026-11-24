# Halogen 0.20.7 concurrency and long-context occupancy

Measured on November 24, 2026 with Halogen 0.20.7 v2 on Ryzen AI Max+ 395,
Windows 11 and WSL2. Windows reported 63.65 GiB of physical memory. The
262K trials used BF16 KV, default concurrency and paired 8,192-token
Prefill settings. A 262,144-position per-request limit controls the largest
individual request. The shared KV pool must cover all simultaneous
reservations, each sized for input plus the output budget.

## Completed long-context waves

The first three rows show one, two and three live near-262K sessions in a
786,432-position shared pool. The other rows show the four-session cases
with shorter contexts. Every row represents one wave, with all listed
requests fully prefilled and live at the same sample, and all requests
subsequently finishing their output budgets.

| Live sessions | Actual input tokens per stream | Output tokens per stream | Mean native Prefill / Decode per stream, tok/s | Aggregate common Decode, tok/s | Aggregate full HTTP, tok/s | Native MTP head accepted/drafted | Min. Windows RAM / commit, GiB |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 × 262,144 | 262,016 | 128 | 1,670.06 / 46.83 | 46.45 | 0.80 | 59/88 (67.05%) | 12.78 / 107.48 |
| 2 × ~262K | 260,608 / 261,368 | 1,536 / 768 | 1,606.73 / 11.04 | 30.64 | 6.03 | 1,070/1,678 (63.77%) | 9.64 / 103.96 |
| 3 × ~262K | 260,096 / 260,088 / 260,080 | 2,048 each | 1,448.63 / 13.80 | 65.64 | 10.23 | 2,906/3,970 (73.20%) | 6.82 / 100.95 |
| 4 × ~131K | 126,976 / 126,968 / 126,960 / 129,024 | 4,096 / 4,096 / 4,096 / 2,048 | 1,727.86 / 16.24 | 96.87 | 32.49 | 7,875/10,224 (77.02%) | 9.50 / 102.80 |
| 3 × ~131K + 65,536 | 126,976 / 126,968 / 126,960 / 63,488 | 4,096 / 4,096 / 4,096 / 2,048 | 1,563.66 / 16.13 | 81.22 | 31.67 | 7,827/10,132 (77.25%) | 10.73 / 104.04 |
| 3 × ~196K + 32,000 | 192,512 / 192,504 / 192,496 / 29,952 | 4,096 / 4,096 / 4,096 / 2,048 | 1,596.41 / 18.13 | 96.92 | 27.30 | 7,627/9,143 (83.42%) | 6.20 / 99.53 |
| 3 × ~196K + 49,152 | 192,512 / 192,504 / 192,496 / 47,104 | 4,096 / 4,096 / 4,096 / 2,048 | 1,655.85 / 17.72 | 95.74 | 28.17 | 7,233/8,827 (81.94%) | 6.13 / 99.45 |

The solo wave dispatched one request into a three-slot profile. The pair
and trio ran in separate four-slot profiles. The pair was staggered
and used unequal output budgets. The trio used equal budgets.
In the four-session waves, the fourth request was
released after the third request finished Prefill. The prompts and output
budgets vary across the rows. In particular, the solo wave generated just
128 output tokens after processing a 262,016-token prompt, while the
three-session wave generated 6,144 output tokens. The full HTTP rate
therefore measures different amounts of Prefill per output token.

Four near-131K streams had the highest full-HTTP result among the long
waves at 32.49 tok/s. The 196K/32K wave recorded 96.92 tok/s in the common
window, close to the observed 96.87 at four near-131K contexts. Each
figure comes from one wave.

### Interrupted waves

The 819,200-position pool started, but the host memory guard stopped the
attempt with three near-262K sessions before dispatch of the 32,000-position
fourth request. The host watcher sampled a minimum of 5.91 GiB free RAM and
99.40 GiB commit reserve across this attempt. With three near-196K sessions
and a fourth at 65,536 positions, all four finished Prefill and the guard
stopped generation, with sampled minima of 5.97 GiB RAM and 99.33 GiB commit
reserve. The same workload completed at 49,152 positions for the fourth
request. A separate four-slot startup with the 1,048,576-position BF16
pool crossed its 4 GiB Windows RAM guard during KV reservation. At the
first crossing the watcher recorded 3.99 GiB RAM and 97.48 GiB commit
reserve. The profile never reached readiness and served zero requests.

### Timing and counters

- **Common Decode** counts native SSE output token events in the
  half-open interval from the latest first event to the earliest last
  event. The replay counts empty text fragments and skips prompt progress
  frames. It verifies event counts against native completion and usage
  ledgers. The previous four-session summary included the end event.
- **Full HTTP** divides all completed output tokens by Windows QPC time
  from first dispatch to last response EOF. It includes Prefill and
  staggered admission delays.
- **Native phase rates** are arithmetic means over the streams' engine
  timers. These timers and the client interval cover different times
  during staggered Prefill and generation. MTP acceptance uses pooled
  native head accepts and proposals. The server classified 763 tokens
  from one stream in each near-131K case as reasoning. They are included
  in its completion count.

[Per-stream counters, timings and SHA-256 evidence digests](halogen0207-session-occupancy-20261124.json)

## Short-prompt controls at configured 262K capacity

The table uses full HTTP for the local rows. A row may contain one
request or a group. The two-code controls used the same prompts in solo,
simultaneous and staggered runs. The three- and four-session `tg128`
runs used the same ten-prompt mix of code, proofs, procedures, chat and
prose. For four sessions, two companion responses contribute only to
the aggregate, alongside the 30 measured requests. These averages
span different cohorts and do not establish a single scaling curve.

| Local workload | Actual inputs | Outputs per stream | Aggregate HTTP, tok/s | Mean native Prefill / Decode per measured stream, tok/s | MTP head |
| --- | --- | --- | ---: | ---: | ---: |
| One code stream | 31 or 41 | 377 or 384 | 97.67 | 302.29 / 101.00 | 88.47% |
| Two code streams, simultaneous | 31 / 41 | 377 / 384 | 111.75 | 294.54 / 61.10 | 93.36% |
| Two code streams, staggered | 31 / 41 | 377 / 384 | 111.96 | 292.01 / 61.22 | 93.36% |
| Three streams, `tg128` | 22–41 | 128 | 82.58 | 198.43 / 30.94 | 84.71% |
| Four streams, `tg128` | 22–41 | 128 | 89.77 | 197.02 / 25.76 | 85.97% |
| Four short code streams | 31 / 41 / 49 / 45 | 384 each | 133.39 | 286.67 / 36.52 | 92.91% |

The three- and four-stream `tg128` runs shared a 786,432-position pool.
Their mean per-request HTTP rates were 28.78 and 23.76 tok/s, respectively.
The separate single-stream `tg128` run averaged 68.96 HTTP tok/s at
163,840 configured positions. Halogen's corresponding single-stream
`tg128` figure was 74.90 HTTP tok/s. [Publisher comparison and `tg128` method](halogen0207-publisher-comparison-20261124.md)

### Halogen's published short-code comparison

Halogen reports 93, 116 and 151 aggregate common-window tok/s for one,
two and four greedy code streams in its 0.20.7 v2 default concurrency
mode. The table has no three-stream row. Its 93 and 116 use a generation
interval and the local one- and two-code controls above use full HTTP.
The four-code replay matched the broad protocol, including four
concurrent requests, greedy sampling, Thinking Off and 384 output tokens.
Halogen used 16 configured slots on Ubuntu and its prompt texts are
unpublished. Strix Alloy used four slots over an 819,200-position pool
on Windows/WSL2, with Cache Off. One warmup wave was excluded and the
following three waves were measured. [Halogen publisher concurrency table](https://github.com/peonist-ai/halogen-flash-server/blob/dea807d22a638c67553abea876344a8192054a94/docs/configuration.md#context-and-memory-one-kv-pool-several-conversations)

| Four short code streams | Halogen | Strix Alloy | Local difference |
| --- | ---: | ---: | ---: |
| Aggregate common Decode, tok/s | 151.00 | 144.15 | −4.54% |
| Slowest stream in that window, tok/s | 36.00 | 32.85 | −8.74% |
| Aggregate full HTTP, tok/s | — | 133.39 | — |

The publisher's configuration guide separately describes around 17 tok/s
per stream for three conversations at 250K. The local near-262K wave
above gives both the native per-stream mean and the aggregate shared
window, with different prompt lengths and arrivals. The guide does not
give a matching full-HTTP result for those conditions. [Publisher notes on shared-pool capacity](https://github.com/peonist-ai/halogen-flash-server/blob/dea807d22a638c67553abea876344a8192054a94/docs/configuration.md)
