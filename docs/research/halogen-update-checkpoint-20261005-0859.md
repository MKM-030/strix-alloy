# Halogen update check — 5 October 2026, 08:59–09:14 UTC

Official releases and the supported GPU/NPU contract are unchanged from the
06:16 checkpoint. No new measurement, restart, installation, driver or runtime
change was made. The completed natural-prose 131072/260000 cohorts were not
repeated; their results remain in the [measurement report](../benchmarks/halogen0162-natural-long-20261005.md).

Halogen `main` and `v0.16.2` still resolve to
[`7f31bbd4021f217a1be9776bdb7304bcf8eca62d`](https://github.com/peonist-ai/halogen-flash-server/commit/7f31bbd4021f217a1be9776bdb7304bcf8eca62d).
The annotated tag is `71b5339a1dc74c26dc0952989e64aee4b06a6546`; the
GitHub Releases collection is empty. README, changelog,
[flags](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md)
and the [NPU contract](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/NPU.md)
remain unchanged. They do not establish the needed Windows FP11 fabric hold
or a supported replacement-MTP interface; the overlap override is unsupported.

| Official channel | Observed availability |
| --- | --- |
| [395 graphics](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html) | Optional 26.9.2 WHQL; Recommended 26.8.1 WHQL |
| [26.9.2 package](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-9-2.html) | Driver Store 32.0.32015.2008; bundled NPU MCDM 32.00.20102.3930 |
| [Ryzen AI software](https://github.com/amd/RyzenAI-SW/releases) | Latest 1.8.0 |
| [Separate NPU channel](https://ryzenai.docs.amd.com/en/latest/inst.html) | Production 32.0.203.376; minimum 32.0.203.280 |
| [Windows ML execution providers](https://github.com/microsoft/WindowsML/wiki/Windows-ML-Execution-Provider-Releases) | VitisAI 1.8.75.0 / EP1605 current, 1.8.80.0 upcoming; MIGraphX 1.8.64.0 current, 1.8.65.0 upcoming |

No relevant new precision or Halogen/WSL fix was established in the checked
release notes. The [OGA hybrid recipe](https://ryzenai.docs.amd.com/en/main/oga_model_prepare.html)
uses NPU prefill followed by GPU token generation, which does not establish
simultaneous execution or a Halogen MTP gain. The
[monitoring SDK](https://www.amd.com/en/developer/ryzen-master-monitoring-sdk.html)
does not establish the required FP11 hold/readback contract;
[ROCm FCLK capping](https://rocm.docs.amd.com/en/docs-7.14.0/about/release-notes.html)
is documented for MI300A. These are scoped documentation findings, not proof
that every possible hardware interface has been excluded. Installed drivers
were not changed or re-enumerated.

Two older SSD ideas were newly inspected through the
[Rulith discussion](https://www.reddit.com/r/StrixHalo/comments/1wv2x6c/rulith_inference_formerly_strix_llama_04_125b_moe/)
and primary code. The October 4
[pregather patch](https://github.com/rulith-dev/rulith-inference/blob/a3f0a386714927caee8511aa8bbb1517cd0e3cfb/patches/apply_prefill_043.py)
schedules upcoming prompt rows early and owns pending asynchronous entries.
Its [results](https://github.com/rulith-dev/rulith-inference/blob/a3f0a386714927caee8511aa8bbb1517cd0e3cfb/docs/results.md)
report a final 110K-chunk row wait of 256 to 3 ms. The reported 2.7–9.4% prefill
gain belongs to the complete 0.4.3 bundle, not an isolated pregather ablation.
The October 1 [SSD wake patch](https://github.com/rulith-dev/rulith-inference/blob/cdd2ef29674eb7ea2a297553a895b0e5eea91414/patches/apply_ple_wake_041.py)
uses Windows unbuffered overlapped reads; its Linux wake function is empty.

Neither is a deployable stock Halogen/HGN option. The existing local controls
expose gather concurrency 32/64, and the lookup adapter qualifies a source
mount. The sealed bridge operates at startup allocation/upload. Retained
Halogen disassembly shows current row IDs copied to the CPU, followed by
reads from mapped lookup pages; it provides no implemented next-chunk
deferred-reader/consumer ownership contract. A transfer would require new
engine integration, not changing a flag. No patch or benchmark was started,
and no Rulith component or bundle result is claimed as a Halogen tok/s gain.

Successful GitHub API checks found no commits since 06:16 UTC in Halogen,
Rulith or the inspected GSQHalo branch. Reddit freshness was incomplete:
the served StrixHalo listing ended at 03:53 UTC, while LocalLLaMA responses
were stale. This check cannot prove the absence of all newer Reddit posts.

Controller 29004 and backend 11988 retained their original creation times and
run IDs; the same owned container remained running. Both health endpoints
were ready/idle with completed8/cancelled0. Final physical reserve was 25.75 GiB,
with 118.64 GiB commit headroom. The NPU remains disabled. Full
hidden-projection accuracy and a useful NPU engine integration remain
unqualified; the existing blocked goal status was preserved. No numbers
notification was due during this check.

[Structured receipts and final health](halogen-update-checkpoint-20261005-0859.json).
The next official check is due at 10:59:32 UTC, two hours after this check began.
