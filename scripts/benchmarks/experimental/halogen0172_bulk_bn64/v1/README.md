# Source-only native complete bulk component

`host.c` pairs the pinned native BN128 and BN64 mode1 kernels at N8192, R81920 and512experts. Each GPU-event timing boundary contains native item generation, GU, denseBF16 DN split2 and native bulk fold. Both use the same deterministic finite Q4/FP16 weight blobs, GU channel metadata, pretransformedBF16 input, stable P/I routing, routeweights, DN/fold channel metadata, BF16 residual and FP32 token scalar. Rotation and sorting are excluded for both. This is synthetic finite route coverage; it makes no serving-rate, actual-model or NPU claim.

The exact 17,765,424-byte code object is SHA256-checked before loading HIP. Its pinned digest is `18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039`. CPU EVP SHA256 requires `libcrypto.so.3`. HIP is dynamically resolved from the explicit library path supplied as the second argument. No HIP headers or custom device kernel are required. This delivery has not been compiled or launched.

The CLI shape for a root-owned later launch is `component PINNED_CODE_OBJECT HIP_LIBRARY [reps1..7]`; the default is3 measured pairs per pattern. Each pattern first runs one excluded paired warmup. The measured order alternates64/128 then128/64. GPU clear/init, event reads, guards, item validation and output copies/comparison are outside the event interval. Start/end events on stream0 enclose exactly the four kernel launches. Fixed LDS comes from native metadata; dynamic shared bytes are0.

All100MiB GU,400MiB DN and40MiB final reference payloads stay on device. The working surfaces are reused sequentially. BN128 outputs are retained after each BN128 execution; a first-running BN64 compares against the last retained identical-input BN128 output, then the new BN128 result also compares against that reference before replacing it. Thus alternating order checks both variant equality and BN128 repeatability. Payload poisons differ (128=0xa5,64=0x5a), so matching missing writes cannot pass by sharing initialization. All words must agree bitwise, all compared BF16 words must be finite, and every allocation's4096-byte prefix/suffix guard must remain unchanged at0xa5. Any mismatch fails the run. There is no relaxed tolerance or performance qualification after failure.

The exact device allocation budget is **2,515,610,388bytes =2.342844743GiB**, including23 guarded allocations. Host staging is two4MiB chunks, retained P/I arrays and one temporary route array; the conservative host peak bound is9,388,032bytes plus loader/runtime overhead. Weights are initialized by chunk, avoiding a host-sized copy of the1.2375GiB blob payload. Full output comparisons also use chunks.

Two patterns are supplied: uniform512x160, and an exactlyR-sized boundary-tail histogram covering row counts around all16/64/128 boundaries plus255/256/257. The boundary assignment selects the ten largest remaining expert degrees per token before decrementing them, giving ten distinct experts per token. P is the stable ascending-expert/original-slot sort, I its exact inverse. Raw512 counts and native active/total bookkeeping are populated on CPU outside both timing boundaries. The Python source review checks the complete route construction, permutation inverses, segment counts, capacities and item row partition. The native items are read back and compared record-for-record against the CPU expectation after every operation.

ABI mapping (host offsets are bytes):

|Aggregate|Offsets|Binding|
|---|---|---|
|Projection152|00,08,10,18|blob pointer, packed offset0, scale offset GU0x32000000/DN0x19000000, scale-row stride GU40/DN10|
|Projection152|20..5f|sixteenFP32 codebook values[-8..7], exact native bytes|
|Projection152|60,68|GU metadata2560/1280bytes; DN metadata5120bytes and null|
|Projection152|70,78|GU pretransformed input/P; DN denseGU/null|
|Projection152|80,88,90|GU or DN item pointer, counts or counts+4, dense output|
|Items56|00,08,10,18,20,28,30|active IDs, compact prefixes, raw counts/bookkeeping, R int32, GUitems, DNitems, counts|
|Fold64|00,08,10,18,20,28,30,38|denseDN, I, N int32, routeweights,5120byte FP16 channel operand, residual, token scalar, final output|

Native projection template selection is GU`ELi1`, DN`ELi2`. The external outputflag1 does not mean DN`ELi1`. Both variant item arrays allocate the larger BN64 capacityC1792: GU5C*16bytes, DN10C*16bytes, counts8bytes. Native grids remain5*C_B and10*C_B (C1281152/C641792), so native count guards exercise the original upper-capacity launch behavior. Fold grid20480/block256. Items grid1/block512. GU/DN block256; fixedLDS34816/36864 for64/128, all wave32.

Safety evidence is supplied by `source-review.py/json` plus sibling `prefill-bulk-moe-retile-scope-20261009/host-route-proof-v1.weight-bounds.md` and `host-route-proof-v1.activation-bounds.md`. GU metadata2560/1280bytes was independently certified over all92epilogue triples, with no expert stride or metadata vector padding. GU/DN blobs865075200/432537600bytes need no packed/scale padding. The final conservative activation read envelope[-8,L+512) is contained in the initialized4096-byte input prefix/suffix. P reads stay inside its327680-byte payload. The source-only ABI and routing check itself does not establish C compilation, device arithmetic equality or performance.
