# Halogen 0.20.7 publisher benchmark replay on Windows/WSL2

The same serving instance ran all ten prompts from the 0.20.7 image.
MTP averaged **71.21 tok/s in the API Decode field** and **74.77 output
tok/s over complete HTTP requests timed on Windows**. The 30 MTP requests
accepted **4,887 of 6,021 neural drafts (81.17%)**. They returned the same
text as the 30 serial controls and took **53.30% less total HTTP time**.

| Mode | Requests | API Decode mean (tok/s) | Mean output / HTTP (tok/s) | Pooled output / HTTP (tok/s) | Head acceptance |
| --- | ---: | ---: | ---: | ---: | ---: |
| Serial | 30 | 32.93 | 35.06 | 33.95 | — |
| MTP | 30 | 71.21 | 74.77 | 72.69 | 4,887/6,021 (81.17%) |

Both modes produced 7,341 output tokens. Complete HTTP time was 216.236 s
for serial and 100.990 s for MTP. Accepted and proposed tokens came from
the neural head. The API reported zero lookup and grammar drafts throughout.

| Publisher prompt | Actual input / output tokens | API MTP Decode (tok/s) | Mean output / HTTP (tok/s) | MTP head accepted / drafted |
| --- | ---: | ---: | ---: | ---: |
| code_a | 31 / 256 | 97.15 | 100.92 | 624 / 687 |
| code_b | 41 / 256 | 83.28 | 86.06 | 579 / 708 |
| proof_a | 24 / 256 | 83.15 | 87.60 | 585 / 711 |
| proof_b | 22 / 256 | 85.19 | 89.71 | 579 / 666 |
| proc_a | 27 / 256 | 74.08 | 77.85 | 525 / 633 |
| proc_b | 30 / 256 | 61.47 | 64.53 | 459 / 591 |
| chat_a | 26 / 143 | 48.00 | 50.23 | 207 / 324 |
| chat_b | 24 / 256 | 61.81 | 65.40 | 471 / 591 |
| prose_a | 36 / 256 | 57.74 | 61.16 | 414 / 552 |
| prose_b | 28 / 256 | 60.26 | 64.24 | 444 / 558 |

## 8K synthetic Prefill

The image's `sweep` workload generator produced 8,184, 8,182, and 8,181
actual input tokens, each with a one-token response. Across the three
requests, input tokens divided by complete Windows HTTP time averaged
**2,040.67 tok/s**. The API Prefill mean was **1,890.59 tok/s**.
Five light calibration calls established the tokenizer overhead and
lead-in lengths. This synthetic filler series is separate from the
[8,192- and 16,384-token novel comparison](halogen0207-kv8-natural-8k16k-20261123.md).

## Comparison conditions

The input text, case order, temperature 0, low effort and 256-token cap
came from the shipped `bench-serving.py` and `eval-prompts.json`.
The caller retained all three serial/MTP pairs per prompt. The production
gateway on port 8840 required the serving model ID in the JSON body.
An earlier preflight submission without it received HTTP 400 at the
gateway. The replay used the stock 32K single-slot BF16 v2/HT4 profile
with prompt cache Off, Thinking Off, and `REV:N Performance`. Every
measured response showed zero prompt-cache reuse. The lowest sampled
physical or commit reserve was 26.92 GiB.

The publisher's 74.57 tok/s ten-shape figure is an engine-ledger Decode
mean on native Ubuntu. The local API mean is **4.50% lower** as reported.
All 60 local API phase sums exceeded their Windows HTTP intervals.
The two local timing columns retain their separate denominators and
unadjusted values. The publisher's separate English-prose figure uses
its text-category workload. The two short prose cases here averaged
59.00 API Decode tok/s. [Publisher methodology](https://github.com/peonist-ai/halogen-flash-server/blob/dea807d22a638c67553abea876344a8192054a94/docs/performance.md)
· [WSL phase-clock audit](../research/halogen0207-phase-clock-audit-20261123.md).

The earlier 0.18.15 replay used the same ten prompt texts and recorded
50.13 native Decode tok/s and 48.62 pooled output tok/s over HTTP.
Its MTP requests reused cached input and produced a different completion
length in `chat_a`. This comparison across versions is descriptive.
[0.18.15 record](halogen01815-comparison-20261025.md#abschließende-kurzserie-und-endzustand).

## GPU operating observations

A read-only ADLX probe sampled the Radeon 8060S 75 times during part of
the run. Fifty-two observations fit fully inside a measured short HTTP
interval. The 18 inside MTP requests had a median of **2,836 MHz** and a
maximum of **2,895 MHz**. The 34 inside serial requests had a median of
2,652.5 MHz. These are adapter-level whole-request observations. ADLX
reported manual GFX, VRAM, and power tuning unavailable for this adapter.
The probe applied no settings.

## Evidence

The collector and sensor exited normally. The same BF16 service remained
ready on port 8840. Raw responses, independent QPC pairs, and the audit
are retained locally under
`server/.local/halogen-update-20261122/primary0207/publisher-bench-prep-v1/publisher-run-v2`.

| Artifact | SHA-256 |
| --- | --- |
| Publisher prompt file | `23df9feb5ec2b343f675bb08dc6c0c2286e17dd6d73acf4e7d363d0c0c49922b` |
| Publisher `bench-serving.py` | `59c4cc804fe9583cc950bcd54af8e3383ee21dec1b4424eaff3d4e077ba51f93` |
| Publisher `halogen-bench.py` | `76229d4343cc5fb6f9326ace64727f6296be2e4ea3922425d7367f19cd0048db` |
| Completed run handle | `b149e9c2c0ee8756b91208479f0d0190cc4d8f0ac33ea029797d74af1930e3da` |
| Numeric summary | `db61a877385406ab43cf769a814bd1c58fbf38fb36106e7f57736463f6d993b6` |
| Independent replay audit | `f39600c6ce7279e9ab9e021255ad68807b2b43c00cd148c08c7401bc860d658b` |
| ADLX samples | `fe319a4f6595aaf6c2a909e4d1467e35d765f2c679ce4abe8ca53366cafddfd3` |
| Final service health | `78fd165fd33cfd25e6f68c56e5c5f416ef8d6ff3b5113ad2477323618a3ca11e` |
