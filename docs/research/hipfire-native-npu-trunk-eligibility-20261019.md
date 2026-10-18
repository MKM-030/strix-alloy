# Hipfire native NPU trunk eligibility — 19 October 2026

**Hipfire's bulk NPU prefill is a distinct useful design, but it cannot be enabled on our available native Windows model with a flag.** Two concrete source conditions prevent that: the model has mixed MQ4/MQ6 dense trunk projections, while preparation requires every projection to be MQ6; and the working paired NPU executor is Linux-only. This is an eligibility finding, not a claim that native Windows NPU acceleration is impossible.

The inspection used retained source, installed SDK headers and the model header/index only. No device/provider, build, inference, lifecycle, driver, model or frozen benchmark packet was changed. The [structured receipt](hipfire-native-npu-trunk-eligibility-20261019.json) preserves the observed header, bounded parse result and source hashes. Its timestamp is 18 October22:31UTC /19 October00:31Berlin. The archive's retained result reports base commit `ddee82c7464946c86f946d89af1b5634f212d466`; local source also contains unreleased0.4.3 work, so this is not represented as a pristine0.4.2.1 checkout.

## Actual model eligibility

The HFQM file at `E:/strix-alloy/hipfire-mq2-ddee82/models/qwen3.8-flash-next-base.mq2-xts-4500` has50,253 tensor-index entries and payload starting at18,407,424. The successful parser read only the32-byte header and bytes32..18,407,424; no quantized payload or full-model hash was read. The terminal receipt is retained in JSON; an index digest was not computed.

| Actual layer0 projection | Shape | HFQM wire tag | Format |
| --- | --- | --- | --- |
| linear_attn.in_proj_qkv.weight |10240×2560|47|MQ6G256V2|
| linear_attn.in_proj_z.weight |6144×2560|44|MQ4G256V2|
| linear_attn.in_proj_a.weight |48×2560|44|MQ4G256V2|
| linear_attn.in_proj_b.weight |48×2560|44|MQ4G256V2|

`hipfire-arch-qwen4/src/npu_trunk/forward.rs:454–475` checks **all** qkv/z/a/b and q/k/v/index references for MQ6G256V2 and exact dimensions before download/allocation. These observed a/b/z entries fail that check. The global MQ2 filename alone does not establish eligibility. The JSON's344-entry shape-filter counts include unrelated router/shared-expert tensors and must not be called a complete trunk-format census.

## What the source actually implements

The paired path moves bulk GDN/QSA **input** projections to XDNA2 using two banks and layer-major scheduling. Mixer cores, output projections, HC, MoE and decode stay on GPU. GPU pack kernels and direct BF16 arena consumers for GDN and QSA already exist. Admission needs gfx1151, Flash-Next familyB/K2560, full8192-row scratch, one device and no EP.

At full families, each bank has22.5MiB packed A,260MiB GDN C and220MiB QSA C: **1,005MiB across two banks**, plus24,576B placeholder pages. Private bankB forward scratch and resident B panels are additional. Family subsets can reduce C. These pages use existing DDR.

`gpu_forward.rs` and its Cargo target dependencies gate the real NPU executor to Linux; non-Linux planned/pipelined queries return false. `railgun::npu` opens `/dev/accel/accel0`, uses the annotated amdxdna kernel7.0/driver0.7.0 UAPI, user-page BOs, PDI/TXN command chains and DRM syncobj timelines. A generation-bound relay orders GPU system-release after A packing, NPU completion, terminal-word publication, GPU stream wait/system-acquire before C consumption, and last-consumer retirement before bank reuse. This machinery is not a Windows MCDM/XRT backend.

The arithmetic is also distinct: MQ6 decode/requantization to W8 with grid scales, packed activation and direct BF16 epilogue. **on==emulate** compares the NPU against its arithmetic twin. Ordinary GPU-off comparisons are KLD gated, not universal byte equality. No decode or MTP-acceptance increase follows from a prefill-only route.

## Native Windows reuse and concrete next change

Our existing native XRT host provides reusable device/context/kernel/run/BO lifetimes, ABI checks and bounded waits. Its old integer/H-projection designs and copied/synchronized I/O do not implement the G80 panel PDI/TXN/BF16 contract. The installed `C:/Xilinx/XRT/include/xrt/xrt_bo.h` exposes4K-aligned user-pointer constructors and Windows64-bit BO export handles. That makes **same-process native Windows sharing plausible but unqualified**: these declarations do not establish dual HIP/XRT registration, cache visibility, stream wait/control-word behavior or coexistence on retained MCDM32.0.20102.3930.

The smallest coherent implementation path is therefore a native Windows Hipfire port comprising mixed-MQ4/MQ6 trunk preparation and new keyed quality calibration; an XRT adapter for the G80 image/arguments/panel offsets; and shared A/C/control pages with release/acquire/retirement semantics integrated into the existing pair executor. It also needs a supported coexistence/fabric contract or authoritative exemption and a complete matched engine result. The [retained fabric review](halogen-windows-fabric-support-20261005.md) does not yet supply that contract.

A Windows NPU→WSL Halogen path adds another missing allocation/import/fence boundary. The [correct staged component handoff](halogen-npu-wsl-handoff-20261007.md) does not establish shared arenas or a bulk speedup. Do not attach the old responder blindly, reinterpret its tiny dispatch floor as bulk throughput, or bypass stock admission/calibration. No transport was implemented here.

The [existing fresh-source checkpoint](../../server/.local/halogen-regression-20261019/fresh-sources.json) retains the author's roughly10.1%16K TTFT improvement on native Linux7.3rc7 with IOMMU PerfOpt. It motivates this separate bulk mechanism; it is not a local speed forecast. GPU prefill/decode improvements remain independently testable while these Windows-specific requirements are unresolved.
