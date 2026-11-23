# Halogen 0.20.7 fixed MTP depth two on three natural 8K tasks

The stock MTP cost policy delivered output faster on all three tasks. On the
CPython release-note prompt it reached **69.675 and 69.512 native decode
tokens/s** in the two stock windows, with **79.80% native head acceptance** in
both and **2,065.713 and 2,046.977 prefill tokens/s**, respectively. The rates
are medians of three measured requests per workload and window. Acceptance is
pooled over those requests. The stock policy remains the serving default.

| Workload | Window | API prefill tok/s | API decode tok/s | Native head accepted/drafted | First text to EOF (s) | Delivered output tok/s | Full HTTP (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pathlib code review | Stock before | 2,069.262 | 67.768 | 228/279 (81.72%) | 1.884 | 67.955 | 5.893 |
| Pathlib code review | Fixed2 | 2,062.489 | 65.150 | 225/306 (73.53%) | 1.960 | 65.299 | 5.961 |
| Pathlib code review | Stock after | 2,027.522 | 66.970 | 228/279 (81.72%) | 1.884 | 67.951 | 5.905 |
| CPython release notes | Stock before | 2,065.713 | 69.675 | 237/297 (79.80%) | 1.834 | 69.801 | 5.831 |
| CPython release notes | Fixed2 | 2,059.430 | 60.692 | 213/330 (64.55%) | 2.101 | 60.912 | 6.115 |
| CPython release notes | Stock after | 2,046.977 | 69.512 | 237/297 (79.80%) | 1.838 | 69.637 | 5.874 |
| War and Peace | Stock before | 1,918.366 | 61.385 | 216/318 (67.92%) | 2.075 | 61.686 | 6.087 |
| War and Peace | Fixed2 | 2,073.032 | 56.710 | 201/354 (56.78%) | 2.252 | 56.833 | 6.257 |
| War and Peace | Stock after | 2,038.521 | 61.636 | 216/318 (67.92%) | 2.072 | 61.765 | 6.145 |

Each prompt contained **8,192 actual rendered input tokens**. All 36 requests
returned 128 output tokens with finish reason `length`. Each task produced
byte-identical output across both stock windows, the Fixed2 window and their
warmups. All three windows used the same resolved joint-round scheduler. Native
head counters were stable within each window and identical between the stock
bookends. Native lookup and grammar accounted for zero rounds, drafts and
acceptances in these requests.

## Fixed2 versus each stock window

Positive latency changes indicate a slower result. The acceptance change is
the same against both stock windows.

| Workload | First text to EOF vs before | First text to EOF vs after | Full HTTP vs before | Full HTTP vs after | Head acceptance change |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pathlib code review | +4.07% | +4.06% | +1.16% | +0.96% | -8.19 pp |
| CPython release notes | +14.59% | +14.32% | +4.88% | +4.09% | -15.25 pp |
| War and Peace | +8.54% | +8.68% | +2.78% | +1.82% | -11.14 pp |

Every measured Fixed2 first-text-to-EOF time was slower than every measured
stock time for the corresponding task. Fixed2 proposed more head draft tokens
and had fewer accepted head tokens on each task. The earlier 4.50–4.70% Fixed2
delivery gain on a different 8K novel prefix was specific to that workload.
[Earlier 8K and 16K Fixed2 benchmark](halogen0207-fixed-mtp-depth-two-20261123.md)

## Method and evidence

- Halogen 0.20.7 v2, official r2-HT4 head, Windows REV:N Performance, one
  32,768-position BF16 slot, an 8,192-token prefill arena and chunk, normal auto
  concurrency, and PLD `3,3`. The candidate set `HALOGEN_MTP_DEPTH=2` and
  `HALOGEN_MTP_GATE_P=0`. Stock used the calibrated depth rule and gate `0.90`.
- The three workload sources were CPython `pathlib.py`, CPython maintenance
  release notes, and a disjoint late passage of *War and Peace*. Requests used
  identical frozen bytes within each task, temperature `0`, seed `1`, Thinking
  Off, Vision Off, and Cache Off. Each task ran one excluded warmup and three
  measured requests in each window, for 27 measured requests and nine warmups.
  The same balanced rotation was used in all three windows.
- Prefill and decode use the native API phase counters. First text to EOF and
  full HTTP use Windows QPC. Delivered output tokens/s divides actual output
  length by the Windows first-text-to-EOF interval. Head acceptance sums
  accepted and drafted head tokens over the three measured requests.
- The independent replay recovered the exact UTF-8 output, token counts,
  finish reason and timings from the raw SSE captures. All 36 native completion
  lines matched request order, input/output counts and speculation rounds. The
  lowest sampled request reserve was 26.12 GiB, taking the lower of available
  physical memory and commit headroom. The coordinator completed the bracket
  and restored the regular stock service on port 8840. A separate readiness
  check confirmed the default profile, zero private listeners and zero
  measurement helpers.

Raw evidence is retained under
`server/.local/halogen-update-20261122/primary0207/fixed-depth-two-natural-generalization-prep-v1/fixed-depth-two-generalization-run-v1`.

| Evidence | SHA-256 |
| --- | --- |
| Frozen fixture manifest | `bbf82b50b7e038f039e60f20786b8309d5a21eb86ac61f827b785a0d533032fd` |
| Stock before summary | `2cb77e88697a80ffaa7ec16d995149d725431d24df9032a20df2f022c6f7368a` |
| Fixed2 summary | `137c0d4fa6b3cd2c38599e5816084d3e835b4b51d5a22a043982b5178807239d` |
| Stock after summary | `0ce9c4c188d5f5e48db8e56ae47be7c3738b9a10cddfdb6aa379af94ed502b61` |
| Independent SSE and native replay | `dbb86504f16dd8241f5aca1b3e843cdae4d41c0fd645f458502a573f73adf7c1` |
| Terminal lifecycle handle | `ca871887f27a2baf770bca6aedcecfdcfe94e2dc2262c055a0c5dd6f7bc9bd00` |
| Separate post-restore readiness check | `e2fea012fd2cf6cf1c099940884aec3eb24f3b12e83e19a74b88b156bef81d73` |
