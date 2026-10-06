# Compact-Q8 two-row GPU H screen, 6 October 2026

The new two-row GPU kernel has **no demonstrated advantage**. It remains
disabled; the original server was restored normally and is ready/open. This
screen measured a component, not Prefill/Decode tok/s or native acceptance.

| Primed resident H | Original | Two-row candidate |
|---|---:|---:|
| Mean latency | 130.425 µs | 133.050 µs |
| Median latency | 130.429 µs | 132.768 µs |

Candidate mean latency is 2.012% higher. It is faster in
3/16 measured pairs; both order-stratum means
favor the original. All outliers are retained. No intrinsic cold-latency or
serving-rate conclusion follows from this primed event screen. The unchanged
screen is not repeated and does not justify an engine cohort.

The fixed shape is K=N2560/M4 with four BF16 input streams and original compact
Q8 rows: 6,963,200 weight bytes and 20,480 input/output bytes. Candidate grid80
replaces original grid160; both use block256, wave32, LDS0 and stream0. The new
source reuses each chunk's X loads across two output rows, without expanded
weights. Offline emission confirmed 80 VGPR, no spills/private storage/LDS,
float mode0xf0, native affine FMA, packed BF16 DOT2 and unchanged row/stream
accumulation order. An independent review released source and harness.

Four excluded warmup pairs and sixteen measured pairs balance A/B inputs and
both arm orders. Each timed launch follows one same-arm primer into separate
scratch output. Poisoning, priming, readback, hashing and file I/O are outside
the GPU event bracket. All40 timed outputs match frozen original hashes exactly.
The80 total launches, eight allocations/frees,84 copies and all event/cleanup
counters were complete. Event brackets include host enqueue gaps and event
instrumentation. Host single-wait can include outstanding primer execution;
host pair time also includes readbacks/hashes and is not pure kernel latency.

GPU assessment: no improvement for this exact MTP H candidate. CPU/NPU offload
has no supported benefit at this device-resident boundary; earlier complete
NPU H was slower. Ordinary target Prefill is outside this shape. Exact frozen
outputs intend preserved proposals, not increased native acceptance. No actual
serving Prefill, Decode or accepted/drafted delta was measured or extrapolated.

The [raw evidence](halogen-gpu-hidden-q8-rows2-screen-20261006.json) contains
every pair and order group, immutable source/runtime/build hashes, memory
reserves, owned cleanup and original-server restoration receipts. Startup
admission retained44/131 GiB stable60seconds; this does not prove sufficiency
at exactly44 GiB. The first restoration observer timed out while the same
original continued loading. Its failed receipt is preserved; a subsequent
read-only observation verified that exact PID/birth/run ready, without a second
start. All own measurement/container/hold helpers are terminal.

The next independent Prefill lead is the [existing native bulk HT pipeline](halogen-ordinary-prefill-trunk-route-20261006.md).
Its complete transform/multiply/sum/output cost and unchanged output tolerance
must be compared against the original prepared-weight/library path on frozen
actual operands. The [subsequent design](halogen-prefill-ht-frozen-replay-design-20261006.md)
binds source scratch allocation and the unsplit pipeline. Current descriptor,
packed format/extent, scratch pointer and stream still need capture. This is a
source lead, not a new speed claim.
