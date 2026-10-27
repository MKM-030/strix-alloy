# Completed HC mean: source-only HIP preparation

This packet implements a real gfx1151 HIP kernel. No device compilation or
execution has been performed by its author. It is separate from all frozen
native and reference packets and installs no relay, capture or producer.

The input is the current saved binding's raw BF16 `[full_rows,4,2560]`, completed
zero-based layers5,15,25,35,45 in that order. `Job` pairs tap0..4 with the actual
completed layer and rejects mismatches. Decode accepts full_rows1..4; prefill
accepts1..8192. Source row/stream strides are BF16 **elements**, not bytes.
Native contiguous values are10240/2560 (20480/5120 bytes); padded aligned strides
are accepted within explicit bounds. Columns must be contiguous, addresses and
strides aligned for eight BF16 words per vector. Descriptor capacities describe
accessible memory supplied by the caller; validation does not query pointers.

`source_first` selects a tail offset within the **full** raw chunk; `rows` is
the selected count. `destination_first` is an independent row offset in the
owned destination. Both intervals must fit their explicitly supplied row counts.
For an absolute chunk beginning at P, selected absolute rows are
`[P+source_first,P+source_first+rows)`; destination row0 has a caller-defined base.
Selection does not replace complete prefill processing or prove canonical-prefix
ownership. Chunk/token IDs, generations and absolute positions remain caller data.

`output_row_stride=2560` writes a separate owned contiguous mean `[rows,2560]`.
`output_row_stride=12800` writes the same mean directly to columns
`[tap*2560,(tap+1)*2560)` of an owned concatenated allocation. Each mean is then
a strided `[rows,2560]` view; all five complete views form `[rows,12800]` without
a second copy/kernel. Unselected rows and other taps are untouched. Capacity and
nonoverlap checks cover the entire declared buffers. The caller must prevent
concurrent jobs from writing overlapping views.

Each lane loads four aligned128-bit vectors (eight BF16 values per HC stream),
widens exactly to FP32, adds in a fixed order, multiplies0.25, and stores one
128-bit BF16 vector. Adjacent lanes cover adjacent columns. Actual instruction
selection/coalescing and register use require Root's compiled-code inspection.

## Arithmetic qualification

The model capture patch says
`hidden_states.unflatten(-1,(4,2560)).mean(dim=-2)`; it adds no norm or stream
weights. Local primary PyTorch2.13.0+rocm10.0.0 headers at git6596a0dea537c1c78520c73cc6678214781a9d06
show `MeanOps` accumulating in acc_t and postmultiplying the factor. For BF16
the reduction uses FP32 operation math. In `Reduce.cuh`, this non-fastest-dimension
reduction has four inputs per output, below the warp-split threshold. Four
zero-initialized accumulators combine in order before project. This motivates
the kernel's explicit FP32 order; it is not a pinned build of the production
source runtime. A changed reduction implementation/compiler/shape may differ.

Sequential FP32 arithmetic is not an exact real mean across all BF16 ranges.
For `[2^24,1,-2^24,1]`, it yields0.25 while the real mean is0.5; reordering the
same values can yield0.5. Four maximal finite BF16 inputs overflow the FP32 sum
before division. Fixtures cover cancellation, overflow, huge exponent spread,
RN-even ties, BF16 subnormals, signed zero, infinities and NaNs, plus4096 random
four-word patterns. NaNs canonicalize to0x7fc0; payload/sign equivalence is not
claimed. Finite, zero and infinity results require exact bits. Preserve FP32
subnormals: no fast math/reassociation/contraction/flush-to-zero build.

`reference.py` uses independent stdlib word decoding and explicit FP32 rounding;
`test_reference.py --run-cpu` compares against the actual CPU Torch expression.
This does not qualify actual GPU mean bits. Root's separate source GPU comparison
is required before claiming source numerical parity on a particular runtime.

## Stream and ownership contract

`enqueue(job,actual_stream)` only validates and launches, returning immediate
submission status. It never allocates, synchronizes, copies, looks up a stream,
changes settings or validates native ownership. Null stream is accepted only
when the actual producer uses that default stream; never infer this from a
pointer. The supplied stream must be the raw producer's actual stream or have
an explicit event dependency on it. A post-layer callback is not completion.

At each qualified completed tap, the caller must either stage the full raw
input to independent storage under a valid lifetime, or enqueue this read on
the actual producer stream before any subsequent overwrite/reuse. Uncontrolled
cross-stream mutation invalidates that ordering. An async borrowed address is
not a lease. Keep the source alive through the read and the destination alive
through all consumers. On another stream, fence against the completed mean;
on CPU readback, wait for a completed copy. Launch success is not completion.
Retire partial five-tap captures on cancel/reset/error/identity or row mismatch;
publish only after all five tap writes complete for the same actual rows and
request generation. This packet supplies no such native lifecycle mechanism.

## CPU checks

Run `run_cpu.cmd` for the standalone host descriptor checks (MSVC, no HIP).
Run `python -B test_reference.py --run-cpu` using the explicit Torch CPU interpreter.
Default tests are stdlib-only. No tests call the HIP fixture implicitly.

## Root-only device qualification, after capture-mechanism review

These commands are instructions, not author-executed results. Build in an owned
scratch directory on Root's HIP host; this does not attach to the engine:

```sh
hipcc --offload-arch=gfx1151 -std=c++20 -O2 -fno-fast-math -ffp-contract=off -fdenormal-fp-math=ieee hcmean.hip fixture.hip -o hcmean_fixture
python -B reference.py fixture-tail --full-rows 4 --source-first 2 --rows 2 --tap 3 --destination-first 1
./hcmean_fixture fixture-tail 4 2 2 3 4 1 actual-tail.u16
python -B compare_source.py fixture-tail actual-tail.u16
python -B qualify_source_gpu.py --run-gpu fixture-tail actual-tail.u16
```

Archive compiler/flags/runtime/architecture and inspect disassembly for widened
BF16, ordered FP32 additions, denormal handling, RN-even narrowing and vector
loads/stores before accepting results. The executable compares **all** output
words, including guard regions, against independently generated expected bits;
the scripts report CPU and actual GPU source-expression comparisons separately.
Use each tap0..4 and decode rows1..4. Prefill must cover rows1,2,3,4,2048,8192,
including a8192-row source tail `(source_first=8190,rows=2)` and a full8192-row
output (generator reserves one guard row when it fits, capped at8192 destination
rows; use source_first0, rows8192 and destination_first0 for the full case).
Exercise separate2560-stride outputs and padded source strides in a
Root-owned additional fixture before qualifying those optional forms; the
provided HIP executable currently tests native contiguous raw/concat layout.
No source runtime equivalence may be generalized from only the small fixture.

For2048 rows and five taps, full raw HC buffers total200MiB while concatenated
means total50MiB. On-device mean can reduce a future readback volume by4x if
capture ownership/fences and consumers are integrated. This is byte arithmetic,
not observed DMA traffic, an I/O-fabric claim, NPU readiness or a tokens/s claim.
GPU-resident and NPU consumers both require explicit completion and ownership.
