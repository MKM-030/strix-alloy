# GPU H candidate: resident native-rounded BF16 weights

Source-only audit completed 6 October 2026; filename retains the assigned 5 October work item.

**A concrete next GPU implementation is a count1 MTP H kernel using resident predecoded BF16 weights, the original four interleaved native BF16 dot2 chains, and the original reduction schedule.** It removes repeated unsigned-code conversion, affine dequantization and weight rounding from every H call. It is implementable with the installed gfx1151 HIP device toolchain and can be compared directly with the retained original M4 kernel. It has no measured speedup yet: weight traffic grows, so it may lose when memory dominates. This is a scoped offline kernel candidate, not another NPU-H live cohort.

Ordinary target prefill does not use this late MTP H boundary. The candidate addresses MTP head generation/replay during decode. It has no demonstrated effect on ordinary prefill, target verification cost or acceptance; exact native arithmetic is intended to preserve proposals, while eventual head/token checks establish that result.

## Original kernel and actual dependency

For normal store7/variant0 and `HALOGEN_LQ8_WAVE` absent or `1`, count1 wire D calls hidden RMS at host `0x17db62d`, then H dispatcher `0x178cf90` at `0x17db65e`. It supplies descriptor `model+0x980`, normalized input `*(base+0x18db210)`, output `*(base+0x18db228)`, `M=4`, `N=K=2560`. The four streams are slices of one whole-row 10,240-element BF16 RMS result; they are not independently normalized rows.

The selected GPU function is `_ZN7halogen12_GLOBAL__N_16k_lq8wILi4ELi16ELi1EEEvPKhPKtPtll`, entry `0x2d7800`, size 2,360 bytes; descriptor `0x1fa640`. Native grid/block are `160/256`, wave32, LDS0/private0, metadata SGPR21/VGPR88. Its user arguments W/X/Y/K/N are at offsets `0/8/16/24/32`, total kernarg40/alignment8, with no hidden arguments. Native H is already one M4 launch sharing decoded weights across four streams.

Return `0x17db663` reaches D seed setup `0x17db9bd`, seed launch `0x17dbb91`, then layer48 dispatch `0x17dbbe1`. H output and the seed consumer are ordered on the default HIP stream. There is no explicit H-to-seed host readback or fence in that path. A replacement must enqueue its GPU output on that stream and preserve this ordering; inserting per-H synchronization would change the baseline dependency.

Retained original timing has four warmup and sixteen measured balanced A/B pairs. H event mean is **158.707124125 µs**, range `150.858..174.740002 µs`. That bracket excludes setup, copies, comparisons and I/O and includes host enqueue/event instrumentation. The **487.1700625-µs host mean covers both E and H enqueue-through-pair-end wait**; it cannot be used as an H-only replacement budget. Neither timing is a live full-head/token-throughput result.

The negative NPU comparison remains: fastest retained complete vector-H call `355.6 µs` already exceeds original GPU H, before its required capture/bridge/GPU publication. A resident GPU candidate avoids those crossings and changes a distinct mechanism.

## Existing vector loads and exact arithmetic

The retained original HSACO was rehashed and inspected read-only with installed AMD LLVM `llvm-objdump`, bounded to `0x2d7800..0x2d8138`. This executes a disassembler only, not a compiler or GPU runtime. The installed disassembler leaves 48 words as `.long` and can misinterpret the following word of an unrecognized instruction; this audit therefore counts only recognized, correctly bounded instruction families and uses the earlier pinned lane/address audit for complete mapping. It does not claim a fully decoded new instruction listing.

The stock shader already has:

| Native GPU instructions | Actual work |
|---|---|
| `0x2d78cc..0x2d7918` | Constructs 16-code sublane position and affine address; `global_load_b128` at `0x2d7910` loads 16 raw u8 codes, `global_load_b32` at `0x2d7918` loads the packed FP16 scale/bias. Subsequent-loop counterparts are `0x2d7eb8/0x2d7ec0`. |
| `0x2d7a28..0x2d7a60` | Eight `global_load_b128` instructions: two 16-byte loads for each of four normalized BF16 input streams. |
| `0x2d79c0..0x2d7a8c` | Sixteen recognized unsigned-byte-to-FP32 conversions per sublane chunk. |
| `0x2d7a9c..0x2d7b18` | Sixteen `v_fma_mix_f32`: code times FP16 scale plus FP16 bias, yielding FP32. |
| `0x2d7b20..0x2d7cac` | Sixteen recognized bit-extracts and sixteen `v_add3_u32` operations implement BF16 RNE using bit16 and `0x7fff`, followed by pair packing. |
| `0x2d7cdc..0x2d7e2c` | Thirty-two recognized `v_dot2_f32_bf16`, interleaved as eight ordered pairs for each of four streams. |
| `0x2d7e3c/0x2d7e44` | Four separate FP32 chunk additions, encoded as two dual-ADD instructions. |
| `0x2d7ee4..0x2d8030` | XOR-distance `8,4,2,1` butterfly; sixteen `ds_bpermute_b32` exchanges across the four streams and separate FP32 additions. |
| `0x2d8080..0x2d812c` | Final BF16 RNE and four halfword output stores from the row's p0 lane. |

