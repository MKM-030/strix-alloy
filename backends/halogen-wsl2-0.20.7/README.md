# Halogen 0.20.7 WSL2 backend

The exact image, engine, API, entrypoint and finite memory bridge are pinned. Four GCC 13.3 CPU products are bound to a complete build receipt. The installed one-slot 32K text profile passed a managed ready start, exact preflight-phase checks, authenticated model discovery and an authenticated functional request. No model, provider or engine was executed during source preparation or the CPU build; the later runtime qualification is recorded separately.

The default one-slot service retains 30/124 GiB startup admission; explicit capacity opt-in retains 30/131 GiB. The 18/18 GiB runtime reserves, text capacity policy and bearer authentication remain. The unchanged 59-field cached wire and CacheOff correction are retained. The preferred `qwen38-flash-next-drafter-r2-ht4.hgn` is verified before start. `HALOGEN_CONC_MODE` remains unset so the pinned 0.20.7 entrypoint owns its compatible v2 default. The qualified run selected both paths, registered `65,163,800,576` main bytes and then `1,488,268,672` HT4 bytes, and returned `HALOGEN_0207_FINAL_READY`. Capacity opt-in, two slots and vision remain separately unqualified.

The subsequent [natural 8K/16K benchmark](../../docs/benchmarks/halogen0207-natural-8k16k-20261120.md)
uses the same one-slot 32K text profile, paired 8192 prefill controls, Cache
Off/`no_store`, Thinking and Vision Off, cost-based MTP gate 0.90 and PLD `3,3`. One warmup
is excluded before three measured requests per size. At 8192 actual input tokens
the means are 951.045333 prefill / 45.087667 decode tok/s, 10.463028 seconds HTTP
QPC and 192/291 = 65.9794% native-head acceptance; at 16384 they are 938.335 /
43.544 tok/s, 18.579666 seconds and 180/279 = 64.5161%. The prefill/decode
figures come from API phase clocks without a RAW observer and therefore remain
unqualified as absolute phase throughput; all eight API phase sums exceeded
their whole-HTTP QPC durations. The matched 0.20.2 rows are a
non-causal reference rather than a measured version effect.

Run CPU checks with `python -m unittest discover -s backends/halogen-wsl2-0.20.7/tests`. Set HALOGEN0207_CAPTURE to a passive extracted image directory for the exact ELF/API/entrypoint cases; absent captures are explicit skips. Linux compilation fixtures are separate and may skip on Windows.
