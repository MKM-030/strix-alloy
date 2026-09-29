# Community tuning notes — 25 September 2026

Two useful reports supplied by the owner; neither is a benchmark of this WSL adaptation.

- [Flow Z13 / Windows](https://www.reddit.com/r/StrixHalo/comments/1wpycdv/two_days_benchmarking_local_llms_on_the_flow_z13/): reported display-off throttling makes display/power state a useful experimental control. The suggested AMD PMF cause is not established; do not disable services on that basis. The [author's benchmark repository](https://github.com/ihanesman/strix-halo-windows-llm-bench) suggests native llama.cpp candidates: 27B microbatch 256/MTP 2, Flash Next microbatch 4096/ngram-simple, f16 KV. These are not Halogen flags. Flash Next 256k was not measured there; two-slot gains include cache reuse and different output counts, not a fixed common decode window.
- [128 GB Bosgame / Linux](https://www.reddit.com/r/LocalLLM/comments/1won03e/strix_halo_128gb_local_llm_tuning_96gb_uma_made_a/): moving a large model from a pressured 64 GiB pool to 96 GiB helps explain the importance of avoiding paging. Its [guide](https://github.com/ddifofeu/strix-halo-128gb-llm-guide) uses native Linux/RADV and different Qwen3 models, with PP512/TG128 tests. Auto UMA and individual advanced GTT/TTM flags were not isolated. It does not establish a better Windows/WSL carve.

Next controlled checks: hold display/power and warm-up conditions constant; record swap/page faults; compare one Halogen prefill-block setting at a time. Keep the qualified 64 GiB carve/WSL 56 profile until a separate test proves otherwise. Halogen's N-Gram table is already disk-backed: llama.cpp lazy-mode is not an additional 47.7 GiB saving here.

The owner reports Windows idle RAM usage of **9 GB**. This is an observation, not an instrumented byte-accurate baseline or a guarantee of free RAM under inference load. No BIOS, service, driver or power setting was changed on the strength of these posts.