Let output `o=16*workgroup+(workitem>>4)` and sublane `p=workitem&15`. Each wave has two independent 16-lane output rows. Each sublane processes chunks `k=16*p+256*q`, `q=0..9`; a raw row is K u8 codes followed by K/64 FP16 scale/bias pairs, stride `2720` bytes. Neighboring p lanes access adjacent 16-byte code blocks and adjacent 32-byte BF16 input blocks. Four neighboring lanes share one affine pair, so cache reuse is possible. This is already contiguous, vectorized access. Generic vector loads, four-stream batching, affine FMA and BF16 dot2 are not new optimizations here.

For finite weights, the decoded boundary is:

```text
scale, bias = FP32(exact FP16 stored values)
z = native fused FP32(code_u8 * scale + bias)
weight_word = BF16_RNE(z)
```

The unsigned u8 times finite FP16 product needs at most nineteen significand bits and fits FP32, so the multiply is exact; separate ordinary FP32 multiplication and addition give the same affine value as the FMA under the recovered nearest-even mode. The BF16 rounding boundary is still mandatory. Finite BF16 RNE is `upper16(bits32 + 0x7fff + ((bits32>>16)&1))`; exceptional-value behavior must follow the native decoder if such weights are admitted.

The projection schedule must remain:

```text
for each output o and stream m:
    S[p] = FP32(+0), for p=0..15
    for q=0..9:
        k = 16*p + 256*q
        D = FP32(+0)
        for pair=0..7:
            D = V_DOT2_F32_BF16(X[m,k+2*pair:k+2*pair+2],
                                Wbf16[o,k+2*pair:k+2*pair+2], D)
        S[p] = ADD32(S[p], D)
    for distance in [8,4,2,1]:
        next[p] = ADD32(S[p], S[p XOR distance])
        S = next
    Y[m,o] = BF16_RNE(S[0])
```

Do not merge ten chunk chains into one long dot2 accumulator, reduce sequentially across p, or convert the dot2 into scalar FMAs/ordinary BLAS. Internal dot2 rounding remains unresolved in the portable CPU/NPU reference, but a GPU candidate using the **same hardware instruction on the same packed words in the same order** does not need to guess it. Preserve the native nearest-even/denormal mode and separate ADD boundaries; avoid reassociation/fast-math.

## Concrete candidate implementation

Use a new HIP device module containing two kernels, without changing the original engine or code object:

1. **Initialization expansion:** read the existing raw Q8 H matrix once and write a `2560*2560` row-major BF16 matrix. Use the original affine FMA and BF16 RNE boundaries, preferably the same GPU instruction/bit sequence. Keep original Q8 bytes available for fallback. Expansion and module/allocation setup are outside recurrent H; record their cost separately when later measured.
2. **Recurrent M4 projection:** same `160/256`, wave32 and `o/p/q` mapping. Each lane loads sixteen already-packed BF16 weights as two aligned 128-bit loads, reuses them for all four streams, issues the original eight-pair dot2 chains, chunk ADDs, butterfly and output conversion. BF16 row stride is `5120` bytes; p step is32 bytes and q step is512 bytes. Keep four stream input offsets `2*K*m` and output offsets identical to stock. No dynamic allocation, host copy, transpose, extra recurrent launch or host wait belongs in this kernel.

One possible device-level instruction contract uses explicit AMDGPU inline assembly for `v_dot2_f32_bf16` with packed `uint32` operands and FP32 accumulator, and explicit ordered FP32 ADD operations. `uint4`/equivalent aligned loads provide the 128-bit weight/input access. Use the same p-indexed lane exchange for XOR reductions. Source syntax alone is not a claim about final emitted code; the scoped offline implementation should retain a disassembly/metadata receipt showing these actual instructions and order.

