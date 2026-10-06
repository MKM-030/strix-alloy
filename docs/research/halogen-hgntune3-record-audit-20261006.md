# HGNTUNE3 record and selection audit — 6 October 2026

The retained 22-record trained plan contains recoverable matrix-shape and
algorithm-selection fields. It does **not** identify a current Prefill shader,
tensor payload or call frequency. Its prior rejected serving comparison remains
rejected; this source audit supplies no reason to repeat that experiment.

This was a bounded read-only inspection of saved disassembly, plan bytes and the
local HIP datatype header. No engine, accelerator, provider, runtime query,
model read, trace, build or tuning run was started.

## Inputs and identities

The pristine host disassembly is retained at
`server/.local/optimization9h-20261004/mtp-route-static-20261004/host-text-disassembly.txt`,
SHA256 `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`.
It describes the pinned native `flash_serve`, SHA256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.

| Saved plan | Bytes | Records | SHA256 |
|---|---:|---:|---|
| `server/.local/optimization9h-20261004/shipped-matmul.plan` | 30,644 | 478 | `a053ca07a4de9642934dcbff91addf5dd457edb06169dc173ae354abe56754d1` |
| `backends/halogen-wsl2-0.16.2/.local/matmul/8k-trained-20261004.plan` | 1,460 | 22 | `9dcfe4789a8a45ed3717f62ce221521606fec5d271f9d648940bf36a42a06d3b` |

Both have the same 52-byte envelope: `HGNTUNE3`, library-version field100401,
20 WGPs and `gfx1151`. Their exact sizes equal `52 + 64 * record_count`.
The shipped file has478 records; the number22 applies only to the local trained
file. The existing [envelope validator](../../backends/halogen-wsl2-0.16.2/scripts/matmul_plan.py)
continues to classify records as opaque; it was not edited by this audit.

## Serialization and field evidence

Reader `0x18c4560` reads64-byte records at `0x18c474e..18c476c`.
Writer is **`0x18c4b50`**; `0x18c4d80` is its caller/destructor, rather than the
writer. A record can be decoded mechanically as little-endian
`<qqqqiiiidd>`: four signed64-bit dimensions, four32-bit integers and two doubles.

| Byte offset | Field | Disassembly evidence |
|---:|---|---|
| 0 | Rounded/bucketed M | Writer `18c4c85..18c4c90` takes node+38; reader `18c4897..18c48ac` reconstructs the key |
| 8 | N | Same writer shuffle takes node+30; reader `18c489f..18c48a7` |
| 16 | K | Writer `18c4c96..18c4c9a` takes node+28; reader `18c488a..18c4892` |
| 24 | Actual M when the choice was created | Writer `18c4c9f..18c4ca3` takes choice+30; reader `18c486b..18c4873`; new choice stores actual M at `18c5bd6` |
| 32 | Internal type selector | Writer `18c4ca8..18c4cac` takes node+20; reader `18c487f..18c4886` |
| 36 | Selected heuristic ordinal | Writer `18c4cb3..18c4cb7`; reader `18c4852..18c485a`; timed selector writes choice+18 at `18c665c` |
| 40 | Returned heuristic-candidate count | Same eight-byte copy; new choice writes choice+1c at `18c5bce..18c5bd2` |
| 44 | Library algorithm identity | Writer passes the selected24-byte algorithm object to getter `18d3c80` at `18c4cbf..18c4cc7`; reader passes this ID to reconstruction routine `18d3c70` at `18c4772..18c47bb` |
| 48 | First heuristic's retained timing | Writer copies choice+20; timed selector records candidate zero at `18c65be..18c65cc` |
| 56 | Best candidate's retained timing | Writer copies choice+28; timed selector stores minimum at `18c665f..18c6665` |

Fields36 and40 are **not** Split-K or workgroup-mapping controls. They describe
the heuristic search. The last doubles come from scaled event timing across
four GEMMs. This audit does not independently bind the stripped PLT names or
decode the scale constant, so it preserves these as native timing values and
does not assign an additional unit or convert them to token rates.

The reader reconstructs an algorithm from the recorded library ID and copies
its first24 bytes into the loaded choice. It retains the recorded ordinal,
count and timings as metadata. Neither plan serializes a shader name, HSACO
digest, tensor digest, layer ID, dispatch count or measured serving frequency.
An ID is meaningful within the matching math-library identity; it is not a
standalone shader binding.

## Shape, layout and type construction

Descriptor constructor `0x18c4f60` receives owner, M in RSI, N in RDX, K in RCX
and type in R8D. It retains these as R12, R15, saved RCX and EBX, respectively.
The descriptor map compares `(M,N,K,type)` through node offsets38,30,28,20.

