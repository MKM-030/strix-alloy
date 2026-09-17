# strix-alloy

Windows-native Qwen inference on AMD Strix Halo, built on [pwilkin's `llama.cpp` fork](https://github.com/pwilkin/llama.cpp/tree/strix-halo).

## Why I started this

My old desktop stopped working. It was still on DDR3, and rather than rebuild around it, I bought a **BOSGAME M5 with 128 GB of memory**. I still have an **NVIDIA RTX 2070 SUPER** that I want to put back to use.

The M5 is also my everyday Windows PC. I want to work on it, develop on it and play games—not turn it into a dedicated Linux inference server. That is the reason for this project: getting large local models running well on the machine I actually use.

I'm also building **REV:N**, an AI-driven GTA V / FiveM project. The goal is to develop and test in-game while hosting the models on the same computer. REV:N is being designed around local models, cloud models, or a mix of both, so players and server owners can choose what suits their setup. `strix-alloy` is my work on the local-inference side, not the game itself.

## The setup I'm working toward

The plan is to use the M5's **Radeon 8060S for LLM inference** and the **RTX 2070 SUPER as an eGPU for GTA/FiveM and other games**, while keeping Windows available for development and normal applications. The NVIDIA card would render games, not add its VRAM to the model's memory pool.

The M5 has a Ryzen AI Max+ 395 and 128 GB of unified LPDDR5X memory. My current firmware allocation reserves 96 GB for the integrated GPU, leaving roughly 31.6 GB visible to Windows as system RAM. That remaining memory is **not all spare gaming RAM**: Windows, development tools and the CPU-side parts of inference—including model-table caching—need it too.

The two GPUs would separate rendering from inference, but not create two independent computers. CPU time, host memory, storage and the APU's memory bandwidth and power budget can still become shared bottlenecks.

**The eGPU and simultaneous gaming/inference setup are still goals, not validated results.** The numbers below were measured with inference running on its own, not while playing GTA.

## Current numbers

Published measurements as of **17 September 2026**: native Windows HIP, TheRock SDK, Qwen3.8-Flash-Next IQ4_NL "PROJFIX," and a 96 GB carve. MTP runs use a shared Q8_0 draft head. Prefill means processing the input; decode means producing the continuation.

| Measurement | Result | Conditions |
|---|---:|---|
| Synthetic serial, `llama-bench tg128` | **31.49 ± 0.17 t/s** | No drafter; pseudorandom token inputs, not a generated answer |
| Synthetic prefill, `pp16384` | **892.59 ± 22.50 t/s** | Batch and microbatch 16384 |
| Served serial decode | **28.3 t/s** | 16,384-token context; no drafter |
| Served MTP decode | **45.31 t/s** | Warm median for one 259-token instructed prompt; maximum draft depth two |
| Served MTP, long-context ladder | **31.0–32.8 t/s** | Separate tests at 16,384–251,904 occupied tokens |
| Maximum-prefill serving setup | **1,031 t/s at 16k; 812 at 251,904** | Warm, no drafter, microbatch 16384; server-reported timing |

`±` is sample standard deviation. These rows are different workloads and configurations—not one combined performance promise. In particular, **31.49 without speculation and 45.31 with MTP do not measure the same thing**.

The full records, including corrections to earlier figures, are in the [benchmark guide](docs/benchmarks/engine-comparison.md) and [claim ledger](docs/benchmarks/CLAIM-LEDGER.md). Completing a 251k request demonstrates capacity; it does not establish comprehensive long-context correctness.

## How this compares

For **speculative serving**, these are some published results from the projects I follow:

| Project | Decode | What was measured |
|---|---:|---|
| strix-alloy | **45.31 t/s** | One short instructed prompt; warm median, MTP depth two |
| Halogen / peonist-ai | **45.3 t/s** | Mean across ten prompt shapes; reported 0.6.0 measurement |
| olliehm's Windows/Lemonade stack | **38 t/s** | MTP serving; headline does not specify occupied depth or aggregation |
| CIRU IU4 v4.4 | **44.53 t/s** | MTP3 on a 12,960-token incident replay; one comparison block |
| CIRU IU4 v4.4 | **60.351 t/s** | Pooled MTP decode on a short HumanEval 0–9 speed panel—not general chat |

This is **not a leaderboard**. Different prompts, weights, operating systems, power settings and statistics prevent a fair ranking. Our one-prompt median matching Halogen's ten-prompt mean does not establish a tie.

The [full comparison](docs/benchmarks/engine-comparison.md) separates synthetic, served-serial, MTP and prefill results, includes ilintar's reference numbers, and links the sources. That is where the detailed tables belong.

## Getting started

This is mainly for Strix Halo owners who want local inference on a Windows machine they also use for other things, and developers investigating the same hardware. It is an experimental build and measurement project, not a one-click application.

Start with the [Windows setup guide](setup/README.md). The [engine patches](engine-patches/), [build provenance](docs/benchmarks/engine-provenance-20260916.md) and [benchmark records](docs/benchmarks/) contain the implementation and reproduction details. Check the [claim ledger](docs/benchmarks/CLAIM-LEDGER.md) for unresolved correctness and stability work before relying on a result.

## Working together

I'm not building this against Halogen, CIRU, olliehm or the other Strix Halo projects. I compare them because we're working on related problems, and I would rather exchange patches and measurements than repeat the same experiments separately.

Most of the kernel work comes from upstream. My contribution here is the Windows integration, local patches, tested configurations and measurement work. The patch series, harnesses and results are public, including experiments that failed and claims I had to correct.

Special thanks to **[pwilkin / ilintar](https://github.com/pwilkin/llama.cpp)**, **[llama.cpp](https://github.com/ggml-org/llama.cpp)**, **[Qwen](https://github.com/QwenLM)** and **[AMD's TheRock team](https://github.com/ROCm/TheRock)** for the foundation; and to **[peonist-ai / Halogen](https://github.com/peonist-ai/halogen-flash-server)**, **[CIRU](https://github.com/ciru-ai/Qwen3.8-Flash-CIRU-STRIX-IU4)** and **[olliehm](https://github.com/olliehm/qwen-flash-next-windows)** for the work and measurements worth learning from. [Full credits](docs/CREDITS.md) include the other kernel authors and community projects referenced here.

I'd be happy to help test a change on Windows, share a result that didn't work, or contribute a useful patch back. The aim is better, correct inference on this hardware—and to find out together how close we can get to its practical limits.
