# GPU hidden BF16: retained emission review

Reviewed 6 October 2026; filename retains the assigned 5 October work item.

**Verdict: no blocking emitted-schedule, load or launch-metadata finding.** The
final standalone kernel retains the original M4 instruction-boundary arithmetic
on prepared row-major BF16 words, and its descriptor floating-point mode matches
the original. This is an offline emission verdict; exact runtime BF16 parity
and GPU timing remain unmeasured.

## Evidence and scope

Only the already-retained source, build receipt, disassembly, metadata and ELF
descriptor bytes were read. This review executed no compiler, disassembler,
runtime, device, test, server or continuation. It wrote this report and one
small descriptor-comparison JSON receipt in the retained base directory.

Retained build directory:
`server/.local/optimization9h-20261004/gpu-hidden-bf16-build-3d8f021748a24748b2a241348d3cbb96`.
The receipt records successful offline compilation/unbundling/inspection with
`runtime_loaded=false`, `gpu_executed=false` and `engine_modified=false`.

| Pinned retained artifact | SHA256 from build receipt |
|---|---|
| `hidden_bf16.hip` | `d4e8ad1ec038aaaed006513fc7e4297be5a1dba675580a8845f26f6319c7b830` |
| `hidden-bf16.hsaco`, 5,928 bytes | `50cb29fde867f1a3a9c58e41bd3bfaf1bbde4941ab75076918eac8a39eb53a4b` |
| `disassembly-stdout.txt` | `f7661423d1f59561ed25da181bf0afb105077a225b7bff3403d84715a1dc084f` |
| `metadata-stdout.txt` | `af906624e8e900cd9f8750e21350cc1403a9ca91d2477bd29b34506afc6ac4b4` |

The compiler command uses gfx1151, `-O3`, `-fno-fast-math`, `-ffp-contract=off`
and **`-mcode-object-version=6`**. The resulting ELF header has AMDGPU HSA OS/ABI
and **ABI-version byte4**, matching the required retained ELF ABI byte. Compiler
code-object version6 and ELF ABI byte4 are distinct values.

## Descriptor floating-point mode

Both descriptors map through file-backed PT_LOAD program header1 with
`p_offset=p_vaddr=0`. Original descriptor VA/file offset is `0x1fa640` within
`p_filesz=0x20d750`; candidate VA/file offset is `0x680` within `p_filesz=0x6c0`.
Both complete64-byte descriptors fit those mappings; both code-object SHA256
values were independently rechecked against the assigned pins.

| Descriptor field | Original | Final candidate |
|---|---|---|
| `compute_pgm_rsrc1`, offset48 | `0xe0af000a` | `0xe0af0046` |
| `compute_pgm_rsrc2`, offset52 | `0x00000084` | `0x00000084` |
| FP32 rounding, bits12..13 | 0 | 0 |
| FP16/64 rounding, bits14..15 | 0 | 0 |
| FP32 denormals, bits16..17 | 3 | 3 |
| FP16/64 denormals, bits18..19 | 3 | 3 |

Both float-mode bytes are `0xf0`: nearest-even rounding and input/output denormal
preservation. Differences in the remaining `rsrc1` bits do not change those
fields. This establishes matching initial descriptor modes, not instruction-specific
DOT2 semantics or runtime equality. Exact mappings/raw fields are retained in
`server/.local/optimization9h-20261004/gpu-hidden-bf16-descriptor-modes-20261005.json`.

## Launch metadata and mapping

The exported function is `halogen_gpu_hidden_bf16`, entry `0x1700`, size1,416
bytes, with its64-byte descriptor at `0x680`. Metadata identifies gfx1151,
wave32, maximum flat workgroup256, kernarg40/alignment8, exactly five8-byte public
arguments at offsets0/8/16/24/32, and no hidden arguments. LDS/private sizes and
SGPR/VGPR spill counts are all zero; dynamic stack is false.

The candidate uses **10 SGPRs and54 VGPRs**, against retained original21/88.
These are emitted resource counts, not a measured occupancy or speed gain.

