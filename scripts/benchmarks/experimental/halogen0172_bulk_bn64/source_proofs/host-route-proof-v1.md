# Host route ownership certificate v1, 2026-10-09

Status: the native mode1 item, permutation and bulk-fold association is statically coherent for BN128 -> BN64 at N8192. Synthetic fixture memory bounds are closed: GU metadata2560/1280bytes across92 triples, exact packed/scale blob minima, and activation reads contained by4096-byte initialized prefix/suffix guards. Rotation is omitted; identical pretransformed input is outside both timings. The root-owned component must compare every GU/DN/fold word bitwise and remain disabled on any difference. This source-only certificate does not assert universal arithmetic equality or actual-model allocation receipts. No hardware, build, inference, lifecycle, STATE, Git or public-file work was performed here.

## Pins and retained evidence

The engine is `runtime-inventory/static-audit-data/usr/local/bin/flash_serve.data`, SHA256 `ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913`. Device ELF is `gpu-moe-compute-20261008/bundle0-gfx1151-code-object.data`, SHA256 `18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039`. Decoder is the pinned `llvm-objdump.exe` at `C:/AI/sdk/therock1151-10.2.0a20260930/lib/llvm/bin/`, SHA256 `f51d8a61cd527b24eb33e844050755886e6a0556499df89e928675ce3105a2c2`.

New `host-route-proof-v1.host.txt` retains sorting helper 0x17d4bb0..0x17d5050. New `host-route-proof-v1.device.txt` retains items64/items128, route hist/scan/scatter and the actual eight-argument BF16-source bulk fold. Existing `host-retile-lifecycle.txt`, GU64/DN64 disassemblies, native128 GU/DN disassemblies, embedded kernel inventory and descriptor registration map supply the other cited addresses. The final manifest pins these files without changing them.

Host registration 0x186cac1/0x186caef/0x186cb1d resolves descriptors 0x18f57c8/0x18f57d0/0x18f57d8 to `k_route_hist`, `k_route_scan`, `k_route_scatter`. Bulk fold descriptor 0x18f4370 resolves at 0x186cb4b to `k_i4r_fold_rows` (device 0x236600, size0x958). Initial transform descriptor 0x18f4368 resolves at0x186ca93 to `k_ht_rot_rows`.

## Definitions and sorter contract

N=8192; original route-slot count R=10*N=81920. Original slot s=10*n+j, n in [0,N), j in [0,10). Expert ID E[s] is an int32 in [0,512). The expert domain is checked explicitly by unsigned comparison with0x200 in both histogram and scatter, including device0x255718 and0x256a88. The number512 is therefore not inferred from spare item capacity. Invalid IDs are excluded by the sorter; item thread0 traps unless the sorter counted all R slots (items64 0xe00234..0xe00248; items128 analogous). A valid complete-operation fixture must preserve all R original valid slots.

Let r_e=count{s:E[s]=e}, sum_e r_e=R. Let p_e=sum_{f<e}r_f. Hist processes blocks of1024 original slots, records the block's512 expert counts and each original slot's local rank among earlier same-expert slots in that block. Hist atomic adds only count totals (0x255868..0x2558c8); local ranks are produced by explicit previous-ID comparisons (0x255a70..0x255d68 and same-four-slot corrections), rather than by the atomic return order. Scan sums the per-block histograms and performs inclusive LDS scans over positive-count flags and counts, forming a compact ascending active-expert list and its exclusive row-prefix array; it then replaces block histogram counts with expert global-row bases plus earlier-block counts.

Scatter uses q=block_base_for_E[s]+local_rank[s]. Its paired stores at0x256b18/0x256b20 (and repeated offsets4/8/12) write forward permutation P[q]=s and inverse permutation I[s]=q. This gives I[P[q]]=q and P[I[s]]=s; the expert's sorted ranks are exactly [p_e,p_e+r_e). Neither P nor I depends on BN.

The five sorter result pointers and owned payloads are:

| Struct offset | Meaning | Bytes at R81920 |
|---|---|---:|
|0x00|active expert IDs, capacity512 int32|2048|
|0x08|active exclusive sorted-row prefixes, capacity513 int32|2052|
|0x10|P, sorted rank -> original route slot|327680|
|0x18|I, original route slot -> sorted rank|327680|
|0x20|raw512 expert counts, active count at+0x800, total valid slots at+0x804|2056|

Additional sorter scratch is80*512*4=163840 bytes for block histograms and4R=327680 bytes for local slot ranks. Total payload1153036 bytes. At an aligned input cursor, the exact sorter allocations advance1153536 bytes (500 bytes padding). All original arena bounds/highwater updates and fatal branch0x17d504a must remain.

