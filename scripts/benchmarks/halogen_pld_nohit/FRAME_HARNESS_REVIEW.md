# Independent real-frame qualifier and launcher review, 6 October 2026

**No remaining blocker was found for the three bounded standalone cases and
their guarded launcher.** Source and retained build-artifact inspection support
that narrow disposition. Root's separate execution receipt reports 18 checks,
zero failures and exit 0 for the same hashed executable. This does not qualify
literal physical x87 metadata, all enabled xstate contents, native installation,
signal/unwind execution, active CET, ownership or proposal readiness.

The reviewer read `native_frame_harness.cpp/.S`, the final
`run_native_frame_harness.py`, its pinned Windows ownership/memory helpers,
the amended `FRAME_RELAY.md`, and root's retained build/run receipts,
instruction/frame/ELF dumps. The reviewer performed only reads, local hashes and
review-document writes. Root performed the build and one execution. No compiler,
test, WSL, engine, model, hardware, serving or lifecycle action was run by the
reviewer, and no implementation was edited.

## Source preservation checks

The genuinely CALLed mock handler saves RBP/R15/R14/R13/R12/RBX and reserves
`0x2648`, reproducing the native `RSP+0x2680` body CFA and saved caller slots.
It JMPs into the same reviewed relay, not an alternative preservation function.
Its hidden direct stock-resume label is inside that mock handler and takes a
normal epilogue/RET only after recording the restored state. It is not the
production engine continuation at RVA `0x172d3c4`.

Independent RIP-relative MOVs snapshot all actual GPRs and original RSP before
and after the relay. The snapshot's PUSHFQ extraction protects the original red
zone with flag-neutral LEAs and restores RSP. Distinct GPR seeds expose a wrong
save/pop order; expected RAX is separately computed as saved RBP plus `0x1e8`.
All 128 original red-zone bytes receive a canary and are copied after resume.
The ordinary arithmetic/DF bits are deliberately set before entry, compared
afterward, and DF is cleared before returning to C++.

The observer is a normal leaf assembly callback: it copies the owned captured
integer image, preserves SysV callee GPRs and RSP, and deliberately changes
caller GPRs, x87 numeric state and SSE/AVX registers. It has no CALL, libc helper,
syscall, allocator, lock or serving reentry. Its final RET balances the relay's
CALL. The observer sink is global only in this explicitly single-threaded
standalone probe; this supplies no production sink/reentry qualification.

Before seeding, the mock saves its normal caller's architectural xstate and
loads an explicitly initialized XSAVE image with XSTATE_BV zero and initial
MXCSR. It independently captures before/after XSAVE images and restores the
caller image before the mock's genuine RET. The three cases are exactly:

| Case | Intended observation |
|---|---|
| Disabled, noninitial x87/SSE/AVX | Integer bypass preserves state and never calls the observer. |
| Enabled, noninitial x87/SSE/AVX | Save/callback/restore recovers the deliberately clobbered contents. |
| Enabled, initial xstate | Components absent from the before XSTATE_BV return to architectural initial contents after the observer creates state. |

