# Credits

`strix-alloy` builds on other people's model, runtime and kernel work. This page keeps the longer credit list out of the README. Referencing a project here does not mean every patch is incorporated or that its authors endorse this fork.

## Foundation

- [pwilkin / ilintar](https://github.com/pwilkin/llama.cpp/tree/strix-halo): the `strix-halo` engine foundation, specialized Qwen kernels, QSA/indexer and PLE work, and the PROJFIX quantization used in the published runs.
- [ggml-org / llama.cpp](https://github.com/ggml-org/llama.cpp): the underlying inference runtime and its contributors, including the model and MTP work.
- [Qwen](https://github.com/QwenLM): the model family being run and tested.
- [AMD / ROCm / TheRock](https://github.com/ROCm/TheRock): the HIP runtime, compiler and Windows SDK used for the native build.

## Kernel, integration and correctness references

- [myhacsint](https://github.com/myhacsint/llama.cpp): shared-MTP fitting and speculative-controller work.
- [stew675](https://github.com/stew675/llama-cpp-rdna-boosts): RDNA performance patches and numerical-correctness investigations.
- [SixVolts](https://github.com/SixVolts/llama-halo-hybrid): Strix Halo/R9700 kernel and integration work.
- [halo-box](https://github.com/halo-box/strix-llama.cpp): RDNA3.5 kernels and recurrent-rollback fixes.
- [drluoto](https://github.com/drluoto/llama.cpp): model/tensor naming and reference work.

The [claim ledger](benchmarks/CLAIM-LEDGER.md) and individual experiment reports distinguish imported changes, candidates still being evaluated and measured negatives.

## Other implementations and shared findings

- [peonist-ai / Halogen](https://github.com/peonist-ai/halogen-flash-server): specialized Strix Halo inference and published benchmarks.
- [CIRU](https://github.com/ciru-ai/Qwen3.8-Flash-CIRU-STRIX-IU4): Qwen/Strix Halo integration, runtime changes and qualification reports.
- [olliehm](https://github.com/olliehm/qwen-flash-next-windows): Windows-native deployment, Lemonade integration and sequence-level validation.
- [Heretek-AI / Chlorine](https://github.com/Heretek-AI/chlorine-server): a separate engine project referenced during the investigation; not a verified Flash-Next speed comparison.

## Measurements, tools and community

Further references carried forward from this repository's earlier README:

- [baldlawyer / strix-halo-iommu-benchmark](https://github.com/baldlawyer/strix-halo-iommu-benchmark)
- [adelj88 / rocm_wmma_gemm](https://github.com/adelj88/rocm_wmma_gemm)
- [shisa-ai / hipEngine](https://github.com/shisa-ai/hipEngine)
- [mighty-studios / StrixHaloCluster](https://github.com/mighty-studios/StrixHaloCluster)
- [vincentkelleher / qwen3.8-flash-next-halo](https://github.com/vincentkelleher/qwen3.8-flash-next-halo)
- [MirkoCovizzi / ninfer-rtx5090-mobile](https://github.com/MirkoCovizzi/ninfer-rtx5090-mobile)
- [r/StrixHalo](https://www.reddit.com/r/StrixHalo/): testing, corrections and configuration reports.

For the memory-allocation distinction in the README, see [AMD's Variable Graphics Memory explanation](https://www.amd.com/en/blogs/2025/faqs-amd-variable-graphics-memory-vram-ai-model-sizes-quantization-mcp-more.html). A graphics allocation is not a separate physical memory bank or a guarantee of workload isolation.

Existing component licenses and attribution requirements still apply. This page does not replace license notices. If I have missed or misattributed your work, please open an issue so I can correct it.

---

*Compiled from this repository's earlier README credits plus the projects referenced in
[`benchmarks/engine-comparison.md`](benchmarks/engine-comparison.md). The kernel, quantization and
correctness references above name where the inherited work came from; see the
[applicability ledger](benchmarks/reference-forks-assessment-20260916.md) and
[claim ledger](benchmarks/CLAIM-LEDGER.md) for which changes are actually in this tree and which are
evaluated candidates or measured negatives.*