## Item certificate and count guards

The item kernels have56-byte kernargs: active IDs pointer0, compact row-prefix pointer8, raw counts/bookkeeping pointer16, R int32 at24, GU items pointer32, DN items pointer40, two-count pointer48. Both use grid1/block512, wave32 and2048-byte fixed LDS.

For B in{64,128}, define a_e=ceil(r_e/B), S_B=sum_e a_e, A_e=sum_{f<e}a_f. For each active expert and tile u in[0,a_e), the kernel writes the16-byte Item=(e,output_tile,p_e+B*u,min(B,r_e-B*u)). Its GU item index is5*(A_e+u)+h for h0..4. Its DN item index is10*(A_e+u)+h for h0..9. The address multipliers80/160 are visible at0xe00710/0xe00720, row increment64 at0xe007f0, and128 analogues at0xe00e14 onward. Inclusive LDS scan is over a_e, not r_e; thread511 reads byte2044 and writes the int32 pair (5*S_B,10*S_B) at0xe008ac..0xe008dc and0xe00fbc..0xe00fec.

The host reserves C_B=floor(R/B)+512, so C128=1152 and C64=1792. For valid counts, S_B<=floor(R/B)+512 because each nonempty expert adds less than1 above r_e/B. The tighter unconstrained histogram maxima for this divisible R are S128<=1148 and S64<=1784; native capacity intentionally retains the larger safe bound. Actual S_B is unknown without a retained route histogram. Do not equate capacity with executed projection items.

Host GU launch bound5*C is5760 ->8960; DN bound10*C is11520 ->17920. Every projection first loads its int32 count from Args+0x88 and returns when blockIdx>=count before reading an item (GU64 0xe01100..0xe01140; DN64 0xe16300..0xe16340; native128 analogous). Therefore live GU/DN item counts are5*S_B/10*S_B. GU consumes counts pointer; DN consumes counts+4.

Each expert's intervals [p_e+B*u,p_e+B*u+rows) are disjoint and partition [p_e,p_e+r_e). Retiling changes interval boundaries and replicated output-tile item ownership but leaves every sorted row's expert and P association unchanged. Since64 and128 are multiples16, sum_u ceil(rows_u/16)=ceil(r_e/16) for either B. GU64 computes g=ceil(rows/16) at0xe01168..0xe01170 and dispatches g1..4; DN64 at0xe16368..0xe1638c similarly, DN128 at0xe71b68..0xe71b94 dispatches g1..8. Logical row16 fragments remain constant; weight/dequantization and submission work can rise with S_B. This is static shape/branch evidence, not a measured cost claim.

## Projection row coordinates and preserved ABI

GU uses152-byte by-value Args with transformed input pointer at+0x70, P at+0x78, GU items at+0x80, GU count at+0x88 and dense GU output at+0x90. Original P[q] is a route slot; the input token is floor(P[q]/10), explicitly using signed magic divide10 and input stride2560 at GU64 0xe01348..0xe013f4. Dense GU rows use640 BF16 words per sorted row. DN Args input+0x70 is this dense GU array, permutation+0x78 is0, item+0x80 is the DN list, count+0x88 is counts+4 and output+0x90 is dense DN. DN uses640 reduction words and2560 output words per sorted row.

The unchanged Args scalar prefix is: pointer+0x00; zero byte offset+0x08; scale-plane byte offset+0x10 (GU0x32000000, DN0x19000000); scale-row byte stride+0x18 (GU40, DN10); four inline16-byte native constant vectors+0x20..0x5f. The integers at+0x10 are byte offsets into the packed blob, not dimension pairs. GU metadata pointers+0x60/+0x68, DN metadata+0x60 and zero+0x68 remain original. Preserve all fields, layer pointers, stream0 and output flag1.

For a DN item (e,h,start,rows), t in[0,256), row group a in[0,ceil(rows/16)), two b128 stores address:

`out + 5120*(start+(t&15)+16*a) + 2*(256*h+(t&0xe0)) + 16*((t>>4)&1) + 32*z`, z in{0,1}.

Each stores8 BF16 words, with predicates suppressing rows>=rows. For fixed row t&15, write u=t>>4, b=floor(u/2) in0..7 and parity=u&1. Channel ownership is256*h+32*b+8*parity+16*z+w, w0..7. The tuple(b,parity,z,w) covers0..255 exactly once; row-group predicates cover each valid item row once. This is dense row-major DN output, not a split-K FP32 partial array. The split2 name does not permit a different fold ABI. Full fragment arithmetic and epilogue association are supplied by the separate GU/DN coordinate audit; this route certificate alone does not establish bitwise projection equality.

