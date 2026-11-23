# Halogen 0.20.7 HT4 confidence rule on natural 8K and 16K inputs

The native confidence rule at 0.90 increased 8K response time by
1.8–2.4% over the two cost-rule controls. First visible text to EOF
took 4.7–4.9% longer. At 16K, the delivery interval rose 1.0–1.1%
and total HTTP time rose 0.23–0.45%. The 8K confidence arm used four
additional verification rounds and accepted four fewer draft tokens per
response. At 16K it used two more rounds and accepted two fewer draft
tokens. The regular Halogen profile uses the image's cost rule.

## Measured warm requests

| Actual input | MTP rule and window | API Prefill tok/s | API Decode tok/s | Native MTP accepted/drafted | Head rounds per request | First text to EOF | Full Windows HTTP |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 8,192 | Cost before | 2,071.84 | 57.81 | 192/291 (65.98%) | 62 | 2.215 s | 6.234 s |
| 8,192 | Confidence 0.90 | 2,047.31 | 55.22 | 180/288 (62.50%) | 66 | 2.318 s | 6.385 s |
| 8,192 | Cost after | 2,049.97 | 57.90 | 192/291 (65.98%) | 62 | 2.211 s | 6.275 s |
| 16,384 | Cost before | 2,045.83 | 55.26 | 180/279 (64.52%) | 66 | 2.316 s | 10.378 s |
| 16,384 | Confidence 0.90 | 2,045.99 | 54.68 | 174/273 (63.74%) | 68 | 2.341 s | 10.424 s |
| 16,384 | Cost after | 2,044.48 | 54.39 | 180/279 (64.52%) | 66 | 2.319 s | 10.400 s |

The default cost rule and the confidence candidate both use the original
r2-HT4 head, with room for up to seven proposals. The measured 8K
confidence arm and the earlier fixed-depth-two arm each accepted 62.50%
of proposals. The fixed-depth-two arm accepted 70 tokens across 56 rounds
per request in its own comparison.
[Fixed-depth-two benchmark](halogen0207-fixed-mtp-depth-two-20261123.md)

## Method

Each window used one 32K BF16 slot, paired 8,192-token prefill limits,
the exact non-repetitive novel prefixes, 128 output tokens, temperature 0,
seed 1, Thinking Off and Cache Off on the `REV:N Performance` profile.
One warmup per input and window was excluded from each three-request
mean. Acceptance pools native head counts. The output bytes and token
counts matched across all 24 responses. Lookup and grammar proposal
counts were zero. The API fields have their native clock scope. Full
HTTP and first text to EOF use Windows QPC.

The candidate sets `HALOGEN_MTP_GATE_RULE=gate`. Both controls inherit
`cost` from the pinned 0.20.7 image. All three have threshold 0.90 in
the profile and run the same scheduler. The bounded managed option,
container entries and native listener statements establish the single
configured treatment. The benchmark uses the stock GPU and leaves the
native copy and timing observers disabled.

The byte-exact request hashes are
`6487438c42d2e1faa3d0365130e064acb2e7a243e3c24c868b3f04bc6cb4439d` for 8K and
`5ab14773484c4d0ea2f9f817b6be3a8ce09b10e9487dcb0b18ae9d4992bdb7ba` for 16K.
The native logs, raw SSE streams and QPC timings live under
`server/.local/halogen-update-20261122/primary0207/mtp-confidence-rule-prep-v1/confidence-rule-run-v1`.
An independent replay reconstructed all 24 responses, native head
counters and timing boundaries. The minimum sampled physical or commit
reserve during requests was 27.71 GiB. The campaign restored Halogen
on port 8840 and closed the private listener. The final checks passed
for the gateway, native backend, ServiceNow router, Native Voice,
TTS and ASR.

| Local artifact | SHA-256 |
| --- | --- |
| Completed campaign | `e1a4efca4e7269b36175d6738ed0795ee9ca93d34cca7e903a4b48159247c09a` |
| Independent SSE replay | `677c0598d830c1cb6263bfd35202aa32e40939343c5ae10bd2142ea01c890b37` |
| Candidate activation | `70d55b628ba43b27203caa7253bc8abe2adc529186fdadbb3911e2406d534356` |
| Restored service health | `9599059b678ed769498e825ce286843552e8c9306bfa1964d2165ec06628c7fa` |

## NPU Prefill representation check

The Gufo fork measured 8K Prefill of 1,715 tok/s on its GPU path and
1,851 tok/s with GPU and NPU on Inkling 2 Mini. Its native Linux
implementation packs shared buffers, overlaps two prefill banks and
waits for the relevant NPU projection before consuming the buffer on
the GPU. The Halogen Windows/WSL integration still needs a qualified
ownership and fence path for those shared buffers. [Gufo benchmark](https://github.com/mikealanni/gufo/blob/499cd1a866fbf43798b1070a2082bedb0040c71a/docs/models/inkling/BENCHMARKS.md#L3-L15) · [Pinned Gufo engine](https://github.com/mikealanni/gufo/blob/499cd1a866fbf43798b1070a2082bedb0040c71a/src/models/inkling/gpu/engine.hip.cpp#L4151-L4227)

A CPU calculation reproduced all 288 sampled native BF16 outputs from
an archived Halogen 0.16.2 layer-zero QKV projection. For every group of
eight values it enumerated the finite shared exponents and gave each
value the closest signed mantissa. Even under this optimistic output
encoding, at least 198 of 288 BF16 values must change and at least 24
exceed the earlier NPU development envelope of `rtol=0.03, atol=0.003`.
This tests the representational limit of one shared exponent per eight
output values on that historical slice. The CPU screen introduces zero
GPU/NPU requests. [Original QKV witness](../research/halogen-prefill-ht-capture-20261006.md) · [Historical tolerance](../research/halogen-npu-precision-20261004.md) · [Gufo output decoding](https://github.com/mikealanni/gufo/blob/499cd1a866fbf43798b1070a2082bedb0040c71a/src/models/qwen38_flash_next/kernels/rocm/kernels.hip.cpp#L9737-L9772)

The CPU result is retained in
`server/.local/halogen-update-20261122/primary0207/inkling-bfp-cpu-prep-v1/screen-result.json`,
SHA-256 `1732943da7fd573ec5b01621e0abbbc66e20071ba0f1fd41f21181d581a698f6`.
