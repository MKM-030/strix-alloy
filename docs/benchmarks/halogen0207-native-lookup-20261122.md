# Halogen 0.20.7 native WSL lookup placement

On 22 November 2026 the ext4 lookup candidate completed its first 8,192-token
request in **9.263 s**, versus **10.566 s** and **10.644 s** with the Windows
lookup mount. That saved 1.303–1.381 s across the two controls. The native
lookup read fell from 4.0 s to 2.9 s in the engine log. The warm runs show
similar throughput and identical MTP acceptance. Native lookup remains an
explicit opt-in.

## First 8,192-token request after readiness

| Arm | Whole HTTP (s) | Lookup read (s) | API prefill (s) | API prefill (tok/s) | API decode (tok/s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows before | 10.566091 | 4.0 | 7.8956 | 1,037.540 | 48.483 |
| WSL ext4 | 9.263389 | 2.9 | 6.8474 | 1,196.367 | 53.604 |
| Windows after | 10.644143 | 4.0 | 7.9245 | 1,033.756 | 48.307 |

Each row is one request. The engine reported 131,072 lookup rows on 64
threads in every arm, with read times rounded to 0.1 s. The ext4 arm took
12.33% and 12.97% less whole-HTTP time and showed 15.31% and 15.73% higher
API prefill throughput against the respective controls. All three first
requests accepted 64 of 97 head proposals.

Each arm inherited its existing OS file-cache state, with file residency
unknown. The result describes first requests in these three launches,
with one observation per arm. The first 16K request followed the four 8K
requests and shares much of their prefix.

## Warm requests

| Arm | Input tokens | API prefill (tok/s) | API decode (tok/s) | MTP head accepted/drafted | Whole HTTP mean (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows before | 8,192 | 2,041.429 | 57.826 | 192/291 (65.98%) | 6.248 |
| WSL ext4 | 8,192 | 2,041.106 | 57.818 | 192/291 (65.98%) | 6.249 |
| Windows after | 8,192 | 2,046.056 | 57.696 | 192/291 (65.98%) | 6.242 |
| Windows before | 16,384 | 2,012.595 | 55.646 | 180/279 (64.52%) | 10.465 |
| WSL ext4 | 16,384 | 2,004.989 | 55.661 | 180/279 (64.52%) | 10.498 |
| Windows after | 16,384 | 2,014.951 | 55.536 | 180/279 (64.52%) | 10.461 |

All 24 requests completed. Each arm generated 128 output tokens per request
on the same frozen natural prompts, with one first request excluded and
three warm measurements per input size. Rates are arithmetic means of the
native API phase observations, with RAW observation disabled. Acceptance
pools native head counters. HTTP time spans request dispatch through
response EOF. Output hashes, token counts and length finishes matched
across arms at each size.

The run used Halogen 0.20.7, v2, one 32,768-position slot, paired 8,192-token
prefill settings, the r2-ht4 drafter, temperature 0, seed 1, MTP gate 0.90 and
PLD `3,3`. Prompt cache was Off with `no_store`. Thinking, vision and
decode prefetch were Off. Only the candidate set `engine.lookup_tuning`.
Its separately verified read-only file contains the same lookup tensor.
Engine startup recorded `/candidate/ngram.hgn` for ext4 and
`/ngram-w4b.hgn` for both Windows controls.

The campaign finished at `2026-11-22T18:08:49.181568Z` with all 24 requests
complete and `promote=false`. The stock Windows lookup profile was restored
ready on port 8840, with controller run `559a8afd89394850897c4c64ddc0b745`
and backend run `ca33b8715b394d5c9962b0faeb14ae24`.

## Reproducibility

The local campaign evidence is under
`server/.local/halogen-update-20261122/primary0207/lookup-native-port-v1/lookup-campaign-run-v1`.

| Evidence | SHA-256 |
| --- | --- |
| Package source manifest | `81210ca5a0391056ce1abb67d93ee05ec398f612e99ee194a434b3cea4b23a8a` |
| Frozen 8,192-token request | `2e26413988ce75fcf745a1a143aa3647297349c1516f9d18968e9d1b4da0632d` |
| Frozen 16,384-token request | `0d9cd3c7820d39ebb3c6f8ec4b712b8301e91d2eb2b97c52d9be678699ce6b3d` |
| `before/summary.json` | `8e218422e0aa80ee910b7a502a00a10e3769dc0af1f104224fbe8083319c5ea9` |
| `candidate/summary.json` | `492db798de191ead151cc707ac77f75ebe10a718660bad912a2af8388f17bd99` |
| `after/summary.json` | `4c30a7ee9d4166532f962561c9fbe200135803e14b1e1d46f401bd2b2644faaa` |
| Final `handle.json` | `42d53b06365aca70827019d972563e1c0b013b0e23f5bd01dfb4cd4091a51fb9` |
| `restore-stock-launch.ready.json` | `1b5841f1620a8992ebbcbc74406283769ca7775f046ce55237d38497834446e0` |
