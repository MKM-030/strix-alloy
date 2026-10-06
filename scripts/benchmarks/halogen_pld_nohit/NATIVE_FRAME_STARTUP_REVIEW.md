# Independent guarded-startup review

No source blocker was found in the frozen [startup header](native_frame_startup.h),
[constructor](native_frame_startup.cpp) or [startup rationale](NATIVE_FRAME_STARTUP.md).
This approval is limited to the guarded, default-off caller of the existing
stock-register installer. It does not qualify an emitted DSO, live native-state
preservation, native-object reads, ownership, a proposer or a serving benefit.
Only source and retained ELF/text/frame reads were performed. No compiler,
tests, runtime, hardware, WSL, process or lifecycle action was used.

## Startup observations and loader boundary

An absent `HALOGEN_NOHIT_FRAME_INSTALL` returns before startup work. The admitted
serving invocation has executable basename `flash_serve`, first argument `--ck`
and exact mode `register-stock-v1`; resident inspection remains stock. Requested
guard failures terminate before serving. The constructor samples its real RSP,
requires the main TID and reads the single anonymous `rw-p` `[stack]` VMA from
`/proc/self/maps`. It supplies that complete mapped interval, without replacing
it with a reservation, probing/growing the stack or installing an alternate
stack. The core independently checks current RSP and mapping, requires one task,
and blocks catchable signals during patch and island publication before
restoring the previous mask.

The release/acquire publication of `StartupObservation` follows successful
`InstalledStockObserver`; no later writer exists in this source. Its contents
are a constructor snapshot. They do not establish later stack permissions,
signal policy, CPU state or native ownership. The actual preload set and loader
constructor order remain dependencies: later foreign constructor work must not
enter the patched handler on another stack or replace the assumed serving
conditions. Neither the basename check nor the one-task check proves that
condition.

## The unconditional entry saves have a concrete ordinary-route basis

The relay moves below the native red zone and reserves/saves another 136 bytes
before checking configured headroom: `128 + 136 = 264` bytes. The late check
cannot protect those first stores for arbitrary entry. The constructor mapping
alone is therefore insufficient. The retained native socket route supplies the
missing source fact.

The executable `PT_LOAD` has file offset `0x17184b0`, RVA `0x17194b0`, size
`0x1ba8d0` and flags `5`; the reviewed windows use ELF offset `RVA - 0x1000`.
The following bytes were independently read from the pinned ELF and agree with
the retained text:

| RVA | Verified bytes / fact |
|---|---|
| `0x17194c4` | `48 8d 3d 65 01 00 00 ff 15 af fc 1b 00`: supplies main `0x1719630` to libc startup |
| `0x1719630` | `55 41 57 41 56 41 55 41 54 53 48 81 ec 18 12 00 00`: six pushes, allocation `0x1218` |
| `0x171ba1a` | `e8 41 08 00 00`: synchronous handler call, return `0x171ba1f` |
| `0x171c260` | `55 41 57 41 56 41 55 41 54 53 48 81 ec 48 26 00 00`: six pushes, allocation `0x2648` |
| `0x171c679` / `0x171f82f` | `e8 82 4b 01 00` / `e8 cc 19 01 00`: calls to connection reader `0x1731200` |
| `0x1731200` | `55 41 57 41 56 41 55 41 54 53 48 81 ec 48 10 00 00 48 89 74 24 30`: reader prologue and unconditional store |
| `0x1730880` | `c7 05 7e a7 1a 00 01 00 00 00 c3`: signal leaf stores one global word, then returns |

The main command vector is zeroed at `0x171b4e8..171b4ff` with XMM0 previously
zeroed at `0x171b40b`. Main constructs empty connection input at
`0x171b9f1..171ba13`, and the handler initializes its request queue empty at
`0x171c3bf/171c3c8`. The reviewed empty-state byte windows agree with the text.
The [owner-serialization analysis](../../../docs/research/halogen-pld-live-owner-serialization-20261006.md)
establishes the reader as the ordinary command producer, before request
construction/insertion at `0x172024c..17202ec` or `0x172a44b`; the listener
poller does not append those commands. The progress path also calls this same
reader, rather than bypassing its prologue.

