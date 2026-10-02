# Unsloth integration and speed update — 19 September 2026

## Finding

The latest Unsloth update repairs a broken Flash-Next MTP launch path. It is worth testing, but the public evidence does **not** establish 42–60 tokens/s on this Windows Strix Alloy configuration. Unsloth can also use the existing Strix Alloy server as an external model; that route keeps our runtime and MTP sidecar and does not itself speed up decoding.

## What Reddit actually says

Checked live on 2026-09-19. Relative Reddit timestamps below are the page's displayed age at retrieval; the release timestamps in the next section are pinned UTC values.

| Source | Date / conditions | What can be concluded |
| --- | --- | --- |
| [Maintainer: Flash-Next speed fixes](https://www.reddit.com/r/unsloth/comments/1wjvjxq/qwen38flashnext_speed_fixes/) | Observed 19 Sep, page displayed 54 minutes old | Daniel Han Chen attributes 1.5–2x slower generation to broken MTP and asks users to update both Desktop to `v0.1.811-beta` and llama.cpp to `b11030-mix-5ff778e`. This is a regression fix. |
| [User: latest .811 is fast](https://www.reddit.com/r/unsloth/comments/1wkeni0/qwen38flash_in_latest_update_v01811beta_is_really/) | Observed 19 Sep, page displayed 1 hour old | Author claims previously 30–40, sometimes 20–50, now over 70 tokens/s; hardware, quant, prompt and timing method are absent. A commenter reports 30 tokens/s on Strix Halo after updating. Another reports 40–60 using **Halogen**. These are anecdotes, not a matched benchmark. |
| [Original 1.7x announcement](https://www.reddit.com/r/unsloth/comments/1w5c0bw/run_qwen38flashnext_gguf_17x_faster/) | 2 Sep 2026 | A commenter reports about 34→42 decode tokens/s on an **Apple M5 Max**, draft depth 2 and `p-min=0.95`. It is not an AMD result. The announcement's 170 tokens/s is an RTX PRO 6000 result. |

No reproducible r/unsloth benchmark was found proving a general 42–60 tokens/s result for our hardware, weights and context. The September 19 discussion does contain the 40–60 range, explicitly attributed to Halogen.

## Pinning the hotfix

- [Desktop `v0.1.811-beta`](https://github.com/unslothai/unsloth/releases/tag/v0.1.811-beta): released 2026-09-18, 16:11 UTC; release notes include the Flash-Next MTP repair.
- [Runtime `b11030-mix-5ff778e`](https://github.com/unslothai/llama.cpp/releases/tag/b11030-mix-5ff778e): released **2026-09-18T15:36:14Z**.
- [Official source manifest](https://github.com/unslothai/llama.cpp/releases/download/b11030-mix-5ff778e/llama-prebuilt-manifest.json): upstream `b11030`; actual compiled source **`6ba30d05b140ebb0baeded27d7d9b843c5b71ff1`**. The release-tag commit shown by GitHub is not the compiled source identity.
- The manifest includes MTP PR 144 at **`ca1426903fabe9af26cd10c42034cb4bbd2e0e11`**, committed 2026-09-18T10:13:30Z.

[PR 219](https://github.com/unslothai/llama.cpp/pull/219), carried by that commit and repinned in [PR 220](https://github.com/unslothai/llama.cpp/pull/220), explains the regression. A rebase reshaped trunk normalization tensors but left the MTP tensor flat. The draft graph then aborted. Studio retried and eventually loaded without speculation, making the apparent symptom lower speed. The fix permits the existing flat GGUF tensor to load in the expected shape; **the weights do not need re-exporting**. A second change lets automatic memory fitting account for a shared draft head without loading its target first. That avoids under-budgeting the draft and then running out of memory.

The [pinned commit](https://github.com/unslothai/llama.cpp/commit/ca1426903fabe9af26cd10c42034cb4bbd2e0e11) reports 43.8 without a drafter, 63.6 with the shared Q8 head and 61.2 with the self-contained head, using UD-Q4_K_XL, 8192 context and depth 2. It describes a GPU held at 30.7 GiB free, not a Strix Halo benchmark. That result is not transferable by its number alone.

The earlier [MTP implementation PR 144](https://github.com/unslothai/llama.cpp/pull/144) describes graph-cache keying and recurrent-state rollback improvements, and explicitly supports the approximately 2.595 GiB shared Q8_0 sidecar. A September 17 comment reports a gfx1151/HIP reproduction and fix: **23.0 serial, 32.7 shared-MTP, 31.9 self-contained-MTP tokens/s**, UD-IQ4_XS and greedy sampling. That is more relevant hardware evidence, but differs from our PROJFIX weights and Windows build. The PR also records sampler-dependent acceptance and lower benefit with concurrent requests.

## What is relevant to our setup

Our [README](../../README.md) identifies Windows 11, Ryzen AI Max+ 395 / Radeon 8060S, 128 GB unified memory, 96 GB carve, IQ4_NL PROJFIX and the shared Q8_0 head. Published measurements are 45.31 tokens/s for one warm instructed prompt and roughly 31–33 at occupied contexts from 16k to 251k; these are different workloads.

The local integration audit in this task found installed Unsloth Desktop `.806` and runtime `b10840`, so testing that installation alone would not test the September 18 repair.

[Unsloth's September 8 release](https://github.com/unslothai/unsloth/releases/tag/v0.1.807-beta) changed Strix Halo/Point's default backend to Vulkan and claimed up to 23% more prefill and 8% more generation against its previous ROCm path. This is a concrete comparison candidate, not evidence that stock Vulkan beats our custom HIP kernels. The [Desktop documentation](https://unsloth.ai/docs/desktop) says its GGUF inference uses llama.cpp and that optional tools add time; changing the UI is not independently a decoding optimization.

Our existing [depth sweep](decode-levers-nmax-and-negative-results-20260915.md) and [later workload comparison](reference-forks-assessment-20260916.md) favor depth 2 as a mixed-workload default. Higher draft depth, `p-min=0.75`, and an n-gram cascade already failed to improve the tested workloads. The M5 comment's `.95` is a possible measured experiment, not a setting to copy on trust. The hotfix's memory-fit repair is useful for ease of loading, while our fixed `--fit off` setup already avoids that fitting failure.

## Integration supported by Unsloth

The official [Connections guide](https://unsloth.ai/docs/integrations/connections) supports llama.cpp/OpenAI-compatible servers. In Settings → Connections, add llama.cpp, use `http://127.0.0.1:8826/v1`, load models, then select `Qwen3.8-Flash-Next`. This connects to the already loaded model and sidecar. It does not require a second GPU copy.

The [existing-model guide](https://unsloth.ai/docs/new/studio/chat#using-old--existing-gguf-models) also permits custom model folders. Having Unsloth load the GGUF itself is a different execution path; backend, sidecar discovery and arguments must be verified separately. Do not infer MTP engagement from the UI toggle alone: check actual generated draft counts and server logs.

## Isolated runtime prepared for a controlled comparison

Only official runtime files were downloaded; no weights were downloaded, existing runtimes were not replaced, and this research task did not launch a model.

| Item | Verified value |
| --- | --- |
| Directory | `C:/AI/runtimes/unsloth-b11030-mtp-vulkan` |
| Executable | `C:/AI/runtimes/unsloth-b11030-mtp-vulkan/llama-server.exe` |
| [Official Windows Vulkan archive](https://github.com/unslothai/llama.cpp/releases/download/b11030-mix-5ff778e/app-b11030-mix-5ff778e-windows-x64-vulkan.zip) | 27,006,858 bytes downloaded; 81,342,198 bytes extracted, 48 entries |
| Archive SHA-256 | `dcff373c1107f6fe7980b246366fb34c014b8ec659cf1b374be8c84d6e5d65cc` |
| Executable version | `0.4.1-dev`, build 11030, commit `6ba30d05b`, MSVC 19.44.35228.0 |
| Device enumeration | `Vulkan0: AMD Radeon(TM) 8060S Graphics`, 114507 MiB reported total; 108782 MiB free at probe time |
| Audit artifacts | `download-provenance.json`, `llama-prebuilt-manifest.json`, `llama-prebuilt-sha256.json`, `version.txt`, `help.txt` in that directory |

Archive, manifest and checksum-list hashes matched GitHub's release-asset digests. Every archive entry's resolved destination was checked to remain inside the new runtime directory before extraction. Free space before downloading was 141,836,132,352 bytes.

The binary's help accepts `--load-mode none`, `--fit off`, `-md`, `--spec-type draft-mtp`, `--spec-draft-n-max`, `--spec-draft-device`, `--spec-draft-ngl`, f16 KV, explicit context/batch/microbatch, one slot and aliases. Use **Vulkan0**, not ROCm0. Lazy loading supports `auto`, `on` and `off`; the on-demand path requires mmap. These checks establish command availability, not successful PROJFIX generation or performance.

The same help says `--agent` enables the server's CORS proxy and built-in tools. It is not required to discover or call an OpenAI-compatible model. `--embedding` is for dedicated embedding models and is unrelated to integrating this chat model into another application.

For the actual A/B, hold weights, shared head, prompt, sampling, context, batch, draft depth and warmup constant; run one GPU-serving process at a time. Separate prompt processing, output decode, time to first token and end-to-end wall time; verify coherent output and nonzero draft acceptance. Root task owns that model execution and its measured results.

## Local comparison completed on 19 September

Both engines successfully loaded the existing PROJFIX shards and the same shared Q8_0 sidecar. No model download or conversion was needed. Tests used the same 54-token maintenance-guide prompt, 256 output tokens, temperature zero, seed 1234, thinking disabled, prompt caching disabled, context 32768, batch/microbatch 2048, one slot and MTP depth two. Only one model server ran at a time. The Unsloth arm used its newly recommended Vulkan backend; this does not isolate the MTP hotfix from all other engine/backend differences.

| Engine | Decode t/s, runs 1 / 2 / 3 | Full request seconds, runs 1 / 2 / 3 | Accepted / drafted tokens, runs 1 / 2 / 3 |
| --- | --- | --- | --- |
| Existing Strix Alloy HIP | 25.45 / 31.78 / 30.02 | 10.72 / 8.50 / 8.89 | 141/227, 139/231, 139/231 |
| Unsloth b11030 Vulkan | 25.93 / 35.19 / 35.62 | 15.35 / 9.73 / 9.69 | 138/231, 143/224, 146/216 |

The Vulkan arm had higher steady generation rates but slower completed requests in this small test. Its prompt processing took 1393–1457 ms in runs two/three versus HIP's 390–407 ms. The complete request includes additional overhead beyond the server's prompt/decode timers. The different draft acceptance and generated sequences mean these are matched workloads, not a proof of numerical equivalence. Three repeats of one short prompt are a screening comparison, not a general performance ranking, and do not establish 42–60 t/s on this machine.

Raw requests, full responses and timings are saved locally under `C:/AI/artifacts/flash-next-integration-20260919/` in `baseline-hip-mtp2.json` and `unsloth-vulkan-mtp2.json`, with separate startup/server logs. A separate test through the installed Unsloth external-provider adapter discovered the model and streamed the requested answer; this confirms client compatibility while retaining Strix Alloy's sidecar, not an acceleration caused by the UI.

A repeat after restoring HIP produced **30.11 / 32.03 / 35.91 t/s**, with full request times **9.65 / 8.56 / 7.48 seconds** and accepted/drafted counts **140/229, 139/231, 139/231**. The client-compatible template was enabled for this arm; its rendered prompt for this ordinary one-turn request is unchanged by regression checks. The repeat shows meaningful run-to-run timing variation, and the existing engine overlaps the new runtime's decode rates while completing these requests faster. The default desktop shortcut therefore keeps the existing HIP engine. This comparison establishes neither a reliable 42–60 t/s target nor a general Vulkan win. The official Unsloth binary remains separately available for future tests.

## Actual ZCode request and final desktop settings

The installed ZCode client sent 30,319 input tokens even for a short sentinel test. Its local provider requires a nonempty API key field; the server needs no authentication, and the placeholder `local` allowed the verified local request. The existing saved provider had no key. Automatic approval review blocked editing those saved settings, so the tests used an isolated local-only provider configuration; the user must enter `local` in the normal ZCode provider settings.

After observing the large initial prompt, the final desktop profile was tested at **65536 context / 8192 batch and microbatch**, still using the same HIP runtime, weights, MTP depth two and compatible template. Both measurements below were each the first ZCode request after server loading, with the identical input token count and zero cached input:

| Measurement | Original 32k context / 2k batch | Final 64k context / 8k batch |
| --- | ---: | ---: |
| Input tokens | 30,319 | 30,319 |
| Prompt time | 61.716 s | 54.607 s |
| Prompt throughput | 491.27 t/s | 555.22 t/s |
| Generated tokens (including reasoning) | 107 | 136 |
| Decode throughput | 26.17 t/s | 27.44 t/s |
| Complete client request | 66.296 s | 60.188 s |
| Visible result | `ZCODE_LOCAL_OK` | `ZCODE_LOCAL_OK` |

This single cold-request comparison reduced prompt time by 11.5% and full request time by 9.2%, while giving the 30k initial prompt more context headroom. Context and batch settings changed together, so it does not isolate a kernel improvement. Output token counts differed, and this is not a general throughput claim. The workstation desktop shortcut now uses this profile; the portable script's default remains 32k/2k. Raw evidence is in the `client-integration/` subdirectory of the local artifact folder, including `zcode-local-64k-8k-result.json` and `zcode-local-64k-8k-log-summary.json`.
