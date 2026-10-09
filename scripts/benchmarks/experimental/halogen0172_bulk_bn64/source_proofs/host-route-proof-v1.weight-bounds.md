# Native mode1 packed weight and scale read bounds

Source-only audit, 2026-10-09. Applies to the four pinned native GU/DN kernels with the unchanged 152-byte Args, valid item expert in [0,511], GU tile in [0,4], DN tile in [0,9], block width256 and positive item rows at most BN. No runtime, hardware, build or numerical-equivalence claim is made.

The address-derived synthetic minimum allocation is **865075200 bytes for the contiguous GU blob** and **432537600 bytes for the contiguous DN blob**. Packed weight and FP16 scale accesses require **zero additional prefix or suffix padding**. These are bounds for synthetic allocations with the pinned offsets; they do not prove the capacities of actual model allocations.

## Flattened weight row

Let t be native thread index, 0<=t<256, e item.expert, j item.output_tile. Every row-count branch has the same weight-row address construction, with register renaming only.

GU uses

`q = 1280*e + 128*j + 16*(t>>5) + (t&15) + 640*((t>>4)&1)`.

The disassembly forms bit4's 640 choice with compare/cndmask, ORs that with `16*(t>>5)` and `t&15`, adds `j<<7`, then adds `1280*e`. The OR operands occupy disjoint set bits over their valid domains. Thus `0<=q<512*1280=655360`. GU's two halves are separate output-weight rows, not a pointer increment past a row.

DN uses

`q = 2560*e + 256*j + (t&0xe0) + 16*((t>>4)&1) + (t&15)`

`=2560*e+256*j+t`, so `0<=q<512*2560=1310720`. The native DN split2 branch retains this same weight-row formula.

These are independent of ordered-row start and row count. Row-count branches change activation/LDS staging and accumulator shape; they do not widen the weight-row coordinate domain.

## Physical packed and scale accesses

With W=Args+0x00, packed offset Args+0x08=0, scale offset O=Args+0x10, scale-row byte stride S=Args+0x18:

|Projection|Packed row stride P|K128 groups G|Scale offset O|Scale stride S|
|---|---:|---:|---:|---:|
|GU|1280|20|838860800 (0x32000000)|40|
|DN|320|5|419430400 (0x19000000)|10|

For group g in [0,G-1], the packed reads cover `W+P*q+64*g+[0,64)`: four 16-byte global loads, at offsets0,16,32,48. The scale read is exactly two bytes at `W+O+S*q+2*g`. Initial scale loads are `global_load_d16_b16`; loop reloads are `global_load_u16`. Neither reads a 4-byte or vector scale word.

Consequently packed reads stay in `[W,W+512*rows_per_expert*P)`, and scale reads stay in `[W+O,W+O+512*rows_per_expert*S)`. The maximum end, exclusive, is:

|Projection|Packed end|Scale end / blob end|
|---|---:|---:|
|GU|838860800|865075200|
|DN|419430400|432537600|

The endpoints are attainable for the final expert/tile/thread/group, so the minima are exact over valid item domains. Their combined payload is1297612800 bytes =1237.5MiB.

## K-loop tail guards and branch coverage

For normal row branches the pipeline loads group0 first. It exits at counter G and tests the preceding counter against G-1 before the next packed/scale load. The next packed pointer is base+64*(preceding_counter+1); the next scale pointer is base+2*preceding_counter with load offset2. The G-1 branch bypasses all five reloads. Therefore there is no eager packed group G or scale index G read.

For the smallest row branches the byte counter increases by64. Counter P exits; counter P-64 bypasses the four packed loads whose offsets are64,80,96,112 and the next two-byte scale load. For a taken load path the byte counter is at most P-128, and its largest physical end is `(P-128)+112+16=P`. The scale pointer advances by2 per group and the final scale reload is bypassed by the same guard. This alternate loop also requires no padding.

The following anchors cover all initial scale-load/weight-address branches, not just the full-row case. Each normal branch has the stated G / G-1 pair; each smallest branch has P / P-64.

|Kernel|Initial scale loads, native addresses|Loop-end anchors|
|---|---|---|
|GU64|e014b0, e03928, e09864, e0e088|e017a4, e03bc0, e09a4c:20/19; e0e22c/e0e244:0x500/0x4c0|
|GU128|e313b8, e341bc, e3fc0c, e49ec8, e52b90, e59fa0, e5fdf0, e64590|e317ac, e345b8, e3ffcc, e4a244, e52e4c, e5a220:20/19; e60078/e60090 and e647d8/e647f0:0x500/0x4c0|
|DN64|e16588, e19624, e1c158, e1e6f0|e168c4, e19910, e1c394:5/4; e1e8f0/e1e908:0x140/0x100|
|DN128|e71d28, e76408, e7a5b0, e7e138, e817dc, e84710, e87174, e8969c|e72140, e767dc, e7a9b4, e7e4f8, e81ae4, e849d8:5/4; e8744c/e87464 and e89934/e8994c:0x140/0x100|

Example complete normal guard/load sites: GU64 e017a4..e01830, GU128 e317ac..e31850, DN64 e168c4..e16950, DN128 e72140..e721c4. Example smallest guard/load sites: GU64 e0e22c..e0e294, GU128 e60078..e600d0, DN64 e1e8f0..e1e958, DN128 e89934..e8998c. The count-pointer guard at each kernel entry suppresses all accesses for grid blocks beyond the emitted item count.

## Evidence and remaining scope

Read the parent GU coordinate analyzer `gu-coordinate-proof-v1.epilogue-base.py` and audited these pinned disassemblies: `gu-bn64.device-disassembly.txt`, `dn-bn64.device-disassembly.txt`, and the native128 `q4moe-mode1-gu-bn128.device-disassembly.txt` / `q4moe-mode1-dn-bn128.device-disassembly.txt` in `gpu-moe-compute-20261008`. Weight-row formulas were checked at every initial scale-load class; corresponding K-tail guards were checked in every class.

This closes **packed weight and scale** padding only. Activation vector loads, including native128 offsets such as-8, GU gate/normalization metadata, rotation metadata, output ownership and arithmetic correspondence retain their own separate certificates. Do not use this note to infer their allocation padding or numeric equality.
