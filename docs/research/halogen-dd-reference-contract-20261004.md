# Public-DD real FC reference contract — 4 October 2026

The documented CPU reference is corrected, but the retained real expert0 NPU
outputs still fail the frozen arithmetic gate: each FC1 case has one violating
element out of 1280; both FC2 cases pass. The correction is a valid reference
fix and does not explain the remaining native residual. No additional NPU run
or numerical adapter change follows from this result.

The initial independent reference rounded scales to BF16 but left
`(q-zp)*scale` in FP32. AMD's public validation helper and the installed 1.8.0
SDK validation accessor both round that product to BF16 as well. The new
`affine_bf16_scale_and_dequant_rne_v2` contract is:

```text
x = widen(saved BF16 input words)
W = BF16_RNE((q-zp) * BF16_RNE(scale))
reference = FP32(FP64_dot(W, x))
```

The public helper is pinned to commit
`b3051f03e20aab237cda3bbe4cd2081f76b72b06`, Git blob
`a10a7a26350fe3be30cd430b7c685f167d580647`, SHA-256
`fb715bdcd3db4343b181f83fe11b8cdc05b812ebbc3fbc6d9cc63f707ab0a5a5`.
Its `ForwardCPU` rounds the scale and then the dequantized weight.
[Pinned AMD helper, lines 75–92](https://github.com/amd/DynamicDispatch/blob/b3051f03e20aab237cda3bbe4cd2081f76b72b06/tests/cpp/include/mladfmatmulbias_helpers.hpp#L75-L92).
The extracted installed `ops/ops_common/mladf_matmul_matrix.hpp` accessors at
lines 242–255 and 403–416 corroborate product rounding; its SHA-256 is
`bf152c12d33ad04fde80c342519dacfe03607ab4a32f37744c62776db6347f00`.
These validation references establish this contract, not complete emulation of
the installed v2 transaction.

Fresh root-owned CPU preparation preserved **both packed buffer hashes and
all four input hashes** from the original NPU run. The existing raw BF16
outputs were replayed against the corrected references at the unchanged
per-element gate `abs(actual-ref) <= .003 + .03*abs(ref)`.

| FC / case | Corrected reference relative L2 error | Violations | Pass |
| --- | ---: | ---: | --- |
| FC1 / 0 | 0.8380% | 1/1280 | No |
| FC1 / 1 | 0.8588% | 1/1280 | No |
| FC2 / 0 | 0.8420% | 0/2560 | Yes |
| FC2 / 1 | 0.8411% | 0/2560 | Yes |

The original failed preparation/admission artifacts remain unchanged.
The new preparation includes the explicit contract and its evidence pins;
the real probe prevalidates both fixtures and every saved case's count, order,
and contract version before native setup. CPU checks covered positive and
negative odd/even BF16 product halfway cases, preserved the separate FP32
approximation diagnostic, and rejected old or malformed contracts.

Retained-array regression does not support a uniform `127/128` attenuation:
actual-versus-original-affine-reference slopes are approximately 1.0041–1.0044.
Multiplying those references by `127/128` worsens relative L2 error from
0.82–0.84% to 1.40–1.42%. No fitted scale or compensation is applied. The
installed v2 route selects BFP activation/weight casts with exponent groups of
eight; host inputs are copied directly. The cast, dequantization and
accumulation arithmetic reside in the opaque transaction. Static host sources
do not establish an exact arithmetic fix.

The separate FP32 affine conversion error against original weights remains
unchanged at 8.45–8.53% relative L2. Actual NPU outputs still differ by
8.42–9.99% from the decoded original FP32 references. Correcting the affine reference does not
qualify approximate draft acceptance, full MTP routing, activation semantics,
or speed. Exporting all 512 experts and repeating the identical hardware run
remain unsupported while FC1 fails.

[Evidence and hashes](halogen-dd-reference-contract-20261004.json) retain the
original regressions and corrected replay. The root replay is
`server/.local/optimization9h-20261004/dd-real-reference-replay.json`; new CPU
preparation is under `dd-real-expert-prepare-a88d6de92c2f4308870143a93be367e3`.
The original operator execution is documented in
[real FC admission](halogen-dd-real-fc-admission-20261004.md).
