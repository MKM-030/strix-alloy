# Tiny runtime-matrix precision diagnosis — 4 October 2026

The guarded first-MatMul failure has an exact offline numerical explanation:
BF16 inputs, K-axis BFP16 eb8 groups with half-away-from-zero mantissa rounding,
and BF16 output ties rounded away from zero reproduce every returned value for
both A and B. The frozen FP32-reference gate remains failed. This explains the
first projection's retained outputs. One four-term split now passes the same
unchanged gate on NPU, but takes more host-call time than CPU at this tiny size.
The complete eight-operator graph and the closed provider's implementation still
require separate evidence. No supported
Windows ML / VitisAI provider option to disable BFP16 GEMM was found in the
current primary references. This diagnostic agent launched CPU calculations only;
the root agent ran the isolated NPU graph under its owned-job guard.

The original NPU eight-operator graph failed 21/64 output elements on fixture B
at the unchanged `rtol=0.03`, `atol=0.003`; the same graph and fixtures passed CPU.
Fixture B is identified by matching all five exact expected values preserved in
the assertion to the seeded independent reference. The old report does not
retain the full failed output.

## Compiler comparison and supported controls

Both the failed runtime-matrix graph and the successful initializer-backed
fixed-top10 graph use the same verified provider DLL
`95fb8d62d424f400a2f5f4e9f4d1ac1affdb35dd8c3309e85339010f50307352`.
Their retained compiler contexts have identical passes: `init`, then
`vaiml_partition` with `vaimlConfig.device=stx`. Both compiler logs select
`GemmBfp16`, serialize `bfloat16,0,1,1`, set `config.enable_bfp16_wts=1`, and
define `AIE_API_EMULATE_BFLOAT16_MMUL_WITH_BFP16=1`. These controls alone do not
distinguish the failing case from the working case.

