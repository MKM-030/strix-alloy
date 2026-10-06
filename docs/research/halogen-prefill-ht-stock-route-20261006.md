# Stock Prefill HT preparation route, 2026-10-06

The completed ordinary layer-0 QKV capture proves that the selected stock
operation prepares original BF16 weights and submits a library GEMM. Its
baseline component replay must include that preparation on every timed call.
This is a route and receipt audit, not a serving speed measurement.

## Bound sources

Pristine Halogen 0.16.2 ELF SHA-256 is
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
Retained host disassembly SHA-256 is
`523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`.
The reviewed capture source SHA-256 is
`bd06d7fcfab41d950aaafe2a504b33bb5a7c91275cd7984941371278d5c41e82`.

Bounded reads of the pristine ELF independently reproduce the helper hashes
listed in `halogen-prefill-ht-independent-audit-20261006.md`:

| Helper | Half-open RVA extent | SHA-256 |
|---|---|---|
| Original preparation | `[17ec6e0,17ecede)` | `34bb1998a74e03c63c714ea1e43d505eb88e59ff1c6266f39ba997a6f174d12d` |
| BF16 GEMM wrapper | `[18c6b80,18c6be6)` | `6336433c1a337ff1faf7f72767ea869bfab343355ce74130226bd0ba76651a7d` |
| Native HT | `[18092f0,1809ba4)` | `fda51e1d8cf5008e6e5e61a85ee33199a008a4833799452d1e6db9786350e231` |

## Cache control and library pointer binding

The environment name at ELF RVA `3e2e2` is
`HALOGEN_PREFILL_KEEP_TRUNK`. Initialization at `17f8d24..17f8ddc`
stores one at global `18dcf41` only for the exact string `"1"`.
An absent or other value stores zero. At `17f861c`, zero bypasses the
packed-pointer cache lookup `180c4e0` and reaches preparation helper
`17ec6e0` through `17f865c` on each direct-original call. Cache helper
`180c4e0` itself is a host map lookup, not a weight preparation routine.

The direct-original branch passes prepared W, original X and Y to
`18c6b80` at `17f8696`. That helper uses the owning router and a plan
keyed by M, N, K and type zero, then dispatches through `18c6850`.
The library receives prepared W as A, original X as B, and Y as both C
and D. The alternate transformed branch at `17f8a00` instead passes
rotated scratch global `18dcf30` as B. A launch whose return caller is
`17ecd6a` establishes execution of original preparation `17ec6e0`.

## Completed capture

Source receipt:
`server/.local/optimization9h-20261004/prefill-ht-capture-9ac79c0cb8c4479189d101c12e6f588f/trace/records.json`.
Its SHA-256 is
`c5e0d744f7160225921dfe163f01694ec33e4f12517c3fce81dff83cfa6dfe7b`.
Root captured the frozen 16K request; the selected first QKV operation
has M=8192, N=10240, K=2560, store16, variant4616 and descriptor mode4.

Independent metadata checks establish:

- Ordinary FC return caller `1791400`, packed return caller `178cfc0`,
  one selected packed original call and original result one.
- One successful kernel launch, caller `17ecd6a`, grid `(20,80,1)`,
  block `(512,1,1)`, zero shared memory and default stream.
- One successful library call; B equals X, C and D equal Y. B differs
  from recorded rotated scratch. This binds the direct-original route.
- Packed, signs, scales, X and Y pointers each fit their recorded
  allocation. Every before/after base and extent agrees. The observer
  performed ten range queries, two synchronizations and five copies.
- Descriptor inventory hashes before and after agree; completion is
  passed, with no recorded error and no candidate operation.

Only JSON receipts and bounded pristine executable ranges were read by this
reviewer. Captured tensor payloads were not independently rehashed here;
their hashes and completion status are the completed capture inventory's
reported evidence. Allocation lifetime remains root's exclusive-window
ownership guarantee in addition to these recorded snapshots.

## Fair replay and remaining limits

A finite within-process comparison can reuse the same initialized router
with fixed M/N/K/type and stabilize stock plan selection during excluded
qualification and warmup calls. At `18c6baf..18c6bc4`, the wrapper invokes
selection helper `18c6290` only while plan+40 differs from plan+48. After
choosing and copying the algorithm at `18c6637..18c6665`, that helper sets
plan+48 to plan+40 at `18c6674`. Successful later calls using the same
router and key therefore skip selection. The timed stock path must include original
W preparation, GEMM submission and completion. The candidate must include
its complete activation rotation, packed multiplication and completion.
Both paths use identical frozen input payloads and require full output
qualification before timing. Balanced ordering limits drift.

Opaque algorithm bytes are not necessary for that limited same-router
comparison if the plan remains stable. An independently bound algorithm
identity is needed before asserting identical selection across engine
processes; matching identities alone would not prove equal performance.
The capture's algorithm pointer points to a transient stack copy;
it is not a persistent algorithm identity. Exact output also does not prove
algorithm identity. The component result cannot be converted into measured
prefill, decode or acceptance; those require a separate admitted engine
comparison if the component qualifies.
