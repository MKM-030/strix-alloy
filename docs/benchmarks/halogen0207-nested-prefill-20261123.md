# Halogen 0.20.7 nested prefill and short-request latency

Admitting the short request during the long request's prefill reduced its
time to first visible text from **9.04–9.05 s to 1.25 s**, about **86%**.
The first quarter of the short response arrived only **0.22–0.23 s earlier**.
The long request's first text arrived **1.23–1.44 s later** and both requests
took **3.05% longer** to finish as a pair. Both outputs were byte-identical
in every window. The regular service uses the single-slot profile.

| Native nested limit | Actual input | First text | First quarter of output bytes | Full HTTP | API Prefill tok/s | API Decode tok/s | MTP head accepted/drafted |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,024 before | 1,536 | 9.045 s | 9.861 s | 12.085 s | 1,606.73 | 42.10 | 195/267 (73.03%) |
| 2,048 candidate | 1,536 | 1.247 s | 9.631 s | 11.858 s | 1,739.37 | 12.06 | 192/264 (72.73%) |
| 1,024 after | 1,536 | 9.037 s | 9.853 s | 12.068 s | 1,622.23 | 42.23 | 195/267 (73.03%) |
| 1,024 before | 16,384 | 8.091 s | 9.820 s | 12.107 s | 2,035.37 | 31.87 | 192/285 (67.37%) |
| 2,048 candidate | 16,384 | 9.535 s | 10.402 s | 12.507 s | 1,725.51 | 43.08 | 180/273 (65.93%) |
| 1,024 after | 16,384 | 8.308 s | 9.828 s | 12.106 s | 2,036.05 | 31.99 | 192/285 (67.37%) |

Each row averages three measured requests after an excluded warmup pair.
Each request generated 128 tokens from an exact natural-text prefix with
temperature 0, seed 1, Thinking Off, Vision Off and Cache Off. One Halogen
0.20.7 v2/r2-HT4 engine ran two slots over the same 32,768-token BF16 KV pool.
Windows QPC measures delivery and complete HTTP. The API fields retain
Halogen's native phase timings during interleaved work. The short candidate's
largest gap between visible frames averaged 630 ms, up from 64–82 ms in
the two controls. Pair makespan was 12.507 s, up from about 12.137 s.

The sole treatment was `HALOGEN_ADMIT_NEST_MAX=2048`. The two stock windows
omitted it and reported the native 1,024-token limit. The same opt-in
`HALOGEN_SERVE_TRACE=1` applied throughout. The guest monotonic probes
bound arrival of the short HTTP headers before the long request reached
8,192 tokens, with at least 3.81 s of margin in the measured pairs.
Native traces separately tied the entire short request to its long parent
in all three candidate pairs. Both controls recorded zero native nestings.

The first live trace attempt exposed that the 8,192-token progress line
and the native 0–16,384 parent-call counter report different scopes.
The corrected parser validates both records by request ID and reconciles
the parent count with the whole-child trace. The earlier warmup is
excluded from the comparison. The lowest sampled reserve was 28.27 GiB.
The coordinator restored Halogen on port 8840. Authenticated model health
and ServiceNow routing, Native Voice, TTS and ASR readiness passed.

The artifacts are under
`server/.local/halogen-update-20261122/primary0207/admit-nest-native-clock-prep-v4/nested-admission-run-v2`.

| Evidence | SHA-256 |
| --- | --- |
| Completed comparison | `a9162ce7d662f0b34506595f8fdae381e606e263088521e6bec24374763846e7` |
| Independent replay of retained SSE | `d046577b02abbe6fb74d2472a37d1d2555765a4b5a9af9985bf8db76a27091ee` |
| Stock before cohort | `11aabcaa1c9eba770cfc6d33f793dbcd2b75a6bb4673f6b9cde5777053a52350` |
| Candidate cohort | `dfbfae96f2d0285cae4dd94f35389a865633686866c4a5e3c8fdf713b31cc6a1` |
| Stock after cohort | `aa08f9203cb7fd4f80601841280714ed29efc408fe4ae493746d3fdf72091b29` |
| Terminal coordinator record | `bcb832989a081109e0ad723cb0873d7505367289336782c24cb8e2058ac0382f` |
| Restored service readiness | `45fd35adf2927a451429841d64f89f10ba886c84512e1d3493ab0af31e7a9a33` |
