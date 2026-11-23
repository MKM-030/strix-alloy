# Halogen 0.20.7 fixed MTP depth two

On the frozen 8,192-token novel prefix, fixed depth two reached **60.496
API Decode tok/s** with byte-identical output. The two stock windows reached
57.779 and 57.659 tok/s. Windows time from first text to EOF improved by
**4.50–4.70%** and full HTTP improved by **1.35–1.56%**, with the first
text arriving about 7–16 ms later. At 16,384 input tokens the fixed depth
increased both delivery time and full HTTP time. The regular service uses
the stock MTP cost policy.

| Actual input tokens | Window | API Prefill tok/s | API Decode tok/s | Native MTP head | First text to EOF | Full Windows HTTP |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 8,192 | Stock before | 2,086.088 | 57.779 | 192/291 (65.98%) | 2.216 s | 6.209 s |
| 8,192 | Fixed depth 2 | 2,075.986 | 60.496 | 210/336 (62.50%) | 2.116 s | 6.125 s |
| 8,192 | Stock after | 2,080.473 | 57.659 | 192/291 (65.98%) | 2.220 s | 6.222 s |
| 16,384 | Stock before | 1,989.565 | 54.078 | 180/279 (64.52%) | 2.306 s | 10.400 s |
| 16,384 | Fixed depth 2 | 2,050.138 | 53.796 | 189/378 (50.00%) | 2.380 s | 10.442 s |
| 16,384 | Stock after | 2,041.491 | 55.424 | 180/279 (64.52%) | 2.309 s | 10.406 s |

All windows ran in one 32K BF16 slot on Halogen 0.20.7 v2 with the official
r2-HT4 head and REV:N Performance. The frozen non-repetitive prompts each
generated 128 tokens at temperature 0, seed 1, Thinking Off, Vision Off,
Cache Off and PLD `3,3`. Each row excludes one warmup and represents three
measured requests. Acceptance pools accepted and drafted head tokens.
The Windows measurements use QPC. The API phase rates retain the native
timing scope.

The fixed profile uses the existing `engine.draft_tokens=2` and
`engine.speculation_policy.HALOGEN_MTP_GATE_P="0"` controls. The live image
reported fixed depth two, and the same joint-round scheduler remained active
in all three windows. The stock windows reported the native cost rule.
[Publisher MTP startup controls](https://github.com/peonist-ai/halogen-flash-server/blob/dea807d22a638c67553abea876344a8192054a94/docs/FLAGS.md#L188-L191)

At 8K, accepted head tokens per request rose from 64 to 70 while drafted tokens
rose from 97 to 112. Verification rounds fell from 62 to 56. The lower
acceptance percentage accompanied more accepted tokens and higher output
delivery speed. At 16K, rounds fell from 66 to 63 but first-text-to-EOF time
rose **3.05–3.21%**. Full HTTP rose **0.35–0.40%**. All 24 requests
reproduced the frozen output for their input size.

Client delivery bursts in these retained streams provide a conditional
screen for a third draft. The additional draft's actual proposal and
acceptance remain unobserved.
[Delivery-burst replay and sensitivity](../research/halogen0207-mtp-delivery-bursts-20261123.md)

The lowest sampled request reserve was 28.59 GiB. Raw events, native
completion logs and per-request QPC times are retained under
`server/.local/halogen-update-20261122/primary0207/fixed-depth-two-campaign-prep-v1/fixed-depth-two-run-v1`.
The coordinator completed and restored the regular server on port 8840.
The authenticated gateway and model checks passed, along with readiness
for ServiceNow routing, Native Voice, TTS and ASR.

| Evidence | SHA-256 |
| --- | --- |
| Stock before summary | `a383326817adae54af98083c06fde32c63a3c12a111121d425ddb66baf72fe85` |
| Fixed-depth summary | `2d13aaac135b68b125379c863f7f48613fef6dd13ba4c3aa3dbaa4b2c4cd45a1` |
| Stock after summary | `9252b8f1f4ac91cdfbbdd3dd2facb0b2147074aa17df08f181b55709ce672a41` |
| Fixed-depth container activation | `f92fbb79ac26217f32c3865011cfbc9d723f3f4bb50e2ea2f7d6270580beda30` |
| Terminal campaign handle | `2f72836cd39bda40c29954d9b3f6f8bd68eefad3627ba8343fb27352323d72f3` |
| Restored service readiness | `d9b249176a94cec96cfb1a1a6c68be7319cf1d3a25eedab77b102657372467be` |
