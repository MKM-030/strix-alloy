# Documented BFP operator reference — 4 October 2026

All four retained real expert0 FC calls pass the unchanged `.003 + .03*abs(ref)`
gate against an independently defined BFP16 operator reference. Relative L2
error is 0.50–0.54%. This comparison includes the BFP operand conversion absent
from the earlier BF16 affine reference, under which each FC1 case still fails
one element. Original receipts and both earlier reference comparisons remain
unchanged. No NPU or engine execution was repeated.

The reference uses the installed 1.8.0 SDK's `f2bfp` defaults: exponent groups
of eight, half-away-from-zero mantissa rounding, and shared-exponent carry if a
signed rounded mantissa exceeds 127. Negative -128 remains representable.
The formula is:

```text
W_bf = BF16_RNE((q-zp) * BF16_RNE(scale))
x_bf = widen(saved BF16 input words)
W_bfp = BFP16_ebs8_half_away_signed_carry(W_bf, axis=K)
x_bfp = BFP16_ebs8_half_away_signed_carry(x_bf, axis=K)
reference = BF16_RNE(FP32(FP64_dot(W_bfp, x_bfp)))
```

K grouping has a public matrix-operand basis independent of the observed pass.
The pinned XDNA2 AIE BFP multiply consumes its weight operand through
`mul_8x8_8x8T` / `mac_8x8_8x8T_conf`; the BF16 companion implementation explicitly
transposes logical K×N weights before converting them to `v64bfp16ebs8`.
Each transposed weight row therefore groups eight consecutive reduction values.
[Pinned BFP multiply source, lines 16–34](https://github.com/Xilinx/aie_api/blob/b0422227afd25e9b47930624c857f384b500b524/include/aie_api/detail/aie2p/mmul_bfp16_bfp16.hpp#L16-L34),
[pinned transpose and conversion source, lines 79–85](https://github.com/Xilinx/aie_api/blob/b0422227afd25e9b47930624c857f384b500b524/include/aie_api/detail/aie2p/mmul_bf16_bf16.hpp#L79-L85).

Installed DD source maps v2 BF16 activation and INT4 weights to `abfp16` and
`wbfp16`, selects the `2x4x4` overlay, and reserves BFP cast scratch with `ebs=8`.
The selected DD transaction does not disclose its intrinsic implementation.
Linking that transaction to the public AIE BFP ABI remains an inference; this
reference does not establish its exact cast or accumulation arithmetic.

| FC / case | Relative L2 error | Exact BF16 outputs | Gate violations |
| --- | ---: | ---: | ---: |
| FC1 / 0 | 0.5209% | 409/1280 | 0 |
| FC1 / 1 | 0.5411% | 408/1280 | 0 |
| FC2 / 0 | 0.5007% | 879/2560 | 0 |
| FC2 / 1 | 0.5103% | 871/2560 | 0 |

The isolated CPU replay independently inverted the pinned group32 packed
formatter and reproduced every corrected affine reference exactly before
applying BFP conversion. It read only the two existing packed buffers
(5,795,840 bytes), small saved arrays, and retained outputs. The installed carry
rule supplies the primary reference because it comes from the matching SDK;
the older public cast test's signed-clamp rule was retained as a comparison.
Both K-axis rules pass these four calls. N-axis comparisons still fail FC1.
No candidate reproduces every output bit, and no fitted gain or tolerance
change was applied.

The public cast test has a material limitation: its non-golden branch compares
`cpu_out` with itself at line 377. The separate MLADF BFP GEMM test reads an
external `bfp16_golden` fixture directory absent from the public source tree.
Those tests therefore do not independently confirm this installed transaction.
[Pinned cast test](https://github.com/amd/DynamicDispatch/blob/b3051f03e20aab237cda3bbe4cd2081f76b72b06/tests/cpp/unit_tests/test_cast.cpp#L375-L378),
[pinned BFP GEMM golden loader](https://github.com/amd/DynamicDispatch/blob/b3051f03e20aab237cda3bbe4cd2081f76b72b06/tests/cpp/unit_tests/test_mladfmatmulbias.cpp#L329-L337).

This qualifies only the four retained numerical comparisons against the stated
BFP operator reference. Native outputs still have the same 8.42–9.99% relative
L2 error against decoded original q4c weights; affine weight conversion remains
8.45–8.53%. Full routing, activation, target quality, acceptance and speed are
unqualified. An exact DD arithmetic formula and a broader route still require
separate evidence.

[Reference evidence and source hashes](halogen-dd-bfp-reference-20261004.json)
bind the [isolated replay source](../../scripts/benchmarks/halogen_dd_real_bfp_reference_replay.py)
and `server/.local/optimization9h-20261004/dd-real-bfp-reference-diagnosis.json`.
The earlier [BF16 contract diagnosis](halogen-dd-reference-contract-20261004.md)
remains available.