The xstate oracle normalizes components marked initial rather than comparing
undefined or reserved save bytes. It compares x87 control/status/tag and occupied
80-bit logical stack values, using TOP to map the abridged physical tags. This
mapping agrees with the kernel's corresponding FXSR tag conversion.
[Linux FXSR register/tag conversion](https://github.com/torvalds/linux/blob/master/arch/x86/kernel/fpu/regset.c)
FOP/FIP/FDP, undefined empty-register payload and reserved fields are explicitly
excluded. MXCSR stays at `0x1f80`: nondefault controls/exceptions are untested.
Enabled AVX512 and PKRU are included in architectural comparison, but their
noninitial contents are not deliberately seeded/clobbered. The actual recorded
mask `0xe7` includes AVX512 and excludes PKRU. The 18 checks are sufficient
evidence for these cases only; no expanded matrix is inferred or requested.

## Guarded launcher

The provisional helper-import issue is fixed: helper hashes are verified before
those modules execute. Source pins are checked around every stage. Build-only is
the default. Separate execution requires an artifact-confined build receipt
and its independently supplied hash, completed unexecuted build status, identical
source pins, confirmed Windows job closure and the artifact-confined executable's
matching hash. The final compiler command includes `-pthread`; build and
instruction/frame/ELF inspection occur before the separate execution invocation.

Each Windows WSL child is created suspended in its owned job. The launcher checks
22 GiB physical/commit reserves before launch and before resume, verifies retained
handle identity, then samples 18 GiB reserves around bounded 250 ms waits. The
final post-wait sample gap is included. Normal, exception and constructor
`error.owner` recovery paths retain handles for close/retry. There is no unrelated
process lookup/termination. A resumed Windows harness launch is distinct from
confirmed successful Linux harness execution; failed/ambiguous execution is null.

Linux timeout supervises its monitored child and same-process-group descendants
with finite TERM/KILL deadlines while the monitor remains effective. Escaping
groups, monitor death and external WSL cancellation are not proved closed. The
receipt explicitly scopes `all_owned_jobs_closed` to Windows jobs/handles and
states these Linux limits. Those limits remain in the accepted disposition.
[GNU timeout manual](https://www.gnu.org/software/coreutils/manual/html_node/timeout-invocation.html),
[GNU timeout implementation](https://github.com/coreutils/coreutils/blob/master/src/timeout.c)

## Retained emitted artifact and root outcome

The build-only receipt has zero-exit tool-hash, compile, instruction, frame and
ELF stages, no errors and confirmed Windows job closure; it records no harness
launch/execution. Current code/launcher hashes match both receipts. The built
executable's current hash matches its build and execution receipts.

Retained instructions show a 290-byte relay at `0x13a0..0x14c2`, the expected
capture/restore order, full-mask XSAVE64/XRSTOR64, real direct
`CALL 0x1476→0x23e0` to the leaf observer and direct
`JMP 0x14bd→0x2301` to the mock stock label. These branches have no PLT/indirect
interior detour in this artifact. The emitted relay CIE/FDE starts at CFA 9856,
changes through capture to 10120, uses RBP during dynamic storage/callback, then
returns through RSP to 9856. The mock's frame/epilogue rules agree. This checks
the retained emitted descriptions, not actual unwind execution. ELF reports an
RW, nonexecutable GNU stack and only libc as a needed library. Its GNU property
states the baseline ISA, so ENDBR instructions/compile flags do not establish
active CET.

Root's separate invocation executes that same pinned binary and retains:

| Observation | Retained value |
|---|---|
| Harness | Exit 0; three completed cases; 18 checks; zero failures |
| CPU configuration reported by harness | AMD, family 26, model 112, stepping 0; XCR0 `0xe7`; standard XSAVE 2432 bytes; architectural scope |
| Minimum physical / commit headroom | 33,582,903,296 / 132,302,245,888 bytes |
| Maximum recorded sample gap | Approximately 0.235 seconds |
| Windows ownership | Harness job/handles closed; no receipt errors |
| Engine/server/GPU/NPU | No engine loaded, server change or GPU/NPU execution reported |

The receipt's pass is retained root execution evidence, not a new reviewer run.
No repeated unchanged qualifier run is needed for this disposition. Native
production continuation/installation, full enabled-component noninitial parity,
literal metadata, signals, CET activation, capture ownership, readiness and
serving Prefill/Decode/acceptance/gain remain unqualified.

## Pins

| Source/evidence | SHA256 |
|---|---|
| `native_frame_relay.h` | `f6aaf827d5187a3eb47bda94bf9f19d6eae29664251ede96c29b7d84e9c74cbe` |
| `native_frame_relay.S` | `b9bbbe04ce46a5c61fefa08fbdac56fcaffd5c9489e7c764c1e9dd4ae8d0fba5` |
| `native_frame_config.cpp` | `8bcc5d760cc6204a7896d8a1ddd866f1bb6b63fdb6a6584a5587a9e65447b57d` |
| `native_frame_harness.cpp` | `68b268b9ceb79f60f77db92b915ff4de0efec687013d14c96ffa163563d514bc` |
| `native_frame_harness.S` | `ee81be186d934ff62cdf1516fde6bb2805d493063a71d18635398cb5481a996e` |
| `run_native_frame_harness.py` | `c1b347f68277f2e98c0246e600af4483a6c4da51340ac728fee54f1f376083b1` |
| `FRAME_RELAY.md` | `f3db49aab6bac77f856528940bebebda781b0c59530d808fa0b8ce4c542df999` |
| Build `20261006-085604-native-frame-19bb0244/result.json` | `ef74171e579136159ef29050a5644319fc67386b7c007a4eb6e5271b516f5956` |
| Built executable `native-frame-harness` | `ee6116a9aa3036c4aa1c5595a25f187fdfe5459ece803742e1bb63c0f607a7ba` |
| Build `instructions.stdout.txt` | `0adc492eeb82b33f4cfd85d9ed0b93f9c94b44fdb5aaf7d3cd29ce5768bb8788` |
| Build `frames.stdout.txt` | `3473933ab3b1f42929360456ab75b13c45dfecfdd51636960b6388deb93970e6` |
| Build `elf.stdout.txt` | `e3213f07f1b09272cabb9c7c0d1beedaa298a479d6ef087ac9623871b3523ae3` |
| Run `20261006-085816-native-frame-39d2732d/result.json` | `234609600e715fb383e3cb81cb29682601d300d5343f733df6be14c20b4fc970` |
| Run `harness.stdout.txt` | `099dec26b14da8714c274724a399590c1fd60a34b5d28537a292e8a7660723a2` |

This document is the single independent qualifier/launcher review. The original
core source review is preserved separately in `FRAME_RELAY_REVIEW.md` with its
pre-execution scope and updated documentation pin. Existing frozen seam/handoff
implementation and earlier handoff/capture reviews were not changed.
