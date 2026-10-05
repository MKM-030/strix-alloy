# Resident BF16 GPU hidden-FC prototype

Source prepared 6 October 2026. This standalone, default-off HIP projection
replays the retained gfx1151 count1 MTP hidden-FC M4 arithmetic using the original
decoded BF16 weight words. It removes repeated Q8 affine decode and weight RNE
from recurrent H calls. Compilation and one finite GPU comparison are complete:
frozen A/B outputs are bit-exact, but the candidate has no qualified speed gain
and remains disabled. Mean component latency is160.095 µs versus136.962 µs;
see [the measured report](../../../docs/research/halogen-gpu-hidden-bf16-20261006.md).

`hidden_bf16.hip` exports `halogen_gpu_hidden_bf16`. The root-owned `build.py`
is the offline compilation helper. `replay.c`, `image_wrapper.py` and
`owned_run.py` provide the finite root-owned standalone comparison. This change
installs no engine hook or profile and adds no live recurrent synchronization.

## Device and launch contract

| Field | Required value |
|---|---|
| Device target | gfx1151, physical wave32 |
| K / N / M | 2560 / 2560 / 4 |
| Grid / block | `(160,1,1)` / `(256,1,1)` |
| Dynamic shared memory / stream | 0 bytes / default HIP stream0 |
| W | Device-resident little-endian BF16 words, row-major `[2560][2560]`, 13,107,200 bytes |
| X | Canonical device-resident BF16 words, `[4][2560]`, 20,480 bytes |
| Y | Canonical device-resident BF16 words, `[4][2560]`, 20,480 bytes |
| Alignment | W and X base addresses aligned at least16 bytes; Y at least2 bytes |
| Aliasing/lifetime | W/X/Y do not overlap; storage stays valid until stream consumers finish |
| Public source parameters | `(const uint16_t* W, const uint16_t* X, uint16_t* Y, int64_t K, int64_t N)` |

The caller validates exact grid/block geometry and emitted gfx1151/wave32
metadata before launch, along with shape, pointer extents, prepared-weight
identity and runtime compatibility. The kernel checks only fixed K/N and returns
without writing Y when either differs from2560; it is not a host error reporting
mechanism. The caller must not consume Y after a rejected launch. Geometry and
wave-size validation belongs to the caller, matching the native fixed launch
contract and avoiding device-side dimension queries.

The four X streams are contiguous slices of the original whole-row RMS result,
not four separately normalized inputs. No NPU input or weight transpose is part
of this GPU contract. Enqueue H into the canonical Y buffer on stream0 before
the original seed consumer, preserving the existing asynchronous H-to-seed
ordering. Module loading, allocation, weight preparation/upload and fixture
copies belong outside recurrent H. No extra per-H copy, launch or host wait is
needed by this kernel.

This is a new module/function, not an assertion of binary ABI identity. Although
the five public parameters have the same nominal widths/order as the retained
kernel's W/X/Y/K/N, W now means BF16 words. The owner must inspect actual emitted
kernarg/hidden-argument metadata and use the correct module-launch mechanism.

## Preserved arithmetic

Workgroup `b`, thread `t` owns output `o=16*b+(t>>4)` and sublane `p=t&15`.
Every physical wave32 contains two independent16-lane output rows. Each q in
increasing order0 through9 starts at `k=16*p+256*q` and loads sixteen BF16 weight
words as two aligned128-bit source loads. The weights are reused across all four
streams; each X stream has the same two128-bit source loads.

Each chunk starts four FP32 accumulators at positive zero. Eight increasing
packed pairs feed four interleaved, independent `v_dot2_f32_bf16` chains. One
separate `v_add_f32` per stream then adds that chunk result to its accumulated
sum. The next q resets each chunk accumulator. The source uses explicit native
instruction assembly for both operations; there is no generic FMA alternative.

After the ten chunks, the four sums undergo XOR-distance8,4,2,1 butterfly stages
in that order, each with a separate FP32 ADD. `__shfl_xor(..., width=16)` uses the
installed HIP integer-bit exchange implementation, which selects the physical
XOR lane through `ds_bpermute`; the wave32 requirement keeps the two rows separate.
All lanes participate before only p0 stores the four outputs. Final BF16 RNE is
the retained integer sequence:

