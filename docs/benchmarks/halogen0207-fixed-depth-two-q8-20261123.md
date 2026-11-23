# Halogen 0.20.7 draft-vocabulary Q8 at fixed MTP depth two

Changing only the draft vocabulary to Q8 lowered 8K Decode from
**60.00–60.36** to **57.00 tok/s**. Native head acceptance fell from 62.50%
to 58.62%. Windows text delivery took **5.27–5.88%** longer and complete
HTTP took **1.93–2.28%** longer than the two Q4 controls. The candidate
remains experimental. All twelve requests returned byte-identical text.

| Draft vocabulary | API Prefill tok/s | API Decode tok/s | Native head accepted/drafted | Head rounds per request | First text to EOF | Full Windows HTTP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q4 before | 2,091.63 | 60.00 | 210/336 (62.50%) | 56 | 2.134 s | 6.112 s |
| Q8 | 2,078.80 | 57.00 | 204/348 (58.62%) | 58 | 2.246 s | 6.251 s |
| Q4 after | 2,076.33 | 60.36 | 210/336 (62.50%) | 56 | 2.121 s | 6.133 s |

All arms used 8,192 actual input tokens from the frozen non-repetitive
novel prefix and generated 128 output tokens. Each row averages three
measured requests after one excluded warmup. The server used Halogen
0.20.7 v2, the official r2-HT4 head, one 32K BF16 slot, paired 8,192-token
prefill controls, `REV:N Performance`, temperature 0, seed 1, Thinking
Off, Vision Off and Cache Off. The fixed two-draft policy and joint
scheduler were active throughout. Lookup and grammar drafts were zero.
The candidate adds `HALOGEN_DRAFT_VOCAB_Q8=1` to that fixed profile.
Live environment and native startup records verify the configured
treatment. They leave the internal projection dispatch unmeasured.

The independent replay reconstructed all twelve SSE streams, exact
output hashes, native counters and Windows QPC boundaries. The lowest
sampled physical or commit reserve during requests was **27.81 GiB**.
API phase rates retain the native clock scope. Windows QPC measures
first visible text to EOF and the complete HTTP interval.

The campaign restored the regular cost-policy profile on port 8840.
Halogen, the ServiceNow router, Native Voice, ASR and TTS passed their
readiness checks. The campaign process exited and port 18840 closed.

The earlier Q8 trial used the adaptive cost policy and gained 4.99
percentage points of acceptance at 8K. The cost policy can adjust the
number of proposals from round to round. This comparison holds the
draft depth at two to isolate the change in vocabulary precision.
Here Q8 accepted 68 drafts per request and Q4 accepted 70, so Q8 required
two additional verification rounds for the same answer.
[Adaptive Q8 benchmark](halogen0207-draft-vocab-q8-20261122.md) ·
[Fixed-depth Q4 benchmark](halogen0207-fixed-mtp-depth-two-20261123.md).

The earlier **71.21 API Decode tok/s** used ten short publisher prompts.
In that replay the two code prompts averaged 90.21 tok/s, the two prose
prompts 59.00 tok/s, and all ten prompts pooled 81.17% head acceptance.
The publisher's official alternating-image benchmark reports 74.57
tok/s in its engine timing on native Ubuntu. The workloads and clocks
give different scopes for those figures and the natural 8K comparison.
[Local publisher replay](halogen0207-publisher-replay-20261123.md) ·
[Publisher methodology](https://github.com/peonist-ai/halogen-flash-server/blob/dea807d22a638c67553abea876344a8192054a94/docs/performance.md#L169-L199).

## Evidence

Raw streams, phase timings, activation and process ownership records
are retained under
`server/.local/halogen-update-20261122/primary0207/fixed2-q8-prep-v1/fixed2-q8-run-v1`.

| Evidence | SHA-256 |
| --- | --- |
| Frozen request | `6487438c42d2e1faa3d0365130e064acb2e7a243e3c24c868b3f04bc6cb4439d` |
| Visible output | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| Q4 before summary | `b8d93edf113a4699e3a18be179b58ac02bb0d3f20f1881ae014e6ecc4008be74` |
| Q8 summary | `2f77509a4d740e04edb9cb812dc6c8011c7caf59174782be1f3fc4b0017193ee` |
| Q4 after summary | `5723b757298a0f8334d9d5f3d2ee465ff95d2f5233cc474e43e6bbedc53cfe72` |
| Q8 container and native activation | `793001cd3bab09b57fa50a60a1a9efabe2b87eeadd61cd01cfe1fc28388fb890` |
| Independent SSE and QPC replay | `14d147097452a2113120676dbebb696831dd4fca0f96dad3db614771ee949d84` |
| Terminal campaign handle | `0aba121f21e6e3449345cb1f030997aded7eb629c4dc335f8227c0825b72d099` |
| Restored service readiness | `09b85ce626f5fa20d83a1e6a024ef7106af2d7ed29af955c74953738a65a45af` |
