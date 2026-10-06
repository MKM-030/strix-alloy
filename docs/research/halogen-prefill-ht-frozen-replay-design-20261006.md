# Frozen DN QKV native-HT replay design, 2026-10-06

This finite source-only design covers one ordinary DeltaNet QKV operation at
`M=8192, N=10240, K=2560`. No engine, hardware, WSL command, model payload,
new disassembly, or build was run. Root owns any later capture and replay.
The original server remains outside this agent's lifecycle authority.

Source: retained pristine host text and registrations under
`server/.local/optimization9h-20261004/mtp-route-static-20261004/`.
Executable SHA-256:
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
Host-text SHA-256:
`523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`.
All addresses are pre-ASLR RVAs; current process identities must come from
root's fresh lifecycle evidence, not from this note.

## Bound interfaces

Ordinary chunk `0x17dd020` calls layer `0x17d9eb0`, then DeltaNet
`0x1791030`. QKV call `0x17913fb -> 0x178cf90` passes descriptor `L+0x8`,
input `*(model+0x6e8)`, output `*(0x18db268)`, N10240, count8192 and K2560.
`L = *(model+0x4d8) + layer_index*0xc68`. The dispatcher first calls
`0x17f8280` at `0x178cfbb`.

The signatures derived from register and stack setup are:

```c
// 0x17f8280, called at0x178cfbb:
bool packed_trunk(void *D, const void *X, void *Y,
                  bool output_float32, int N, int M, int64_t K);
// SysV: RDI,RSI,RDX,CL,R8D,R9D; K is stack argument7.
// This particular ordinary dispatcher passes output_float32=0.

// 0x18092f0, called at0x17f841f:
bool native_ht(void *D, const void *X, void *Y,
               int N, int M, int64_t K);
// SysV: RDI,RSI,RDX,ECX,R8D,R9.

// Stock original-weight preparation at0x17f865c ->0x17ec6e0:
void prepare_original(const void *packed, int mode, int N, int64_t K,
                      const void *input_signs, const void *output_scales,
                      void *prepared_weight);
// Seventh argument is on the stack. Return value is not used by the caller.

// Stock library helper at0x17f8696 ->0x18c6b80:
void matmul(void *router, const void *prepared_weight,
            const void *X, void *Y, int64_t M, int64_t N, int64_t K);
```

The stock helper uses the existing library cache and `hipblasLtMatmul`.
Replay should reuse the original host functions and registered original GPU
kernels within an exclusive owned engine process. The previous standalone FC
replay loads only GPU code; it does not provide these host helpers or the
initialized matmul router. Do not claim it is already a ready HT replay binary.

## Descriptor and byte bounds

Capture the fixed host descriptor prefix `[D,D+0x78)` once, then decode only
the following source-used fields. Host pointers are metadata; pointed-to GPU
payloads require HIP copies and independently established extents.

| Offset | Width | Meaning supported by this caller | Required extent |
|---|---:|---|---|
| `+0x30` | 8 | Packed HT pointer | Current packed payload extent remains missing |
| `+0x38` | 8 | Input sign/rotation vector pointer | K native16-bit words:5120 bytes |
| `+0x40` | 8 | Output scale vector pointer | N native16-bit words:20480 bytes |
| `+0x48` | 4 | Mode selecting native template3 or alternate4 branch | Record actual value; do not assume |
| `+0x4c` | 4 | N check | Must equal10240 |
| `+0x50` | 8 | K check | Must equal2560 |
| `+0x70` | 8 | Diagnostic name field used by error path | Record pointer; no unbounded string read |

X needs exactly M*K native16-bit words =41,943,040 bytes (40 MiB).
Y needs M*N native16-bit words =167,772,160 bytes (160 MiB), because this
ordinary call has `output_float32=0`. Original prepared W needs
N*K native16-bit words =52,428,800 bytes (50 MiB). Preserve the raw words;
do not reinterpret or convert their floating format during capture.

The existing CPU decoder `scripts/benchmarks/hgn_ht_slice.py` specifies
`N*K/2` packed bytes only for validated store16/variant0x1208. That would be
13,107,200 bytes here **if the actual tensor receipt proves that format**.
It does not establish this current descriptor's format, especially mode3.
Obtain the selected tensor's declared size/store/variant and current allocation
mapping before copying `D+0x30`; do not guess an extent from mode or copy the
entire containing model allocation. This is the only tensor-specific byte
extent not settled by the finite host audit.

## Scratch allocation now bound

At `0x176e3df..0x176e433`, let
`a = min(*(int32_t *)(model+0x218),8192)` under the surrounding startup branch.
The source writes:

```text
18dcf28 = a * 6144                  // capacity in16-bit elements
18dcf30 = allocate(a * 12288 bytes) // same storage, twice the capacity
```

