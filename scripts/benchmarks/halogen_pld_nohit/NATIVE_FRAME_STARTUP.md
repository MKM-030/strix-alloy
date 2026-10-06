# Guarded preload startup caller

`native_frame_startup.cpp` adds the actual ordinary ELF preload constructor that
calls the frozen `native_frame_install::install_before_handler` core. Without
`HALOGEN_NOHIT_FRAME_INSTALL` it returns immediately. The exact value
`register-stock-v1` admits only `/proc/self/exe` basename `flash_serve` with first
command-line argument `--ck`; the preliminary `--resident-gib` invocation stays
stock. Requested guard failures exit 78 before serving. This follows the
existing guarded constructors in `halogen0162_mtp_route_tap.c` and the preflight
bridge, while retaining the frozen direct near entry/continuation mechanism.

The constructor supplies actual process observations, not caller qualification
flags. It requires the actual main TID and parses the single kernel `[stack]`
anonymous `rw-p` VMA containing its real RSP, passing the complete mapping to the
core. It does not substitute the larger RLIMIT/pthread stack reservation for
mapped memory, grow/probe the stack, install an alternate stack or change CPU
affinity. The core independently requires one task, checks the supplied mapping,
blocks catchable signals during publication, verifies the pinned engine/entry,
discovers the architectural xstate candidate and installs the stock observer.

The separate owned `StartupObservation` records that mapping, RSP/TID,
kernel-provided signal-frame minimum, derived reserve, observed CPU and complete
1024-bit main-task affinity set. `copy_startup_observation` is false when
disabled and publishes an immutable snapshot only after installation. The source
never calls the observer, interprets a captured address, reads native objects,
constructs a packet, selects a draft or supplies owner/prefix authority.

## First 264 bytes on the admitted native path

The frozen relay reserves 128 red-zone bytes and captures 136 bytes before its
configured lower-bound check. A startup mapping alone cannot prove those initial
264 bytes below every conceivable later entry. The retained normal native path
provides a stronger concrete fact:

| Retained source site | Stack/entry fact |
|---|---|
| `_start` `0x17194c4/17194cb` | Passes native main `0x1719630` to libc startup |
| Main `0x171b4e8..171b4ff` | Zeroes the serving-command descriptor at `A+0x140/+0x148/+0x150`, where `A=main RSP+0x180` |
| Main `0x171b9f1..171ba13` | Constructs this connection with an empty input string |
| Main CALL `0x171ba1a` | Calls handler `0x171c260` synchronously; native main CFA offset is `0x1250` |
| Handler `0x171c260..171c276` | Six pushes and `sub rsp,0x2648` establish outer `S`; CFA is `S+0x2680` |
| Handler `0x171c3bf/171c3c8` | Initializes the local request queue empty |
| Handler `0x171c679`, `0x171f82f` | Reads/parses the actual connection through `0x1731200` before command insertion can create a request |
| Reader `0x1731200..1731211` | CALL return plus six pushes plus `sub rsp,0x1048`; unconditional store `[rsp+0x30]` writes at `S−0x1050` |
| Native no-hit `0x172d3bd` | Uses that same fixed outer `S`, after a request exists and prefill/forward has completed |

The listener poller `0x1730890` does not append serving commands. The reader is
the source-pinned ordinary producer of owned connection command lines. The
known progress callable can also invoke that same reader; it does not create a
shortcut around its prologue. Request construction/insertion occurs later at
`0x172024c..17202ec` or `0x172a44b`. The first ordinary main socket request must
therefore follow a successful write at `S−0x1050`, which is 4,176 bytes below
outer RSP and beyond the 264-byte entry reservation. On the ordinary contiguous
Linux main-stack VMA, that successful write establishes mapped writable coverage
of `[S−264,S)`. Balanced returns preserve the fixed outer frame. The main accept
loop reuses its same CFA/frame depth, and the pinned native path does not shrink,
unmap or protect that stack VMA between the reader and seam.