## Eight-argument native bulk fold certificate

The flag1 branch at host0x17d2002 launches descriptor0x18f4370 at0x17d2277, gridceil(20*N/8)=20480, block256, stream0. Its kernarg size is64 bytes:

|Offset|Original binding|Address-derived extent|
|---|---|---:|
|0|dense DN BF16 rows|R*2560*2=419430400|
|8|I from sorter result+0x18|4R=327680|
|16|N int32|4|
|24|route weights, global0x18f9f60|4R=327680|
|32|layer metadata, original stack+0x78, FP16 channel operand|2560*2=5120|
|40|global0x18f9f30, BF16 token-row operand|N*2560*2=41943040|
|48|global0x18f9f50, FP32 token scalar operand|4N=32768|
|56|model output object+0x910, BF16 token rows|N*2560*2=41943040|

For local t, fold work group q=8*blockIdx+(t>>5), lane=t&31. Entry guard q<20*N (0x236610..0x236630), token n=floor(q/20) (magic divide at0x236634..0x236670), channel base c=128*(q%20)+4*lane. For each j0..9, it loads I[10*n+j] and route_weight[10*n+j], then4 BF16 DN words at dense offset5120*I[10*n+j]+2*c. Explicit unrolled inverse loads are offsets0,4,...36 at0x2366cc..0x236a18; matching weights use0..36 at0x236720..0x236a38. Native scalar FP32 multiplications and additions retain j order0..9. This is exact original route-slot association, independent of item BN.

After slot summation the native fold performs its unchanged lane transform, FP16 channel operand, explicit BF16 rounding, token scalar/residual operation and final BF16 store. Preserve the kernel and all operands: bitwise DN identity plus identical I, weights and remaining operands makes final output identity deterministic without reimplementing these steps. The final b64 store at0x236f4c writes token n/channel c..c+3; the guarded work groups cover each N*2560 output word exactly once.

## Fixture memory and readiness boundary

Known native payloads: transformed input40MiB; dense GU100MiB; dense DN400MiB; sorter payload1153036 bytes (aligned advance1153536); GU/DN items total276480 bytes BN128 or430080 BN64; counts8 bytes. At N8192 the item allocations are exact multiples256, counts occupy the next8 bytes and dense DN begins256 bytes after item end. The initial-transform+sort+items/count-padding+DN native arena advance is462803712 bytes BN128 or462957312 BN64, a precise153600-byte increase. Global GU dense allocation is separate and must retain its original binding.

Packed projection addressing gives minimum full-domain GU blob data0x32000000=800MiB and scale plane512*1280*40=25MiB; DN data0x19000000=400MiB and scale plane512*2560*10=12.5MiB. GU flattens expert*1280+weight-output channel then multiplies by1280 packed bytes at0xe012f4/0xe01300 and scale stride40 at0xe01314. DN flattens expert*2560+channel, multiplies by320 packed bytes at0xe16474/0xe1649c and scale stride10 at0xe164b8. A64-byte packed K128 group has one16-bit scale (GU0xe014b0, DN0xe16588); the loop advances64 packed bytes/2 scale bytes. Thus scale groups are K128,20GU/5DN. These are minimum addressable extents, not a recorded native allocation size. Preserve the blob and native inline codebook constants.

A sequential paired complete-operation fixture can reuse input/weights/sort scratch/GU scratch and a BN64-capacity item allocation. Comparing every GU, DN and final fold word needs retained BN128 references100+400+40=540MiB (unless retained on host with equivalent transfer outside the timed operation). Both runs include native item generation, GU, DN and bulk fold at N8192 with valid routes; initialize all inputs once and bind identical residual operands. Omit rotation entirely and supply identical pretransformed synthetic input outside both timings. Sorting may be outside both boundaries or included identically. Routing work must have the same timing treatment in both variants.

An actual-model fixture additionally needs actual tensor binding receipts, original routing state and verified arena capacity/aliasing. The isolated synthetic paired component has finite sufficient read bounds in `host-route-proof-v1.fixture-abi.md`, `host-route-proof-v1.weight-bounds.md`, `host-route-proof-v1.metadata-bounds.json` and `host-route-proof-v1.activation-bounds.md`. Fully initialized identical synthetic operands and4096-byte tensor guards are sufficient for memory safety under the valid-route contract; arithmetic is checked by every-word paired comparison. No tolerance relaxation, N substitution, mode2 threshold patch or FP32 small-row fold is compatible with this certificate. There is no discovered host route-slot mismatch.