The allocator `0x17789a0` forwards its byte count to the HIP allocator at
`0x17789d4`. At a8192 the capacity is50,331,648 elements and allocated size
100,663,296 bytes (96 MiB). Native admission at `0x1809301..0x1809321`
compares M*K directly to that element capacity. The40-MiB rotated input fits
the96-MiB source allocation. Startup branch, actual value of model+0x218,
current pointer and actual allocation identity remain live observations to bind.

Optional partial-sum scratch `0x18dcf38` is allocated as128 MiB at
`0x176e454..0x176e465` only after its preceding capability check. The source
does not prove the current buffer is populated. Do not allocate or enable it
merely to expand this experiment.

## Complete native pipeline

`0x18092f0` launches the initial original input rotation:

```text
k_ht_rot_rows_h(X, D.signs, rotated_X, M, K)
```

Argument assembly is `0x18093b4..0x1809444`; registration identity is
`0x18d6248`. The source grid for this shape is20480x1x1, block256x1x1.

The native multiply's nine arguments are assembled at
`0x180968f..0x1809764` (or the corresponding mode4 branch):

```text
(packed, rotated_X, M, K, N, K_blocks_per_split,
 output_scales, Y, optional_FP32_partials)
```

For this shape, K_blocks=20, base tile count=
`ceil(M/64)*ceil(N/128)=128*80=10240`. The target getter
`0x180cdc0` defaults80 and admits values1..4096. Every admitted target is
below10240, so split count is1 and K_blocks_per_split is20. Consequently
the source skips the sum launch, independent of optional partial scratch.
Record actual controls rather than silently changing them.

The second threshold getter `0x180ce00` defaults256. With that default,
M8192 and even `N/128=80` take the large-row branch:
`0x1809633 ->0x180c980` for mode3, otherwise
`0x180991c ->0x180ca60`. These wrappers launch registered
`k_ht_tg3<3>` / `k_ht_tg3<4>` (identities `0x18d6250/0x18d6258`),
grid64x40x1, block512x1x1. A changed threshold can instead select
`k_ht_tg<3>/<4>` with grid128x80x1 and block256x1x1.
These are source registrations, not a current observed dispatch or shader patch.

If a later distinct shape genuinely uses split>=2, the source sum arguments
at `0x1809980..0x1809a4d` are
`(FP32_partials, split_count, output_scales, Y, M, N)`.
The frozen8192/10240/2560 experiment needs no added sum case: replay the
source's actual unsplit pipeline and include all work inside its multiply.

## Minimal root-owned capture and replay

1. Use the existing normal lifecycle and a default-off version-pinned preload
   hook at `0x17f8280`. On exactly one original ordinary QKV call, require the
   shape, `output_float32=0`, expected ordinary caller lineage and descriptor
   fields above. Establish the executable base/hash and complete hook bytes
   before entering; keep the original call result and Y untouched.
2. Record the descriptor, selected tensor metadata, current scratch allocations,
   router identity, library handle/stream, algorithm bytes/identity and native
   control values. Copy just the bounded packed tensor, sign/scale vectors and
   X using HIP on their owning stream. Save the completed original Y as the
   reference. Capturing a direct `0x17f8696` path proves that stock reference;
   a transformed or cache path must be recorded as such, not relabelled.
3. In the same exclusive owned process, give replay its own frozen X, packed
   tensor, vectors and Y, plus a shallow descriptor with only required pointers
   rebound. Reuse initialized original registration/router state. Stock invokes
   `prepare_original` and `matmul`; native invokes `native_ht` directly with
   the frozen arguments. Neither invokes another model engine or changes the
   server's general threshold or KEEP_TRUNK policy.
4. Compare completed raw Y against the saved original Y. Preserve any already
   declared QKV tolerance verbatim. No QKV tolerance is established by this
   source note: do not borrow the MTP FC tolerances or widen a tolerance to pass.
   Record exact word mismatches and numerical errors; exact output preservation
   is the strict default until root identifies an existing boundary contract.
5. Use a short excluded warmup and a fixed alternating paired schedule to avoid
   the order bias exposed by earlier screens. Time complete stock preparation
   plus matmul against native rotation plus multiply and required completion.
   Record total CPU submission-to-completion wall as well as GPU events. Only
   use one stream's event interval when all actual operations share that stream;
   otherwise a full completion boundary is required. Capture/file transfer and
   numerical comparison remain outside the timed interval. Reject partial
   multiplication-only timing.

The capture fixture is the reusable result; no benchmark loop is justified
without its missing packed-format/allocation, current route/algorithm, actual
stream and initialized-router bindings. Root's existing reserves, exclusive
ownership and final original-server ready/open requirement still apply.

GPU offers the concrete existing packed pipeline. CPU supports capture metadata
and correctness review. NPU has no qualified packed-HT or GPU-buffer interface
for this boundary and should not be inserted into this screen. A component
improvement is not Prefill tok/s: only a later qualified engine cohort could
measure Prefill, Decode and native acceptance separately. No new throughput
or acceptance result is claimed here.
