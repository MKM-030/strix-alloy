# Native FC accumulation order and portable reference limits

The original selected `k_lq8w<1,16,1>` and `k_lq8w<4,16,1>` shaders have a
recoverable reduction schedule. A BF16-weight NumPy/BLAS MatMul does not specify
that schedule. The accessible authoritative AMD documentation does not establish
the internal fusion/rounding sequence of `V_DOT2_F32_BF16`, so the schedule below
is an instruction-boundary specification, not a qualified portable bit-exact
implementation. Frozen `.002/.0002` tolerances remain unchanged.

This source-only inspection used the original gfx1151 HSACO sealed in
[the FC dispatch audit](halogen-native-d-fc-dispatch-20261004.md). No payload,
provider, model, GPU, NPU, WSL or numerical test was read or run.

## Exact lane and chunk schedule for K=N=2560

For workgroup index `b` and workitem `t` in `0..255`, output row is
`o=16*b+(t>>4)` and the row's sublane is `p=t&15`. A wave32 contains two
independent 16-lane output-row groups. This comes directly from the right-shift,
mask and row construction at M1 GPU `0x2d1214..0x2d1238` and M4
`0x2d7814..0x2d7834`.

Each sublane handles ten contiguous 16-column chunks, with starts
`k=16*p+256*q`, `q=0..9`, in that increasing order. Weight codes begin at
`W[o]+k`; affine pair is for group `floor(k/64)`. The next-code offset increases
by256 bytes and next affine address by16 bytes. Evidence is M1 initial loads
`0x2d12c8..0x2d1314`, loop increments `0x2d15b4`, `0x2d16ec..0x2d170c`, and
M4 equivalents `0x2d78cc..0x2d7918`, `0x2d7e58..0x2d7e78`.

Within each chunk, decoded weights are BF16 RNE, as already audited. The eight
packed pairs cover `(k,k+1)`, `(k+2,k+3)`, through `(k+14,k+15)`, in that order.
The first DOT2 starts with FP32 zero; the following seven DOT2 operations use
the previous pair's result as their FP32 accumulator. The chunk result is then
added with a separate FP32 ADD to the sublane's running sum. The DOT2 chain is
reset to zero at the next chunk; the ten chunks do not share one DOT2 chain.

| Shader | First and last chunk DOT2 | Separate chunk-sum ADD | Per-stream running accumulator |
|---|---|---|---|
| M1 | `0x2d15e0` / `0x2d16c4` | `0x2d16d4` | `v16` |
| M4 | first pair `0x2d7cdc..0x2d7d00`; last pair `0x2d7e14..0x2d7e2c` | `0x2d7e3c..0x2d7e44` | streams0/1/2/3: `v21/v20/v19/v16` |

M4 loads each normalized input stream at `X+2*K*stream` bytes
(`0x2d7994..0x2d7a60`). Its four DOT2 chains are interleaved in instruction
issue but have independent accumulators and the same eight-pair order. There
is no arithmetic reduction across streams.

After all chunks, the shader uses `DS_BPERMUTE_B32` to exchange values at
wave-lane XOR distances **8, then4, then2, then1**, with a separate FP32 ADD
after each exchange. XOR distances preserve the two 16-lane row groups.
The p0 lane alone stores each output, after BF16 RNE. Evidence is M1
`0x2d176c..0x2d1870` and M4 `0x2d7ed8..0x2d812c`. A CPU emulation must compute
each butterfly stage from the preceding stage's values, not update lane sums
in place or substitute a sequential sum over sixteen lanes.

## Instruction-boundary specification

`Add32` means the original single-precision ADD; `Dot2Native` deliberately
retains an unresolved original instruction boundary. `Wbf16` is the native
BF16-rounded decoded weight, not the original FP32 decoder result.

```text
for output o, stream m:
    for p = 0..15:
        S[p] = FP32(+0)
        for q = 0..9:
            k = 16*p + 256*q
            D = FP32(+0)
            for j = 0..7:
                D = Dot2Native(X[m,k+2*j:k+2*j+2],
                               Wbf16[o,k+2*j:k+2*j+2], D)
            S[p] = Add32(S[p], D)
    for distance in [8,4,2,1]:
        T[p] = Add32(S[p], S[p XOR distance]) for all p
        S = T
    Y[m,o] = BF16_RNE(S[0])
```

The mode in both original kernel descriptors is `0xf0`. The 32-bit
`compute_pgm_rsrc1` at descriptor+48 is `0xe0af0007` (M1 descriptor `0x1fa340`)
or `0xe0af000a` (M4 descriptor `0x1fa640`). The installed LLVM hardware layout
defines round32 at bits12..13, round16/64 at14..15, denorm32 at16..17 and
denorm16/64 at18..19. These fields select nearest-even and preserve input/output
denorms. Neither complete shader contains a mode-register update. This decodes
the default mode for operations that obey those fields; it is not an independent
proof that DOT2 has no instruction-specific denormal exception.

The original `V_FMA_MIX_F32` dequantization is fused. For finite unsigned8 codes
and finite FP16 affine values, the code-times-scale product needs at most19
significand bits and remains in FP32 range, so that multiplication is exactly
representable in FP32. Under ordinary nearest-even FP32 arithmetic, the same
affine result follows from explicit FP32 multiply then add; the important
subsequent BF16 weight-rounding boundary still must be preserved. This is a
format argument, not a result fitted to frozen inputs.

## What the authoritative documentation establishes

AMD's [machine-readable ISA page](https://gpuopen.com/machine-readable-isa/)
publishes the [official XML archive](https://gpuopen.com/download/machine-readable-isa/latest/).
The RDNA3.5 XML fetched on October4 has release date2026-02-20, schema1.1.1,
12,342,460 bytes, and raw SHA256
`c36b6d79b1e940d74107221c985f5a7fde248025da251d2c6ef756c4cd31391a`.
It explicitly identifies FMA_MIX as fused and DOT2 as two BF16 products with an
FP32 accumulator. Its DOT2 entry contains encoding/operand metadata and a prose
description, with no executable arithmetic semantics or internal rounding rule.
The archive was inspected in memory only.

AMD's [floating-point dot builtin reference](https://rocm-handbook.amd.com/projects/amd-rocm-optimization-guide/en/docs-1.0.0/compiler-builtins/cross-arch/arithmetic-ref/dot-float-builtins.html)
also establishes the BF16-pair/FP32-accumulator contract and RDNA3.5 availability,
without stating the internal rounding sequence. The primary
[RDNA3.5 ISA PDF](https://www.amd.com/content/dam/amd/en/documents/radeon-tech-docs/instruction-set-architectures/rdna35_instruction_set_architecture.pdf)
and its docs.amd.com PDF endpoint returned access errors during this audit; a
PowerShell request to the direct PDF returned HTML, not a PDF. Search-indexed
algebra or an RDNA4 pseudocode listing is insufficient to establish RDNA3.5
rounding and is not used as a proof.

Consequently, do not label a replacement such as two scalar FMAs, two rounded
products plus additions, or a single rounded exact three-term sum as an exact
emulation of this DOT2 without additional authoritative semantics. General
BF16 operands also require explicit treatment of overflow, subnormals, signed
zero and NaNs. The original native-kernel replay remains the available oracle.
If the ordinary BF16-weight screen misses its frozen gate, this recovered
schedule supplies a principled next reference specification, but portable exact
DOT2 emulation remains an open requirement. No fitting or tolerance change is
justified by that miss.
