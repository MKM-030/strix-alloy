# Halogen 0.20.7 adaptive MTP with a two-draft cap

With the native cost rule active, capping the chain at two drafts raised
draft acceptance to **68.89% at 8K** and **66.67% at 16K**. It reduced
accepted draft tokens per answer by two at both sizes and added two
verification rounds. Windows time from first visible text to EOF rose
**1.19–1.41% at 8K** and **1.18–1.28% at 16K** against the two controls.

| Actual input | Cost-rule cap | API Prefill tok/s | API Decode tok/s | Native accepted/drafted | Rounds per response | First text to EOF | Full Windows HTTP |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 8,192 | 7 before | 2,002.84 | 56.15 | 192/291 (65.98%) | 62 | 2.222 s | 6.258 s |
| 8,192 | 2 | 2,078.34 | 56.84 | 186/270 (68.89%) | 64 | 2.253 s | 6.244 s |
| 8,192 | 7 after | 2,036.27 | 57.32 | 192/291 (65.98%) | 62 | 2.227 s | 6.240 s |
| 16,384 | 7 before | 2,031.17 | 55.27 | 180/279 (64.52%) | 66 | 2.316 s | 10.401 s |
| 16,384 | 2 | 2,031.89 | 54.62 | 174/261 (66.67%) | 68 | 2.343 s | 10.478 s |
| 16,384 | 7 after | 2,043.07 | 55.33 | 180/279 (64.52%) | 66 | 2.313 s | 10.350 s |

At 8K, full HTTP improved by 0.22% against the first control and took
0.06% longer than the second. At 16K it rose by 0.74–1.23%. The 8K
candidate's higher API Prefill reading accompanied time to first text
of 3.991 s versus 4.036 and 4.014 s. The delivery interval establishes
a slower result after the first visible text. The candidate stays out
of the regular profile.

The profiles used one 32K BF16 slot, Halogen 0.20.7 v2 with r2-HT4,
paired 8192 prefill controls, the same two non-repetitive novel prefixes,
128 outputs, temperature 0, seed 1, Thinking Off and Cache Off. All
24 responses used the same request and output bytes within each size.
Each row averages three measured requests after one excluded warmup.
The native head totals are pooled over the three measured requests.
API phase rates retain the native clock scope. Windows QPC measures
the first visible text and EOF independently.

The candidate's only profile difference is `engine.draft_tokens=2`,
forwarded as `HALOGEN_MTP_DEPTH=2`. All arms explicitly retain
`HALOGEN_MTP_GATE_P=0.90`, inherit the cost rule, and use the same
joint scheduler. Each native listener reported its own cap at startup.
The [fixed-depth-two comparison](halogen0207-fixed-mtp-depth-two-20261123.md)
turned gating off and accepted 70 drafts per 8K response across 56
rounds. That profile reached 60.50 API Decode tok/s on its separate
8K cohort.
[Publisher MTP controls](https://github.com/peonist-ai/halogen-flash-server/blob/bfe1cee6117579a9876784bfea1ffdc79c902e27/docs/FLAGS.md#L188-L191)

## Evidence

The independent replay reconstructed all 24 responses, matched their
native completion logs, and verified output, usage and QPC boundaries.
The request reserve samples stayed at or above **28.13 GiB**. The campaign
restored the regular 8840 profile. Its gateway, ServiceNow routing, Native
Voice, ASR and TTS passed readiness checks, and port 18840 closed.

The raw SSE, native logs and process receipts are retained under
`server/.local/halogen-update-20261122/primary0207/mtp-cost-cap-two-prep-v1/cost-cap-two-run-v1`.

| Evidence | SHA-256 |
| --- | --- |
| Q4 cap-7 before summary | `57043e4ed553e120832e83f77a13a7d1d0d13242e2e16fd93f2303c885830bb3` |
| Q4 cap-2 summary | `89cfc4dedb70d68e03a1a77c09dc8b23a6c640083ee3b9396819e36a992fa7fe` |
| Q4 cap-7 after summary | `01447491a83e52d177323da9833ad0a7796fd9202b8ceb9d737abe40e961dcf7` |
| Independent SSE and QPC replay | `7fbb7c1aa0dbf0889bfb0d056c6bafdb48b035776830b4dfd90fddfdc8ee8c2` |
| Terminal handle | `fdebaca051ce86864fc845aad0d51f45c05c347ae32237b0ca5da70876211845` |
| Restored service readiness | `e2247031db4da8fc3032f1f325051ffd78d742cc90bbb9b14b2cade5f3acd7a5` |
