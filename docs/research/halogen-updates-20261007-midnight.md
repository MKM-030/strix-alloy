# Midnight Halogen update and mechanism check — 7 October 2026

This bounded source check began at **2026-10-06 22:24:01 UTC** and completed at **22:29:51 UTC** (00:24–00:29 on October 7 in Europe/Berlin). The [evening receipt](halogen-updates-20261006-evening.json) completed at 20:23:42 UTC; its 22:23:42 gate had passed. The next check must begin no earlier than **2026-10-07 00:29:51 UTC**, two hours after this check completed. The continuation's current official-update fields and receipt SHA agree with that evening baseline; older conflicting schedule fields were not used.

**Result:** one new user comment on Halogen's KV-cache issue, with no new feature or maintainer commitment. The checked tracked versions and repository heads remain unchanged. No new route is qualified for the current single-active-request, cache-off Halogen Prefill/Decode/native-acceptance profile. The managed engine remains 0.16.2; this task made no host or continuation-state changes.

## Concrete delta

[Halogen issue #142](https://github.com/peonist-ai/halogen-flash-server/issues/142#issuecomment-6025206427) received a comment from `apartje` at **2026-10-06 20:50:46 UTC**. The user reports no noticeable quality loss from llama.cpp Q8 and wants the capacity for more context, quoting the earlier maintainer's promise to measure. The author has GitHub association `NONE`. This is an anecdote in another runtime, not a KV-quantization implementation, new maintainer commitment or local throughput/acceptance result. The issue remains open; the evening finding of BF16 KV with no supported KV-quantization feature is unchanged.

The bounded [Halogen issue query](https://api.github.com/repos/peonist-ai/halogen-flash-server/issues?state=all&sort=updated&direction=desc&since=2026-10-06T20%3A23%3A42Z&per_page=10) returned only that updated issue. Its comment body was inspected rather than inferring a feature from the update timestamp.

## Unchanged official sources

| Source | Fresh comparison with evening receipt | Scope |
| --- | --- | --- |
| Halogen | Main remains `6d4e791ea4ca596a1f90e38beefdf2e017ae4544`; commits since 20:23:42 UTC are empty. Tracked version remains 0.16.4. | Same pinned server whitespace fix; prior engine/checkpoint assessment stands. Tags were not separately refreshed. |
| Strata | Latest release remains v0.1.40.1, published and updated 2026-10-06 09:53:35 UTC. | Same Python server hotfix; engine unchanged from 0.1.40. |
| AMD Max+ 395 drivers | Optional 26.9.2, dated September 29; recommended 26.8.1, dated August 20. | Package listing only; installed versions were not queried and release notes were not fetched again. |
| Ryzen AI | Latest release remains v1.8.0, published and updated July 23 at 04:37:16 UTC. | No new release within the check window. |
| Kyojin | Main remains `8c91be29da2cfbaf22ebd89c047ca8eecd4ad28f`. | Evening confidence-stopping assessment remains source-only; no new source mechanism. |
| ROCm/TheRock #8709 | Comments since 20:23:42 UTC return literal `[]`. | No new AMD firmware statement or clarification. |

Primary sources: [Halogen head](https://api.github.com/repos/peonist-ai/halogen-flash-server/git/ref/heads/main), [pinned changelog](https://github.com/peonist-ai/halogen-flash-server/blob/6d4e791ea4ca596a1f90e38beefdf2e017ae4544/CHANGELOG.md), [Strata release](https://github.com/Niko1221/Strata/releases/tag/v0.1.40.1), [AMD driver listing](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html), [Ryzen AI release](https://github.com/amd/RyzenAI-SW/releases/tag/v1.8.0), [Kyojin head](https://api.github.com/repos/Yamz-Labs/kyojin/git/ref/heads/main), [TheRock comment query](https://api.github.com/repos/ROCm/TheRock/issues/8709/comments?since=2026-10-06T20%3A23%3A42Z&per_page=10). GitHub API bodies were read through bounded read-only HTTP requests after the web tool could not access those API URLs. An empty-array PowerShell projection was corrected by inspecting the raw two-byte body; no null object was counted as a comment.

Fresh [Windows NPU installation documentation](https://ryzenai.docs.amd.com/en/latest/inst.html) still lists minimum driver `32.0.203.280` and production `32.0.203.376`, including Strix Halo. Fresh [Linux documentation](https://ryzenai.docs.amd.com/en/latest/linux.html) still lists STX/KRK and an NPU-only flow using XRT/amdxdna. Both pages show September 28 as their update date. These documents establish no new WSL NPU bridge or arbitrary HGN operator contract.

The evening's installed AGESA `1.0.0.2b` metadata and AMD's reported firmware prerequisite match remain inherited evidence; this task did not query host metadata. Local overlap correctness remains unproved. BOSGAME compatible release availability remains unresolved from the earlier bounded check and was not searched again. The held-clock and unsupported-overlap conclusions are unchanged.

## Reddit and useful approaches

Four distinct targeted queries were checked. The two queries for Halogen 0.16.4 and October 6 Strix Halo speculation returned no results. The two broader Halogen/Kyojin and Strix Halo/NPU queries returned older indexed discussions despite their two-day recency filter. Search results are therefore not proof of activity after the evening completion.

The [October 5 Kyojin discussion](https://www.reddit.com/r/LocalLLaMA/comments/1wybesy/qwen38flashnext_125b_on_a_single_strix_halo_mini/) is the evening's already assessed EXL3 lead; its primary head is unchanged. The [October 2 Halogen NPU discussion](https://www.reddit.com/r/StrixHalo/comments/1wvfrj0/halogenflashserver_0160_strix_halo_npu_now_serves/) concerns side models and overlap. The [September 30 FastFlowLM discussion](https://www.reddit.com/r/StrixHalo/comments/1wuczmb/fastflowlm_can_now_run_qwen38_27b_on_strix_halos/) concerns another runtime/model. None supplies a newly qualified local Halogen improvement.

The [October 1 Rulith discussion](https://www.reddit.com/r/StrixHalo/comments/1wv2x6c/rulith_inference_formerly_strix_llama_04_125b_moe/) describes proper sampled speculative acceptance. That mechanism is already recorded in the [October 1 source assessment](reddit-prefill-decode-20261001.md), so it is not a new candidate. Its eight-conversation aggregate headline is outside the current single-active greedy profile. No anecdotal rate was used as local performance evidence.

The stale continuation wording about WMMA/LDS was not promoted into a fresh lead: the [selected-H review](halogen-next-mechanisms-20261006.md) establishes that selected H has no WMMA/LDS staging to pad. Prior defeated proposer, continuation, Q8 and rollback cohorts remain excluded; ongoing bulk Prefill remains separate work.

Only public-source research and the two report writes occurred. No inference, sampling, GPU/NPU execution, driver/firmware operation, install, WSL action, lifecycle action, capture, rejected native-controller audit retry or automation change occurred. Coverage is bounded, with potentially lagging Reddit indexing. The [JSON receipt](halogen-updates-20261007-midnight.json) records sources, comparisons and the next gate; continuation state was left untouched.
