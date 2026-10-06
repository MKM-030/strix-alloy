# Native host read issuer

`native_owner_read_issuer.h/.cpp` defines the previously absent `NativeReadBoundary`
friend of `NativeReadInterval`. It is default off and produces only value-owned,
unqualified no-hit observations. It supplies neither `OwnerIdentity` nor
`PriorPrefixAcknowledgement`, always passes `acknowledgement=nullptr`, and never
initializes a qualified handoff or supplies a proposer packet. Existing capture,
decoder, handoff, consumer, relay and installer files are unchanged.

The issuer performs real native reads only inside a privately constructed,
noncopyable `PausedNativeOwnerEntry`. It validates the source-pinned main/handler
stack binding: return at outer `+0x2678` is base `+0x171ba1f`, aggregate is outer
`+0x2800`, successfully constructed model is outer `+0x2d58`, connection is outer
`+0x2968`, and cache pointer agrees with retained main `RSP+0x38`. It binds the one
actual owned queue record to real `R15/RBP`, completed prefill and selected slot,
observes known progress data/manager/callable and null pending holder, actual null
disk holder and all five empty model hook pairs, then derives the exact suffix
from the request's native vector descriptor. It constructs the read interval in
the same lexical call and copies `0x1f8/0x902/0x308/0x180` bytes plus at most 512 IDs
through the unchanged `NativeOwnerCapture`. The native queue/main stack supplies
the hold; pointer equality, a sequence, a retirement notice or numeric mapping
bounds do not independently create that hold. Device/staging buffers are excluded.
This first reader also bounds vector allocation capacity to 262,144 IDs, beyond
the decoder's current-length bound. It deliberately declines a larger growable
allocation even when that allocation's current prefix would be legal.

The precise missing upstream connection is `NativeOwnerReadConnection`, the intended
external issuer of `PausedNativeOwnerEntry`. The observing `NativeReadBoundary`
is also a C++ friend but its frozen source never constructs that capability.
The connection must run a separate
synchronous trusted no-hit CALL while the real owner remains paused, after the
real register/extended-state preservation entry. The frozen register observer
does not allow native reads and cannot be expanded to call this issuer. Reading
the installer's saved first register image after native execution resumes cannot
construct a valid entry either. The separate entry's direct placement, stack
budget, state restoration, unwind and signal policy still need native review.
The returned owned observation is about 2 KiB and the call tree includes capture
and decoding. Root must record the emitted stack usage of this exact build and
its complete CALL tree; the frozen assembly leaf observer's 256-byte budget
cannot be reused for this entry.

Before that CALL, the connection must retain actual cache/model identity from
cache preallocation exit `0x173c3e9` (`RBX=C`, no allocation/start), or failed-init
continuation `0x173c3ab` after teardown/join and holder clear at `0x173c3a0`.
It must establish startup indexed-dispatch quiescence after any successful native
join and exclude new dispatch/other owner-thread execution throughout the CALL.
The genuine main-to-handler and ordinary no-hit stack path supply successful
construction-timer and forward copy-worker return provenance; nested progress
callbacks cannot construct an entry. Immutable pinned image/token definitions,
the actual held registered stack mapping and a unique owner-issued namespace
must also remain alive for the CALL. These are direct source/event connections,
not publicly constructible qualification flags. This source implements no
connection or detour for them and therefore cannot yet be enabled by the stock
register-only installer.

The issuer never mints request birth, epoch/reset/slot generations, loaded-model
authentication, full-prefix fingerprint or prefix continuity from its reads.
Those separate authorities remain required before handoff qualification. The
nonce/counter identifies this issuer's lexical observation only. Default-off or
missing-entry calls read no native memory; failed observations leave native state
untouched and return a value status. Exclusive handler ownership is required; the local
reentry guard is not a cross-thread lock.

Proof: [host-publication closure](../../../docs/research/halogen-pld-host-publication-20261006.md).
CPU does bounded host copy/decode. GPU/NPU proposal placement, Prefill/Decode,
acceptance, readiness and total time per committed token remain unmeasured.
The source author used only retained-source reads and source review: no compiler,
test, runtime, WSL, hardware, process action, staging or commit. Root owns the
single build of the frozen source.