Let `S` be fixed handler outer RSP. Retained CFI gives main CFA offset `0x1250`,
handler CFA `S+0x2680`, and reader CFA offset `0x1080`. The direct reader call's
return address, six pushes and `0x1048` allocation put reader RSP at
`S-0x1080`. Its unconditional `[rsp+0x30]` store writes `S-0x1050`, 4,176 bytes
below `S`, before an ordinary socket request can reach the no-hit seam. On the
contiguous writable main-stack VMA, successful execution of that deeper store
establishes writable coverage of `[S-264,S)`. Balanced calls retain the outer
frame. This reasoning excludes injected/foreign handler calls, stack switches,
asynchronous seam reentry and foreign mapping changes.

The registered constructor VMA may remain narrower than later ordinary stack
growth. The full check still requires XSAVE bytes plus `264 + 128 + 63`, the
callback budget and signal reserve inside that immutable interval. Failure
takes stock bypass; capture is not guaranteed. The 256-byte callback budget
applies to the present register-only assembly leaf. It cannot qualify the
separate host-copy issuer or another callback.

## Signal and scheduler dependencies

Kernel `rt_sigaction` queries include all catchable signals, including
libc-reserved numbers, and reject preexisting custom handlers. These queries
precede the core's signal block and remain observations, not a continuing
policy. Pinned main supplies leaf `0x1730880`, an empty mask and source flags
zero to SIGTERM/SIGINT at `0x171b810/171b81f`. With each signal blocking itself,
the two known leaves permit two nested deliveries. The source-derived reserve
`2 * (actual AT_MINSIGSTKSZ + 128)` accounts for two kernel contexts and user red
zones. The [kernel auxv documentation](https://www.kernel.org/doc/html/latest/arch/x86/elf_auxvec.html)
distinguishes context-delivery space from additional user-handler consumption.

Libc may add a restorer and kernel flags to these source `sigaction` requests.
Actual restorer/unwind behavior, later handlers or masks, `SA_NODEFER`, alternate
stacks, reentry and changed xstate permissions remain unqualified. Source flags
zero must not be reported as observed raw kernel flags.

Affinity is recorded without pinning. The sampled CPU precedes core
CPUID/XGETBV discovery and need not be the CPU executing that discovery; it also
does not prove migration consistency during discovery or later capture. The
1024-bit allowed set is not proof that all its CPUs share the required xstate
behavior. Actual compatible CPU coverage, noninitial AVX512/PKRU restoration,
debug/privileged flags and per-thread CET need later qualification. The
[kernel shadow-stack documentation](https://docs.kernel.org/arch/x86/shstk.html)
places enabling with loader/application code; ELF notes and hardware capability
bits do not prove activation. Refusing observed active shadow stack does not
turn an unsupported status query into proof of inactivity.

## Required qualification remains with root

Root must inspect the same emitted DSO's constructor/init-array connection,
ordinary unwind tables, link resolution and existing copied-island layout,
branches, relocations and FDEs under [the installer requirements](NATIVE_FRAME_INSTALL.md).
Later live qualification must cover the real loader/preload set, initialized
main-stack route, signal dispositions/restorers, xstate permissions, CET and
executing CPU set, plus actual preservation and unwind behavior. This review
does not authorize or justify an isolated hardware pilot. The stock-only DSO
remains source/build-only until a useful timely complementary proposer exists.
Startup and capture add CPU overhead; acceptance and serving gain remain
unmeasured.

## Frozen inputs

| Input | Independently verified SHA256 |
|---|---|
| `native_frame_startup.h` | `6c1148c8ec746b193b7613d35fbd4beec911ab9901ab95b460ba4a47257d2edf` |
| `native_frame_startup.cpp` | `d18591aa560c3b280698909bddeb8584a29603cf0a065b78828d9ad4abfdae91` |
| `NATIVE_FRAME_STARTUP.md` | `b9731cc69812e8f0a3a5c1d0d5df1a9006178ddc0e36464a210c5714be9f8e31` |
| ELF, 26,052,768 bytes | `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` |
| Retained host text, 22,406,098 bytes | `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` |
| Retained host frames | `03b9bef6fd4182013dcec8ecb9c850dcc5c5ae474b57ecf2925934359115b923` |

The ELF is `backends/halogen-wsl2-0.16.2/.local/flash_serve`; text and frames
are `host-text-disassembly.txt` and `host-frames.txt` in
`server/.local/optimization9h-20261004/mtp-route-static-20261004/`.
