# Compact-Q8 H with fused packing and reduction

This standalone, default-off GPU candidate uses original compact-Q8 weights and
the original single-row grid160/block256/wave32 geometry for K=N2560/M4. It is
not connected to a serving engine. The caller enforces the exact launch,
nonaliasing aligned allocations, stream0, and retained frozen buffer sizes.

Native FP32 FMA_MIX and scalar integer BF16 RNE remain unchanged. A byte
permutation extracts the upper halfwords of two already-rounded FP32 bit
patterns. The selector `0x03020706` selects bytes[6,7,2,3] from
`(uint64(first)<<32)|second`. Eight packed-pair instructions replace the
shift/mask/merge pairs in the source sibling without altering rounding.

The ten chunk-local native BF16 DOT2 chains and separate FP32 chunk additions
remain. Sixteen ADD-DPP instructions implement the XOR8/4/2/1 butterfly directly,
with full EXEC until the p0-only store. DPP permutes src0, so physical ADD operand
order reverses. Finite FP32 RNE addition is commutative; no universal NaN payload
or exceptional-value equivalence is claimed. Exact frozen native output hashes
remain the required hardware qualification.

The final offline build contains16 FMA_MIX,32 DOT2,8 weight-pair permutations,
16 ADD-DPP,9 vector128 loads and1 affine32 load in the static loop/reduction.
It reports68 VGPR, zero spills/private storage/LDS,40-byte arguments and original
float mode0xf0. Compiler instruction counts do not establish latency.

The harness is derived from the retained primed two-row comparison, using the
same original raw weights, A/B inputs, native output hashes and runtime pins.
Both arms now use grid160. Four excluded warmup pairs and sixteen measured pairs
balance input and arm order. Each arm receives an untimed same-arm primer;
readbacks, poisoning, hashes and file I/O remain outside event timing.

GPU placement avoids a new host crossing at this resident MTP Decode boundary.
CPU/NPU placement has no qualified advantage here; prior complete NPU H was
slower. Ordinary target Prefill is outside this fixed shape. Exact outputs intend
preserved proposals and acceptance. Actual Prefill/Decode tok/s and acceptance
require separate comparable serving measurements and cannot be inferred from
component microseconds. Root alone owns the finite hardware window, memory
reserves and normal restoration of the ready/open stock server.

The completed finite screen matched all40 timed frozen outputs exactly. Original
mean169.846microseconds versus candidate173.988 gives2.439% higher candidate
latency in this run; the candidate wins7/16 measured pairs. Order groups reverse
sign and later pairs are faster for both arms, so no intrinsic slowdown is
asserted. There is no demonstrated component benefit. Keep disabled; no unchanged
rerun or serving cohort is justified. See the
[screen evidence](../../../docs/research/halogen-gpu-q8-fused-status-20261006.json).
