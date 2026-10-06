# Conditional original-W preparation plus stock GEMM, 6 October 2026

This plan is eligible only if the released W16 preparation screen first
preserves every captured prepared-W word and shows useful complete preparation
savings. The screen's current source is unchanged at SHA256
`0fe60be21173d1f2395725da4ea83aa1210b5d492f3e871927b4e00941d89e5b`.
No result is assumed here. A failed or unhelpful preparation result closes this
candidate; it does not authorize a complete-path cohort.

The smallest comparison that preserves the **same stock GEMM** uses the
already initialized native router and its original BF16 wrapper in one
exclusive engine lifetime. Merely adding a newly chosen standalone
hipBLASLt algorithm to `halogen_prefill_deq/replay.c` would not establish that
binding. This audit prepared only this document: no existing screen, pins,
production files, hardware, runtime, WSL or lifecycle state were changed.

## Exact GEMM boundary

The [stock route](halogen-prefill-ht-stock-route-20261006.md) and retained
host disassembly bind the following chain:

`ordinary layer0 QKV -> original W preparation -> 0x18c6b80 -> 0x18c4f60`
`-> optional excluded selection 0x18c6290 -> 0x18c6850 -> hipblasLtMatmul`.

The native BF16 wrapper is a private executable function addressed by RVA,
not a discovered public GPU symbol in the original HSACO. Its ABI is:

```c
typedef void (*stock_bf16_mm_fn)(
    void *router, const void *W, const void *X, void *Y,
    int64_t M, int64_t N, int64_t K);
/* Call: mm(router, own_W, own_X, own_Y, 8192, 10240, 2560). */
```

| Binding | Identity |
|---|---|
| Pristine executable | SHA256 `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`, 26,052,768 bytes |
| BF16 wrapper | RVA extent `[0x18c6b80,0x18c6be6)`, file offset `0x18c5b80`, 102 bytes |
| BF16 wrapper bytes | SHA256 `6336433c1a337ff1faf7f72767ea869bfab343355ce74130226bd0ba76651a7d` |
| Dispatch helper | RVA `0x18c6850` |
| Imported GEMM call / return | `0x18c68e7` / `0x18c68ec` |
| Initialized router global | `0x18db4d8`, dereferenced once after ready and checked throughout |
| Router library handle / workspace / stream | Router offsets `+0x38 / +0x40 / +0x48` |
| Workspace passed by dispatch | 134,217,728 bytes / 128 MiB |
| Captured stream | Null/default stream |

The public imported symbol is `hipblasLtMatmul`. The existing capture uses
the following 16-argument C ABI, with status represented as an int:

```c
int hipblasLtMatmul(
    void *handle, void *desc, const void *alpha,
    const void *A, void *A_desc, const void *B, void *B_desc,
    const void *beta, const void *C, void *C_desc,
    void *D, void *D_desc, const void *algo,
    void *workspace, size_t workspace_bytes, void *stream);
```

Dispatch constructs FP32 scalar alpha=1 and beta=0 at
`0x18c6874..0x18c6883`; it passes W as A, X as B, and Y as both C and D.
The constructor's type 0 uses BF16 input and output storage. Its column-major
layouts are `A[K,N], ld=K`, `B[K,M], ld=K`, `C/D[N,M], ld=N`, with A transpose
and B nontranspose. This implements row-major `X[M,K] * W[N,K]^T -> Y[M,N]`.
The exact internal accumulation remains the original library choice; this
plan does not infer a new arithmetic specification from storage types.

## Why a fresh standalone choice is insufficient

The selected capture reports `algorithm_bytes=null` and
`algorithm_identity=null`. Its algorithm pointer was a transient stack copy,
not a reusable allocation. The dispatch copies 24 bytes of the selected
algorithm to that stack at `0x18c6895..0x18c68a1`.

The [HGNTUNE3 audit](halogen-hgntune3-record-audit-20261006.md) decodes a
shipped plan record with M-bucket 8192/N10240/K2560/type 0 and algorithm 817.
That file does not prove the selected live capture used 817, and its ID is
meaningful only within the matching loaded library identity. The rejected
trained plan's 819 is not an eligible substitute. Full Y equality is useful
arithmetic evidence but does not independently establish algorithm identity.

