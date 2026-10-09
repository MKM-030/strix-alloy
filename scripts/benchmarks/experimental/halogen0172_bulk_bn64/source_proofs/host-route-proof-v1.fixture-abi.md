# Standalone fixture ABI requirements, v1

**This file supplies the synthetic paired fixture ABI and finite memory bounds; it does not supply a runnable implementation.** The root-owned component may allocate synthetic payloads and4096-byte initialized prefix/suffix guards on tensors, initializing every read field identically for both variants. GU metadata footprints are closed across all92 static triples; activation reads fit within the guarded allocations. Actual model contents, native allocation receipts and universal arithmetic equality are not prerequisites. Rotation is omitted entirely: the same pretransformed synthetic BF16 input is supplied outside both timings. The component compares every GU, DN and final fold word bitwise and remains disabled on any difference.

## Complete152-byte projection aggregate

The original aggregate begins at host stack+0x80. Fields are identical between native64/native128 except item/count pointers and coherent host capacity. Values below preserve the original mode1/output-flag1 path. All pointer fields are8 bytes.

| Args byte offset / size | GU value and binding | DN split2 value and binding | Minimum extent / unresolved contents |
|---|---|---|---|
|0x00 /8|layer GU blob, original stack+0x130|layer DN blob, original stack+0x148|GU865075200 bytes; DN432537600 bytes; exact synthetic minima, zero packed/scale padding|
|0x08 /8|uint64 zero packed-data offset|uint64 zero packed-data offset|scalar fully pinned|
|0x10 /8|uint64 scale-plane byte offset0x32000000|uint64 offset0x19000000|scalar fully pinned; not dimension pairs|
|0x18 /8|uint64 scale-row byte stride40|uint64 stride10|20/5 FP16 scale values per weight-output row; K128 scale groups|
|0x20 /16|fourFP32 values[-8,-7,-6,-5]|same|engineRVA0x14710, exact bytes000000c10000e0c00000c0c00000a0c0|
|0x30 /16|fourFP32 values[-4,-3,-2,-1]|same|RVA0x13e30,000080c0000040c0000000c0000080bf|
|0x40 /16|fourFP32 values[0,1,2,3]|same|RVA0x14580,000000000000803f0000004000004040|
|0x50 /16|fourFP32 values[4,5,6,7]|same|RVA0x14650,000080400000a0400000c0400000e040|
|0x60 /8|layer+0x758 metadata pointer, original stack+0x140|layer+0x768 metadata pointer, original stack+0x78|GU2560bytes: two contiguous640-element FP16 planes. DN/fold channel operand2560FP16 values=5120bytes. Identical initialized synthetic values|
|0x68 /8|layer+0x760 metadata pointer, original stack+0x138|zero|GU1280bytes:640FP16 values, zero extra b64 padding; DN nullfullypinned|
|0x70 /8|original transformed BF16 input, saved stack+0x128|denseGU pointer, global0x18f9f38|GU8192*2560*2=41943040bytes; DN81920*640*2=104857600bytes|
|0x78 /8|P, sorter result+0x10, original stack+0x120|zero|GU81920int32=327680bytes; DN nullfullypinned|
|0x80 /8|GU Item list|DN Item list|BN1285*1152*16=92160 /10*1152*16=184320bytes; BN64143360 /286720bytes|
|0x88 /8|counts pointer|counts pointer+4|oneint32 each insideoriginal8byteallocation|
|0x90 /8|denseGU global0x18f9f38|denseDN arena pointer, original stack+0x38|GU104857600bytes; DN419430400bytes|

The four inline vectors are the exact signed-int4-to-FP32 codebook[-8..7], not an external buffer to rebuild or a quantization change. Raw constants were read through ELF64 PT_LOAD RVA-to-file-offset mapping (for these addresses fileoffset==RVA). GU channel/weight indices flatten expert*1280+channel; DN flattens expert*2560+channel. Blob scales are byte strides40/10, not40/10 separate16-bit elements. Preserve the original blob bytes. Native weightscale loads are16bits; paired packed weight loads cover64bytes perK128group.

## Complete64-byte fold aggregate

The same original values must be bound for both variants. No fold arithmetic replacement is part of the fixture.

| Offset / size | Original value | Pointee layout / content requirement |
|---|---|---|
|0 /8|denseDN arena BF16 pointer|R rows,2560 words/row,5120byte row stride; everyword comparedbitwise|
|8 /8|I, sorter result+0x18|R int32 values; I[s]=sortedrank; byte stride4|
|16 /4|8192|bytes20..23 are ABI alignment padding; original host packing preserved|
|24 /8|global0x18f9f60 routeweights|R FP32 values, byte stride4; preserve original weights and j0..9 order|
|32 /8|layer metadata original stack+0x78 (layer+0x768)|FP16 channel operand,2560 values, byte stride2; identical initialized synthetic contents and4096-byte guards|
|40 /8|global0x18f9f30|BF16 token-row operand, N*2560 values,5120byte rowstride; preserve originalcontents and aliasing|
|48 /8|global0x18f9f50|FP32 token scalar operand, N values, byte stride4; preserve originalcontents and aliasing|
|56 /8|model output object+0x910|N*2560 BF16 values,5120byte rowstride; retainBN128referencebeforecandidateoverwrites|

Fold argument32 is used by FP16 mixed FMA at0x236e08..0x236e24 after the fixed lane transform. Argument40 is loaded aspackedBF16 at0x236aa0 and enters the final FP32 FMA, argument48 is loaded by token index at0x236ad0. The exactsemantic metadata generator and numericcontents are not pinned merely by these consumption addresses.

## Synthetic input, metadata and allocator preparation

Omit `k_ht_rot_rows`. Allocate and initialize the41943040-byte pretransformed BF16 input once and bind that identical pointer for both timings. GU/DN packed/scales use the exact minimum blob sizes above, requiring zero extra physical padding; optional tensor guards do not change offsets. GU metadata+0x60/+0x68 require2560/1280bytes, with no expert stride or extra b64 padding. The92-triple analyzer checks every load address, pointer-base addition and zero channel high word; see `host-route-proof-v1.metadata-bounds.json`.

Use4096-byte initialized prefix/suffix guards around tensors and pass the payload pointer. The conservative activation envelope[-8,L+512) is contained inside those allocations for L41943040 GU and104857600 DN. P reads stay within327680bytes. See `host-route-proof-v1.activation-bounds.md` for row clamps, Kpanel recurrence and native128 signed-offset/helper evidence. The bounds apply to valid synthetic routes; they do not certify original model allocation capacities.

All arena allocations preserve original256bytealignment, capacity comparison, cursor/highwater update and overflowexit. At this N item arrays require no interarray padding; counts use8bytes within the256bytegap beforedenseDN, leaving248bytes padding. The sorter needs500bytes totalalignmentpadding from an alignedcursor. Known GU+DN+finalfold reference payload is104857600+419430400+41943040=566231040bytes (540MiB). Native code registration, synthetic operands and sorter/permutation/items/counts are owned by the root component.

Every payload and guard read by either variant must be initialized identically. Require exact bitwise comparison of every GU, DN and final fold word before reporting successful paired execution. Any difference keeps the route disabled. A fixture using actual model tensors is a separate scope requiring its actual binding receipts. No universal arithmetic-equality prerequisite remains for this bounded synthetic fixture.
