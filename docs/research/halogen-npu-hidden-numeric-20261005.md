# Original hidden projection: repaired offline reference

5 October 2026. CPU-only validation of the two frozen original-GPU A/B fixtures.
The reconstructed reference matches all 20,480 oracle BF16 words exactly. It
passes the unchanged CPU screen (rtol 0.002 / atol 0.0002) and NPU development
screen (rtol 0.03 / atol 0.003). This is not a hardware NPU result, full-head
qualification, or token-throughput improvement.

The recovered M4 schedule has sixteen independent lanes. Each lane processes a
sixteen-value block with eight dot2 operations, resets for every block, adds ten
completed FP32 blocks, and participates in the XOR 8/4/2/1 reduction. The old
reference used a different summation order. Its hidden-B values at indices 1729
and 7029 missed the strict CPU screen by one BF16 step. The repaired schedule
matches the stored GPU outputs at both positions and every other position.

Three explicit dot2 models (fused, sequential, pair-then-accumulate) all match the
BF16 oracle on these fixtures, although their intermediate FP32 outputs differ.
This does not identify the GPU instruction's internal rounding or prove the
native AIE kernel's arithmetic. Hardware output still needs the frozen NPU
screen and subsequent complete-head/output checks.

The unsigned-u8 times FP16 scale product has at most nineteen significand bits,
so it is exactly representable in FP32. Separate multiplication and addition
therefore give the same affine value as one FP32 FMA for these finite inputs.
An affine-FMA discrepancy was not the established cause of the earlier misses.
The native decoder preserves the exact affine sum, FP32 RNE and BF16 RNE.

The accelerated CPU implementation checks FP64 intermediate additions with
TwoSum and falls back to exact integer dyadics when necessary. A proposed common
int64 accumulator was rejected because its bounds overflowed on the fixtures.
Twelve focused rounding, schedule, cancellation and equivalence tests pass.

Evidence: [raw comparison report](halogen-npu-hidden-numeric-20261005.json),
[reference](../../scripts/benchmarks/halogen_npu_hidden_numeric.py),
[focused tests](../../scripts/benchmarks/tests/test_halogen_npu_hidden_numeric.py).

Reference SHA256: `73cf7859aa8fceafb7ad34b85f95be70e65b0cd1da8d4dd90239f3a2d71562ba`.
The earlier native-H design's unresolved CPU-failure statement is superseded
only for these frozen fixtures. Its hardware, transport and speed gates remain.