Therefore do not add `hipblasLtMatmulAlgoGetHeuristic`, new tuning, copied
opaque plan parameters, a reconstructed 817 choice or a replacement GPU
GEMM to the released standalone preparation worker. Its original HSACO
contains the dequantization kernels; it does not contain an established
public symbol for this library GEMM. The existing initialized native wrapper
is the available concrete seam.

## Frozen activation, complete oracle and minimum buffers

Use the same selected layer0 tensor and existing capture. No activation
generation, new shape, recapture, model read or tolerance change is needed.
The fixed descriptor remains store 16/variant 4616/mode 4, PRE=1/KFAST=1, and
the full projection remains M8192/N10240/K2560.

| Existing fixture | Bytes | SHA256 |
|---|---:|---|
| `packed.bin` | 13,107,200 | `d27fc76fab0646ba5b675f9dd9137c342a39f70aa980acf62f6959f5fdf0245d` |
| `signs-u16.bin` | 5,120 | `0866b9d9d28380f5f6ea3fdc0fa78a5643db9629c8a3e0094eb01f5b3e33cd7c` |
| `scales-u16.bin` | 20,480 | `dad8e70f72ce13f67692a184cac608e71986d740d43f72201ee52acc4146061e` |
| `x-u16.bin` | 41,943,040 / 40 MiB | `d42beb978ad9532b52d282738fe9fe1a01c1e075b0ac9217b8807ed759000668` |
| `y-reference-u16.bin` | 167,772,160 / 160 MiB | `d8bf83e883f3bddf62d5ee9a717d1dc10dc171c89cc22f6eda8f01a72385bec0` |
| `descriptor-before.bin` | 120 | `d2b1fc6537f1fd8e3761832a43f3fe2940d59863ef641d1007e484355880cb5c` |
| `records.json` | 3,508 | `c5e0d744f7160225921dfe163f01694ec33e4f12517c3fce81dff83cfa6dfe7b` |
| `complete.json` | 156 | `dd4aa107d90eb5b9ec1b9f4ea085f5bbc7fe2d9c2d178b4d112a36f8690df143` |

X is the captured normalized ordinary activation, not rotated scratch.
Its entire MxK BF16 content must remain fixed. The output oracle covers all
83,886,080 raw 16-bit Y words. The complete capture has already reported a
successful original library call with B=X and C=D=Y.

Reuse one own W between arms to keep the exact W pointer, alignment and
library inputs unchanged. Minimum device buffers are packed/signs/scales,
W 50 MiB, X 40 MiB and Y 160 MiB: 262.524414 MiB total, 200 MiB beyond the
released preparation worker. The router's 128 MiB workspace already exists
and must be included in ownership accounting, not newly allocated or
excluded from physical reserve.

Host staging with X, captured Y, Y readback, a released 50 MiB original-W
oracle and a 50 MiB W readback is 472.524414 MiB plus bounded metadata. Native
registered preparation launches avoid a second copied code object. The
standalone screen's two raw W files and validated result supply the
prepared-W release evidence; seal their actual result hashes if referenced.
Only one original-W oracle needs loading for the full-path checks.

## Smallest conditional implementation

Create a separate, default-off full-path component and receipt; leave the
released preparation source and pins untouched. The existing
`scripts/benchmarks/halogen_prefill_ht/replay.c` (SHA256
`63890d4da04b045e85bfba4ae93f46cc2be145616c991eae3bb5804fd97ada83`)
already supplies the no-hook post-ready worker, helper hashing, private
router binding, fixed X/Y loading, native wrapper ABI, full-output check and
normal cleanup structure. Reuse those bounded mechanisms without its
retired native-HT/cache arms or optional scratch requirements.

Only two arms are relevant:

```text
Original: original prepare helper -> original BF16 wrapper -> full completion
W16=0:   existing sibling prep launch -> same BF16 wrapper -> full completion
```

The original arm calls `base+0x17ec6e0` with
`(packed,4,10240,2560,signs,scales,W)`. The candidate uses the already
registered original shader at `base+0x18d5c30`, public `hipLaunchKernel`,
grid 20x80, block 256, dynamic shared 0, stream 0 and exactly six arguments:
`(packed,K=2560,signs,scales,W,KFAST=1)`. The stock launch is the sibling at
`base+0x18d5c20`, block 512. Both shaders remain PRE=true/mode 4. Preserve the
checked launch/error path and final full-device completion.

