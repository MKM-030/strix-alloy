# Halogen 0.20.7 MTP with greedy and top-k-one sampling

Halogen returned identical output bytes in both arms for each workload. On the
8,192-token novel prefix, the sampled `top_k=1` arm averaged **46.59 Decode tok/s**
against **56.26 tok/s** under greedy MTP. Its head accepted **49.57%** against
**65.98%**. The short chat reached its natural stop in both arms and showed the
same performance direction.

| Workload | Actual input / output tokens | Request | API Prefill tok/s | API Decode tok/s | Native MTP head accepted/drafted | Mean complete HTTP |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| Novel prefix | 8,192 / 128 | Greedy MTP | 1,997.74 | 56.26 | 192/291 (65.98%) | 6.422 s |
| Novel prefix | 8,192 / 128 | Sampled `top_k=1` MTP | 1,966.74 | 46.59 | 174/351 (49.57%) | 6.956 s |
| Publisher `chat_a` | 26 / 143 | Greedy MTP | 255.32 | 57.31 | 207/324 (63.89%) | 2.599 s |
| Publisher `chat_a` | 26 / 143 | Sampled `top_k=1` MTP | 254.82 | 45.53 | 174/414 (42.03%) | 3.243 s |

The sampled route took 0.450–0.588 s longer in every measured novel pair and
0.638–0.653 s longer in every short-chat pair. API Decode fell by 17.18% and
20.55%, respectively. Greedy MTP remains the serving default.

## Comparison conditions

The same one-slot, 32K v2/HT4 Halogen 0.20.7 serving run handled all 16 requests
with Thinking Off and Cache Off. The Windows scheme was `REV:N Performance`.
The greedy control used `temperature=0`. The sampled candidate used
`temperature=1`, `top_k=1`, `top_p=1`, `min_p=0` and seed 1. The pinned API mapped
that candidate to the native `SAMPLE 1 1 1 0 1` command. Both arms reported active
native MTP. All prompt-lookup and grammar draft counters were zero.

Each workload had one excluded warmup pair followed by three measured pairs
with alternating order. The runner checked frozen response bytes, actual token
counts and finish reason on every request. The novel request ended at its length
limit. The short chat stopped naturally. The Windows complete HTTP durations
use a client monotonic clock. Prefill and Decode rates use the native API phase
fields. The lowest request-sampled Windows reserve was 30.44 GiB. Each cohort's
gateway counters advanced by eight completed and zero cancelled requests.

Raw requests, responses and timing receipts remain locally under
`server/.local/halogen-update-20261122/primary0207/top-k-one-20261123-v1`.

| Local evidence | SHA-256 |
| --- | --- |
| Novel cohort plan | `2bb091139d94a9715f9b9e9962e7812a711a912831c1cfd3db2a227ca1d9e525` |
| Novel cohort summary | `4e3080af9c740ce72ebe34143f1e6042896563a3a2f9f5b5a697b00e5c7918c3` |
| Short-chat cohort plan | `7db02acde0be4aa536fffe21e162ba4aa853d75bd18fbd32b548fc2543716fc1` |
| Short-chat cohort summary | `171d336f717618338af4c5f1dab862fea1319214fe1a12ff67b48a568423c216` |
