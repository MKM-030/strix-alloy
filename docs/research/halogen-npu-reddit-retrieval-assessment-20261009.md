# NPU retrieval assessment — 9 October 2026

The [supplied Reddit post](https://www.reddit.com/r/StrixHalo/comments/1x0wx70/the_npu_in_your_strix_halo_is_finally_doing_real/) supplies a useful separate-task NPU candidate: retrieve relevant source passages and rerank them before asking the large GPU model. It does not supply a new Flash prefill, decode, or MTP acceptance mechanism. The source review was followed by one frozen CPU-only retrieval quality screen; no new GPU/NPU experiment or Halogen request was performed.

## What the published evidence supports

The author's [benchmark report](https://github.com/aic0d3r/qwen38-strix-halo-harness/blob/2da9e968cc4ffc57099d33bc95f0fd5dbbe5b373/docs/BENCHMARKS.md) reports 13.6 minutes for four completed NPU-assisted coding runs and about 18.7 minutes for three successful baseline runs, plus one failed baseline run. This is a small task-completion study on a 128 GB Linux machine, not a matched local engine-rate comparison. Its headline reduction is about 27%; baseline failure handling and task variability limit that figure.

The [retrieval extension](https://github.com/aic0d3r/qwen38-strix-halo-harness/blob/2da9e968cc4ffc57099d33bc95f0fd5dbbe5b373/extensions/npu-retrieval.ts) performs query embedding, CPU cosine selection, then NPU reranking. It returns source excerpts through a separate agent tool. It neither replaces Flash weights nor adds an MTP draft branch. Its usefulness would come from avoiding unnecessary large-model requests and context, rather than increasing native tokens processed per second.

The public companion [20-query scorer](https://github.com/aic0d3r/neon-ladder/blob/master/cap-eval.py), read on 9 October, labels its baseline ripgrep but invokes GNU `grep -ric --include=*.py` repeatedly for up to six query keywords. It also multiplies baseline seconds by 1000 while printing `s/query`; that displayed unit is wrong. The search-quality comparison therefore does not isolate an NPU placement benefit over a strong CPU semantic baseline. In a later comment on the supplied post, the author reports Semble CPU search 17/20 versus NPU 15/20 and grep 9/20. These are the author's results, not independently reproduced local measurements.

## Applicability to this host

The [Halogen NPU documentation](https://github.com/peonist-ai/halogen-flash-server/blob/fb04285a616befa8db34864b9ac7b9731dd9b7f1/docs/NPU.md) requires Linux amdxdna, an exposed accelerator device, host XRT with its NPU plugin, and supported GPU fabric-clock control. It also describes shared memory-bus and power-budget competition during concurrent work. Existing root-owned limited path observations found `/dev/dxg` but neither `/dev/accel/accel0` nor `/opt/xilinx/xrt` in our WSL distro. This does not establish that every possible WSL NPU route is unavailable; it does establish that the upstream launch is not currently ready to copy here.

The installed Windows NPU provider is a different route. Its earlier component execution does not qualify the upstream semantic models or a new reranker. Keep normal Halogen 0.17.3 serving unchanged and separate GPU/NPU work windows until coexistence is qualified.

## Selected experiment and first result

The default-off `code_lookup` prototype indexes 52 eligible tracked Python sources in 248 bounded chunks. An independent agent froze 16 authored source-location questions before root evaluation: 13 with known answers and three out of scope. Root evaluated CPU BM25 and the pinned `cross-encoder/ms-marco-MiniLM-L6-v2` reranker once, using the same corpus and candidate policy. This is a different small model from the author's Qwen pipeline and does not reproduce that pipeline.

BM25 returned a correct line span in its top three for 12/13 known questions; MiniLM did so for 10/13. The raw median lookup observations were 117.22 ms and 485.60 ms respectively. Neither correctly abstained on the three out-of-scope questions. These are heterogeneous single-task observations, not a repeated performance cohort or Halogen token-rate measurements. The [full local first-screen report](halogen-npu-code-lookup-first-screen-20261009.md) retains the frozen questions, source identities, scores, and limitations.

This MiniLM candidate remains disabled and will not be placed on the NPU: faster placement cannot repair its worse source-location ranking. The CPU index still needs calibrated answer sufficiency and a real workflow comparison before automatic routing. The post remains useful for the separate-task architecture; it supplies no qualified local engine gain. The frozen token-only acceptance selector also remains rejected. No NPU component milliseconds are converted to native prefill/decode or acceptance.