`18c5078..18c50b6` sets matrix-operation fields to112 and111, the transpose and
nontranspose values. Layout construction at `18c50e1..18c5131` makes
`A[K,N]` with leading dimensionK, `B[K,M]` with leading dimensionK, and
`C[N,M]` with leading dimensionN in the column-major library interpretation.
This is compatible with row-major `X[M,K] * W[N,K]^T -> Y[M,N]`.
The assignment does not itself identify which live tensor is X or W.

Type construction at `18c50c3..18c50dd` selects input datatype14 except for
type1, which selects datatype0. Output datatype is14 for type0 and0 otherwise.
The retained local `hip/library_types.h` identifies14 as `HIP_R_16BF` and0 as
`HIP_R_32F`, giving:

| Internal type | Input layouts | Output layout | Caller wrapper |
|---:|---|---|---|
| 0 | BF16 | BF16 | `18c6b80` |
| 1 | FP32 | FP32 | `18c6bf0` |
| 2 | BF16 | FP32 | `18c6c60` |

These are storage/layout types, not a new proof of every internal accumulation
or shader arithmetic operation. The22 trained records contain types0 and2.

When bucketing is enabled, a tuning path exists or more than one algorithm is
requested, and M is at least32, `18c51a0..18c51c6` rounds M upward to a multiple
of `2^(floor(log2(M))-4)`. Thus8076 maps to8192 and32304 maps to32768. Descriptor
dimensions remain the actualM; rounding applies to the plan key. SmallerM is
unrounded. `ALGOS=1` with no plan path does not enter this rounding condition.

## The trained choices and shipped 8K comparison

The trained file has eight small-M records, thirteen8192-bucket records and
one32768-bucket record. All thirteen8192 records were created at actualM8076.
The32768 record was created at actualM32304 with N=K=2560/type0/algorithm819.
The shipped file has fourteen8192-bucket records: thirteen matching keys plus
N=1280/K=2560, created at actualM8186. Its other thirteen were created at8192.

| Bucket M | N | K | Type | Trained actual M | Shipped algorithm | Trained algorithm |
|---:|---:|---:|---:|---:|---:|---:|
| 8192 | 48 | 2560 | 0 | 8076 | 1120 | 945 |
| 8192 | 320 | 10240 | 0 | 8076 | 900 | 901 |
| 8192 | 336 | 10240 | 0 | 8076 | 901 | 900 |
| 8192 | 512 | 2560 | 0 | 8076 | 850 | 850 |
| 8192 | 512 | 5120 | 2 | 8076 | 1177 | 1177 |
| 8192 | 640 | 2560 | 0 | 8076 | 1141 | 850 |
| 8192 | 2560 | 640 | 0 | 8076 | 836 | 941 |
| 8192 | 2560 | 2560 | 0 | 8076 | 898 | 850 |
| 8192 | 2560 | 6144 | 0 | 8076 | 819 | 819 |
| 8192 | 6144 | 2560 | 0 | 8076 | 817 | 819 |
| 8192 | 10240 | 320 | 0 | 8076 | 906 | 837 |
| 8192 | 10240 | 2560 | 0 | 8076 | 817 | 819 |
| 8192 | 12288 | 2560 | 0 | 8076 | 817 | 817 |

Nine of the thirteen common keys choose different algorithm IDs. Their training
timings compare different actualM and different training runs, so they do not
isolate an algorithm speed effect. Selection index0 is a valid result, not a
missing choice; every trained row reports eight returned candidates.

The earlier [matched serving comparison](../benchmarks/halogen0162-matmul-20261004.md)
already found the frozen trained plan slower and changed all eight retained
TG128 output hashes, including warmups. MTP acceptance fell from60% to55%.
Those observations prevent promotion regardless of this additional field audit.

## Current 8192 profile and remaining ambiguity

The accepted profile uses both `max_prefill_tokens=8192` and
`prefill_chunk=8192`. This fixes the allocator and ordinary input chunk ceiling;
it does not prove every internal GEMM has M at most8192. The retained32304
record equals four times8076, but the plan alone cannot identify whether that
axis is expert replication, another packed axis or a different call. It cannot
be assigned to an obsolete32768 arena merely from its numeric value.

For a current main-Prefill optimization, the missing evidence is the binding
from a concrete current chunk's tensor descriptor and caller to its algorithm,
actual shader and useful recurring cost. The static main-Prefill path and this
plan format are complementary; neither supplies a retained current bulk
dispatch/tensor/hash record. A WMMA or LDS proposal must target such a binding
before a new hardware experiment is justified.

| Device/metric | Result of this development |
|---|---|
| GPU | Matrix shape/type/choice fields are recoverable; no newly selected shader or demonstrated speedup |
| CPU | Saved-plan decoding is read-only analysis, with no serving substitution |
| NPU | No compatible current bulk offload or additional-memory mechanism established by these records |
| Prefill / Decode / acceptance | No new measured values or improvement; existing rejected plan remains disabled |
