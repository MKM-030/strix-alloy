# Exact GU64/DN64 activation bounds

Finite source-only tightening,2026-10-09. Valid positive item rows<=64, native block256, GU P slots0..81919, item sorted intervals contained in0..81919. The stock native64 family exists in the unchanged0.17.2/0.17.3 GPU object. These64-row kernels need **zero activation prefix or suffix padding**. The earlier[-8,L+512) envelope remains an intentionally conservative synthetic-fixture bound; it is not a required real-model allocation extent or an admission condition.

Each initial activation address has masked in-row coordinate `m=(8*t)&0x78=8*(t&15)` BF16 words, m0..120, followed by a16-byte load. GU source row is token `floor(P[start+min(local_row,rows-1)]/10)` in0..8191; DN source row is `start+min(local_row,rows-1)` in0..81919. GU row2560words and DN row640words are multiples128words, so their OR with m is exactly addition, with no carry or hidden stride.

Every actual vector read is therefore:

`X + row_bytes*valid_row + 256*g + 2*m + [0,16)`.

Here g0..19 GU and0..4 DN. Initial reads have g0. The last physical read ends at row_start+256*(G-1)+240+16=row_start+256*G. Thus GU reads are exactly bounded by[0,41943040) and DN reads by[0,104857600), without under-read or over-read. All activation instructions in these two kernels have immediate offset0; negative-offset staging belongs to native128 only.

## All row-specialized classes

|Kernel / row groups|Mask PC|Initial activation load PCs|Reload activation load PCs|
|---|---|---|---|
|GU64 /4|e01270|e01484,e0148c,e014bc,e014c4|e01878,e01880,e018b0,e018b8|
|GU64 /3|e037d4|e038e8,e03934,e0393c|e03c7c,e03cac,e03cb4|
|GU64 /2|e0978c|e09828,e0986c|e09b20,e09b28|
|GU64 /1|e0df4c|e0e048|e0e2a4|
|DN64 /4|e163d4|e1655c,e16564,e16594,e1659c|e16998,e169a0,e169d0,e169d8|
|DN64 /3|e194b0|e195e4,e19630,e19638|e199cc,e199fc,e19a04|
|DN64 /2|e1c078|e1c118,e1c160|e1c468,e1c470|
|DN64 /1|e1e61c|e1e6bc|e1e968|

The normal4/3/2 classes form reload byte displacement `next_group<<8` at GU e01848/e03c64/e09af0 and DN e16968/e199b4/e1c438. Before reloads, their G exit and G-1 no-prefetch predicates are:

|Kernel / class|G comparison|G-1 comparison|Branch skipping all activation reloads|
|---|---|---|---|
|GU64 /4|e017a4:20|e017c4/e017cc:19|e01844|
|GU64 /3|e03bc0:20|e03be0/e03be8:19|e03c60|
|GU64 /2|e09a4c:20|e09a6c/e09a74:19|e09aec|
|DN64 /4|e168c4:5|e168e4/e168ec:4|e16964|
|DN64 /3|e19910:5|e19930/e19938:4|e199b0|
|DN64 /2|e1c394:5|e1c3b4/e1c3bc:4|e1c434|

The G-1 select produces0; `s_and_not1_b32 vcc_lo,exec_lo,predicate` then makes vcc nonzero and branches past every activation reload. For earlier groups it selects-1, vcc becomes0 and the next-group reload executes. No groupG physical activation read occurs.

The one-group class initially saves activation pointer+256 (GU e0e120, DN e1e78c), then increments it by256 per iteration (GU e0e1c0, DN e1e878). The initial loop entry bypasses the increment. Counter64*g exits at GU1280 (e0e22c/e0e240) or DN320 (e1e8f0/e1e904). Counter64*(G-1) sets the no-prefetch predicate at GU1216 (e0e244/e0e24c) or DN256 (e1e908/e1e910); branches e0e2a0/e1e964 bypass the activation load. The saved pointer would reach row_start+256*G on the final step, but it is never physically dereferenced there. Actual reloads are groups1..G-1.

GU row-clamp anchors include e011b4/e011d4/e011d8/e011e4 (4groups), e036cc/e036e8/e036ec (3), e0968c/e096a8 (2), e0df28 (1). DN anchors include e163d0/e163dc/e163e0/e163e4 (4), e194a0/e194c8/e194e8 (3), e1c02c/e1c03c (2), e1e5f4 (1; min3 also caps15). The pointer formation is through Args+0x70, not an expert-dependent activation base. GU P reads are4bytes within327680bytes. This certificate needs no actual-model allocation capture and no universal arithmetic-equivalence proof.