At `0x1700..0x1730`, the only runtime shape checks are K and N against2560.
The former device-side launch-dimension query/division prefix is absent. The
caller must validate grid `(160,1,1)`, block `(256,1,1)`, stream0 and the actual
gfx1151/wave32 module before launching.

`0x1734..0x1798` recovers `p=t&15`, `o=16*b+(t>>4)`, row byte stride5120 and
sublane byte stride32. The row construction uses a shift/OR with disjoint low
four bits, equivalent to the original addition for the fixed block. Thus each
physical wave contains two independent16-lane output rows.

## Loads, pair chains and loop

All ten source vector loads are actual `global_load_b128` instructions:

| Data | Emitted locations | Packed registers used in increasing pair order |
|---|---|---|
| W, shared by four streams | `0x17e4/0x17ec` | `v14..v17`, then `v10..v13` |
| X stream0 | `0x17f8/0x1800` | `v22..v25`, then `v18..v21` |
| X stream1 | `0x1890/0x18a8` | `v26..v29`, then `v38..v41` |
| X stream2 | `0x1898/0x18b0` | `v30..v33`, then `v42..v45` |
| X stream3 | `0x18a0/0x18b8` | `v34..v37`, then `v46..v49` |

Load issue order sometimes fetches the upper128 bits first; arithmetic still
consumes lower pairs first. Effective X stream byte offsets are0/5120/10240/15360.
For streams1..3, split address additions plus encoded load offsets produce
those exact strides. No scalarized weight/input loads, affine decode or generic
FMA projection appear in the body.

At `0x18c0/0x18c8`, all four chunk accumulators `v50..v53` reset to positive
zero on every iteration. `0x18e4..0x19f4` contains exactly32
`v_dot2_f32_bf16`: eight increasing packed pairs, each interleaving streams0..3.
Each destination is also its own prior FP32 accumulator. There is no cross-stream
sum and no dot2 chain carried into the next chunk.

Four distinct FP32 ADDs at `0x19fc/0x1a00/0x1a04/0x1a08` add the chunk results
to running sums `v3/v2/v4/v5`. Counter `s[2:3]` starts0, increments512 bytes at
`0x18d0/0x18d8`, compares against5120 at `0x18dc`, and branches back from
`0x1a0c` to `0x17b8` while unequal. Loads therefore cover q0 through9 exactly,
with `k=16*p+256*q`.

## Butterfly and output

Physical lane ID comes from `v_mbcnt_lo_u32_b32` at `0x1a10`. XOR lane addresses
are bounded to the current16-lane half and converted to byte indices. The
emitted exchange/ADD stages are:

| Distance | Four `ds_bpermute_b32` | Four separate FP32 ADDs |
|---|---|---|
| 8 | `0x1a48..0x1a64` | `0x1a70..0x1a88` |
| 4 | `0x1a8c..0x1aa4` | `0x1ab4..0x1acc` |
| 2 | `0x1ae0..0x1af8` | `0x1b08..0x1b24` |
| 1 | `0x1b38..0x1b50` | `0x1b5c..0x1b74` |

Some lane addresses are prepared early, but each exchange reads the preceding
stage's sums. All lanes participate before `p==0` masks EXEC at `0x1b78`.

Four `v_bfe_u32` operations extract bit16; four `v_add3_u32` operations add
the original FP32 bits, that bit and `0x7fff`. Four
`global_store_d16_hi_b16` operations at `0x1c64/0x1c6c/0x1c74/0x1c7c` store
the upper halfwords directly to Y streams0..3, implementing the original BF16
RNE sequence without extra floating-point conversion or NaN canonicalization.

These findings agree with the retained M4 schedule in
[the accumulation audit](halogen-native-fc-accumulation-20261004.md) and
[the GPU candidate audit](halogen-gpu-vector-h-candidate-20261005.md).
Prepared-weight identity, full frozen-output equality and a
finite same-stream GPU comparison remain separate gates. No throughput,
acceptance, end-to-end or ordinary-prefill gain follows from this report.