Do not set environment variables after lazy initialization or write engine
W16/PRE/KFAST globals. Verify that the original helper uses its accepted
default preparation before qualification. Restrict any observer to the
component worker; constructor remains hardware-inert and serving argv[1]
must be exactly `--ck`, as in the reviewed prior replay.

Both arms call the same `base+0x18c6b80` with the same router/W/X/Y pointers
and actual dimensions. Preparation executes on every timed call. **Do not
insert a synchronization or prepared-W readback between preparation and
GEMM inside the measured path.** Ordered default-stream submission supplies
the dependency; such an added boundary would change the complete workload.
W/Y poisoning and pre-start completion stay outside the timing bracket.

Use two excluded complete-path qualifications, then two excluded balanced
warmup pairs and eight balanced measured pairs: 22 complete pipelines total.
Each pipeline has one preparation and one original GEMM submission plus
full completion. Require every Y word to equal the fixed capture after
each completed call. Validate complete prepared W during qualification,
outside the timing bracket, against the released original-W oracle. Keep
distinct arm poisons. A mismatch or unexpected library dispatch retires
the candidate without further timing or diagnostic cohorts.

## Proving stable same-library execution

Selection is lazy: wrapper `0x18c6baf` compares plan+0x40 with plan+0x48.
Selection at `0x18c6290` copies the winning 24 algorithm bytes and sets
plan+0x48=plan+0x40 at `0x18c6674`. Exclude any first-call choice work;
do not change the stock tuning environment. Successful later calls with
the same router/key skip the selection path. Current source also has a
library-error fallback in the dispatch helper; a stable router alone does
not excuse a measured fallback or algorithm change.

A narrowly scoped witness of the public `hipblasLtMatmul` call can seal the
actual 24 algorithm bytes while the transient pointer is valid. The reviewed
capture's public ABI can be reused. Require exactly one successful primary
call returning to `0x18c68ec` per warmup/measured pipeline, and identical
algorithm-byte digest, handle, descriptors, workspace pointer/128 MiB size
and stream 0 across both arms. Require A=W, B=X, C=D=Y, alpha=1 and beta=0.
Any selection/fallback work remains excluded or causes qualification failure;
no alternate algorithm is promoted. Restrict this witness to a fixed number
of bytes/calls, without a new broad trace or shader-disassembly project.

This proves the limited same-lifetime component comparison. It does not
claim an algorithm identity shared with a different historical process.
If runtime/library identity is reported, pin the actually loaded library
files; the existing HIP SHA alone is not a hipBLASLt-library identity.

## Cost, decision and placement

Keep host submission-through-full-completion wall and the complete default-
stream event interval separately. The bracket includes preparation and
library submission/completion in both arms. It excludes all readback,
comparison, hashes, poisoning, file I/O and initial allocation/selection.
Do not time preparation and GEMM independently and add those intervals;
that would miss scheduling/cache interactions which already defeated the
selected original-W cache.

For 22 complete calls, mandatory Y readback validates 3,520 MiB outside the
brackets. Two qualification W checks add 100 MiB outside the brackets.
Uploads, the native engine's cold admission/startup, module/router
initialization, hashing and cleanup are separate costs. The root-owned
ordinary lifecycle/reserves remain unchanged. This is more expensive than
the no-model preparation worker and is conditional on its useful exact
result.

The historical complete stock mean 22.8911 ms and isolated excluded
preparation 0.706895 ms give context only. The latter was a single
excluded call; neither number predicts this candidate's complete return.
Report actual balanced complete-path differences with every retained pair,
hash and order group. A preparation-only win cannot overcome an unchanged
or slower complete-path result. No global W16 setting or serving comparison
is justified before a useful exact complete-component result.

| Processor | Placement and consequence |
|---|---|
| GPU | Original sibling preparation and identical original BF16 GEMM; only the thread decomposition changes |
| CPU | Submit both arms, retain immutable bindings and verify complete W/Y; no replacement arithmetic or speed claim |
| NPU | No qualified original-HT dequantizer, GPU publication contract or compatible complete GEMM consumer; producing 50 MiB prepared W would add transport without an established advantage |

No Prefill tok/s, Decode tok/s or native accepted/drafted improvement follows
from this plan or from an isolated preparation result. Those remain separate
later serving qualifications. Identical preparation and GEMM preserve the
chosen arithmetic; they do not independently improve proposal quality.
