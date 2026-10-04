# Bounded native embedding cache candidate — 5 October 2026

The new [cache source](../../scripts/benchmarks/halogen0162_mtp_embedding_cache.c)
and [shared header](../../scripts/benchmarks/halogen0162_mtp_embedding_cache.h)
implement a bounded GPU memoization core and a separately gated native shim.
This document describes source behavior. No compilation, hardware execution,
model/payload read, server restart, parity result, throughput gain or NPU
execution was performed by the source author. Root alone owns those operations.
The colleague's existing engine remains untouched.

The [independent replay](../../scripts/benchmarks/halogen0162_embedding_cache_replay.c)
includes the exact core with `HALOGEN_EMBEDDING_CACHE_CORE_ONLY`. It can qualify
cache copies against two frozen original GPU M1 outputs without loading a
checkpoint or installing native detours. It does not qualify the full shim.

## Core interface and bound

`ECACHE_ABI_VERSION=1` uses fixed BF16 rows of 5120 bytes, token domain
`0..248319`, and capacity `1..64`. The maximum row allocation is 327,680 GPU
bytes plus at most 64 HIP events and fixed host metadata. HIP runtime/event
driver allocations are additional and are not bounded by this row calculation.
There is no producer thread, host tensor staging, transport or NPU producer.

The owner supplies initially zeroed state, exact allocation/copy/event
callbacks, one immutable arithmetic generation, live disjoint 5120-byte input
and output allocations, and exclusive init/reset/close lifetime ownership.
Device pointers are opaque numeric values. CPU code never dereferences their
contents. Span/alias checks reject wraparound, odd BF16 pointers, input/output
overlap and overlap with cache rows; those checks do not prove GPU allocation
extent or liveness. The runtime owner supplies that proof.

Every operation uses the original default stream `NULL`. The callback must
enqueue exactly one unchanged original M1, return zero on success, and retain
any native errno needed by the owner. `ecache_apply` returns:

| Value | Meaning |
|---|---|
| `ECACHE_HIT=1` | A completed entry supplied an ordered D2D copy; original M1 callback was skipped |
| `ECACHE_MISS=0` | The original callback completed its enqueue successfully, exactly once |
| `ECACHE_ERROR=-1` | The state is failed; caller must fail stop and must not retry the native operation |

A failed copy enqueue may already have submitted a partial candidate write.
`ECACHE_ERROR` is never permission to fall back after that write. Overlap or
reentrancy sets an atomic permanent failure flag. The detecting caller must
fail stop; this core is not a scheduling or serialization service. Statistics
and entries may be inspected only with exclusive ownership. The native shim
separately rejects overlapping full heads before core use.

On a supported miss, the core prefers an empty slot, or searches at most the
fixed capacity for a completed round-robin victim. The callback runs once, then
a D2D copy from its original output into that slot is enqueued and the slot's
precreated completion event is recorded. An entry is valid for lookup only
after that event was successfully recorded. `hipEventQuery` is nonblocking:
a ready entry hits; a matching pending entry runs native without recapturing or
waiting. If every occupied slot is pending, the miss runs native without
capture. Tokens outside the bounded domain also run native without capture.
The `pending_fallbacks` counter counts matching pending entries, not a full
cache whose unrelated entries are pending.

Completed-entry eviction does not rerecord a still-pending capture event.
Earlier hits read the cache row on the same default stream as subsequent
overwrite captures; stream order therefore protects those reads. No per-hit
synchronization or host-to-device row copy is introduced.

Reset requires a nonzero generation distinct from the current one. It drains
the default stream, invalidates every entry, changes the 16-byte generation and
reuses the allocated rows/events. The owner must supply globally fresh epochs;
the fixed core stores only the current epoch, not unlimited generation history.
Position or acceptance rollback is not a token-projection identity change.
Model/arithmetic/allocation retirement is a generation change and cannot reuse
entries.

