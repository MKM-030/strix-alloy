# Native hidden projection: contiguous vector-load plan

5 October 2026. **Plausible enough to implement as a distinct offline sibling.**
Rearrange decoded BF16 words into the recovered lane/pair order, transpose the
canonical input once per call, and replace the hot scalar gathers with aligned
vector loads. Preserve every arithmetic boundary. This document is source and
retained-result review initially; the source sibling was subsequently authorized
and written. No tests, compiler, hardware, WSL, lifecycle, continuation, or
original-weight access was performed by its author. Root owns validation.

## Evidence and scope

The finite decoded A/B screen used zero warmups and two distinct inputs. Complete
copy/poison/sync/launch/wait/readback samples were **4.7757 / 2.2519 ms**, mean
**3.5138 ms**. The earlier packed screen reported **25.4992 / 22.8709 ms**, mean
**24.18505 ms**. Each checked all 20,480 outputs against the frozen original GPU
oracle at unchanged rtol 0.03 / atol 0.003, with zero gate failures and one BF16
word mismatch (reported maximum absolute error 0.000488). The decoded result
reports zero per-projection weight decoder calls. These are initial screens,
without warmup or a steady-state cohort; their separate-session observations
justify inspecting the next mechanism, without establishing a speed ratio.

Results: [decoded](../../server/.local/optimization9h-20261004/native-hidden-decoded-stopped-component-0af50913d99b409abc6883adfb15e51a/native-result.json),
[packed](../../server/.local/optimization9h-20261004/native-hidden-stopped-component-99fc925b97154c89beb6cb4bad833a08/native-result.json).
The retained original GPU H device-only 158.707 us bracket omits readiness,
transport, and publication; it is not a matched replacement comparison. No
engine integration, token throughput, or device-speed gain is inferred here.

## Arithmetic that must remain identical

Current [kernel](../../scripts/benchmarks/halogen_npu_native_hidden_decoded/kernels.cc)
uses `k = lane*16 + pair*2`, sixteen independent lanes, eight pairs per K256
chunk, and ten separately rounded FP32 chunk additions. Each pair performs the
same ordered two `aie::mac` calls; each chunk starts from zero. Finish retains
the explicit XOR 8/4/2/1 FP32 additions and final BF16 RNE bit conversion.

The [recovered reference](../../scripts/benchmarks/halogen_npu_native_hidden_decoded/numeric_reference.py)
and [shader review](halogen-native-d-fc-dispatch-20261004.md) establish the M4
block/lane schedule and affine FP32-to-BF16 weight boundary. The GPU dot2
instruction's internal rounding remains unresolved: all three investigated
models match these frozen BF16 fixtures. Preserve the existing AIE sequential
MAC contract; do not substitute matrix multiplication, pair-summed products,
a different reduction, wider accumulation, or a claimed fused GPU dot2 match.

## Exact layout and kernel change

Keep outer weight order `[column8,group5,Kchunk10,worker4]`. Inside each existing
8192-byte chunk replace `[row16,K256]` with
`[row16,pair8,component2,lane16]`, using this word-only permutation:

```text
Wp[row,pair,component,lane] = W[row,lane*16 + pair*2 + component]
Xp[stream,kchunk,pair,component,lane]
  = Xcanonical[stream,kchunk*256 + lane*16 + pair*2 + component]
```

Pack weights offline from the already prepared, SHA-pinned decoded payload.
Retain the original raw SHA and decoded row-major SHA, publish a new packed SHA,
and prove complete inverse reconstruction equals all 6,553,600 decoded words
bit for bit. No original Q8 file read or second affine decode is required.

The host accepts the unchanged canonical `[4,2560]` BF16 wire/cohort input,
checks it, and permutes its 10,240 words once per `compute` into the existing
input BO. It must keep request binding hashes over canonical bytes. Measure the
transpose inside the complete component timer, before BO copy/sync; include it
in any eventual readiness-to-consumer bracket. This removes input gathers from
the core while retaining one whole input object reused across all five output
groups. Input vectors are reloaded for each output row; the first version should
not cache all input pairs in registers.

Use row -> pair -> four explicitly named stream accumulators. One contiguous
32-BF16 weight load supplies `extract<16>(0)` and `extract<16>(1)` once, reused
for four streams. For each stream load its contiguous 32-BF16 input pair,
extract the two halves, then execute the existing first MAC and second MAC in
that order. Initialize four independent `accum<accfloat,16>` blocks per row;
after pair 7 apply each existing `to_vector<float>()` and separate partial add.
Interleaving independent streams changes no per-lane dependency chain. Keep
`hidden_reset` and `hidden_finish` unchanged in this step.

