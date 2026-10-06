# Native stock-only frame relay source

`native_frame_relay.S` is a real Linux x86-64/SysV JMP-entry assembly core, with
`native_frame_relay.h` describing its local saved-frame ABI and
`native_frame_config.cpp` discovering startup CPUID/XCR0 configuration. It is
default off and **uncompiled, unexecuted and not native-qualified at this source
handoff**. The core has no installer, production observer, native dereference,
packet, model or hardware work. The two standalone harness files define only a
test observer/resume. The frozen handoff/consumer/capture components are unchanged.

## Entry, storage and continuation

The only admitted frame descriptor is the pinned outer decoder no-hit body:
CFA=`original RSP+0x2680`, return=`CFA-8`, caller RBX/R12/R13/R14/R15/RBP at
`CFA-56/-48/-40/-32/-24/-16`. Live RBP is the request, so the relay cannot enter
as a normally CALLed function or use its incoming RBP as a wrapper frame pointer.
The nested controller has another CFA and is explicitly unsupported here.

The first stack movement is `LEA RSP,[RSP-128]`; it changes no flags and protects
the complete original red zone. PUSHFQ and all 15 non-RSP GPR saves plus an
original-RSP slot occupy another 136 bytes. Only after capture does the relay
calculate original RSP and use saved RBP as a stable frame base. Register order
matches the existing consumer's GPR array. Saved-register/flags views and the
actual XSAVE image are invocation-owned on the current native stack, never TLS
or shared global scratch.

CFI starts with the exact native CFA/caller-save rules and changes at every
PUSH/LEA/POP boundary. During dynamic allocation and the callback it describes
CFA=`relay frame base+0x2788`; before restoring live RBP it switches back to the
matching RSP rule. Original native caller slots remain untouched throughout.
Generated unwind tables and actual unwind/signal behavior still require review
and a standalone real-register qualifier. No exception, longjmp, cancellation
or debugger/trap transparency is admitted.

Each enabled invocation reserves the actual CPUID-derived standard XSAVE extent
plus 128 bytes of metadata separation and at most 63 bytes of alignment loss,
then aligns RSP to 64. It zeroes the complete XSAVE image, saves with XSAVE64 and
the complete enabled XCR0 mask. DF is cleared after its capture for image zeroing;
x87 mode and masked C MXCSR are established only after XSAVE. A hidden directly linked observer receives an immutable local
`NativeFrameView`. Its genuine CALL/RET has a 16-aligned pre-CALL stack. After
return, XRSTOR64 requests the **same full mask**, including components whose
XSTATE_BV bit is zero; then every original GPR, ordinary arithmetic/DF flags and
original RSP are restored. The original displaced `LEA RAX,[RBP+0x1e8]` is the
sole intended GPR/native-stack mutation. The AMD x87 metadata caveat below remains.

Required unresolved hidden symbols are:

- `halogen_nohit_frame_observer(const NativeFrameView*) noexcept`: a normal SysV
  observer with a source-reviewed bounded call tree. It may inspect owned copies;
  it must not mutate the image/view, change FS/GS/process state, dereference
  native objects, reenter serving, or exit nonlocally. Its stack budget includes
  its call frames and red zone. No lazy linker, libc/runtime/device work belongs
  in this first observer. It must retain stack access when PKRU is enabled.
- `halogen_nohit_native_stock_resume`: a direct link-time target at stock
  RVA`0x172d3c4`, or a separately reviewed near landing pad followed by a direct
  native jump. The relay has ENDBR64 and uses only direct callback/continuation
  branches, with no PLT, forged RET or indirect jump into a native instruction
  interior. Link/placement must reject out-of-range rel32 branches. Original
  shadow-stack CALL/RET ownership is retained.

There is no success/packet route or copy-back whitelist implementation yet. A
later local adapter can project the real saved registers into the same existing
consumer; its synthetic 1024-byte opaque array must never restore machine state.

## Configuration and exact remaining limits

`discover_configuration()` performs CPUID XSAVE/OSXSAVE checks before XGETBV(0),
records vendor/family/model/stepping, checks the complete mask against CPUID user
support, reads standard extent `(0xD,0).EBX`, and verifies enabled component
extents/nonoverlap. Capacity is bounded at 64 KiB. This first core recognizes
x87/SSE/AVX/AVX512/PKRU; it refuses AMX/XFD, APX additional GPRs, MPX, supervisor
components and unknown enabled user features. No new Linux xstate permission is
requested. A refused candidate stays disabled.

