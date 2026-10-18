# Native HC6<3> split: source feasibility and bounded ROI test

2026-10-10. Source-only work. No GPU/NPU access, module loading, engine execution, WSL/Docker, lifecycle/API call or serving-state change was performed by this subtask. The new candidate is a two-launch HC6 dependency split. Its net latency benefit is unmeasured. Root owns any execution.

The smallest initial candidate executes the unchanged native function with grid96, then an in-place tail variant with grid160 on the same stream. Both use block256 and the same17 explicit arguments. The tail adds96 to its WG ID and bypasses only the HC6 middle-completion poll. Its descriptor, metadata, allocation, arithmetic, buffer accesses and output stores remain native. This is distinct from the rejected125→120 register remap and the completed causal64/policy/Q4 screens.

## Exact current-version identity

Preparation root is `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008` (PREP below). Root's `hc6-split0174-preparation-20261010/current-hc6-extraction.json` pins the current object. A separate read-only CPU byte search also found the complete selected body exactly once in the current engine at file offset`0x40e600`.

| Artifact | Bytes | SHA256 |
|---|---:|---|
| Current0.17.4 engine |26996440|`68f6e378ba9edb60d1e6348616f0d61603811fea81935a2c750fa1e0c2a448ca`|
| Current gfx1151 object, engine offset`0x53000` |18566544|`d9c5ad87f9fbdd0024cce498fdf9d7d76b35524a8d4bc803986cd9e5ed8a98f6`|
| Old0.17.2 gfx1151 object |17765424|`18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039`|
| Selected complete body, identical in both |21468|`be571ef631410256670c079f0545e812123278cb2d33c2a8738c910d4b6d6206`|

Exact symbol:

```text
_ZN7halogen12_GLOBAL__N_112k_hc6_fused3ILi3EEEvPtPKtPKfS4_iNS0_5LqGrpES2_liPKhS4_S2_PfPyySB_y
```

Old entry`0x3b3c00` maps to current entry`0x3bc600`, a body-wide RVA shift`+0x8a00`; current body file offset is`0x3bb600`. Old descriptor`0x1fefc0` maps to current descriptor`0x201680`. Descriptor byte differences are exclusively offsets16/17 in the entry displacement:1788992→1814400. All resource/mode bytes agree, including `COMPUTE_PGM_RSRC1=0xe0af000f`, FP32 round mode0 and denorm mode3. Do not transplant old host-descriptor/caller addresses. An isolated module component needs the current object and arguments; any later engine adapter needs an independent current host registration map.

CPU decoding of the selected AMDGPU MessagePack metadata from both objects found the **entire selected metadata map equal**, including all explicit/hidden arguments, kernarg680/alignment8,125VGPRs,38SGPRs,1120 fixed LDS, zero private scratch/spills, wave32 and WGP mode. Current descriptor and metadata must remain unchanged for the first split candidate.

## Partition, dependencies and exact edits

With arg32=12 and arg352=84, native grid256 partitions WGs0..11 into residual/normalization producers,12..95 into middle/LqGrp consumers and96..255 into HC6 consumers. The middle waits for the producer counter. HC6 waits for the **middle** counter. Splitting at middle completion is therefore the minimum two-launch boundary; it retains the producer→middle rendezvous.

| Launch | Function | Grid | Work performed |
|---|---|---:|---|
| A | Unchanged current native |96|All12 producers and84 middle WGs; native waits, stores, cache/barriers and both publication atomics|
| B | Current native tail variant |160|WG IDs adjusted to96..255; HC6 work and all native outputs; middle-counter poll bypassed|

The variant uses two fixed-length patch sites; no instruction relocation occurs.

| Current RVA | Native words | Expected candidate words | Purpose |
|---|---|---|---|
|`0x3bc624`|`bf031802 bfa11139`|`8002ff02 00000060`|Replace producer comparison/branch with8-byte `s_add_u32 s2,s2,0x60`, including literal96|
|`0x3bc81c`|`bfa50014`|`bfa00014`|Replace `s_cbranch_execz20` with `s_branch20`, same target`0x3bc870`|

