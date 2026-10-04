# DD dense and INT8 weight route: static evidence, 2026-10-04

The public SD dense GEMM can pack decoded FP32 weights into BFP16 ebs8 constants. The installed 1.8.0 SDK also contains suitable padded transaction names. A usable installed client contract is nevertheless unproven: the pinned DLL and import library export **zero** SD `gemm` or LiquidAI `gemm_bf16` methods. No dense client, expert export, native import, or hardware admission was made. Existing INT4 preparation, gates, and receipts remain unchanged.

The machine evidence is [halogen-dd-dense-weight-route-20261004.json](halogen-dd-dense-weight-route-20261004.json). Its DLL/export review uses `dumpbin` metadata only. The inventory was already saved from the staged wheel; only two 24-byte parameter members were read from `dyn_bins.zip`, with CRC validation. The 405 MB archive was neither streamed nor rehashed.

## Disclosed dense API and missing installed contract

The installed header declares `ryzenai::sd::gemm<InT,WtT,BiasT,OutT>` with this constructor:

```cpp
gemm(ifm_dtype, weight_dtype, bias_dtype, out_dtype, load_xrt, attrs);
```

Its public methods include both `initialize_const_params` overloads, `execute`, `set_params(xclbin,pdi_name)`, `get_layer_params`, `shuffle_wts_bfp16(float*,float*)`, transaction/parameter accessors, buffer requirements, and control-packet metadata accessors. The header supplies declarations, not their implementations.

AMD's [pinned public SD implementation](https://github.com/amd/DynamicDispatch/blob/b3051f03e20aab237cda3bbe4cd2081f76b72b06/src/ops/sd/gemm.cpp) discloses:

- BF16 input/output; `float32` or already packed `bfp16ebs8` weights. The float specialization is `gemm<uint16_t,float,float,uint16_t>`.
- Attributes `weight_shape=vector<int>{K,N}`, `input_shape={B,M,K}`, `output_shape={B,M,N}`, and `bias_enable` as bool or integer vector.
- Row-major logical K×N float weights and a bias tensor are passed to constant initialization. The float path accesses both tensor slots even when bias is disabled. The packed path copies the packed byte extent.
- Packing transposes K×N and groups eight consecutive K values for each N. Constants occupy `K*N/8*9`, plus `(K/svK)*N*2` when bias is enabled.
- Parameter words are `[M,K,N,L1M,L1K,L1N]`; the last two control weight tiling. Input/output tensors use ordinary contiguous BF16 storage.