```text
uint16((bits32 + 0x7fff + ((bits32 >> 16) & 1)) >> 16)
```

The original finite-value conversion is retained without added NaN
canonicalization. Prepared weights must be finite; exceptional-input/output
qualification remains the owner's parity responsibility. Source arithmetic and
aligned `memcpy` load intent do not prove the emitted instruction sequence.

## Prepared weights

Use the existing exact native-decoded H words. The streamed NPU preparation
payload is not directly the GPU W buffer. Its lossless inverse, already defined
by `unpack_decoded()` in `../halogen_npu_native_hidden_decoded/pack.py`, restores
the original row-major words:

```python
words = np.frombuffer(packed, dtype="<u2").reshape(8, 5, 10, 4, 16, 256)
words = words.transpose(0, 1, 3, 4, 2, 5).reshape(2560, 2560)
row_major = np.ascontiguousarray(words, dtype="<u2").tobytes()
```

This rearranges already-decoded words once before upload; it performs no new
Q8 decode, fitting, quantization or input-dependent calculation. Validate the
source size13,107,200 bytes and hash before inversion, the full finite-BF16
condition, and the resulting size/hash before publishing the cache:

| Artifact | SHA256 |
|---|---|
| Prepared streamed BF16 source | `0981771c06ee35910915713916f510e38bb995088eb8afe710686ba6762e5328` |
| Required original row-major decoded BF16 | `6c324951fa67bf51b66e3911f1dc31560f05a18f5143312714c47f7d38acb008` |
| Original raw Q8 H provenance | `018511894df3996e3a2fcb1dff60860c45a808b65036fd38db472b6e985bdd3f` |
| Retained original gfx1151 HSACO | `45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83` |

No new preparation script is supplied. The original Q8 checkpoint remains
mapped and available for stock fallback. The resident BF16 side cache adds
13,107,200 bytes (12.5 MiB); both H representations total20,070,400 bytes.
Candidate unique weight read footprint is13,107,200 bytes against stock
6,963,200 bytes, a difference of6,144,000 bytes. That difference is not the
added allocation. Removing repeated decode/rounding may help, while the larger
weight footprint may lose under bandwidth/cache pressure.

## Owner qualification gates

1. Offline compile with the installed explicit ROCm7.2 AMD HIP toolchain for
   gfx1151/wave32; disable fast-math, FP contraction and reassociation. Request
   matching original ELF ABI byte4 (code object V6, compiler
   `-mcode-object-version=6`). Preserve FP32 nearest-even and
   input/output denormals, matching original descriptor float mode0xf0.
2. Inspect actual ELF/metadata and device emission: wave32/launch compatibility,
   mode/absence of unexpected mode updates, public/hidden kernargs, ordered
   native BF16 dot2 chains, ten separate chunk sums,8/4/2/1 exchanges, final RNE,
   two128-bit loads per weight/input chunk, register counts, spills and scratch.
   The retained baseline is SGPR21/VGPR88, LDS0/private0; no candidate register
   or occupancy result is known. A source-only review is not this gate.
3. Compare every output BF16 word against the retained original M4 module on
   the same frozen canonical X and original H provenance. Establish exact parity
   before drawing proposal/token conclusions or allowing later integration.
4. Measure a finite, balanced same-stream GPU comparison with input/weights
   resident and output ready for the existing consumer. Keep setup/copies and
   initialization separate. Preserve the original dependency, with no added
   stock per-H host wait. Any later live hook needs its own stock fallback and
   complete head/acceptance qualification.

Retained original H event mean is158.707124125 microseconds (range150.858 to
174.740002), excluding setup, copies and comparisons. The487.1700625-microsecond
host E+H bracket is not an H-only budget. This prototype has no GPU measurement,
token/s result, end-to-end speedup or acceptance result. It targets late count1
MTP hidden-FC generation/replay during decode; ordinary target prefill is not
this boundary and has no demonstrated gain from this change.

The original mapping and arithmetic evidence are in
[the GPU candidate audit](../../../docs/research/halogen-gpu-vector-h-candidate-20261005.md),
[the native dispatch audit](../../../docs/research/halogen-native-d-fc-dispatch-20261004.md)
and [the accumulation-order audit](../../../docs/research/halogen-native-fc-accumulation-20261004.md).
