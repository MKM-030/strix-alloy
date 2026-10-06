# Original-weight preparation thread decomposition, 6 October 2026

One independent, bounded GPU candidate remains: use the already compiled
`k_ht_deq_orig<4,true,8>` sibling for the original BF16 weight preparation,
then execute the unchanged stock BF16 GEMM. This changes the preparation
block from512 to256 threads. It does not retain a weight cache or substitute
the retired packed native HT multiplication. No hardware, engine, WSL,
provider or process-lifecycle operation was performed in this audit.

This is a **candidate**, not a proved exact or faster implementation. The
available decoder does not fully decode the retained shader, so static
arithmetic equivalence cannot be claimed. A complete prepared-W byte
comparison is necessary before any timed comparison. If that comparison
fails, retire this variant at the existing exactness boundary.

## Source and current-call binding

The local pristine executable is
`backends/halogen-wsl2-0.16.2/.local/flash_serve`, SHA256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
The retained host-text SHA256 is
`523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`.
The retained `mtp-route-static-20261004/engine-gfx1151.hsaco` SHA256 is
`45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83`;
its ELF machine flag is `EF_AMDGPU_MACH_AMDGCN_GFX1151` (`0x4a`).

The [completed capture](halogen-prefill-ht-stock-route-20261006.md) binds the
ordinary layer0 QKV to descriptor mode4, `M8192/N10240/K2560`, one original
preparation launch returning to`0x17ecd6a`, grid`(20,80,1)`,
block`(512,1,1)`, launch shared-memory argument0 and stream0. It then binds
prepared W and original X to the stock BF16 GEMM. The same captured packed,
signs, scales, X and Y are applicable to this alternate preparation; no new
model payload or broad route capture is needed.

Original helper`0x17ec6e0` has API
`prepare(packed, mode, N, K, signs, scales, W)`. In mode4, with the existing
PRE=true default, it selects the following registered shader:

| Preparation | Host registration RVA | Registration call RVA | Device symbol extent |
|---|---:|---:|---|
| Default W16=true | `0x18d5c20` | `0x184870c` | `[0x498b00,0x49bb0c)` |
| Candidate W16=false | `0x18d5c30` | `0x1848768` | `[0x49da00,0x4a2984)` |

Both function names are global/protected exports in the original code object.
Their64-byte `.kd` descriptors are global exports at`0x1fd800` and
`0x1fd880`, respectively. The exact function sizes are12,300 and20,356 bytes.

Names are, respectively,
`_ZN7halogen12_GLOBAL__N_113k_ht_deq_origILi4ELb1ELi16EEEvPKjiPKDF16_S5_Pti`
and
`_ZN7halogen12_GLOBAL__N_113k_ht_deq_origILi4ELb1ELi8EEEvPKjiPKDF16_S5_Pti`.

Both use six kernel arguments: offset0 packed pointer; offset8 K/int32;
offset16 signs pointer; offset24 scales pointer; offset32 W pointer;
offset40 KFAST/int32. Kernarg size is44 bytes/alignment8. With KFAST=1 the
grid is`ceil(K/128)` by`ceil(N/128)`, giving20 by80. The W16 flag changes
the block size only: default512, candidate256. Both branches use the same
grid, argument inventory, zero dynamic shared-memory argument and default
stream, and converge on the original checked launch/error path at
`0x17ecd58..0x17ecd75`.

## Exact native control semantics

These are lazy getters inside the preparation helper, not independent
getter functions. The guard APIs initialize their retained values once.
Absent controls default to1. A present value is disabled exactly when its
first byte isASCII `0`; other strings, including an empty string, select1.
An experiment interface should accept only explicit integers0/1.

| Control | String RVA | getenv call | Retained value | Init guard |
|---|---:|---:|---:|---:|
| `HALOGEN_HT_DEQ_KFAST` | `0x16971` | `0x17ecdb2` | DWORD`0x18dcf70` | `0x18dcf78` |
| `HALOGEN_HT_DEQ_PRE` | `0x1e1d2` | `0x17ecdf2` | BYTE`0x18dcf80` | `0x18dcf88` |
| `HALOGEN_HT_DEQ_W16` | `0x4475f` | `0x17ece30` | BYTE`0x18dcf90` | `0x18dcf98` |

W16 is read at`0x17ec788`; mode4 tests it at`0x17ec871`. True reaches
the512-thread launch configuration at`0x17ec879..0x17ec890` and PRE=true
registration selection at`0x17ec937`. False reaches the256-thread
configuration at`0x17eca06..0x17eca16` and PRE=true registration selection
at`0x17ecabd`. **Keep KFAST/PRE at1.** They are separate mechanisms and
are not part of this candidate.

`kernel_controls.py` does not currently admit any of these three names.
The previous documented kernel screen did not include them. The existing
matmul tuning object supplies ALGOS8 training or ALGOS1 frozen replay;
HGNTUNE3's ordinal/count fields do not expose Split-K or workgroup controls.
That defeated full-plan selection is not a rationale for another tuning run.

## Emitted cost and arithmetic limits

