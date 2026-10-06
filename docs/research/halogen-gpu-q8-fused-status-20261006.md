# Compact-Q8 fused GPU candidate, 6 October 2026

The new default-off single-row GPU H candidate is exact on the frozen inputs,
but **has no demonstrated component advantage**. The completed finite screen
measured169.846microseconds original versus173.988candidate mean,2.439% higher
candidate latency in this run. The candidate wins7/16 measured pairs. All40
timed outputs matched the original frozen hashes. Keep disabled; no unchanged
rerun or serving cohort is justified. No new token rate or acceptance is available.

| Primed resident H | Original | Fused candidate |
|---|---:|---:|
| Mean latency |169.846µs|173.988µs|
| Median latency |171.119µs|163.865µs|

The paired median candidate-minus-original is+6.590µs. Order-group mean differences
reverse sign:−1.536µs when original goes first,+9.820µs when candidate goes first.
Both arms are faster in the later eight pairs. All outliers are retained. The
lower marginal candidate median establishes no paired advantage. This screen
does not prove an intrinsic2.439% kernel slowdown or a cold/serving-rate effect.

The first pre-stop admission observed System PID4 Copy utilization1%; attribution
to a foreign program was not established. It made no hardware launch or server
stop. After that observed load cleared, the normal guarded lifecycle admitted
one finite hardware screen. Its owned measurement container/job are closed.
The normal stock server was restored and independently verified ready/open on
port8840. The same controller was observed through loading; no second start was
performed after observation timeouts. All own measurement/restoration helpers
are terminal. Physical/commit headroom at final verification was31.077/122.989GiB.

## Distinct mechanism

The [source](../../scripts/benchmarks/halogen_gpu_hidden_q8_fused/hidden_q8_fused.hip)
retains original compact unsigned-Q8 weights, native fused FP32 affine arithmetic,
scalar BF16 nearest-even rounding, eight-pair DOT2 chunk chains and ten separate
chunk ADDs. Grid160/block256/wave32 preserves original single-row geometry. It
differs from the defeated two-row candidate and exchange-only DPP patch:

- Eight byte-permute instructions pack already-rounded FP32 upper halfwords in
  each static chunk body. There is no intermediate FP16 affine rounding.
- Sixteen ADD-DPP instructions implement XOR8/4/2/1 directly, eliminating the
  separate cross-lane exchanges and their address work from this source.
- Inputs and weights stay resident; no recurrent producer, transport or host
  publication is introduced.

DPP permutes src0, so physical ADD operand order reverses. Finite FP32 addition
under matching RNE/denormal mode is commutative, including zeros. No universal
NaN payload equivalence is claimed; finite inputs alone do not prove finite
intermediates. The frozen original-GPU output hashes matched after each timed
launch. This qualification is bounded to these two original inputs and shape.

The final offline build has6352bytes,68VGPR, no spills/private storage/LDS,
40-byte arguments, wave32 and original float mode0xf0. Root checked emitted
counts:16FMA_MIX,32DOT2,8weight-pair PERM,16ADD-DPP,9vector128 loads and1affine32
load. The invariant permutation selector is0x03020706. Source/emission review
was performed by `/root/q8_engine_roi`; harness/lifecycle review by
`/root/q8_affine_math`. These counts and reviews establish no latency advantage.

## Excluded conversion alternatives

Packed FP16 affine arithmetic is not equivalent. Code3, FP16 scale0x3c03 and
bias0x9000 produce FP32 affine3.00830078125 and BF16word0x4041. FP16 affine first
rounds to3.0078125, then BF16word0x4040. The difference arises from double rounding
with finite normal values. The original precision boundary stays unchanged.

The inspected [LLVM gfx1151 definition](https://raw.githubusercontent.com/llvm/llvm-project/llvmorg-21.1.8/llvm/lib/Target/AMDGPU/GCNProcessors.td)
selects FeatureISAVersion11_5_1, whose
[feature list](https://raw.githubusercontent.com/llvm/llvm-project/llvmorg-21.1.8/llvm/lib/Target/AMDGPU/AMDGPU.td)
does not supply BF16ConversionInsts. The
[packed BF16 conversion](https://raw.githubusercontent.com/llvm/llvm-project/llvmorg-21.1.8/llvm/lib/Target/AMDGPU/VOP3Instructions.td)
requires that feature. The official
[RDNA3.5 ISA XML](https://gpuopen.com/download/machine-readable-isa/latest/)
also has no matching BF16 CVT/PACK instruction. Integer packing above preserves
both original rounding operations; it does not posit unsupported hardware.

## GPU, CPU, NPU and serving metrics

| Placement/outcome | Assessment |
|---|---|
| GPU | Direct resident implementation; frozen correctness passed, no component advantage |
| CPU | No qualified faster replacement across this device-resident boundary |
| NPU | Prior complete H routes slower; no producer is attached to a defeated consumer |
| Prefill tok/s | Ordinary target Prefill outside this fixed MTP H shape; no measured gain |
| Decode tok/s | Could benefit only eligible H calls; no measured serving delta |
| Native acceptance | Exact output intends unchanged proposals; no improved acceptance established |

The latest primed original H bracket130.425microseconds comes from the earlier
[two-row screen](halogen-gpu-hidden-q8-rows2-screen-20261006.md). The historical
full-head3.323555ms and73count1 calls are a different window; retained counters
do not bind all73 to this compact-H dispatch. Neither a component time nor an
instruction saving becomes a predicted serving tok/s number.

Root completed the same frozen A/B comparison with four excluded warmup pairs,
sixteen balanced measured pairs, untimed same-arm primers and forty exact-output
hash checks. Both arms use grid160. The existing22GiB component admission,
continuous18GiB reserve and normal44/131GiB restoration rules remain. The
component minimum physical/commit reserves were43.710/198.769GiB. Do not repeat
any defeated unchanged cohort. Actual serving rates remain the goal.

Raw source/build/admission paths and hashes are in the
[companion evidence](halogen-gpu-q8-fused-status-20261006.json).