This is a source proof for the normal main-to-handler socket route. It does not
admit debugger/injected calls, a foreign callable invoking the handler on another
stack, a stack switch, asynchronous seam reentry, or a foreign stack-permission
change. Those paths cannot be rescued by the relay's late bounds check. Later
ordinary VMA growth below the constructor snapshot does not widen the immutable
registered interval: the relay uses its existing stock bypass if the complete
XSAVE/callback/signal footprint lies below that registered low address. No new
claim is made that an observation will necessarily occur.

Retained evidence: exact ELF 26,052,768 bytes, SHA256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`; retained
host text 22,406,098 bytes, SHA256
`523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`; retained
frames SHA256 `03b9bef6fd4182013dcec8ecb9c850dcc5c5ae474b57ecf2925934359115b923`.
The existing host-publication and owner-serialization reports supply the main
frame, reader/queue and callback analysis. No new executable disassembly or
native execution was performed by this source author.

## Concrete signal and CPU limits

The constructor queries all catchable Linux signals through kernel
`rt_sigaction` with the eight-byte mask, including libc-reserved numbers. It
refuses preexisting user handlers; default and ignored dispositions require no
continuing user callback budget. Pinned main sets SIGTERM and SIGINT to the same
leaf `0x1730880` at `0x171b810/171b81f`, with flags zero and an empty signal mask.
The leaf stores one global word and returns without calls or stack allocation.
Each signal blocks itself; the two distinct signals can nest. The supplied
reserve is therefore `2 * (actual AT_MINSIGSTKSZ + 128)` for two kernel contexts
and two full user red zones. Missing or excessive actual auxv values fail before
installation. The [kernel auxv documentation](https://www.kernel.org/doc/html/latest/arch/x86/elf_auxvec.html)
defines this minimum as context-delivery space and explicitly requires adding
user handler consumption. This is not a budget for foreign handlers installed
later, SA_NODEFER, unusual restorer paths, handler reentry or runtime changes to
dynamic xstate permissions. The startup query cannot prove their later absence.

CPU affinity is observed without restricting native execution. The frozen core's
CPUID/XGETBV discovery describes its executing startup CPU, not every CPU in that
allowed set. Future affinity changes, migration consistency, debug/privileged
flags and actual noninitial AVX512/PKRU restoration remain unverified. The core
refuses observed active shadow stack; an unsupported status query does not prove
CET inactive. [Kernel CET documentation](https://docs.kernel.org/arch/x86/shstk.html)
places userspace enabling with the loader/application and exposes per-thread
status; neither a hardware feature bit nor an ELF note proves activation.

## Root build and normal lifecycle dependency

Root adds ordinary `native_frame_startup.o` to the four exact-basename installer
objects and uses the frozen link arrangement in `NATIVE_FRAME_INSTALL.md`. This
new object stays outside the copied island and keeps ordinary compiler unwind
tables. Root must inspect the same emitted DSO's constructor/init-array entry,
link resolution and ordinary CFI along with the already specified copied-island
branches, relocations and three FDEs. No source-only success claim substitutes
for that emitted inspection.

The real remaining startup dependency is the native lifecycle's actual dynamic
loader/preload set: all constructor work precedes the audited main handler and
no foreign constructor/callable enters that handler or changes its stack. The
runtime dependency is the real initialized process retaining the admitted main
stack route, known signal dispositions/masks, architectural xstate permissions,
CET state and a compatible CPU set. Root can qualify these during its next
already-authorized normal backend lifecycle: inspect real task maps/status,
auxv and main-task affinity after initialization, and exercise the source-pinned
main request/termination path in the same process while validating actual native
state and unwind behavior. A CPU-pinned qualifier can establish one observed
CPU without pretending it establishes an unrestricted multicore serving result.
This stock-only DSO by itself does not justify a hardware pilot; parent keeps
this source/build-only until a timely complementary proposer path exists.

No native integration, runtime capture or accelerator result is claimed here.
CPU performs startup and bounded register capture with additional overhead;
GPU remains the stock target continuation and NPU performs no work. Stock
register observation cannot improve acceptance. Readiness, placement, capture
cost, Prefill, Decode, acceptance and serving gain remain null/unmeasured. A
future proposer comparison must use total target time per actually committed
token, including preparation, transfers, verification, commit/replay and fallback.