The existing FC dispatcher entry `0x178cf90` has ordinary SysV arguments `(descriptor, X_device, Y_device, N_i32, M_i32, K_i64)`; this is a more practical later launch seam than an interior H shader patch. A count1 D wrapper can select only hidden descriptor `model+0x980`, `M4/N2560/K2560`, then enqueue the candidate into the original Y buffer on stream0. Unsupported shape/policy or unavailable prepared weights calls stock. The existing head/TLS and FC publication sources already supply the necessary source patterns; do not route this candidate through the Windows NPU wire or copy GPU pointers to another API/process. First implementation should be the standalone frozen-input kernel/harness, with no live detour required.

## Quantified tradeoff

There are `2560*16*10 = 409,600` lane/chunk iterations per H. Recognized stock code has sixteen u8 conversions, sixteen affine FMAs, sixteen rounding bit-extracts and sixteen rounding integer ADDs per iteration: **at least 64 removable lane operations per iteration, or 26,214,400 per H**, excluding removable pair packing/address work. This is an instruction count, not cycles or FLOPs. Dequantization is shared across all four streams already.

The candidate retains `13,107,200` lane dot2 operations (`26,214,400` MACs; `52,428,800` projection FLOPs), `1,638,400` chunk FP32 ADDs and `655,360` butterfly FP32 ADDs. It may lower register pressure by removing the temporary decoded FP32 weights and bit-rounding registers; native metadata is VGPR88. No candidate VGPR count, occupancy or scheduling gain is known before offline emission.

| Count1 H weight quantity | Stock raw Q8 | Candidate BF16 |
|---|---:|---:|
| Unique weight storage/read footprint | 6,963,200 bytes (6.640625 MiB) | 13,107,200 bytes (12.5 MiB) |
| Per-lane weight load bytes summed over H | 8,192,000 | 13,107,200 |
| Weight load instructions per lane/chunk | one128-bit + one32-bit | two128-bit |
| Added allocation with stock Q8 retained | — | 12.5 MiB |
| Both H representations resident | — | 20,070,400 bytes (19.140625 MiB) |

The stock issued-byte count includes the affine pair loaded four times per64-code group; its unique footprint counts that pair once. These are memory operands/footprints, not measured DRAM traffic. Input unique footprint remains20,480 bytes and input load operands total52,428,800 bytes across output rows in either kernel; caches may satisfy much of that reuse. Output remains20,480 bytes.

Decoded weight footprint is **1.88235×** stock unique bytes and **1.6×** stock weight load operands. Extra unique bytes are6,144,000; the illustrative added transfer cost is122.88/61.44/30.72 µs at effective50/100/200 decimal GB/s. Those bandwidths are examples, not measured device capabilities. Under a strictly memory-bound equal-bandwidth model the candidate loses; under a decode/rounding/register-pressure bound it can win. The observed stock unique-footprint/event ratio is43.875 GB/s, but the event bracket contains much more than weight traffic and is not a bandwidth measurement.

The maximum savings from deleting H entirely in this bracket is158.707 µs per H call; a2× H kernel saves79.354 µs. For total decode-step time T and h H calls on its critical path, a component change saves at most `h*(t_stock-t_candidate)`, and speedup is `T/(T-h*(t_stock-t_candidate))` if every other cost and acceptance remain fixed. No T/h/acceptance receipt is established here, so no token/s or percent end-to-end gain is claimed. An H-only result cannot be extrapolated to ordinary prefill.

## Toolchain path available locally

Read-only path/version/hash inspection found:

