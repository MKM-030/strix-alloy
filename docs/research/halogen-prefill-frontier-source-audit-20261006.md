# Prefill frontier source audit, 6 October 2026

No eligible unexecuted Prefill GPU/CPU mechanism was found in the requested
evidence and current isolated sources. The remaining full-path document is a
concrete implementation design, but its prerequisite was defeated. Building it
now would continue the same retired preparation candidate. This audit used
source and retained metadata only; it performed no hardware, engine, WSL or
lifecycle operation and changed no implementation.

The [full-path plan](halogen-prefill-deq-fullpath-plan-20261006.md) requires useful
original-W preparation savings. The [completed screen](halogen-prefill-deq-status-20261006.md)
found exact W16=0 output but no useful advantage: GPU paired mean delta
-5.214 microseconds, paired median +7.455 microseconds, wins 8/16 and order-dependent
host results. The [independent review](halogen-prefill-deq-independent-review-20261006.md)
explicitly makes the full-path plan ineligible. The earlier
[next-mechanism audit](halogen-next-prefill-mechanism-20261006.md) is therefore
superseded by that completed result.

| Mechanism | Existing implementation | Why it is closed |
|---|---|---|
| Packed native HT instead of original preparation/GEMM | `halogen_prefill_ht/replay.c`, `execute(NATIVE,...)` | 26,787,285 Y-word mismatches; retired before timing |
| Selected resident original 50 MiB W | Same source, `prepare_cached_once()` and `execute(CACHED,...)` | Complete component 23.2392 ms versus stock 22.8911 ms; 1.5208% higher mean latency |
| W16=0, 256-thread original preparation sibling | `halogen_prefill_deq/replay.c`, fixed loop in `main()` | Exactness passed, useful savings did not; same-GEMM follow-up remains unexecuted and ineligible |

These are separate mechanisms. Preparation-only exactness is not a complete
pipeline gain, and the cache's complete-path loss cannot be repaired by adding
independent preparation/GEMM times. CPU currently supplies submission, immutable
binding and checking; no bound CPU replacement with an expected advantage is
provided by these sources. Larger chunks were already defeated in the
[additional mechanism audit](halogen-next-mechanism-audit-20261006.md); the
[HGNTUNE3 audit](halogen-hgntune3-record-audit-20261006.md) preserves the rejected
trained-plan comparison and supplies no reason to repeat it.

The reusable full-path boundary is precise: original preparation
`base+0x17ec6e0(packed,4,10240,2560,signs,scales,W)` followed by original BF16
wrapper `base+0x18c6b80(router,W,X,Y,8192,10240,2560)`. Router global is
`0x18db4d8`; stock workspace is 128 MiB. The retired sibling is registered at
`base+0x18d5c30`, grid 20x80, block256, PRE1/KFAST1, six arguments and stream0.
These RVAs bind the plan's pristine `flash_serve` pin
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` and original
gfx1151 object `45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83`.
The plan binds captured X (40 MiB) to
`d42beb978ad9532b52d282738fe9fe1a01c1e075b0ac9217b8807ed759000668` and full Y
(160 MiB) to `d8bf83e883f3bddf62d5ee9a717d1dc10dc171c89cc22f6eda8f01a72385bec0`.
Its stock algorithm bytes remain unbound in the old capture; recreating a plan
ID or choosing a fresh standalone GEMM would not preserve that original call.

Current source pins verified in this audit:

- `halogen_prefill_ht/replay.c`: `63890d4da04b045e85bfba4ae93f46cc2be145616c991eae3bb5804fd97ada83`.
- `halogen_prefill_deq/replay.c`: `0fe60be21173d1f2395725da4ea83aa1210b5d492f3e871927b4e00941d89e5b`.
- Full-path plan: `f5157fe3941dd2d941b268c92a5795f8cb530e5d5f93356ddd6526f7e531e783`.

The `gpu-draft-snapshot` worktree has the identical preparation source and
full-path-plan hashes. Its separate MTP embedding cache gates
`valid_head_entry()` on `count==1`, so it is not an ordinary M8192 Prefill
replacement. The other listed worktrees supply older shape/cache scripts and
embedding-related sources, without a new bound original-QKV pipeline in the
inspected mechanism inventory. Continuation references the completed preparation
decision as `retired-no-useful-advantage` and the retained frontier triage as
`4ecb1eead563bb4f6ff73f8eec4e1e95b8ba3f46112fcce56107533d039c186d`.

There is no justified implementation action or expected speed benefit for these
closed paths. Preserve the existing frozen fixture and native wrapper for a
genuinely different future arithmetic/submission mechanism; do not build the
conditional W16 follow-up, add algorithm-witness-only work, or repeat unchanged
cohorts as acceleration work.
