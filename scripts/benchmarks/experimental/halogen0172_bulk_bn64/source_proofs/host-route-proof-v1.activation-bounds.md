# Synthetic activation allocation envelope

Static source review, 2026-10-09. This is a conservative physical-read certificate for the isolated paired fixture, with block width256, valid positive item rows, expert/tile domains from the route certificate, P containing original route slots0..81919, and item intervals contained in0..81919. Rotation is omitted: identical pretransformed synthetic BF16 input is supplied outside both timings.

The root-authorized **4096-byte initialized prefix and suffix on every tensor safely contain the native activation reads**. No unbounded row or K address remains in this synthetic contract. Exact minimal activation padding is not needed to use these guards.

GU permutation reads address P[start+min(local_row,rows-1)]. Both BN64's four row classes and BN128's eight classes use the item-row clamp; native128's odd partial classes also clamp the lane-derived row to111,79,47 or15 before the item-row clamp. Therefore every P read is a4-byte word inside its327680-byte payload. Dividing its valid nonnegative slot by10 gives token0..8191; the native signed reciprocal sequence implements this quotient on this domain. DN directly uses the clamped sorted row0..81919.

For activation vectors the initial in-row coordinate is a masked multiple of8 BF16 words: mask0x78 gives0..120 words in BN64; mask56 gives0..56 words in BN128. Vector width is16 bytes. Normal loops advance the activation panels by256 bytes, bounded by20 GU or5 DN K128 panels. The small native128 classes stage the two128-byte halves separately. Their largest explicit pointer bias is0x88, and their vector instruction offsets range from-8 through120; the pointer recurrence remains256 bytes per panel. Treating the panel index conservatively as0..G inclusive, independent of final-prefetch suppression, gives this envelope relative to the chosen row start:

`[-8, 256*G + 2*120 + 136 + 120 + 16) = [-8, row_bytes + 512)`.

The upper bound deliberately combines maxima from different classes and permits the exit panel. It safely includes all actual initial, reload and next-panel activation vectors without relying on numerical values or minimal-padding claims. Normal G/G-1 and small P/P-64 guards are independently recorded in `host-route-proof-v1.weight-bounds.md`; they only tighten this envelope. Since every row is valid, the resulting whole-tensor envelopes are:

|Tensor|Payload bytes L|Conservative physical-read envelope|Allocated fixture envelope|
|---|---:|---|---|
|GU transformed BF16 N*2560|41943040|[-8,L+512)|[-4096,L+4096)|
|DN input BF16 R*640|104857600|[-8,L+512)|[-4096,L+4096)|
|P int32 R|327680|[0,L)|[-4096,L+4096)|

The signed-8 instructions are safe more tightly: GU128 e600d8/e64838 and DN128 e874ac/e89994 use an activation pointer biased+0x88, hence net+128 bytes. Their+120 siblings read the following K panel, with the last prefetch skipped. GU128 e719fc is the full-eight first-panel helper: its pointer v181:182 was formed from the fourth clamped row and mask56. e71a7c contains LDS/permutation operations and no global load. These helpers do not introduce an expert stride or an unbounded new source.

Audited source classes: GU64 initial activation paths around e01484/e038e8/e097e4/e0e0c0; GU128 around e31388/e341cc/e3fc18/e49ed4/e52b9c/e59fac/e5fe70/e64610, plus e719fc; DN64 around e1655c/e19630/e1c164/e1e77c; DN128 around e71d7c/e76414/e7a5bc/e7e144/e817e8/e8471c/e87224/e8973c. The row clamps and all negative-offset sites are visible in the pinned four disassemblies. Anchor neighborhoods identify classes; the envelope above includes every activation reload in each class.

Fold inputs remain dense finite operands: DN419430400 bytes, I327680 bytes, routeweights327680 bytes, FP16 channel operand5120 bytes, BF16 token operand41943040 bytes, FP32 token scalar32768 bytes. Their source fold certificate binds the fixed ten original-slot iterations and exact channel/token extents. Guard and payload bytes must be initialized identically between paired variants. The component must compare every GU, DN and final fold word bitwise and reject activation on differences. This certificate makes no universal arithmetic-equality or actual-model-allocation claim.