| Tool/source | Local evidence and purpose |
|---|---|
| Explicit HIP compiler | `C:/Program Files/AMD/ROCm/7.2/bin/clang++.exe`, 102,940,944 bytes, PE version21.0.0git, SHA256 `b99a59bfbd1a878c2938f7c7c6b6c056399111bcffe9e157be1d6d9e30f1bc7b`. |
| Explicit driver/linker | Same directory `hipcc.exe` (462,088 bytes), `hipcc.bat` delegates to it; `ld.lld.exe` (67,504,904 bytes). Use these exact paths: PATH resolves hipcc/amdclang wrappers in Python312 Scripts instead. |
| gfx1151 device inputs | `C:/Program Files/AMD/ROCm/7.2/amdgcn/bitcode/oclc_isa_version_1151.bc` plus ABI400/500/600 bitcode, hip/ockl/ocml bitcode and installed HIP BF16/runtime headers exist. This is a viable device-only offline compile/link path; no compiler was invoked and its output is not yet qualified. |
| Static inspection | `C:/Program Files/AMD/ROCm/7.2/bin/llvm-objdump.exe`, SHA256 `abb4332b579bc183eed0843d6ac6cffcebf8879e300a55b3693394fed0580536`; bounded read-only original disassembly executed. Its incomplete decoding is disclosed above. `llvm-readobj.exe` also exists. |
| Windows HIP runtime | `amdhip64_7.dll` exists, SHA256 `b558d1e23023e925c69b3a398f1d9a95e9c268bd347b7e596fbd08f013e84593`; presence is not a Halogen Linux ABI/handle-sharing result. No load/query. |
| Vulkan compiler/headers | `C:/VulkanSDK/1.4.357.0/Bin/glslc.exe` and `glslangValidator.exe`, headers357, SPIR-V BF16 capability declarations and `VK_KHR_shader_bfloat16` type/dot/cooperative-matrix feature fields exist. |
| Vulkan loader | `C:/windows/System32/vulkan-1.dll`, PE version1.4.357.0, SHA256 `cd862090370454630b31b174e3d4eb474fda38ea034998d1fe1767b0c99a8696`. No `vulkaninfo`/device/extension query. |

For the scoped offline implementation, use explicit HIP device-only `--offload-arch=gfx1151`/gencode emission with the installed ROCm7.2 compiler and `-mcode-object-version=6`, then inspect the resulting ELF/metadata before runtime use. **HSA ELF ABI byte4 is the original identity; it corresponds to compiler code object V6.** The option `-mcode-object-version=4` instead emits ELF ABI byte2 and does not match this pin. Root's subsequent offline inspection established that distinction; the harness checks actual `e_ident[8]==4`. The raw HSACO, not a Windows host executable/DLL, is the portable artifact for the original Linux HIP module loader. Offline compilation is outside this agent's audit.

The later standalone host runner should reuse the existing pinned Linux image and its exact HIP module loading mechanism/runtime seal `6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5`; no WSL/container was opened now and current Linux compiler availability was not queried. Windows toolchain presence is enough to start writing the device kernel; it does not imply direct access to Halogen's Linux device buffers. Vulkan is an alternative source/toolchain experiment only: current headers do not prove active device BF16-dot support, exact instruction lowering, or HIP-buffer interoperability. HIP is the direct first route for this candidate.

## Decision and next scoped work

**Proceed to an offline HIP expansion+M4 kernel implementation and a standalone original-versus-candidate fixture harness.** This candidate removes a concrete recurring operation rather than duplicating native vectorization. Keep original raw weight/input hashes and native arithmetic; aim for identical BF16 A/B outputs. A later finite same-stream GPU comparison should measure inputs ready on GPU through output ready for the existing seed consumer, with initialization separate and no added stock host wait. It should precede any full-head/acceptance claim. No repeat NPU-H live cohort is warranted by this source audit.

Broader GPU work still needs separate target-prefill/verification kernels and complete decode/acceptance comparisons: H is one small late head component. This candidate should not consume the entire optimization effort or be presented as a prefill improvement.

## Rechecked source/code pins

| Artifact | SHA256 |
|---|---|
| Original gfx1151 HSACO,17,704,408 bytes | `45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83` |
| Existing FC timing C | `e6da80abb13b318354627788888bd5537e905bb9858713da13152d9a115ca61f` |
| Existing FC dispatch audit | `e6f0ef9eb1cb1c73dc13df9aaf1a95977e97eee50cb8be85fe9dda5c9faa48c0` |
| Existing accumulation-order audit | `d44524bff59f76f46bebf148ce404906af2187df261d196f0a755e6ad02ca7ce` |
| Existing GPU timing summary | `5f1ee5c9acf68d318d1c7adcb9e33e746f36c73807626921fc9e432f37add796` |

The host ELF/disassembly pins remain those in [the FC dispatch audit](halogen-native-d-fc-dispatch-20261004.md); native arithmetic/reduction is documented in [the accumulation-order audit](halogen-native-fc-accumulation-20261004.md). Timing source is `scripts/benchmarks/halogen0162_fc_timing.c:372..407`; summary is `server/.local/optimization9h-20261004/alloy-fc-timing-f7c3c720f88f4edfaa0a1adcee68a56d/gpu-timing-summary.json`. No compiler/runtime/hardware/model payload/process/lifecycle action or existing-source/continuation edit occurred. Only this new report was written.