The [public test](https://github.com/amd/DynamicDispatch/blob/b3051f03e20aab237cda3bbe4cd2081f76b72b06/tests/cpp/unit_tests/test_sd_gemm.cpp) demonstrates the float specialization and [packer](https://github.com/amd/DynamicDispatch/blob/b3051f03e20aab237cda3bbe4cd2081f76b72b06/src/ops/sd/sd_helper.hpp). This older source uses the `sd_` path. The installed header adds `sd_fastpm_`, preemption, slice, and transformation state; their selection attributes and the selected binaries' bias requirements are not disclosed. An older formatter cannot substitute for that missing contract.

The DLL does export the transformer `MatMulQ` BF16/BFP16 specialization and `OpBuilder::create`. Its SDK header has no implementation showing a decoded-float constant path or linking it to these SD transactions. The disclosed `initialize_bfp16_wts` takes int8 weights, zero points, bias and scales. Generic factory availability does not establish installed SD/LFM registration. No dtype strings or hidden registry entries were guessed.

LiquidAI's only plain dense LFM inventory tuple is `(B,M,K,N)=(1,1,2048,65536)`. It cannot enclose FC1's K2560; FC2 alone would require 144 MiB of packed weights per expert before bias. Its direct methods are also absent from the exported ABI.

## Padded shapes and constant budget

There are 61 plain dense primary transactions across `sd_fastpm`, `sd_preemption`, and `lfm2`. Neither requested FC has an exact B1/M1 tuple. The following SD transactions enclose both:

| FC | Logical K×N | Padded B,M,K,N | Parameter words | Weight bytes | Optional zero-bias bytes |
| --- | --- | --- | --- | ---: | ---: |
| FC1 | 2560×1280 | 1,1,2816,1280 | 1,2816,1280,16,176,80 | 4,055,040 | 40,960 |
| FC2 | 640×2560 | 1,1,3072,3072 | 1,3072,3072,16,128,64 | 10,616,832 | 147,456 |

The exact inventory keys are `sd_fastpm/gemm_a16bfw16bfpacc16bf_1_1_2816_1280` and `sd_fastpm/gemm_a16bfw16bfpacc16bf_1_1_3072_3072`, each with transaction, control, parameter, and control-metadata members. FC1 requires zero-padding K; FC2 requires zero-padding K and N, then cropping output N. This preserves mathematical padding semantics but does not prove a binary's invocation contract or numerical behavior. FC2 computes **5.76 times** its logical coefficient extent; FC1 computes 1.10 times.

| Representation | Bytes per expert | 512 experts |
| --- | ---: | ---: |
| Logical decoded BF16 | 9,830,400 | 4.6875 GiB |
| Logical unpadded BFP ebs8 | 5,529,600 | 2.63671875 GiB |
| Padded SD, no bias | 14,671,872 | 6.99609375 GiB |
| Padded SD with zero bias | 14,860,288 | 7.0859375 GiB |
| Two packed copies with zero bias | 29,720,576 | 14.171875 GiB |

One zero-bias bank leaves only 936 MiB under the existing 8-GiB process ceiling, before contexts, instructions, scratch, and other model state. A retained host bank plus BO copies already exceeds it. The 22/18-GiB reserve requirements remain in force. No full-bank export is justified. A small resident expert cache would require separate performance qualification.

## Original-q4c fidelity boundary

Promoting decoded BF16 q4c weights to FP32 is exact and would avoid the measured 8.45–8.53% affine INT4 weight approximation loss. BFP packing still introduces its own conversion loss. No dense weights or dense outputs were generated in this review, so its error against the full original-q4c FC reference is **unmeasured**. The previous affine/BFP replay results do not qualify this new route; there is no acceptance, MTP, or speed claim.

## A16W8/group32 review

The same finite inventory contains 243 A16W8-named GEMM/matmul transactions, but zero names identifying BF16/BFP16 activation with W8. The [public A16W8 MLADF implementation](https://github.com/amd/DynamicDispatch/blob/b3051f03e20aab237cda3bbe4cd2081f76b72b06/src/ops/matmul_a16w8_mladf/matmul_a16w8_mladf.cpp) uses integer `uint16`/`int16` activations and int8/uint8 weights. It packs weights with int64 QDQ coefficients, int32 QDQ parameters, and kernel parameters, rather than disclosing BF16-input, group32 affine constants. Its public specialization is `matmul_a16w8_mladf<uint16_t,uint8_t,uint16_t>`.

The installed DLL and import library export zero methods for that class. Its only matching `gemm_mladf` transaction is `gemm_mladf_a16w8acc16_4096_512_512`, which cannot enclose either FC K dimension. Other integer convolution/GEMM rows match FC K/N at M64/256/1024; those names do not establish the required group32 operation. There is **no complete public BF16 A16W8/group32 FC contract** in this pinned SDK/ABI/inventory review, and no unsupported native candidate was attempted.

The bounded numerical route therefore remains the functioning INT4 adapter with its separately recorded fidelity limits. Reopening dense or INT8 work requires an actual compatible public operator implementation, exported API, and constants/shape contract together.

## Public rebuild boundary

Missing installed exports are not an absolute ban. AMD's latest public source is still [commit b3051f03](https://github.com/amd/DynamicDispatch/tree/b3051f03e20aab237cda3bbe4cd2081f76b72b06), version `1.1.0-dev`. Its [CMake target](https://github.com/amd/DynamicDispatch/blob/b3051f03e20aab237cda3bbe4cd2081f76b72b06/src/CMakeLists.txt#L191) compiles SD GEMM, including explicit decoded-float/BFP specializations, alongside matching [SD transactions](https://github.com/amd/DynamicDispatch/tree/b3051f03e20aab237cda3bbe4cd2081f76b72b06/transaction/stx/sd) and [SDGemm.xclbin](https://github.com/amd/DynamicDispatch/blob/b3051f03e20aab237cda3bbe4cd2081f76b72b06/xclbin/stx/SDGemm.xclbin). This is a coherent older source bundle; local compilation and current-driver compatibility remain unverified.

Its smallest direct enclosing FC1 tuple is `(2,64,5120,1280)`, parameters `[128,5120,1280,32,80,80]`; FC2 is `(2,64,1280,5120)`, parameters `[128,1280,5120,32,80,80]`. Padding one useful row computes respectively 256× and 512× its logical multiply extent. No current `sd_fastpm` implementation or enclosing B1/M1 pair was found. The older formatter must stay with these older transactions.

Git blob pins: `gemm.cpp=04c3760bb516fb389f8c5eb718507b1c8006d949`; `sd_helper.hpp=3fd0f502fcf9fb728eb9b63a62f0bd4e6a123e15`; SD transaction tree `245070d2a512adbb58326aa795f461a5cb45fef2`; XCLBIN `9e7a36cf5215b19fd0dd2100a452c0e3a695aa31`. The rebuild option, padded cost, unverified compatibility, and inaccessible Halogen external-draft seam justify no speed run. No build or hardware work occurred.
