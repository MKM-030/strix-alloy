# Halogen 0.20.7 tool-output wrapper on longer public-source excerpts

Wrapping the same tool result in `output` cut median Windows HTTP time by
**12.47–12.65%** on a CPython source excerpt and **16.06–16.25%** on a passage
from *War and Peace*, compared with the two `result` controls. All 24 requests
returned the exact expected arguments. Each timed triplet favored `output`
against both controls.

| Workload | Wrapper | Actual input / output tokens | API prefill tok/s | API decode tok/s | MTP head accepted/drafted | LOOK accepted/drafted | First tool event (s) | First tool event to EOF (s) | Full HTTP (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CPython `pathlib.py` | `result` before | 5,274 / 521 | 2,005.78 | 106.29 | 1311/1398 (93.78%) | 0/0 | 2.729 | 4.847 | 7.590 |
| CPython `pathlib.py` | `output` | 5,274 / 521 | 2,019.53 | 131.35 | 90/90 (100.00%) | 1260/1260 (100.00%) | 2.717 | 3.913 | 6.630 |
| CPython `pathlib.py` | `result` after | 5,274 / 521 | 2,016.44 | 106.02 | 1311/1398 (93.78%) | 0/0 | 2.717 | 4.858 | 7.575 |
| *War and Peace* | `result` before | 5,265 / 663 | 2,010.46 | 99.24 | 1653/1854 (89.16%) | 0/0 | 2.721 | 6.503 | 9.230 |
| *War and Peace* | `output` | 5,265 / 663 | 1,861.28 | 125.59 | 81/102 (79.41%) | 1638/1638 (100.00%) | 2.766 | 4.982 | 7.748 |
| *War and Peace* | `result` after | 5,265 / 663 | 1,995.83 | 100.87 | 1653/1854 (89.16%) | 0/0 | 2.736 | 6.514 | 9.251 |

For CPython, median first tool event to EOF fell **19.27–19.44%**.
The candidate committed 420 lookup tokens per reply in 60 LOOK rounds and
reduced total verification rounds from 77 to 66. For *War and Peace*, the
corresponding interval fell **23.40–23.53%**. The candidate committed 546
lookup tokens per reply in 78 LOOK rounds and reduced total verification
rounds from 107 to 85. The native counters reported seven accepted LOOK
tokens in every lookup round for both excerpts. The two `result` controls
recorded zero LOOK rounds on each task.

On the prose excerpt, neural MTP head acceptance fell from 89.16% to 79.41%
as the verification mix shifted toward LOOK. Median API prefill was also
6.74–7.42% lower, and the first tool event took 1.10–1.67% longer. Faster
delivery after that event still reduced full request time.

## Method

Each task asked a forced, strict preview function to copy a contiguous
multiline passage between two plain-text markers. The tool result carried the
same source and reference context in both arms. Changing `result` to
`output` replaced one rendered prompt token. The pinned API projected the
plain source into an additional LOOK view with 4,555 IDs for CPython and
4,663 for *War and Peace*. The same projection produced zero additional LOOK
IDs for `result`. The live native counters and completion logs confirmed the
shift to lookup drafts.

One excluded A/B/A triplet and three timed triplets ran per task, with
alternating task order. Each task returned its exact UTF-8 argument bytes
(2,171 for CPython and 2,657 for *War and Peace*) and the corresponding
521 or 663 output tokens in every repetition. All calls ended with
`tool_calls`. No tool executed and no external service received a request.

The same running Halogen 0.20.7 v2/HT4 service on port 8840 used one 32K BF16
slot, the stock cost policy, PLD `3,3`, greedy seed 1 and Cache, Thinking and
Vision Off. The Windows REV:N Performance profile was active. Latencies in
the table are QPC medians. API rates are medians of native phase fields.
Acceptance counts pool the three measured requests per window. The lowest
measured request reserve was 28.74 GiB. A separate post-run check confirmed
that the same normal server remained ready with zero private listeners or
measurement helpers.

The measured gain applies to strict calls that reproduce substantial existing
tool text. `output` exposes the text to LOOK while preserving the tool role,
call ID and exact string. This extends the earlier fictional-incident result
to longer source-code and prose copy tasks.
[Earlier wrapper benchmark](halogen0207-tool-output-wrapper-20261123.md)

## Evidence

Raw SSE, QPC receipts and native completion logs are under
`server/.local/halogen-update-20261122/primary0207/public-copy-lookup-wrapper-prep-v1/run-public-sources-v1`.
The independent review regenerated the medians from these raw files and
confirmed request hashes, exact argument bytes, native token counts, strict
tool enforcement, and all 24 completions.

| Evidence | SHA-256 |
| --- | --- |
| Frozen fixture manifest | `bce1eb8a5c4345222b36f1d0ec2c0eadf076c41ab9939a736f4757171bd1be2f` |
| Executed campaign | `4fa8d817cf12fcf7f99c6e4acb6901554cddf19f63105958508d0abb3cb526d9` |
| Successful campaign summary | `aa40f999c2cc9aebdf70ced72b642836639681c52e35b4748952bf05c9f3638c` |
| Independent raw replay, `independent-public-copy-replay.json` | `83b0b240faefc1237d5597dab3b6b8b7279afde3175903c0c8211662660b2a3b` |
| Separate post-run readiness | `0c1e79b4a20fc1365491b14f7ac022a6c3eb4b51e2864d83d4004872184e303c` |
