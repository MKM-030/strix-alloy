# Paired FC unarmed discovery contract

The disabled-by-default `shadow4-v1` shim now has one bounded unarmed discovery
head before its existing four paired SHADOW samples. It resolves the model-pointer
arming dependency by publishing host identity evidence. Discovery performs no
observer HIP copy, synchronization, allocation, candidate publication, provider
creation, or model/checkpoint payload read. The original head, FC dispatchers and
HIP launches execute once, preserving original return values and `errno`.

This is a source contract. Build, live discovery, transport, model/graph binding,
arithmetic, NPU, native parity, full-D/full-head integration, reset interception,
acceptance and performance remain unqualified. Root alone owns build and runtime
windows; this change performed neither.

## Fresh process and serial lifecycle

Activation retains the exact native engine, head and dispatcher hashes and both
FC callsite signatures. `HALOGEN_MTP_FC_QUALITY=shadow4-v1`, explicit
`HALOGEN_MTP_WIRE=D`, the default/enabled Q8 wave route, and a fresh constructor-owned
`/tmp/alloy-mtp-fc-quality-<32 lowercase hex>` directory remain required. With the
mode absent there are no detours. Existing MLP sources, packet formats and receipts
remain separate.

The constructor captures `getpid()` plus field22 of a bounded `/proc/self/stat`
read. Field22 is the Linux process start time in clock ticks since boot. Parsing
starts after the final closing parenthesis of the command-name field, which may
contain spaces and parentheses. PID/starttime are rechecked during discovery and
armed admission; the PID is in the native process's Linux PID namespace. It is
not the Windows controller PID or necessarily a host-namespace container PID.
Root must independently bind this namespace identity to the owned process.

The first eligible unarmed head requires count1, a known native return RVA,
nonnegative token, ABI position, outer position and slot, readable host model/token
spans and enabled MTP. Known return RVAs are `0x17dcc08`, `0x17dcd54`,
`0x17dcf49` and `0x17de236`. TLS then observes the real embedding and hidden FCs
at returns `0x17db548` and `0x17db663`. It requires each original FC once,
N=K=2560, M=1/4, unchanged normal Q8 descriptors, D/initialized guard, the actual
Q8 M1/M4 kernel identities `0x18d6690`/`0x18d66f0`, their checked W/X/Y/K/N
arguments, grid160/block256, zero shared memory, default stream, and successful
native launch results. Hidden buffer pointers are captured at hidden FC entry
after native RMS sets them; they are not guessed from uninitialized entry globals.

Every head registers before its original body, including excluded counts and
nested calls. Any overlap invalidates discovery/arming. Any overlap after a
candidate copy attempt remains fatal through original full-head exit, including
successful native-output restoration. Discovery never attempts such copies.

Only after the original head returns successfully, with one matched native pair,
unchanged descriptor/device-buffer identities and a single in-flight head, does
the shim publish `observed.bin`. The original changes model `+0x220` after
seed-add, so the record stores both its pre-seed outer value and its actual
post-head value. Failure disables further observation and publication; discovery
has a hard one-head reservation and cannot retry or replace an existing record.

The discovery wrapper supplies a one-off cooperative arming rendezvous after
the original head returns and the observation publishes, before returning to its
native caller. It first writes and fsyncs the `native_discovery_published` receipt,
then releases the state mutex while retaining in-flight=1. For at most2 seconds
(`ARMWAIT_NS=2000000000`), it polls in bounded10-ms intervals for the existing
120-byte arm. Root can validate the observation/native receipt, complete relay
HELLO with those exact observation bytes, bind qualification manifests and publish
ARM in this interval without issuing another inference request or requiring an
external engine pause. No packet layout changes are introduced.

Every poll rechecks process/model/descriptor/device-buffer/slot/guard identity,
the unchanged observed file and disabled state. A valid matching arm is reread
and compared under the state mutex, its model/run checked, and the epoch descriptor
frozen before the deadline. The final synced receipt records
`native_discovery_armed`, `native_discovery_arm_timeout` or
`native_discovery_arm_rejected`. Timeout, invalid arm or overlap disables all
candidate writes; the wrapper still forwards its saved original result and errno.
The mutex remains available during polling, so concurrent or nested heads register
and invalidate the rendezvous. The existing200-ms candidate wait remains separate.
Root's owned-job deadline remains necessary for cooperative I/O/HIP bounds.

Any additional unarmed head after observation, unsupported
count/caller after observation, pointer/descriptor/model/process/slot/guard
change, armed-descriptor change, overlap, or backwards ABI/outer position disables
later candidate writes. Each excluded call still executes its native body once.

The C arm gate requires the unchanged on-disk observation and its internally
retained exact process, model, descriptor and device-buffer snapshot. Nonzero
manifest hashes alone cannot admit writes. The historical discovery token-host
pointer is evidence for that invocation; later heads may use a different checked
host token pointer. Tokens and positions naturally change between admitted heads.

