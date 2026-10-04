# Complete count-one MTP forward timing — 2026-10-04

The instrumented native MTP forward averaged **3.32356 ms** across 73
single-token calls. This includes input transforms, the entire layer48 block,
vocabulary projection, argmax, native device synchronization and result copy.
It is a wider scope than the previously measured MLP-only 0.404612-ms bracket.
Neither measurement is an exact uninstrumented latency or an NPU speed claim.

| Instrumented measure | Calls | Mean ms | Median ms | p95 ms |
|---|---:|---:|---:|---:|
| Complete forward, GPU stream0 event bracket | 73 | 3.323555 | 3.298629 | 3.587692 |
| Complete forward, host duration | 73 | 3.254002 | 3.222963 | 3.496359 |
| Wrapper including restore/cache work, host duration | 57 | 3.325287 | 3.281405 | 3.698751 |

The 73 GPU brackets sum to 242.619546 ms. Their callers were native direct
forward `0x17dcd54` (16) and wrapper `0x17dcf49` (57). The armed request made
115 original forwards in total: 42 calls with count other than one were
counted but excluded from timing. Therefore the sum is **not the total MTP
cost of the request**. The sampled-only selector `0x17e9980` is also outside
the bracket. Results do not assign latency to accepted or rejected tokens.

## Executed qualification

Root compiled the frozen C source with GCC `-O2 -Wall -Wextra -Werror -shared
-fPIC -fno-optimize-sibling-calls`, linked only libdl/libcrypto/pthread, then
bound the exact SO SHA to the launcher. The unchanged service owned startup,
the 18-GiB physical/commit guard and ordinary shutdown. No Remote Desktop was
used. Context was 262144, checkpoint v2, cache Off and MTP depth2.

The single armed request had exactly 8192 input tokens and 128 output tokens,
temperature0 and thinking off. Request, calibrated prompt and output hashes
match the existing stock/routing fixture. All frozen source pins were unchanged.
Original cleanup and memory recovery passed. Minimum physical/commit headroom
was 22.4347 / 113.9627 GiB. This diagnostic is not a new stock throughput row.

The tap precreated 256 events during unarmed startup and recorded on stream0.
There were no injected per-call synchronization, copies or file writes. After
the response, one final-event wait covered the pool; all events were destroyed.
All observed operations used stream0, and the native callback managers were
absent. The original forwards made 3050 observed kernel launches, 127 async
copies, 73 device synchronizations and 73 synchronous result copies. No observed
hipBLASLt calls occurred inside this forward.

GPU event brackets include host enqueue gaps and native waits; native device
synchronization may wait for opaque activity elsewhere on the device. Host
durations include observer overhead. Wrapper durations include the nested
observer and restore/cache work. These scopes cannot be subtracted to derive
exact individual stage costs or compared directly with an isolated synthetic
NPU expert subgraph.

## Retained identities

Sources:
[C tap](../../scripts/benchmarks/halogen0162_mtp_full_event_tap.c),
[launcher](../../scripts/benchmarks/halogen0162_mtp_full_event_tap_launcher.py).
Native forward entry `0x17db310`, wrapper `0x17dcde0`, pinned engine SHA256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.

| Artifact | SHA256 |
|---|---|
| C source | `f8ea59ef5903916527bae0a99fa6c5699d5a425cd70ba95255ad7f43f4aac8ce` |
| Launcher | `e0a0ad994c66da72854669cc29a07eceb7a331329d1bf50c2c4e5ce1ad8d3174` |
| Compiled SO | `7ba8c0d2f1e6e58871a3b9d6972ac5cd697f00b4f8b22543473301d7205d5b16` |
| Root coordinator | `ced2fbd01fca639a4022e0b31a43d60769c674191b7884297ce9dcadb7b7d271` |
| Result | `fe42c0646e5f4563bd78cbb91312501c78701103209ab5b471dfd2cc78415367` |
| Event statistics | `4898ed5ba2dcbbef1ffdd95166bd95277e7b69e8e821dbcadeb32f159aec0a0d` |

Raw evidence remains under ignored
`server/.local/mtp-full-event-20261004/mtp-full-event-timing-c668467aa0fc49e0a809d0bcac850fbe/`.
The completed coordinator was terminal with exit0 and `passed=true`. No NPU
execution, live draft replacement, acceptance improvement or overall speedup
is established by this run.
