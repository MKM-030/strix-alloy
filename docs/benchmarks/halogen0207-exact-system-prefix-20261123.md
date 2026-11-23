# Halogen 0.20.7 Exact reuse of a system-prefix checkpoint

In-memory Exact caching reused **8,192 of 8,498 input tokens** on every
measured follow-up to a shared system prompt. Mean complete Windows HTTP
time was **0.408 s**, down from **4.340 s** and **4.408 s** in the two
Cache Off controls. This saved **90.6–90.8%** of follow-up time. All 27
answers matched the expected response text byte for byte.

| Arm | Input / processed / reused tokens | API Prefill tok/s | API Decode tok/s | Native head acceptance | Mean follow-up HTTP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Off before | 8,498 / 8,498 / 0 | 1,831.35 | 75.50 | 12/12 (100%) | 4.340 s |
| Exact | 8,498 / 306 / 8,192 | 886.26 | 81.63 | 12/12 (100%) | 0.408 s |
| Off after | 8,498 / 8,498 / 0 | 1,955.71 | 81.23 | 12/12 (100%) | 4.408 s |

Each arm started a private Halogen 0.20.7 v2/r2-HT4 engine with a single
32,768-position BF16 KV slot and paired 8,192 Prefill settings, then ran one
seed, two excluded warmups and three measured pairs of distinct questions.
The frozen `/v1/responses` requests use the same long `instructions` and
vary `input`. Each response used three output tokens at temperature 0,
with Thinking Off. The cold seed reused zero tokens in each arm and took
7.792, 7.874 and 7.647 s respectively. The minimum sampled request reserve
was 28.30 GiB.

API Prefill measures processed tokens and uses the native phase clock. The
Windows QPC comparison covers dispatch through receipt of the full body.
The three-token completions give only a short-response Decode observation.
[Phase clock audit](../research/halogen0207-phase-clock-audit-20261123.md)

## Where the improvement applies

Exact reused a completed 8,192-token checkpoint followed by a new suffix.
The earlier 16K full-prompt repeats missed in both the in-place and copied-KV
smokes. Flexible caching has also accelerated a similar Responses fixture,
using 64-token alignment and its own policy. [Exact 16K smokes](halogen0207-exact-cache-16k-20261122.md)
· [Flexible Responses smoke](halogen0207-responses-system-cache-20261123.md)

The regular shared ServiceNow server uses Cache Off. Actual ServiceNow
requests use Chat Completions through the existing transformer. In an
offline audit with its synthetic caller context, the original request had
2,826 rendered tokens, and the changed-note request shared 2,569 leading
token IDs. These fixtures are below the measured checkpoint. Changing only
the conversation ID produced identical token IDs. In the pinned adapter,
`prompt_cache_key` is recording metadata and provides no cache namespace.
Use the measured request pattern only within a single trust boundary with
a common reference text. [ServiceNow prefix audit](../integrations/halogen-servicenow-prefix-cache-20261101.md)

## Evidence

Raw HTTP JSON, Windows QPC timestamps, native cache and MTP counters and
restoration receipts are retained under
`server/.local/halogen-update-20261122/primary0207/exact-system-prefix-prep-v1/exact-system-prefix-run-v1`.
The offline ServiceNow receipt is kept in the adjacent
`exact-system-prefix-independent-v1` directory.

| Artifact | SHA-256 |
| --- | --- |
| Exact benchmark runner | `fe95eeb53ed21ee636fb60ed8fbe42ca7c4abb78a59b48a893bb6b78760c5cf4` |
| Terminal campaign handle | `fb75def1af86a5a7ee52a096f568ef6a5c081758347542c6cd2d76197cfb6622` |
| Independent replay of all 27 requests | `f66f0de0e7441a6c827d58f41bcb6967a27ce7285c093b3edc2c2a8a636dce29` |
| Restored standard server and Voice readiness | `f54292da2b75b027f80b6db70f8201051a5dbe18be999dea1ed6aa02457520c3` |
| Synthetic ServiceNow token audit | `b1a987e2875d5f555f0e0b2e06f689d0acd0f70449f126a35218cd324a13fd21` |