These checks do not intercept native resets. A reset that preserves checked
identity fields and does not move a position backwards may remain undetectable.
Root must use a fresh serial owned epoch with no reset/reload after discovery;
reset interception and reset-lifetime qualification stay false. An old directory
or observation cannot be adopted into a new process or epoch.

## Fixed observed record

The exact little-endian Python layout is:

```python
OBSERVATION = struct.Struct("<8sII16sIIQQQiiiiiiIIQQQQQQQQQQ120s120siiiI32s")
# OBSERVATION.size == 464; final digest begins at byte432.
```

The natural Linux x86-64 C layout is asserted at compile time. Fields appear in
this order; all reserved fields are zero:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 8 | Magic `HGNFCO01` |
| 8 | 4 | Version1 |
| 12 | 4 | Record bytes464 |
| 16 | 16 | Nonzero run nonce, matching the directory suffix |
| 32 | 4 | Native Linux PID, positive int32 range |
| 36 | 4 | Reserved0 |
| 40 | 8 | Nonzero `/proc/self/stat` starttime ticks |
| 48 | 8 | Known native head return RVA |
| 56 | 8 | Native model pointer identity |
| 64 | 4 | Discovery sequence0, separate from SHADOW packet sequence0 |
| 68 | 4 | ABI count1 |
| 72 | 4 | ABI position |
| 76 | 4 | Host token value |
| 80 | 4 | Model slot `+0xa0` |
| 84 | 4 | Outer model position `+0x220` before seed-add |
| 88 | 4 | Actual wire68 (`D`) |
| 92 | 4 | Actual initialized guard byte, nonzero |
| 96 | 8 | Historical token-host pointer |
| 104 | 8 | e_norm device pointer |
| 112 | 8 | e_projection device pointer |
| 120 | 8 | h_norm device pointer |
| 128 | 8 | h_projection device pointer |
| 136 | 8 | Native seed destination device pointer |
| 144 | 8 | e descriptor address, exactly model+`0x908` |
| 152 | 8 | h descriptor address, exactly model+`0x980` |
| 160 | 8 | e raw weight pointer, descriptor+`0x10` |
| 168 | 8 | h raw weight pointer, descriptor+`0x10` |
| 176 | 120 | Full unchanged e host descriptor |
| 296 | 120 | Full unchanged h host descriptor |
| 416 | 4 | Original head result, nonnegative |
| 420 | 4 | Original head `errno`, signed int32 |
| 424 | 4 | Actual outer model position after original head |
| 428 | 4 | Reserved0 |
| 432 | 32 | SHA256 of exactly the first432 bytes |

All pointers transported to Python are opaque uint64 identities. Python must
never dereference them. The C reads only validated host pointer slots and host
descriptors; device tensor and weight pointers are not CPU-dereferenced. The four
tensor spans (5120/20480/5120/20480 bytes) must not overlap each other or the
20480-byte seed destination. Normal descriptors require zero `+0x00`/`+0x30`,
nonzero 16-byte-aligned `+0x10` and an overflow-safe 6,963,200-byte weight extent.
Pointer extents and observed routes do not establish GPU allocation or payload
identity; root's independent native/assets qualification remains required.

Publication uses a new 0600 exclusive regular `observed.partial`, checked write,
file fsync/close, `renameat2(RENAME_NOREPLACE)` to `observed.bin`, directory fsync,
and exact no-follow unchanged regular-file reread. Input opens are nonblocking
before file-type validation, so FIFO arm/observation/response names cannot stall
admission. The directory is owned0700. No existing final is overwritten. The
source retains at most one observation plus five fixed discovery/SHADOW contexts,
asserted below400 KiB total host staging. The existing four-request and bounded
200-ms cooperative response limits remain; root's external owned-job deadline
and resource guard remain necessary.

Root must also require `records.jsonl` outcome `native_discovery_published` and
its one-per-branch original/launch success counters before arming. A final file
alone is insufficient if directory fsync or final reread failed. The pure
coordinator validates supplied bytes and independently supplied owned-process
identity; it performs no live process or transport lookup itself. Canonical
model qualification must bind this observation digest, process/run identity,
the native model/assets, and the fresh external epoch. Graph qualification must
bind the graph/data lineage, CPU gate, provider/hardware receipts and that same
epoch. Those canonical manifest bytes and their qualification are root-owned.
Root must require the later `native_discovery_armed` receipt before treating
arming as accepted; the early publication receipt confirms discovery only.

The armed descriptor remains exactly120 bytes,
`<8sII16s16sQ32s32s>`, magic `HGNFCA01`, version1, reserved0, run nonce16,
epoch16, model pointer, model-binding32 and graph-binding32. The FC packet header
remains224 bytes with request-binding offset192; discovery does not change the
paired packet codec or introduce a skip path.