An explicit startup request provides a registered writable, resident stack range,
reviewed callback budget and actual signal reserve; discovery checks their finite
dimensions. The assembly checks original RSP against that range and worst-case
headroom before dynamic XSAVE allocation or callback. Nested invocations have
separate images; insufficient headroom or an unregistered signal stack takes
the state-preserving stock bypass. Every entry still requires **264 writable
bytes below original RSP for initial capture**, even on bypass. The owner must
prove this for admitted native and signal/nested entry paths before use.
There is no mapping/guard-page/signal registration implementation in these files.
CPU migration/configuration, stack residency/permissions, PKRU-safe observer
memory access, immutable publication and signal policy remain external startup
proofs. Configuration publication is permitted only under complete entry
quiescence; no hot enable/disable/removal protocol is supplied.

AMD admission requires CPUID`0x80000008.EBX[2]` (XSaveErPtr). AMD APM Volume2
Rev3.44, March2026, §11.5.10 describes restoration with that bit set, while XSAVE
can canonicalize x87 pointer fields to zero without pending #MF. Consequently,
**this full-mask core does not prove literal preexisting physical FIP/FDP/FOP
metadata parity on AMD**. Literal physical-metadata requests are refused for
every vendor; generic CPUID and XSAVE are insufficient to qualify that scope. The
architecture-defined XSAVE candidate is experimental and cannot be promoted to
a full native preservation qualifier by its status alone. Older conditional
pointer implementations are refused, rather than using Linux's leakage sanitation
as an exact-preservation mechanism.
[AMD OSRR p68](https://www.amd.com/content/dam/amd/en/documents/processor-tech-docs/programmer-references/56255_OSRR.pdf),
[AMD current APM Volume2 §11.5.10](https://docs.amd.com/api/khub/documents/sD1_QL~h4Afq2_tvzxqqSQ/content),
[Linux restoration source](https://raw.githubusercontent.com/torvalds/linux/master/arch/x86/kernel/fpu/core.c).

PUSHFQ/POPFQ preserve the admitted arithmetic/DF contract, not literal RF/VM,
privileged flags, single-step or debugger behavior. User XSAVE excludes FS/GS
bases and supervisor CET state; their preservation relies on prohibited mutation
and balanced control flow. Actual Linux/glibc thread CET status, signal frame size
and installation/relocation/unwind registration remain unqualified.

The next runnable step is a source-reviewed, owned standalone Linux CPU qualifier
with a real native-shaped frame and directly linked observer/resume labels. It
must inspect emitted instructions/CFI, clobber admitted user state, exercise init
components, compare ordinary flags/GPRs/red-zone canaries/stock RAX, and establish
the honest AMD architectural-versus-physical x87 boundary. No compiler, test,
runtime, WSL, serving/engine/lifecycle action or GPU/NPU work ran in this source
pass. No source-only serving gain or ready-producer claim follows.

| Measurement | Value |
|---|---|
| Actual CPU XSAVE mask/size / real register parity | null |
| Native installation / observations / selections | null |
| Preview-to-no-hit window / producer readiness | null |
| Serving Prefill / Decode / acceptance / token rate / gain | null |
| GPU/NPU work or contention | null |

Frame/disassembly facts and the outstanding installer policy come from the
[native frame adapter plan](../../../docs/research/halogen-pld-native-frame-adapter-20261006.md),
SHA256`46b79139e5cd35c352809fe540131189e047625b8a33b83518207b544169b52f`.

## Standalone real-register harness source

`native_frame_harness.cpp/.S` provides three focused cases: disabled with
noninitial x87/SSE/AVX state; enabled with that noninitial state; and enabled
with actual XRSTOR-initialized state (XSTATE_BV clear). A genuinely CALLed mock
handler saves RBP/R15/R14/R13/R12/RBX and allocates0x2648, giving exactly the
retained body CFA0x2680. It JMPs into the **same relay** and supplies a direct
mock stock-resume label. Independent RIP-relative snapshots observe all actual
GPRs, original RSP, ordinary arithmetic/DF flags and128bytes of red-zone canaries.
The normal leaf assembly observer has no runtime/helper/syscall calls; it records
the owned captured image and changes caller GPRs and x87 numeric/SSE/AVX state.

The xstate oracle compares architectural contents with init components
normalized, ignores undefined/reserved/empty-register payload and excludes literal
x87 FOP/FIP/FDP metadata. MXCSR remains initial throughout; nondefault control,
rounding and exception state are not exercised. Enabled AVX512/PKRU components
are restored/compared if present, but this observer does **not** deliberately
populate or clobber their noninitial state. Thus even a future passing receipt
would establish these three bounded cases, rather than every enabled component,
physical metadata, signal/unwind execution, active CET or installed native parity.
Startup obtains actual pthread stack bounds; the mock restores its normal
caller's architectural xstate and callee GPRs before returning. Root owns any
later guarded build, emitted-instruction/CFI review and execution; none ran here.