Init allocates one row/event per slot. Partial init failure attempts a default
stream drain and destroys/releases each retained unique resource. A failed
drain retains initialized resources because their in-flight lifetime is
unknown. Close likewise drains before invalidation and release. Failed release
or event destruction is counted, its handle is discarded, and the state remains
permanently failed; no retry or resource-reuse claim is made. The caller must
fail stop after any such failure. Close may clean a failed state but still
returns `ECACHE_ERROR` because the permanent failure remains latched.

## Native shim gate and activation

The full source is Linux x86-64 only. Its constructor returns immediately when
`HALOGEN_MTP_EMBEDDING_CACHE` is absent; exported HIP observers merely forward
ordinary calls. No cache allocations, head/FC patches or result directory are
created in that mode. Native activation is additionally compiled out by
default. Setting its environment mode in an ordinary build fails with
`native-live-admission-unqualified`.

Only root, after the required hook/lifetime review and fresh owned-process
admission, may build with
`-DHALOGEN_EMBEDDING_CACHE_ENABLE_NATIVE_CANDIDATE=1`. This is an experiment gate,
not a claim that this document or the standalone core replay qualifies live
use. Root's external ownership, deadline and 22/18-GiB reserve guard remain
authoritative. No production launcher was added.

An admitted owned process would require all of these explicit values:

```text
HALOGEN_MTP_EMBEDDING_CACHE=gpu64-v1
HALOGEN_MTP_WIRE=D
HALOGEN_LQ8_WAVE=1
HALOGEN_MTP_EMBEDDING_CACHE_GENERATION=<fresh nonzero 32 lowercase hex>
HALOGEN_MTP_EMBEDDING_CACHE_IMMUTABLE=engine-single-generation-v1
HALOGEN_MTP_EMBEDDING_CACHE_DIR=/tmp/alloy-mtp-embedding-cache-<same generation>
HALOGEN_MTP_EMBEDDING_CACHE_CAPACITY=<optional integer 1..64; default 64>
```

The directory must be fresh; constructor creates it exclusively with mode0700
and owner-only activation/result files. `HALOGEN_MTP_FC_QUALITY` must be absent.
Do not combine this shim with any other head/FC tap, runtime interposer or
checkpoint lifecycle machinery. Installation must precede all serving work.
The patches are not a concurrent hot-patch protocol; partial install fails the
owned process. Root must pin the HIP library/runtime/device/context externally.
The full shim does not hash HIP or prove that `RTLD_NEXT` avoids every other
interposer.

The executable must be `flash_serve` with first argument `--ck`, exactly
26,052,768 bytes and SHA256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
File stat consistency, ELF64 little-endian x86-64 ET_DYN, unique PT_LOAD
offset/flag matches, full mapped head/FC hashes, exact entry signatures,
callsites, globals and kernel-address ranges are checked before both near
trampolines are prepared, sealed RX and then patched. The pins are inherited
from the retained audited dispatcher shim:

| Site | RVA / file offset | SHA256 |
|---|---|---|
| Head | `0x17db310` / `0x17da310` | `132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20` |
| FC dispatcher | `0x178cf90` / `0x178bf90` | `f8f9d77041011251d11d0b97d7298926aa053d5435310826a00c408e5bff24e9` |
| Embedding FC return | `0x17db548` | exact original call instruction checked |
| Hidden FC return | `0x17db663` | exact original call instruction checked |

All full-head invocations increment an in-flight count. Overlapping or nested
heads fail stop; a mutex protects only metadata and never serializes complete
heads. Count1 with a known caller (`0x17dcc08`, `0x17dcd54`, `0x17dcf49`,
`0x17de236`), valid host token/model state and actual wire-D is eligible. Other
counts/callers continue through the original head and FC. They do not obtain
cache hits. Retirement failure paths remain conservative even on an excluded
head.