AMD documents the AIE API definition as choosing block-float emulation for
higher throughput with an accuracy cost. Its public XDNA2 implementation
converts both GEMM operands to `bfp16ebs8`, transposing B before conversion.
This confirms that a BF16 graph ABI does not imply a native BF16 GEMM datapath.
It does not identify the closed provider's complete layout or arithmetic.
[AIE API matrix multiplication guide](https://download.amd.com/docnav/aiengine/xilinx2025_1/aiengine_api/aie_api/doc/group__group__mmul.html),
[pinned AMD/Xilinx AIE API implementation](https://github.com/Xilinx/aie_api/blob/b0422227afd25e9b47930624c857f384b500b524/include/aie_api/detail/aie2p/mmul_bf16_bf16.hpp).

AMD's current 1.8 configuration reference exposes `config_file` and documents
two BF16 `vaiml_config` controls: `optimize_level` (1, 2, 3), and
`preferred_data_storage` (`auto`, `vectorized`, `unvectorized`). It does not
document `enable_bfp16_wts` or the AIE compile definition as user provider
options. Its `target` choice and `opt_level` apply to integer models.
Therefore setting an invented `enable_bfp16_wts=0` provider option or environment
variable would not be an evidence-backed single-change candidate.
[AMD 1.8 model compilation reference](https://ryzenai.docs.amd.com/en/latest/modelrun.html).

The AMD Windows ML Python example passes `config_file` through
`SessionOptions.add_provider_for_devices`; the page directs readers to the same
model compilation reference for supported options. ONNX Runtime's VitisAI page
also delegates detailed BF16 configuration to AMD. The old 1.4 option
`enable_f32_to_bf16_conversion` is not listed in the current 1.8 table and is not
a justified switch for this pinned Windows ML EP.
[AMD Windows ML EP guide](https://ryzenai.docs.amd.com/projects/WinML/en/latest/winml_ep.html),
[ORT VitisAI reference](https://onnxruntime.ai/docs/execution-providers/Vitis-AI-ExecutionProvider.html),
[historical AMD 1.4 reference](https://ryzenai.docs.amd.com/en/1.4/modelrun.html).

## Bounded offline result

[`halogen_npu_precision_diagnose.py`](../../scripts/benchmarks/halogen_npu_precision_diagnose.py)
verifies every original A/B input and reference hash before calculating five
fixed approximations. All inputs and operator outputs are rounded to BF16 using
round-to-nearest-even. BFP variants use eb8 blocks on GEMM reduction axes, with
BF16 inputs, the documented Quark half-even rounding, and either its ordinary
CPU saturation or its compiler-style exponent carry. The implementation follows
the pinned public Quark CPU algorithm; it does not claim to emulate the WinML
device kernel.
[Quark BFP operator specification](https://quark.docs.amd.com/latest/onnx/custom_operators/BFPQuantizeDequantize.html),
[pinned Quark v0.12 CPU implementation](https://github.com/amd/Quark/blob/1b229f781a1974cc742884e42d8eefc1eebb4f0a/quark/onnx/operators/custom_ops/src/bfp/cpu/bfp_kernel.cc).

| Approximation | A violations / 64 | B violations / 64 | B maximum absolute error |
| --- | ---: | ---: | ---: |
| BF16 only | 0 | 3 | 0.013867557 |
| Quark BFP16 weights | 0 | 7 | 0.016098678 |
| Quark BFP16 both GEMM operands | 0 | 16 | 0.029834867 |
| Quark compiler-style BFP16 weights | 0 | 6 | 0.016098678 |
| Quark compiler-style BFP16 both GEMM operands | 0 | 16 | 0.029834867 |
| Retained NPU B assertion | Not retained | 21 | 0.04092014 among violations |

All approximations fail to reproduce the five retained actual values exactly.
For output `[0,8]`, NPU returned `0.006134033203125`; BF16-only gives
`0.0225830078125`, and both-operand BFP16 gives `0.01214599609375`. A's largest
simulated error is below `0.000835`, so its pass is weak precision evidence under
the absolute tolerance `0.003`. B's larger values and cancellation expose more
error. This is an inference from the approximations, not a demonstrated provider
root cause.

The offline model does not reproduce GEMM packing, accumulation order, the
provider's SiLU approximation, or the ReduceSum tree. Those unknowns and the
missing full NPU output prevent a cause claim. Raw outputs, source/evidence
hashes, and the five exact observed values are retained in
[precision-diagnosis.json](C:/AI/halogen-mtp-npu/precision-offline-20261004/precision-diagnosis.json).

## First-operator probe prepared and CPU verified

[`halogen_npu_precision_probe.py`](../../scripts/benchmarks/halogen_npu_precision_probe.py)
builds exactly one synthetic `MatMul`:
`x[1,64] × W_gate_up[10,64,64] → gu[10,1,64]`. It imports the original frozen
seeded fixtures, uses a separate per-expert FP32 NumPy reference, alternates
A/B in one session, and preserves every full returned array plus its hash before
checking the gate. A numerical failure does not discard the result or stop
collection of the other input set. Any failed call keeps overall `passed=false`
and exit status 1. It allows four excluded warmups and at most eight measured
calls. Compile/session creation, hashing, retention and validation are excluded
from host-call timing; failed runs do not produce qualified timing statistics.

The NPU branch keeps the frozen provider verification helper, exact same provider
options, `session.disable_cpu_ep_fallback=1`, session fallback disabled, unchanged
`rtol=0.03` / `atol=0.003`, and requires every profiled Node to be VitisAI. The
external owned-job guard remains necessary for the 18 GiB physical/commit reserve
and exclusive hardware window. No NPU launch was made by this diagnostic work.

CPU replay completed all 12 calls at the stricter original CPU tolerance
`rtol=3e-5`, `atol=3e-6`. Maximum absolute error was
`4.76837158203125e-7`; all 12 profile nodes were `CPUExecutionProvider`. The
fixture/reference storage is 333,312 bytes and each call feeds 164,096 bytes.
[CPU receipt with all actual/reference arrays](C:/AI/halogen-mtp-npu/precision-offline-20261004/first-gemm-cpu.json).

| Artifact | SHA-256 |
| --- | --- |
| First-GEMM probe source | `7f5141a7bb79512e275ce6557607135a842141da1427e152cc54051decf8b019` |
| Offline diagnosis source for original receipt | `021e596c5277bad9d08e1ef704b20260ae10862f4073a41bb08bcc57e9454445` |
| 314-byte first-GEMM ONNX | `675d29f32f7e6840ede6a075f18f3abe100dc299775b934b3ebe967b485bfd14` |
| First-GEMM CPU receipt | `9a55049a1b0085304d5f34410f462095a3d9942bc7f5bab7c8f02820be85add0` |
| Offline diagnosis receipt | `16c88b93eeb410d9b70e192f3f5328dad45f27d641407abe3a9aad5f53a57194` |

## Guarded first-GEMM outcome and exact arithmetic

The root-owned run at
[first-gemm-guarded-20261004](C:/AI/halogen-mtp-npu/first-gemm-guarded-20261004/result.json)
is terminal and **failed**: build and CPU exited 0, NPU exited 1, all three owned
jobs closed, no timeout, guard error or cleanup error. Fresh monitored minima
were 47.6309166 GiB physical availability and 202.5882072 GiB commit headroom,
above the 18 GiB reserve. The embedded GPU-state snapshot contains an earlier
17.8495 GiB minimum and an idle-counter recovery receipt; it is not this probe's
live memory minimum.

One NPU session returned all four warmups and eight measured calls. Its 12 Node
events were exclusively `VitisAIExecutionProvider`; initialization including
compilation took 12,244.3618 ms. Every A call had the identical complete output,
as did every B call. A failed 16/640 elements with maximum absolute error
`0.011208534240722656`; B failed 87/640 with maximum error
`0.03724312782287598`, at the unchanged `rtol=0.03`, `atol=0.003`.
`timing_qualified=false`: this result supplies no throughput or speedup claim.

The full arrays permit a substantially stronger comparison than the original
assertion. Using BF16 round-to-nearest-even inputs, shared exponents for eight
consecutive K values, and Quark's compiler-style exponent carry, half-even BFP
mantissa rounding reproduced 76/640 A values and 82/640 B values. Quark's
documented rounding mode 0, half away from zero, instead reproduced 635/640
values for **each** set. All five remaining differences in each set were exact
BF16 halfway cases: the FP32 low bits were `0x8000` and the retained BF16 LSB was
even. Rounding the output tie away from zero instead of to even reproduces
**640/640 values for A and 640/640 for B**, with identical output hashes and zero
residual. No fitted scale, output correction, or tolerance relaxation is used.
[Quark's supported BFP rounding modes](https://quark.docs.amd.com/latest/onnx/custom_operators/BFPQuantizeDequantize.html).

The resulting formula is:

```text
x_bf = BF16_RNE(x); W_bf = BF16_RNE(W)
x_q = BFP16_eb8_half_away_with_exponent_carry(x_bf, axis=K)
W_q = BFP16_eb8_half_away_with_exponent_carry(W_bf, axis=K)
gu = BF16_nearest_ties_away(FP32_MatMul(x_q, W_q))
```

The source check is bounded. The verified provider copy's 7,573-member
`third-party.zip` contains no AIE API, VAIML or GemmBfp16 source. The compiler
loads its embedded include VFS from the verified DLL. Public
`aie2p/mmul_bf16_bf16.hpp` explicitly uses `v64bfp16ebs8` in both flag-enabled
4×8×8 and 8×8×8 paths; it transposes the 8×8 B tile before conversion. Its
conversion is a hardware intrinsic, whose bit-level implementation is not in
that header. The type guide defines exponent groups of 8 and 16; native vector
lengths 32/64/128/256 are not exponent-group sizes. Comparing documented eb16
and the three Quark rounding modes did not reproduce complete outputs. For
example eb16 half-away with the same output tie rule reproduced 135/640 A and
244/640 B values. Thus 32-wide groups would be an invented variant and were not
tested. The exact observed formula is numerical evidence, not a claim that the
public header is the exact version embedded in the provider.
[AMD AIE block-vector type definitions](https://download.amd.com/docnav/aiengine/xilinx2026_1/aiengine_api/aie_api/doc/group__group__basic__types.html),
[pinned AIE source](https://github.com/Xilinx/aie_api/blob/b0422227afd25e9b47930624c857f384b500b524/include/aie_api/detail/aie2p/mmul_bf16_bf16.hpp).

`optimize_level` and `preferred_data_storage` remain documented optimization and
layout controls; the consulted references do not document changing BFP rounding
or disabling BFP arithmetic through either. New Vitis AI Gen2 board options
target Versal devices and do not establish support in the pinned Windows ML
Strix EP. No precision/backend knob is proposed without that evidence.

The extended offline report verifies raw artifact hashes, every retained array
hash, all fixture/reference hashes, repeat consistency, and the exact formula:
[first-gemm-exact-formula.json](C:/AI/halogen-mtp-npu/precision-offline-20261004/first-gemm-exact-formula.json).
The prior note is preserved at
[original note snapshot](C:/AI/halogen-mtp-npu/precision-offline-20261004/halogen-npu-precision-before-first-gemm.md).
Original probe/model and earlier receipts remain unchanged.

| Guarded artifact | SHA-256 |
| --- | --- |
| NPU receipt | `c17155def4457be0c02371e5b44acd6558ffd204242e5c9a8100ef111f830b42` |
| CPU receipt | `6114ef927b242386f584bfa1730097b97b8550d73ab66363d8ed9ccb67d23c6c` |
| A output tensor | `1c553b0654de0af0e01604d0b2c6ee63b417750d802d166cc654460a82384c0b` |
| B output tensor | `34f2e99abc81fb39afd53cad26d48f17ba2e15a382119555349a7809133cb02a` |
| Guard result | `895c4fcd9d9904eba73c24715b65f69ad7aca31a9c25611f55e0599dd60eabf5` |
| Memory samples | `e22dc2ab31f4fa4776b4e10fd68eb0aff83dcb1335c7fce732074fba01bbcfc3` |
| Extended offline diagnosis source | `f5c27d4e66cd60e4e221e6dd51bd311f4fb6ff9331e5b1c84431979f97938ccc` |
| Exact-formula offline receipt | `6fbb2028330f8b86d393862d174b28b7d0e897654fa76f8e0f3a1aa1d31b9825` |

## One four-term mitigation, guarded NPU pass

[`halogen_npu_precision_split_probe.py`](../../scripts/benchmarks/halogen_npu_precision_split_probe.py)
prepares `high = BFP16_eb8_half_away_with_exponent_carry(BF16_RNE(original))`
and `low = original - high` for x and W. Its graph contains four MatMuls and
three Adds:

```text
gu = x_high @ W_high + x_high @ W_low + x_low @ W_high + x_low @ W_low
```

This is the original product's algebra before finite-precision evaluation;
the reference remains the original frozen FP32 per-expert x @ W. Preparation
and fresh contiguous feed copies are included in every timed host call. The
candidate retains the original strict provider verification and attribution,
all twelve full arrays before their gate, NPU tolerance `0.03` / `0.003`, and
CPU tolerance `3e-5` / `3e-6`. This changes the graph rather than introducing a
provider knob. Each call feeds 328,192 bytes; stored fixtures, preparation
checks and references account for 989,696 bytes under the 64 MiB ceiling.

Quantization idempotence was checked explicitly. Both x high parts are stable;
74/40,960 A weight highs and 24/40,960 B weight highs change when quantized
again, by at most `0.00390625` and `0.0078125` respectively. A legal negative
mantissa of -128 can reconstruct to the next power of two without the positive
carry rule; on the next pass its higher exponent changes other mantissas in that
block. `high_quantization_idempotent=false` is diagnostic metadata. FP32
subtraction also leaves one A weight and two B weights differing from exact
high+low reconstruction, by at most `2.3283064365386963e-10`. These findings are
reported explicitly rather than changing the requested one-pass formula.

CPU execution passed all twelve calls against the original reference, with
maximum absolute error `4.76837158203125e-7` and all 84 Node events on CPU.
[CPU receipt](C:/AI/halogen-mtp-npu/split-offline-20261004/cpu-final.json).
The first two local pre-session receipts are preserved: they reflect temporary
admission checks requiring idempotence and bitwise reconstruction. Those
checks are now diagnostics; the frozen numerical gate is the acceptance test.

The offline forecast explicitly requantizes the high inputs, applies the
observed first-GEMM formula to all four products, and assumes the Adds return
BF16 with the same nearest/ties-away output rule. It has zero tolerance
violations for A and B, with maximum errors `0.008962393` and `0.017512321`.
The original forecast receipt remains unchanged and records its then-unverified
NPU status. The later guarded run below verifies its complete output hashes;
that agreement supports the formula for these fixtures, without separately
exposing the fused graph's internal Add outputs.
[Offline forecast](C:/AI/halogen-mtp-npu/split-offline-20261004/forecast.json).

| Split candidate artifact | SHA-256 |
| --- | --- |
| Frozen split-probe source | `012f496c94e52f06ed2b530a58fbc35781ef7795f44715b16f13d75285a68412` |
| 634-byte ONNX, 4 MatMul + 3 Add | `d31b1225a27934c0c6762b66dd697d8a61fc63f44dd021933fc0d75d58a762df` |
| Final CPU receipt | `972e333327ef327500c7eebf41e7bc94eba40fd3978c36a1ccf872156399ca7b` |
| Offline forecast | `012fac13b43f7efded74ae3a0305721e5b1c7f939ab3a266d0637da3f53e2e79` |

Only the root-owned 18 GiB guard may launch the split candidate in an exclusive
hardware window. No NPU execution was launched by this diagnostic work.

The root-owned
[split-gemm-guarded-20261004](C:/AI/halogen-mtp-npu/split-gemm-guarded-20261004/result.json)
is terminal **passed**: build, CPU and NPU exited 0, all three owned jobs closed,
and no timeout, guard error or cleanup error was recorded. Fresh monitored
minima across 33 samples were 47.5411339 GiB available physical memory and 202.5874481 GiB commit
headroom. All twelve NPU Node events were `VitisAIExecutionProvider`; the CPU
provider in the session's advertised provider list had no Node event. This is
strict ORT provider attribution, not visibility into closed-provider placement.

All four warmups and eight measured calls passed. Each A call has zero violations
out of 640 values and maximum absolute error `0.008962392807006836`; each B call
has zero violations and maximum error `0.01751232147216797`. Outputs are identical
across repeats for each set. Independent read-only arithmetic review recomputed
the original fixture, split-feed, reference and returned-array hashes and every
numerical gate. Applying the observed GEMM formula to four products and BF16
nearest/ties-away after each Add reproduces **640/640 values for each fixture**,
including their complete NPU output hashes.

| Same-window split execution | Mean host call | Median | p95 | Initialization |
| --- | ---: | ---: | ---: | ---: |
| CPU | 0.7020375 ms | 0.70075 ms | 0.7197 ms | 4.2605 ms |
| NPU | 1.17655 ms | 1.1619 ms | 1.2605 ms | 13,297.5061 ms |

These eight-call timings include high/residual preparation, fresh contiguous
copies, input transfer, execution and output return; initialization, retention,
hashing and validation are excluded. The NPU call is about 1.68 times the CPU
call at this tiny geometry. The passed receipt qualifies this first projection's
precision only and supplies no Halogen or MTP speedup.
[CPU receipt](C:/AI/halogen-mtp-npu/split-gemm-guarded-20261004/cpu.json),
[NPU receipt](C:/AI/halogen-mtp-npu/split-gemm-guarded-20261004/npu.json).

| Guarded split artifact | SHA-256 |
| --- | --- |
| NPU receipt | `2d77b95b66f265e41b42a15431a4de494e995ac142bcb3359a424bd82473ee37` |
| CPU receipt | `2ad61505d21aadfd90b145ced264f9c49efa3d8bc96a1c056067d2654a1312b7` |
| NPU profile | `dea45b0d779c7bb3e1ed5b6fd1b6d5a76a7e2447a93f6b98797c17a06764d8fa` |
| CPU profile | `8315dbfb9d3a16b38fe37c8430d6760eb29b6a01236665cba98fcf90fbec4195` |
| A NPU output tensor | `7f423fb9eed5eb93f3b200f656adeb15258266341f5136fdbebc7762e8d7a04d` |
| B NPU output tensor | `f415bc8e8991d33de5f4c58c79327b9c407a88434ff84aa31e05da013b521ee1` |
| Guard result | `d1cf551cb9a4137c5d41d4dcabeb69dbbf8d15a901437c7cd9aa0ac51740bb52` |
| Memory samples | `c07e3314fcf085a40cddff62f510e0645e630533c4f0c2ee7fd5cc2368574c1d` |
| Owned-stage receipts | `d8b0f84c579d499b8e3d1f571bd5e7fb178386fd4e94c59e3f215e424b13067d` |
| Cleanup receipt | `2412b2c72f59b3ff0dedc7ec08e190004fbb7b4cb4536101f431fab31fb6705f` |

This work does not qualify full-width dynamic expert matrices, full NPU MTP,
acceptance, live target-state handoff, or a Halogen speedup. The measured builder,
original parameter probe/guard, provider files, and checkpoint files were not
edited.
