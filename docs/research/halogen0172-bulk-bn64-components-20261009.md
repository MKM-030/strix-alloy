# Native bulk-MoE BN64 component comparison, 2026-10-09

The native BN64 path passed the finite exact-output checks and was faster in all six measured longer-window pairs. This supports an isolated engine experiment. No Prefill/Decode tok/s or acceptance improvement has been measured for this change.

The complete 17,765,424-byte native GPU code object is byte-identical in Halogen0.17.2 and the newly published0.17.3 image. The host/API binaries differ. These component runs use the0.17.2 container's stock runtime; the byte match does not qualify a0.17.3 server upgrade.

## Workload and boundary

Both arms have N8192 token rows, R81920 routed rows and512 experts. The weights, FP16 scales/metadata and BF16 inputs are initialized deterministic synthetic data; they are not captured model weights or tokenized prose. Routing supplies ten distinct experts per token, with stable forward/inverse permutations. One histogram has512 experts with160 rows each. The other includes counts around every16/64/128-row tail boundary while retaining all81920 rows.

Each timed operation includes native item generation, GU, dense-BF16 DN split2 and native bulk fold. Identical pretransformed input and CPU sorting are outside both arms. All changed item work and the original capacity-based projection grid launches are included. Initialization, output clears, transfer, item/guard checks and word comparisons are outside both GPU-event windows.

V1 encloses one complete operation per arm. Its timing reversals motivated one distinct v2 measurement method: four consecutive complete operations per event, elapsed divided by four. Each pattern has one excluded paired warmup and three alternating measured pairs. V2 repeats the same component working set within an arm; it is a component estimate, not fresh full-model Prefill. Both completed series remain retained and will not be repeated unchanged.

## Actual measured means

| Window | Synthetic pattern | BN128 ms/operation | BN64 ms/operation | Time reduction |
|---|---|---:|---:|---:|
| v1 (1 operations) | uniform512x160 | 129.003 | 106.058 | 17.79% |
| v1 (1 operations) | boundary_tails | 107.030 | 104.820 | 2.07% |
| v2_batched (4 operations) | uniform512x160 | 86.135 | 70.570 | 18.07% |
| v2_batched (4 operations) | boundary_tails | 78.095 | 66.243 | 15.18% |

V1 does not establish a stable gain: measured pairs change sign, and its uniform BN128 time falls from145.08 to105.38ms. V2 favors BN64 in all six measured pairs, with finite full/tail coverage. Its results justify a controlled server comparison, not a universal shape policy or a tok/s estimate.

## Correctness and resources

Every paired comparison covers52,428,800 GU,209,715,200 DN and20,971,520 final BF16 words. All mismatches and nonfinite counts are zero in both series. Distinct output poisons detect missing writes. The original native fold preserves the fixed ten route-slot order. Every device buffer has initialized4KiB prefix/suffix guards, all unchanged. V1 checks complete outputs after each operation; v2 checks after each four-operation arm with immutable input and no feedback.

The fixture allocates2,515,610,388 guarded device bytes (2.343GiB), with bounded CPU staging under9.4MB plus runtime overhead. Minimum observed physical reserve exceeds21GiB in both runs; commit exceeds108GiB. No server stop/restart, API inference or NPU work occurred. The normal0.17.2 server remained ready in its visible console; both owned measurement helpers are closed.

## Next integration

A default-off engine candidate must retain native64 item/GU/DN selection together, provision the larger item arrays and use the original dense GU/DN/fold ownership. The original BN128 item arena is too small for native64 and must not be reused at its old capacity. It needs a frozen full-engine before/candidate/after comparison with identical greedy output and explicit Prefill, Decode and combined native MTP+PLD acceptance. No speed promotion follows from component milliseconds alone.

Authored sources, ABI bounds and exact finite rows are linked by hashes in the companion JSON. Vendor binary/code objects and disassemblies are not redistributed. NPU benefit remains unmeasured for this candidate.
