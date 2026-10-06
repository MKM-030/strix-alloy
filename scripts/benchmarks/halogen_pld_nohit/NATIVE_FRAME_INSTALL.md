# Stock register-observer installer core

`native_frame_install.h/.cpp`, `native_frame_install_link.S` and
`native_frame_install.ld` implement a real Linux x86-64 startup patch core for
the pinned no-hit seam. They preserve the frozen relay/configuration sources and
the owned-view-only observer ABI. The new observer copies only the first real
owned `RegisterImage`; it never follows its native pointer values. There is no
owner/prefix qualification, native object read, packet, proposal or success join.

## Actual source connection

The explicit startup API is `install_before_handler(StartupRequest)`. Both its
default-false `enable` field and exact
`HALOGEN_NOHIT_FRAME_INSTALL=register-stock-v1` are required. This core supplies
no automatic enabled constructor. A separately reviewed guarded preload caller
must invoke it before any native handler entry and supply actual stack bounds
and reviewed callback/signal budgets. Matching environment strings or numeric
budgets cannot prove native state or a read lifetime.

The core checks the actual `flash_serve --ck` process; the existing preliminary
`--resident-gib` route stays stock. It validates the exact 26,052,768-byte PIE ELF
and SHA256 `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`,
its RX PT_LOAD/file mapping, and a 32-byte file/live instruction window at
`0x172d3bd`. Its first seven bytes must be the displaced LEA. It uses the existing
preload convention of fatal requested guard failures before serving.

The linked island has fixed relative offsets and four page-aligned ranges:

| Copied range | Final permission | Contents |
|---|---|---|
| Code | RX | Unchanged relay, normal CALL/RET leaf observer, direct stock pad |
| Read-only data | R | Relay MXCSR constant and only these assembly objects' PC-relative CIE/FDE records |
| Configuration | R | Startup candidate copied once before publication |
| Owned observation | RW | One immutable register image after atomic ready publication |

The linker fragment extracts exact named object sections and appends a frame
terminator. It rejects copied-code cross references to ordinary `.text`, PLT or
GOT output sections. Startup rejects dynamic RELA destinations in the island;
REL/RELR encodings are deliberately unsupported. Only three simple PC-relative
FDEs are accepted: relay, ordinary leaf observer and stock pad. The pad retains
the native CFA `RSP+0x2680` and saved-caller rules after the relay restores RSP.

Following existing guarded preload allocation, the core searches 256 alternating
2 MiB offsets with `MAP_FIXED_NOREPLACE`. It copies the whole linked island into
RW storage, preserving internal RIP/direct-call/frame displacements. It patches
only the pad's rel32 sentinel to native stock `0x172d3c4`, then applies RX/R/R/RW
permissions. Copied frame records are registered with libgcc and their lookup
membership is checked before native text changes.

On the single actual main task, the core temporarily blocks catchable signals
at the kernel interface and verifies the supplied RW stack contains current
startup RSP. It publishes `E9 rel32 + NOP + NOP` over the seven-byte native LEA,
using an RW-to-RX transition without RWX, then checks bytes/permissions and restores
the previous signal mask. The frozen relay restores its own real state, replays
the LEA and directly jumps through the pad to stock. No FF25 far wrapper, native
indirect continuation, fabricated return or synthetic frame restoration exists.
The DSO, island, frame registration and observation remain alive until process
exit; there is no hot rollback/uninstall/destructor.

## Build and review boundary

Root owns every build, inspection, process and installation. Compile exact
basename objects `native_frame_relay.o`, `native_frame_config.o`,
`native_frame_install.o`, `native_frame_install_link.o` with PIC; use C++20 and
`-Wall -Wextra -Werror` for C++. Keep normal EH tables for installer/config
functions. Link the shared DSO using:

```text
-Wl,-T,native_frame_install.ld,-z,max-page-size=4096,-z,separate-code,-z,now,-z,relro
-Wl,--no-undefined
-ldl -lcrypto -lgcc_s
```

Do not pack relative relocations. Root must inspect relocation tables, every
copied direct/RIP-relative reference, page layout, observer/pad instructions and
all copied CFI in the **same emitted DSO**, then inspect the actual startup
caller. Source checks are not emitted-object evidence. The source author ran no
compiler, linker, WSL, test, runtime, hardware or lifecycle action.

The provided API is installation progress; its real preload invocation is still
an independent required connection. Native register/xstate preservation at the
actual seam, first 264 stack bytes, complete callback/signal headroom, signal
unwinding, kernel/loader/CET behavior, debug/privileged flags and CPU migration
remain root qualification work. The core refuses observed active shadow stack;
an unsupported status query supplies no new CET proof. The prior limited real
register qualifier remains limited, including its noninitial AVX512/PKRU gaps.

## Separate future read and serving effects

The positive-owner audit supports an independently established later host read
interval; it does not relax this observer ABI. A separate installed read entry
must prove main/queue/model holds, the five absent optional model hook pairs,
worker/backend completion, reset/birth/slot continuity, and a prior complete
prefix acknowledgement. Later previews/seals must observe actual authoritative
host output IDs. Controller draft width above three requires prior retirement
for the existing four-output handoff. No such issuer or outcome entry is added
here. Commit return alone does not establish device rollback completion.

CPU performs this bounded register capture and adds overhead to native serving.
This stock-only connection cannot improve acceptance and provides no measured
Prefill or Decode benefit. GPU/NPU could later perform independent proposal/state
work with qualified owned publication; neither executes here, and their readiness
or placement is unmeasured. The useful future comparison is total target time per
actually committed token, including private preparation, transfers, verification,
commit/replay and fallbacks. Capture cost, readiness, acceptance, committed tokens
per second, Prefill, Decode and serving gain all remain **null / unmeasured**.
