# Halogen 0.20.7 publisher benchmark comparison

On the ten published short prompts, Strix Alloy averaged **77.24 native
Decode tok/s** with MTP and accepted **4,887 of 6,021 head drafts (81.17%)**.
Halogen published 74.57 tok/s for the corresponding native `bench` row.
The completed `tg128` sweep averaged **68.96 output tok/s over HTTP**
against Halogen's 74.90. The Cache Off Prefill sweep ranged from **−1.89%
to +4.96%** against the published HTTP rates. [Halogen 0.20.7 performance](https://github.com/peonist-ai/halogen-flash-server/blob/dea807d22a638c67553abea876344a8192054a94/docs/performance.md#0207-both-checkpoints)

## Single-request results

Rates are arithmetic means of per-request rates. MTP acceptance uses the
sum of native head accepts divided by the sum of native head proposals.

| Workload | Actual input tokens | Requests | Halogen tok/s | Strix Alloy tok/s | Difference | Strix Alloy MTP head |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `pp8192`, full HTTP | 8,184 / 8,182 / 8,181 | 3 | 1,983 | 1,945.53 | −1.89% | — |
| `pp32768`, full HTTP | 32,768 / 32,767 / 32,767 | 3 | 1,876 | 1,968.97 | +4.96% | — |
| `pp131072`, full HTTP | 131,064 / 131,062 / 131,061 | 3 | 1,796 | 1,819.60 | +1.31% | — |
| `bench`, native MTP Decode | 22–41 | 30 | 74.57 | 77.24 | +3.58% | 4,887/6,021 = 81.17% |
| `bench`, serial Decode | 22–41 | 30 | 41.07 | 36.48 | — | — |
| `tg128`, full HTTP | 22–41 | 30 | 74.90 | 68.96 | −7.93% | 2,508/3,126 = 80.23% |

The Prefill sweep follows the publisher's calibrated filler protocol with
one output token. Its local native API Prefill means were 1,977.78,
1,974.97 and 1,792.33 tok/s, respectively. The `bench` capped responses at
256 tokens and returned 143 or 256. Each prompt's output was identical
across the serial and MTP modes. The local MTP mean over complete HTTP
was 75.89 output tok/s. The local serial figure uses the native engine
clock. The publisher's serial clock boundary is unspecified.

Every `tg128` request returned 128 tokens. The identical 163,840-position
profile served 12 requests on November 23 and the remaining 18 on
November 24, with three repetitions for each of the ten prompts. This
combines two collection windows. The first covered only code and proofs,
while the second covered procedures, chat and prose. The combined native
means were 239.22 Prefill and 74.28 Decode tok/s. All 30 native Decode
rates were cross-checked against the engine ledger. The publisher also
reports 76.37 HTTP tok/s for `tg128` in its separate alternating version
comparison.

## Two-slot arrival schedules

The two-slot campaign ran the public code and prose prompts alone, with
simultaneous dispatch, and with B released at A's first visible text.
Each schedule used one excluded warmup and three measured repetitions
per prompt or pair. The raw SSE audit verified all 48 responses, including
warmups. Every measured pair showed overlapping visible delivery. Code
used temperature 0 and prose used 0.7, both with top-p 0.95 and seed 1.

| Workload | Arrival | Actual input A/B | Actual output A/B | Pair HTTP s | Pair HTTP output tok/s | Pooled MTP head |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Code | Simultaneous | 31 / 41 | 377 / 384 | 6.667 | 114.15 | 1,644/1,761 = 93.36% |
| Code | Staggered | 31 / 41 | 377 / 384 | 6.676 | 113.99 | 1,644/1,761 = 93.36% |
| Sampled prose | Simultaneous | 36 / 28 | 337 / 384 | 9.819 | 73.50 | 1,179/1,719 = 68.59% |
| Sampled prose | Staggered | 36 / 28 | 337 / 384 | 9.788 | 73.69 | 1,179/1,719 = 68.59% |

The staggered requests dispatched B a mean 0.270 ms after A's first
visible text for code and 0.316 ms for prose. The paired code answers
matched their corresponding solo runs byte for byte. The sampled prose
answers differed from their solo runs. The local context and shared KV
pool held 32,768 positions, with two configured slots.

Halogen reports 116 tok/s for two code streams and 89 tok/s for two sampled
prose streams over the interval when both streams were generating. Its
test used 16 configured slots, a 384-token output budget and short prompts
whose text was unpublished. Strix Alloy uses the separate public
`eval-prompts.json` prompts. Local pair rates span first dispatch to last
EOF, including Prefill. SSE event counts differed from completion-token
counts, so the local capture establishes overlap duration and full HTTP rates.
[Publisher concurrency results](https://github.com/peonist-ai/halogen-flash-server/blob/dea807d22a638c67553abea876344a8192054a94/docs/configuration.md#speed-by-concurrency-the-previous-default-mode)

### Two 262K windows on Strix Alloy

The BF16 follow-up used two 262,144-position slots over one verified
524,288-position KV pool. It replayed the same short requests with byte-for-byte
identical request bodies. The baseline configured two 32,768-position slots
over one 32,768-position pool.

| Workload | Arrival | 32K profile HTTP tok/s | 262K profile HTTP tok/s | Observed difference | 262K pooled MTP head |
| --- | --- | ---: | ---: | ---: | ---: |
| Code | Simultaneous | 114.15 | 111.75 | −2.10% | 1,644/1,761 = 93.36% |
| Code | Staggered | 113.99 | 111.96 | −1.78% | 1,644/1,761 = 93.36% |
| Sampled prose | Simultaneous | 73.50 | 72.94 | −0.75% | 1,179/1,719 = 68.59% |
| Sampled prose | Staggered | 73.69 | 73.05 | −0.87% | 1,179/1,719 = 68.59% |

All 36 measured responses, including the solo controls, matched the
corresponding 32K responses byte for byte. The paired MTP acceptance
counts were identical at both capacities. The requests still used 28–41
input tokens per stream, and the output cap remained 384. The two profiles
were measured in separate runtime windows. The pair rates cover the entire
HTTP interval.

An isolated test profile used an 18 GiB request-entry floor. The lowest
sampled Windows physical or commit reserve during requests was 20.48 GiB.
The regular single-slot 32K service was restored on port 8840. [262K results
and per-stream phase rates](halogen0207-two262k-comparison-20261124.json)

## Test conditions

The local Windows/WSL2 host ran Halogen 0.20.7 v2 with r2-HT4, Performance
mode, paired 8,192-token Prefill controls, Cache Off and Thinking Off.
Requests in `bench` ran one at a time with 32,768 positions and two
configured slots. The sweep used 163,840 positions and one slot. After starting,
the initial 262,144-position profile had 21.27 GiB of free physical memory,
below the 22 GiB request threshold. The manufacturer used 128 GB Ubuntu
hosts at about 85 W with the default 262,144-position context, 32,768-token
Prefill setting and different slot and KV-pool geometry. The publisher
documents Cache On as its default. The exact cache setting for its
`bench` row is unspecified. [Publisher configuration](https://github.com/peonist-ai/halogen-flash-server/blob/dea807d22a638c67553abea876344a8192054a94/docs/configuration.md#speed-by-concurrency-the-previous-default-mode)

The local HTTP timer runs from dispatch through response EOF in Windows
QPC. Native rates come from engine measurements and the native Decode
ledger. The phase clocks have known discrepancies relative to Windows QPC,
so report the native and HTTP rates under their respective time bases.
[Phase-clock audit](../research/halogen0207-phase-clock-audit-20261123.md)

The [machine-readable results](halogen0207-publisher-comparison-20261124.json)
include per-prompt phase rates, MTP counters, measurement dates, paired
stream results and SHA-256 digests of the retained local evidence.
