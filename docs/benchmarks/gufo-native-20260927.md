# Native Windows GUFO: measured progress

27 September 2026, Qwen3.8 Flash Next. MTP draft cap 3 improved sustained decode over cap 1 by
**6.4% greedy / 10.1% sampled** in our matched local test. This is experimental
native Windows inference, not a finished installer or general-purpose service.
The later service-policy source patch has not produced these measurements.

## Matched local results

Tokens/s, mean ± sample standard deviation, three repetitions per cell.
Same IQ4_XS weights, request bodies and order; one session, 4,096-token capacity,
thinking off and cache bypass. MTP uses the shared Q8_0 sidecar, full vocabulary
and length policy. AR means no speculative decoding.

| Measurement (actual input/output tokens) | AR | MTP cap 1 | MTP cap 3 |
|---|---:|---:|---:|
| Cold HTTP prefill (2,047/1) | 875.47 ± 9.02 | 795.66 ± 10.12 | 795.73 ± 13.79 |
| Engine prefill (same requests) | 905.93 ± 8.58 | 827.58 ± 9.54 | 829.00 ± 16.06 |
| Sustained engine decode, greedy (71/256) | 27.89 ± 0.02 | 33.83 ± 0.24 | 35.99 ± 0.46 |
| Sustained engine decode, sampled (71/256) | 27.57 ± 0.05 | 34.25 ± 1.16 | 37.71 ± 0.88 |

HTTP prefill includes transport, preparation and one output token; engine rates
use native timing counters. "Cold" here means no prompt-cache reuse, not cold
storage or a freshly started model. Do not mix these timing boundaries. The sustained
answers hit the 256-token budget before completing the requested runbook; this
is token throughput, not completed-task throughput. Context capacity is not
occupied input length. The three configurations ran in separate ordered
processes, not randomized/interleaved trials.

Short-answer cap-3 results were higher: **54.53 ± 0.30 tok/s** for German JSON
(39 output tokens), and **52.85 ± 0.24** for a greedy tool call (32 tokens).
Neither is a sustained-chat average. All 15 greedy answer pairs matched the
AR controls. Full instruction compliance was 17/30 in each condition: code
answers added unwanted fences and long answers were truncated. MTP acceptance
was 1,542/2,082 proposals (74.06%); aggregate counters do not prove every
draft-depth path executed. Cold prefill remained about 9% below AR.

## Halogen-style HTTP prefill comparison

Historical deployment comparison, **not an isolated engine or OS speedup**.
Same filler/calibration and one-output HTTP measurement for our two deployments;
no prompt-cache hits. Local cells retain all three repetitions (mean ± sample
SD). The GUFO column uses the completed **16k-capacity AR run**, not the 4k
AR/MTP runs above. Author figures are published references, not our measurements.

| Requested PP size (our actual input/output) | Halogen Linux, author reference | Our WSL2 Halogen 0.13.8, serial | Our native GUFO, AR/16k |
|---|---:|---:|---:|
| 2048 (2047/1) | 812 | 820.95 ± 32.72 | 849.01 ± 11.54 |
| 8192 (8185/1) | 1041 | 783.39 ± 85.23 | 901.41 ± 19.51 |

Our WSL2 2k result is close to the published reference; its 8k result is lower.
This does not establish general Linux/Windows parity. The deployments differ
in model format/quantization (Halogen HGN w4b versus GUFO GGUF IQ4_XS), version,
context capacity (WSL2 32k versus GUFO 16k), carve (32 versus 64 GiB), and run
conditions. WSL2 restart/first-request failures remain documented separately;
these are retained successful benchmark runs, not cold-start guarantees.

Decode must stay in separate recipe groups: our historical Halogen ten-prompt
MTP mean was **41.20 tok/s** across 30 requests. The GUFO sustained runbook
measurements above are not that corpus, so they cannot establish a decode win
or loss against it. Native Strix Alloy/PROJFIX's synthetic llama-bench and
single-prompt served results likewise do not fill this table. Published GUFO
stage-timed/warmed PP is not interchangeable with one-output HTTP PP.