The first eligible head binds one model and execution thread. Cache rows/events
are lazily allocated in that thread at first admission. Binding retains the
embedding table `*(model+0x4f0)`, gamma `*(model+0xae8)`, full 120-byte embedding
descriptor at `model+0x908`, descriptor raw weight `+0x10`, normalized input
`*(model+0x6c8)`, original e output `*(model+0xb00)`, seed and wire guard.
These pointer/descriptor identities must remain unchanged and source bytes
must remain immutable for the entire generation. Pointer checks cannot detect
in-place weight/table/gamma mutations. Such writes are prohibited by the owner
contract and are not automatically monitored.

At exactly embedding return-RVA `0x17db548`, descriptor/model identity and
`N=K=2560, M=1` are checked before cache use. The normal Q8 descriptor requires
zero alternate pointers at offsets0/0x30 and a live owner-qualified, aligned
6,963,200-byte raw-weight allocation at offset0x10. Every capture follows one
observed original M1 launch with exact kernel identity `engine+0x18d6690`,
launch return-RVA `0x17fdba0`, grid160x1x1, block256x1x1, shared0, streamNULL,
and exact raw weight/input/output/K/N arguments. A launch failure or route
mismatch fails stop before capture. A hit relies on the pinned unchanged
dispatcher, the qualified miss route and immutable generation binding; the
skipped launch cannot be reobserved on that hit.

Gather and embedding RMS execute before this seam. Hidden FC and all remaining
head/seed/controller operations forward to their original functions. Misses
execute the original embedding dispatcher once; hits enqueue the D2D write in
its stream order and skip only that dispatcher/M1. Successful miss errno is
restored from the original callback, and a hit retains incoming errno.

## Retirement and material limitations

After model binding, any external `hipFree`, `hipDeviceReset`, `hipCtxDestroy`,
`hipCtxSetCurrent`, `hipCtxPushCurrent`, `hipCtxPopCurrent` or `hipSetDevice`
conservatively retires the cache. This catches frees whose base differs from a
bound interior pointer. With no head in flight it drains and closes cache
resources before forwarding the lifecycle operation; all later calls remain
native. An intercepted lifecycle operation during any head fails the owned
process before forwarding. Cache-owned init/close operations use a TLS bypass
and `RTLD_NEXT` frees; those do not retire their own generation.

This is incomplete driver/lifetime interception. Uninterposed free/reset APIs,
direct driver operations, process fork, another library bypassing these
symbols, context transfer on another thread, and device failure/recovery are
not qualified. Root must maintain a single immutable device/context/model
generation and prevent bypasses before any native activation. Host pointer
mapping checks also do not prove allocation lineage. The standalone replay
cannot discharge these requirements.

There is no timing log inside a head. Activation is published at constructor
time and one bounded summary at normal destructor time. Fatal `_exit(79)` may
leave only activation; no destructor receipt is guaranteed. Even a summary
with zero failures leaves integration, arithmetic, NPU, parity, acceptance,
performance and native reset interception qualification fields false.

The shared-core replay uses capacity1, one warmup and two measured eight-step
cycles. It checks original and cached BF16 outputs against frozen hashes and
each other, expected native callback counts, eviction and a reset that reuses a
key for another frozen row. Input/poison/output transfers, setup, reset and
validation remain outside event and monotonic enqueue-through-end-wait timing.
Keys and hit rate are synthetic; frozen inputs are CPU-prepared normalized
rows. Native gather/RMS lineage, pending lookup behavior, live model lifetime,
head integration, proposal/acceptance and end-to-end tok/s remain unqualified.

The earlier [feasibility calculation](halogen-mtp-embedding-cache-feasibility-20261004.md)
uses approximately0.153 ms standalone M1 and an ideal one-hit-per-output toy
bound of approximately0.649% at42.15 tok/s. It is not a measured result. Core
replay omits the shim's repeated host mapping/binding checks; those can erase
any small saving. There is no established prefill benefit or NPU advantage.
