# Direct CPU/Vulkan token proposer — 6 October 2026

**The direct GPU realization is substantially cheaper than the tested CPU and NPU realizations, but no Halogen speed or native acceptance gain is established.** The original target was stopped through its normal lifecycle for one finite, root-owned comparison. Both owned component processes completed successfully and closed. The candidate remains disabled pending a credible engine benefit; the original server was restored ready/open with its unchanged profile.

This follows the [source boundary audit](halogen-cpu-gpu-proposer-boundary-20261006.md) and [exhaustive GGUF token-map check](halogen-gguf-proposer-token-map-20261006.md). Full numerical results, source/build/raw-output hashes, timestamps and parity captures are in [the JSON evidence](halogen-cpu-vulkan-proposer-screen-20261006.json).

## Actual component measurements

| Realization | Clear/prefill of 512 IDs, ms | Three independently predicted IDs, ms | One authoritative append, ms | Offline leading matches |
|---|---:|---:|---:|---:|
| CPU, four threads | 1,112.69 | 30.47 | 14.62 | 19/44 |
| Vulkan, Radeon 8060S | 52.34 | 10.66 | 4.87 | 22/44 |
| Previous Windows NPU2 | 418.29 | 45.22 | 22.46 | 21/44 |

Three predicted IDs require two consumed speculative scalar forwards; the first ID comes from already copied committed-prefix logits. The final case has two IDs and one scalar forward. Command timing includes synchronization, ownership of the entire logit row and greedy selection. Snapshot writes are excluded from command timing but included in whole-process elapsed time.

CPU and Vulkan use exactly the same pinned `Qwen3.5-0.8B-Q4_0.gguf`, revision `9447f74101aeb4e93621884dfa36ee8effb8831b`, SHA256 `57d1997790d1744fba5b40a7317df71ea5e2acee28c47e78f0cce39c0703f8cf`. It is mixed Q4_0/F32 with a Q8_0 embedding. The NPU uses a different `q4nx` quantization of the same architecture; its first-call policy also differs. The NPU row is a retained reference, not an identical-tensor device comparison.

Each new backend received one excluded warmup, followed by the same 15 frozen 512-ID suffixes from one retained target request. Fourteen cases request three drafts; the last requests two. A separate 256-ID seed plus ten authoritative count1 updates ends at 266 IDs and is compared against a fresh 266-ID prefill. There are 54 commands per backend, a 1,024-token context, one sequence and no rollback snapshots. These are bounded screens, not warmup-plus-three engine cohorts or independent held-out documents.

The GPU warmup included first-use pipeline costs: 1,087.03 ms clear/prefill and 218.38 ms for three proposals. Measured later ranges were 51.40–54.11 ms and 9.87–11.33 ms. CPU later ranges were 1,105.58–1,123.68 ms and 29.26–31.73 ms. End-to-end owned process durations, including startup, snapshots and teardown, were 21.89 s CPU and 4.44 s Vulkan. Runtime physical reserve stayed at least 43.72 GiB, with commit reserve at least 198.47 GiB; the raw receipt preserves byte values.

## What the predictions establish

CPU matched 19/44 leading continuation IDs; Vulkan matched 22/44. They match the captured native opening head in ten of fifteen cases. The GPU's three additional matching IDs occur in case12, whose first proposed ID `17739` differs from the retained native opening head `7963`. Applying that offline head constraint leaves **19 leading matches for either backend**. Actual PLD hit coverage, stock proposal width, opening-gate execution and timely publication were not observed.

These counts are **not native MTP acceptance**. They cannot replace the qualified Halogen acceptance values or be compared to a 60% engine acceptance measurement as if the denominators were the same. There is no measured Halogen Prefill, Decode or acceptance delta for either proposer.

## State and placement

Native logs confirm CPU offloaded **0/25** layers and Vulkan offloaded **25/25** layers to the Radeon 8060S. CPU backend initialization enumerates Vulkan devices; enumeration does not establish GPU compute. CPU KV/recurrent/compute buffers were 12/19.27/43.16 MiB. Vulkan KV/recurrent/compute buffers were 12/19.27/41.16 MiB, plus 5.02 MiB host compute and 0.95 MiB host output. Main-engine coexistence or shared-bandwidth contention was not measured.

Append and fresh prefill contain the same 266 committed IDs and select greedy next ID `6574` on both devices. Full F32 row parity fails: 248,069 of 248,070 shared rows differ on CPU and 248,067 on Vulkan. Maximum shared absolute logit differences are 0.325107 and 0.365640 respectively. Tolerances were not relaxed, and numerical append equivalence remains unqualified. This comparison distinguishes a shared greedy answer from complete-row equivalence; it does not isolate a state-transfer or synchronization defect.

## GPU, CPU and NPU applicability after this development

- The native raw-ID adapter and safe authoritative-update transaction work as source mechanisms across CPU and GPU. The earlier NPU realization uses the same bounded ID protocol. Hardware execution is recorded separately for each.
- This proposer adds work during speculative decoding. It does not accelerate ordinary target prefill or remove target weights. Its own weights remain a separate resident model; both verify and authoritative commit still use the full target.
- CPU avoids target GPU queue occupancy but competes for host scheduling and memory bandwidth. Its measured rebuild cost rules out the current rolling-window synchronous route.
- GPU reduces small-model component time, but shares target compute and DDR. A 512-ID rebase costs 52.34 ms before the 10.66 ms proposal; an always-full rolling suffix needs frequent rebuilds. A faster isolated proposer is insufficient evidence of net Decode improvement.
- NPU still has the largest proposal cost among these tested realizations, and its on-chip SRAM is not extra GPU-addressable capacity. It remains disabled in the running target.

Adoption requires a concrete native-seam benefit, timely proposals, accurate accepted-prefix state and a matched complete-engine improvement under actual contention. Preserve the [retained benefit bound](halogen-independent-proposer-benefit-20261006.md); do not run an engine cohort merely because the component executed successfully.

The independent benefit audit rejects the current CPU and strict rolling512 GPU routes before live injection. Even an optimistic planning bound using 37 committed tokens in 15 retained rounds, four maximum committed tokens per candidate round, 48.2804 reference Decode tok/s, perfect hits/readiness/opening and no contention allows only 31.76 ms extra unhidden work per round. CPU proposal plus one append costs 45.09 ms. GPU proposal plus a required rolling512 rebuild costs 63.00 ms. These are cross-cohort planning bounds, not measured seam timing. A shorter growing GPU window has a 15.54 ms proposal-plus-one-append proxy, but rejection/rebase costs, additional accepted-output updates, full-row qualification and actual target contention remain unresolved. It remains disabled; this evidence does not justify another engine cohort.