## Source operation count, not a cycle estimate

One H call executes `32 workers * 5 groups * 10 chunks = 1600 hidden_chunk`
invocations. Expanding the current row/stream/pair/lane loops gives:

| Hot chunk operation per complete H | Current source | Proposed source |
| --- | ---: | ---: |
| Indexed scalar BF16 loads | 52,428,800 | 0 |
| Scalar vector `.set` calls | 52,428,800 | 0 |
| Lane-loop iterations / `k` constructions | 13,107,200 | 0 |
| Contiguous `load_v<32>` calls | 0 | 1,024,000 |
| Contiguous-half `extract<16>` calls | 0 | 2,048,000 |
| Ordered `mac` calls on sixteen lanes | 1,638,400 | 1,638,400 |

The new loads comprise 204,800 weight vectors and 819,200 input vectors. Weight
word reads fall from 26,214,400 to 6,553,600 through four-stream reuse; input word
reads remain 26,214,400. Host preprocessing adds 10,240 word reads and 10,240 word
writes per call. These are source-level dynamic counts: compiler combining,
instruction expansion, scheduling, bank conflicts, and spills can change the
machine operation count. The finish kernel's scalar XOR-lane assembly remains.

## Feasibility and ABI/memory impact

The installed AIE headers support contiguous `load_v<32>` and sixteen-element
subvector extraction with partition indices 0/1. Thirty-two BF16 words occupy
64 bytes; every pair starts at a 64-byte multiple. The reviewed decoded map's
96 compute input/weight buffers are already 64-byte aligned, at addresses
4096/24576/32768. Re-prove alignment in the new emitted map rather than inheriting
it. AMD's [AIE API memory documentation](https://xilinx.github.io/aie_api/group__group__memory.html)
requires alignment for `load_v`; its XDNA2 512-bit access requirement is 64 bytes.
The installed `aie.hpp`, `vector.hpp`, and `detail/ld_st.hpp` were inspected as
the toolchain-specific source evidence.

Keep weight BO 13,107,200 B, input/output BOs 20,480 B, chunk 8192 B, aggregate
32768 B, existing FIFO depths/DMA traversal, 4096 B partials, and declared
4096 B stack. Nominal worker storage remains 45,312 B; per-call DDR traffic
remains 13,291,520 B. Transpose directly into the mapped input BO to avoid new
device scratch or another host staging allocation. Four live accumulators raise
register pressure; actual spills/stack and bank placement remain build gates.

Create a separate `halogen_npu_native_hidden_vector` package. Give its
design, artifacts and weight sidecars distinct format/layout tags, including
both weight and internal input layouts, so same-size old payloads fail closed.
BO argument positions and the canonical external H protocol stay unchanged.
Update host sidecar checks and emission verification for those tags and the
alignment contract; retain original decode/reference SHA provenance.

## Next implementation gates

1. Prove the full weight and input permutations are bijective; use independent
   coordinate/sentinel tests at row, worker, group, Kchunk, lane and pair edges,
   including BF16 signed zero. Check full decoded inverse hashes. Do not derive
   the pack from input or oracle values.
2. Prove every stream/lane sees the same ordered operands and rounding
   boundaries. Compare layout-aware scalar evaluation against the existing
   sequential reference on cancellation and BF16 tie cases.
3. Offline build a fresh sibling; inspect LLVM/linked assembly for contiguous
   loads, retained ordered MAC/add boundaries, no hot lane gathers, four-stream
   weight reuse, spills, actual alignment/allocation, and all 32 linked stack
   paths. Existing decoded linked evidence does not qualify the new binary.
4. Only after those gates, root may authorize a finite real-input accuracy and
   complete-cost screen, including the new host transpose. A later matched
   original readiness-to-consumer comparison and full-head qualification are
   separate requirements before any engine or throughput claim.

Source package now prepared:
[halogen_npu_native_hidden_vector](../../scripts/benchmarks/halogen_npu_native_hidden_vector/README.md).
It includes exactly three focused synthetic layout tests, unrun by the author;
root will run them after review and owns compiler/linked/device verification.

The smaller-change alternative only repacks weights and leaves input gathers;
it misses half the current gather assembly. A tile transpose/cache adds local
scratch and another dataflow boundary. The proposed host permutation and direct
vector loads offer the clearest bounded next mechanism, with unchanged DDR and
FIFO extents. **Proceed to source implementation, subject to the offline gates;
device benefit remains unmeasured.**