The next native comparison computes the middle boundary12+84=96 and sees adjusted WG IDs96..255, so it takes the HC6 path. `s2` subsequently yields the same HC6 row/address calculation as the original WG. The add's SCC is overwritten by the native boundary calculation/comparison before use. New words require a bounded current-object AMDGPU disassembly before execution.

The poll bypass leaves saved EXEC in`s4`, retains restoration at`0x3bc870`, accumulator initialization, outstanding weight-load wait, block barrier and post-wait cache invalidations. Poll temporaries`v5..v7` are overwritten before use; poll VCC is overwritten by the first later VCC reference, a `v_cmp_gt_u32` at old`0x3b6374`/current`0x3bed74`. No counter value enters HC6 arithmetic. Same-stream completion of A publishes all middle outputs before B, so the deleted observation is redundant under that ordering.

The bypass also removes the poll's `buffer_gl1_inv`/`buffer_gl0_inv`. HIP7.1.1's official [programming model](https://rocm.docs.amd.com/projects/HIP/en/docs-7.1.1/understand/programming_model.html) guarantees visibility of prior command side effects to subsequent commands on the same stream, and its [module launch reference](https://rocm.docs.amd.com/projects/HIP/en/docs-7.1.1/doxygen/html/group___execution.html) assigns normal default-stream synchronization semantics to stream0. This guarantees the required A→B visibility for the documented exact same-stream/same-device launch pair; the native tail's additional post-wait `gl0/gl1/gl0` invalidations are retained. Distinct streams or any-order dispatch would require a separate proof. Runtime parity remains necessary to qualify the real native module route.

The common return needs its native predicates, rather than assuming the consumer region simply ends. HC6 sets`s25=0` at old`0x3b6358`, saves EXEC into`s6` at`0x3b635c`, restores EXEC at`0x3b7230`, and tests`exec&s25` at`0x3b7238`; thus the middle body is skipped. The next common guard sets`s3=0` at`0x3b810c` and computes`exec&~s3`; nonzero restored EXEC takes the native common end at`0x3b8fd0`. The initial full EXEC is guaranteed only for the documented256-thread block/wave32 shape. These guard instructions and native termination are retained.

`PREP/hc6-split0174-preparation-20261010/transform_split.py` is the new CPU-only source. It pins the current object/body, checks every retained word of3352 instructions against the current body, audits the predicate-qualified common return and guard dominance, applies only the two sites in memory, and checks the whole-object mutation whitelist. It supports `--audit-only`; its write mode creates only inert `current-hc6-tail-split.data` and an exclusive receipt, refusing overwrites. The transformer was syntax-parsed, but this subtask has not executed it or emitted a candidate. Root should run the audit before producing the inert object.

The only hidden-kernarg load in the complete body is group-size-x at byte436 (`0x1b4`), in the producer path. There are no hidden block-count/grid-count/global-offset loads. Grid96 keeps the producer block size and hidden group-size unchanged; grid160's HC6 path uses adjusted`s2` and never executes that producer load.

## Argument and shared-state contract

Kernarg680 bytes, alignment8. Seventeen explicit values end at byte424; use normal HIP packing with the original by-value aggregate and hidden metadata. All pointer aliases, packed weight formats, buffer lengths, scalar values, optional-output validity and lifetimes must be copied from one qualified complete-operation fixture. The table's pointer meanings come from the pinned old native caller; the current device ABI is exactly equal, while current engine allocation addresses are not established here.

| Offset | Type / meaning |
|---:|---|
|0|`uint16_t*`, residual/context output|
|8|`const uint16_t*`, residual/context input|
|16|`const float*`, residual scales|
|24|`const uint16_t*`, norm weights|
|32|`int`, producer count12|
|40|`LqGrp`,296 bytes by value; two native projection records|
|336|`uint16_t*`, middle output|
|344|`long`, native value10240|
|352|`int`, middle count84|
|360|`const uint8_t*`, HC6 packed weights|
|368|`const uint16_t*`, HC6 input|
|376|`uint16_t*`, HC6 output|
|384|`float*`, optional float output|
|392|`uint64_t*`, producer counterP|
|400|`uint64_t`, producer targetP|
|408|`uint64_t*`, middle counterM|
|416|`uint64_t`, middle targetM|

For distinct native counters with initial valuesP0/M0 and no overflow, preserve the original targetsP0+12/M0+84. After A, require the same native outputs and exact countersP0+12/M0+84; after B, counters must remain at those values. Native producer and middle publication atomics are retained in A, at current`0x3c111c` and`0x3c19c0`. They must not be removed: later calls rely on cumulative counter state. Resetting counters to0 while retaining accumulated targets would deadlock A. Initialize every comparison arm from the same full pre-operation snapshot, including in-place residual data, outputs read by epilogues, scratch and both counters.

Require one controlled host producer, no capture, no concurrent scratch reuse, and no external interleaving between the two submissions. B must be submitted on the exact same stream after A. Keep all allocations/argument storage alive through complete B retirement. Returning a successful enqueue status does not establish completion. A component may submit both kernels then use one final event/synchronization; do not host-synchronize between A and B.

No retained standalone complete HC6<3> tensor/counter fixture or math host was found in PREP. The remap/registration directories contain engine adapters and cohorts; `test_registration.c` qualifies registration rather than HC6 computation. Existing Q4/DFlash snapshots lack the producer normalization,296-byte LqGrp, middle buffers and cumulative counters. They are not a complete-operation fixture. Reuse an authentic HC6 fixture only after its full ABI, aliases and prestate are qualified; otherwise fixture acquisition is still work for root. A synthetic microkernel or zero-middle launch cannot substitute for this native operation.

## Resource option and ROI gate

Predicate-qualified HC6 paths reach at most`v115`; middle reaches`v124`, while producer/tail reach`v73`. A separately considered4-byte direct common-end branch structurally prunes inactive middle/producer bodies and yields an unconstrained reachable max`v115`. It is excluded from the initial transformer. If a later resource experiment is justified, logical count116 encodes120 and physically allocates120 registers/wave, whereas native125 encodes128/allocates144. Its expected resource field is15→14 (`0xe0af000f→0xe0af000e`), with metadata125→116 and other descriptor bits unchanged. Do not combine this with the first split experiment: allocation improvement alone already failed the previous remap cohort.

The guaranteed removed work is160 initial64-bit middle-counter reads, associated compare/branch/cache instructions, and any unmeasured retries. The hypothesis also removes HC6 residency while middle work is pending. The costs are one additional HIP dispatch, a queue boundary, and loss of HC6 weight-preload overlap with middle computation. No captured spin-iteration/stall budget supports a positive net forecast. The instrumented HC61.64s count×mean total is invalid as an uninstrumented budget because diagnostic sums exceed wall time.

The bounded test must compare **one complete native grid256 operation against the complete A+B pair**, using the same qualified fixture and native control through the same module route. Warm module setup outside the bracket. Include all launches, output stores, counter atomics and full completion in timing; bracket the native operation or both candidate launches on the same stream, followed by one final retirement boundary. Also record host wall cost so the extra submission is visible. No poll-only or tail-only latency is an acceptance metric.

Require exact parity of all output/in-place/scratch regions, optional float output when valid, both counters and guards, with no errors or nonretirement. Then run a small native/candidate/native component comparison with resets outside timed brackets. Proceed beyond this component only for a material complete-operation advantage beyond paired native drift. Reject or stop on parity failure, deadlock, zero useful fixture coverage or no complete-pair advantage. No serving hook/cohort is qualified by this source work.