Reference: [pinned Halogen README](https://github.com/peonist-ai/halogen-flash-server/blob/c8270bb31cd824a0bf53fe9ecf80059c13e7a5bf/README.md#served-throughput-end-to-end-over-http).
Local sources: `C:\Projects\strix-alloy-wsl2\docs\benchmarks\upstream-20260924.md`
and its original size log; research report `gufo-native-ar16k-v3-20260926.md`
and result SHA-256 `A813E83F9EBF362D065DA73E0F7A25ED563CBB1CF0C9888952BC8A679A099809`.
The 27 September read-only check revalidated all six GUFO PP request hashes,
counts, means and sample SDs. WSL2 HTTP statistics come from the original client
log, not a reconstruction from its differently timed engine CSV. The full
four-way recipe/caveat map is `halogen-alloy-gufo-comparison-20260926.md` in the
research archive. No model was rerun to add this section.

## Memory and status

Cap 3 reported **66.114 GiB (70.99 GB)** device usage after loading. Sampled
adapter-total peak was 67.614 GiB; minimum available Windows physical memory
was 44.104 GiB. These overlapping counters must not be added. All 36 requests,
owned shutdown and recovery checks completed. The test server is stopped.
These are sampled observations, not guaranteed allocation ceilings or approval
for arbitrary context sizes/concurrency. No driver, carve or OS setting changed.

## What the additional Reddit reference changes

The following community comparison was checked on 27 September. All rates
are tokens/s; our cells use mean plus/minus sample SD over three repetitions.
The community columns are author-reported, not locally reproduced results.

| Measurement | Our Halogen WSL2 | Our native GUFO | Community GUFO Windows port | Wordweaver Windows fork |
|---|---:|---:|---:|---:|
| Model format | HGN w4b | GGUF IQ4_XS | GGUF UD-Q4_K_XL | GGUF IQ4_XS |
| Filler PP2048, HTTP for our runs | 820.95 +/- 32.72 | 849.01 +/- 11.54 | No matched figure | 994 |
| Filler PP8192, HTTP for our runs | 783.39 +/- 85.23 | 901.41 +/- 19.51 | No matched figure | 1026 |
| Filler PP32768 | Not measured in this suite | Not yet measured | No matched figure | 1015 |
| Halogen ten-prompt decode, MTP mean | 41.20 | Not yet measured | 43.0 | 47.6 |
| Our sustained runbook, AR greedy | Different corpus | 27.89 +/- 0.02 | Not reported | Not reported |
| Our sustained runbook, MTP cap 3 greedy | Different corpus | 35.99 +/- 0.46 | Not reported | Not reported |
| Our sustained runbook, MTP cap 3 sampled | Different corpus | 37.71 +/- 0.88 | Not reported | Not reported |

The Reddit post's main table supplies the Wordweaver figures; the GUFO Windows
port contributor's comment supplies 43.0 on Halogen's ten prompts. Wordweaver
describes a custom native HIP llama.cpp fork on a 60-70 W laptop, not GUFO,
and had no public repository in the checked post. Neither contributor supplies
the complete raw repetitions and timing boundaries needed to establish a
controlled cross-engine comparison here. Our GUFO PP cells are AR at 16k
capacity; its runbook decode cells are at 4k capacity. They must not be combined
into an implied single configuration or substituted for its missing Halogen
ten-prompt result. See the local timing, quantization and configuration caveats
above; these numbers do not establish Windows/Linux parity or a causal gain.

The [Wordweaver discussion](https://www.reddit.com/r/StrixHalo/comments/1wqsv03/yet_another_windows_strix_halo_q38fn_attempt/)
supports isolated tests of prompt lookup on repetitive versus ordinary text,
and the sampled MTP survival policy. Its author has no public fork in the
checked post. Our pinned GUFO Windows port already contains its documented
Windows execution fixes. Vocabulary pruning remains separate from the
multilingual baseline. None of the community headline numbers establishes
a matched Windows/Linux or engine comparison.

## Reproducibility

Measured source: pixmaate/gufo `cff564964e8506c0abb3e530cecb55332187ac6c`;
TheRock 10.2.0, gfx1151; Windows 11, Ryzen AI Max+ 395 / Radeon 8060S, 128 GB,
existing 64-GiB carve. Unsloth UD-IQ4_XS revision
`38bb39ee97821de2c9009abb7e93950eec396e66`. Greedy uses T0/top-k0/top-p1/seed42;
sampled uses T1/top-k20/top-p0.95/seeds1001–1003. Exact corpus and explicit
sampler fields are in the repository's `matched_recipes` harness.

The local research archive (outside this repository) retains all requests,
responses, manifests, telemetry and independent numerical/semantic reviews in
`C:\Projects\strix-alloy-research\reports`. Full report:
`gufo-matched-draft3-20260927.md`. Raw result identities:

| Run | Result SHA-256 |
|---|---|
| AR v2 | `97DC20DA7FE2BE184136C94EE27A4118F7F53845A0DAA74696141D3285E6FE5C` |
| MTP cap 1 | `CFC1882BFF7FB8B7D1200E70EB24AC6E57D7B04B54F02B5F5CFD18A08414A67E` |
| MTP cap 3 | `5248F816FB0DAC73685C9E7A8E5F29C8C700AB1CB7C6BF3C6BE3023C0FB39D70` |

Raw evidence needs a portable, reviewed export before a public release.
Exact upstream benchmark recipes, PP32K, small concurrency and reusable
build/start/status/stop qualification remain unfinished. The consumed finite
test profiles must not be replayed by deleting their attempt markers.