Metadata obtained from the two retained symbols gives:

| Property | Default512 threads | Candidate256 threads |
|---|---:|---:|
| Waves per block, wave32 | 16 | 8 |
| Static LDS bytes | 65536 | 65536 |
| VGPR count | 75 | 140 |
| SGPR count | 16 | 20 |
| VGPR/SGPR spills | 0/0 | 0/0 |
| Private fixed bytes | 0 | 0 |
| Decoded barrier sites | 4 | 4 |
| Decoded `ds_store_b32` sites | 128 | 192 |
| Decoded scalar/pair LDS-load sites | 96/16 | 128/32 |
| Decoded 16-bit global-store sites | 32 | 64 |

Each grid tile has128x128 output words; multiplying global-store sites by
block threads yields the same16,384 words. The candidate doubles work per
lane while halving waves and has a concrete prospect of reducing wave
setup and LDS exchange: the store-site count multiplied by waves is25%
lower. Counting pair loads as two values gives the same25% reduction for
LDS-load sites multiplied by waves. These are **static projections**; exec
masks and decoder gaps prevent converting them into actual memory traffic
or latency. The greater per-thread VGPR count and unchanged64KiB LDS can
offset the potential benefit. There is no justified performance prediction.

Both shaders remain original-weight dequantization with the same mode/PRE
template parameters and BF16 destination. Nevertheless, template names,
matching tile coverage and similar visible add/sub/multiply stages do not
prove the precise floating-point graph or rounding order. The installed
`llvm-objdump` leaves undecoded `.long` words and invalid-register annotations
for this retained object. Its SHA256 is
`abb4332b579bc183eed0843d6ac6cffcebf8879e300a55b3693394fed0580536`;
`llvm-readobj` SHA256 is
`0b3071d4f81e4c3c46d6a5f6752098eddd9e1476dfa4d1e88e0af84f0d34c71c`.
No static arithmetic-equivalence claim rests on those incomplete decodes.

The measured complete stock component was22.8911ms. The separately excluded
single original preparation was0.706895ms. That one-time number is not a
steady-state decomposition or upper bound, but even treating it as a budget
shows why this is a small component candidate:0.706895/22.8911 is3.088%.
The proposal keeps the same13,107,200 packed bytes and50MiB prepared W;
it neither removes that write nor reuses weights between calls.

## Bounded binding and qualification plan

Root can reuse the captured inputs and complete-path replay structure in
`scripts/benchmarks/halogen_prefill_ht/replay.c`; use a separate default-off
candidate and receipt. Preparation must execute on every timed call in
both arms. The already initialized router, actual M/N/K, BF16 GEMM wrapper
`0x18c6b80`, library selection and output/completion path stay identical.

For a same-process comparison, changing the environment after a stock
preparation cannot switch a lazy getter. Do not write the engine control
globals. A narrow candidate can instead launch the already registered
`base+0x18d5c30` with the six bound arguments and256 threads. The existing
capture source declares the matching public `hipLaunchKernel` ABI and
demonstrates the512-thread original launch. Runtime binding of the alternate
registration must be checked before relying on that direct launch.

Before timing, obtain the stock50MiB W, poison a separate50MiB candidate W,
perform the candidate preparation and full completion, and require equality
of **every prepared-W word**. Then require every finalY word to equal the
existing167,772,160-byte captured output at unchanged raw16-bit equality.
Those are qualification calls, excluded from timing. Failed prepared-W orY
qualification retires the candidate; no tolerance change or diagnostic
campaign follows.

If exactness passes, one bounded balanced complete-component comparison is
appropriate: two excluded warmup pairs and eight measured pairs, with
preparation, the unchanged GEMM, submission and completion in both arms.
Preserve all pairs and order/drift evidence. Reuse normal ownership,
reserve, cleanup and stock-restoration requirements. No serving benchmark
or general W16 environment override follows unless the complete component
shows useful savings. Production use would need an explicit validated
switch or a strictly scoped preparation substitution; none was implemented.

Root's first implementation is narrower: a standalone prepared-W oracle using
the single original HSACO twice, through the public HIP module API and these
exact exported symbols. It reads only the three pinned captured files
packed/signs/scales, uploads them once, allocates one own50MiB W, executes
one excluded512-thread original oracle and one256-thread exactness
qualification. A mismatch stops before timing. If exact, its fixed screen
has four excluded warmup pairs and sixteen balanced measured pairs; every
launch is single, followed by full completion and all50MiB raw-word
validation. Wall/event times cover preparation alone. They do not measure
the stock GEMM, whole Prefill, Decode or acceptance, and cannot select a
serving override. A preparation win would only make a later complete
prep-plus-same-GEMM comparison eligible. No cache/native HT cohort repeats.

GPU owns preparation and the original GEMM. CPU owns the immutable binding,
submission and full-byte checks. NPU provides neither this registered
dequantization consumer nor a compatible GPU LDS/weight-production seam;
its transport would add work, with no established benefit here. No new
Prefill tok/s, Decode tok/s or native accepted/drafted value was measured.
