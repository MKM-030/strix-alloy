# Native frame adapter reuse and minimum observation path, 6 October 2026

**Existing shims provide reusable startup checks and nearby detour allocation, but
no complete interior GPR/RFLAGS/XSAVE relay.** A new, small Linux x86-64/SysV
assembly adapter is required to connect the reviewed no-hit consumer. The first
justified native observation is a finite stock-only frame pilot, after its source
and standalone real-register preservation checks pass. A ready producer, custom
selection, useful overlap and serving gain remain unqualified.

This is a source plan. Only this document was created. Work was local source,
retained disassembly/frame reads, static hashing and primary documentation reads.
No WSL, compiler, tests, runtime/model loading, hardware, serving request,
engine/process/lifecycle action, implementation change, staging or commit occurred.
The frozen `HANDOFF_REVIEW.md` and all existing implementation files were untouched.

## What can be reused

The scoped scan of `scripts/benchmarks` and `server` C/C++/header/assembly sources
found no implementation of XSAVE/XRSTOR/XGETBV, FXSAVE/FXRSTOR, PUSHFQ/POPFQ,
ENDBR64 or relay CFI; its only XSAVE match was the synthetic-frame comment.
The existing shims are function-entry replacements with normal C wrappers.
Their ABI preservation cannot be transferred to an arbitrary decoder instruction.

| Existing source and function | Useful part | Required adaptation or limit |
|---|---|---|
| `halogen0162_mtp_embedding_cache.c:473`, `same_stat`, `verify_hash`, `buffer_hash`, `contained`, `find_sites` | Stable file identity, exact ELF/file and mapped function hashes, PT_LOAD bounds/file offsets, unique main-executable site and ASLR base checks. | Pin the decoder/seam and every observer range, including mapped bytes, rather than the old head/FC ranges. These are startup operations. |
| Same file `prepare_detour:525`, `patch_detour:550` | Finite nearby `MAP_FIXED_NOREPLACE` search, exact placement check, rel32 range check, RW construction followed by RX verification. | Its displaced bytes are five bytes of complete prologue pushes. The no-hit instruction is seven bytes. Its memcpy patch is not an atomic hot-patch protocol. |
| `halogen0162_mtp_full_event_tap.c:540`, `install_hook` | Explicit complete-instruction relocation length and NOP filling beyond the five-byte branch. | Keep complete seven-byte seam coverage and reviewed branch entries. Replace the unconditional indirect continuation with a CET-compatible route. No generic relocation engine is present. |
| Embedding cache `install:576`; native-H replacement `install:696` | Default-off mode, serving-process identity, image checks before patching, fresh-process startup and refusal to combine incompatible taps. | The embedding native candidate is additionally compile-gated off at line583. Preserve default-off admission; do not reuse a serving process or hot-load the adapter. Constructor placement alone is not proof that no thread can execute the affected page. |
| Embedding cache `cached_head:406`, `context_live:308`, `retire_cache:433` | Explicit in-flight/reentry rejection, handler thread/slot binding, permanent retirement and retirement before known resource/context operations. | These use mutexes, `/proc/maps`, HIP resource operations and incomplete HIP interposition coverage. Reuse the policy, not these operations inside an interior hook; they do not establish request reset/birth coverage. |
| Native-H `finish:556` and retained owned launchers | Refuse teardown with in-flight work; retain owned handles/resources until confirmed completion. | Neither this destructor nor embedding teardown restores original hook bytes and safely unmaps a live trampoline. The minimal pilot retains code/metadata until owned process exit/reap. |

The old `absolute_jump()` emits `ff 25 00 00 00 00` plus an address. It preserves
GPRs but creates an indirect branch. It is not an XSAVE relay or automatically a
valid continuation under IBT. The wrapper's normal call/return relationship also
does not exist when a JMP enters the middle of the decoder.

## Concrete seam and unwind identity

The retained instruction is:

```text
0x172d3bd: 48 8d 85 e8 01 00 00    lea rax,[rbp+0x1e8]
stock continuation: 0x172d3c4
proposal success join: 0x172e95f
```

The existing consumer implements that displaced LEA on every decline. Its
success changes only saved RBX and `4*n` proposal bytes at original outer
`RSP+0x360`, then selects the existing join. The join begins with its own LEA and
initializes native constraint/count locals before returning to the existing
opening comparison and target verifier. No additional native protocol is needed.

Retained disassembly shows the decoder entry saving RBP/R15/R14/R13/R12/RBX and
subtracting `0x2648` from RSP. The FDE at `host-frames.txt:62776` sets the body CFA
to RSP+9856 (`0x2680`); the last CFA adjustment before the no-hit seam restores that
same offset. Thus at this seam the caller return is at original RSP+`0x2678`, and
caller RBX/R12/R13/R14/R15/RBP are at CFA−56/−48/−40/−32/−24/−16. Live RBP is the
request here, so a conventional RBP-based wrapper frame cannot be assumed.

The nested controller has a different body CFA, RSP+176 (`0xb0`), in FDE
`0x173b630..0x173bb86`. Its output block is controller `RSP+0x30`, while outer PLD
uses outer `RSP+0x1980`. Each future preview/seal relay needs its own pinned frame
descriptor and CFI. The same assembly preservation core may be shared; the stack
layout and displaced-instruction descriptor cannot be shared blindly.

## Minimum new source pieces

Proposed files alongside `halogen_pld_nohit` are a hand-written
`native_nohit_entry.S`, a local `native_frame_adapter.h/.cpp`, and a bounded native
relay harness. They are not implemented by this note. Keep `seam_contract.*` and
`native_outcome_handoff.*` intact; link and call their existing interfaces.

1. Startup code validates the exact image/mappings/sites and branch distances,
   discovers the real xstate configuration, establishes thread/stack/storage and
   signal/CET policy, resolves all helper references, and prepares immutable relay
   metadata and unwind tables before installation. Allocation, hashing, mapping
   inspection and symbol lookup belong here.
2. The JMP-entered assembly records original RSP, every intercepted GPR and flags
   before changing them. Before its first PUSH or CALL, a flag-neutral stack
   reservation must move below the original 128-byte red zone. Reserve a proved
   bounded area on the same registered native stack for this first implementation;
   startup must account for xstate, adapter frames, the consumer's large token
   bitmap/local copies and signal headroom. Do not guess that a 1 KiB buffer or
   the native decoder's frame size supplies that headroom. A separate stack would
   require a separately reviewed switch/unwind/signal contract.
3. Save enabled user xstate into separately owned, aligned real XSAVE storage
   before entering C/C++. Preserve the image as an opaque native save area. The
   assembly supplies the C ABI's required stack alignment, DF and x87-mode state
   after saving the intercepted state; the callback has a normal return only.
4. A local projection fills the existing `SavedFrame.gpr`, `rflags` and
   `outer_stack` from the real saved frame/original outer stack. Its synthetic
   `opaque_extended_state[1024]` is not the real XSAVE image and is never used to
   restore machine state. The native owner adapter supplies copied `SeamCapture`
   facts and its immutable ready packet or null, then calls the same
   `NativeOutcomeHandoff::consume_at_seam()`.
5. Validate the returned decision and apply a strict copy-back whitelist: on
   decline, copy only the consumer's saved RAX result; on selected success, copy
   only saved RBX and the `4*n` bytes at original outer RSP+`0x360`. Preserve all
   other intercepted state and native locals. Never copy the whole projected stack
   back into the native stack. Bounds, B, packet identity and one-shot admission
   still belong to the reviewed consumer.
6. Restore real xstate, all remaining GPRs, original RSP and permitted flags,
   then take a flag-neutral native continuation. Decline jumps to `0x172d3c4`
   after the projected LEA effect; selected success jumps to `0x172e95f`. Do not
   enter the stock zero-count path after a successful decision, and do not invent
   additional register/stack changes. The observational mode always supplies no
   eligible packet and therefore takes the exact stock result.

The source adapter must register a bounded invocation/nesting policy. A global
scratch image or ordinary lazily initialized TLS lookup is not enough: a signal
can interrupt the relay, and a handler can reenter intercepted code. Any nested
bypass must preserve its own real frame before declining; it cannot overwrite the
outer save area. The hot relay has no allocator, lock/wait, file output, device
work, dynamic loader call, native serving reentry or exception/nonlocal exit.

## Architectural checks that the implementation must satisfy

Require CPUID XSAVE and OSXSAVE before XGETBV(0), enumerate the supported user
mask, and preserve the complete enabled XCR0 mask in EDX:EAX. Derive standard-format
capacity from CPUID `(0xD,0).EBX`, validate component extents with subleaves, and
use 64-byte alignment. Record vendor/family/model and mask/size in the future
receipt; this audit queried none. Use the 64-bit XSAVE/XRSTOR forms for the x87
pointer format. These are architectural requirements, not a claim that this host
has a particular mask or area size. [Intel SDM Volume1, chapter13](https://cdrdv2-public.intel.com/671436/253665-sdm-vol-1.pdf)

Use baseline standard-format XSAVE initially. Initialize the whole save allocation
at setup, especially the header. Restore with the full enabled mask, including
components whose saved XSTATE_BV bit is zero; otherwise callback-created state can
survive. XGETBV(1) and the in-use bitmap are insufficient restore masks. Optimized
or compacted save formats need separate qualification. User XSAVE does not cover
FS/GS bases or supervisor state; preserve those by prohibiting mutation rather
than trying privileged XSAVES/XRSTORS in user code. [Intel XSAVE/XRSTOR definitions](https://cdrdv2-public.intel.com/671143/334569-sdm-vol-2d.pdf)

Linux dynamic xstate permissions and signal-stack sizing must be checked, rather
than assuming every XCR0 feature has ordinary first-use behavior. Do not request
new AMX permissions or alter process features for this pilot. Preserve enumerated
components generically or fail admission for an unsupported configuration.
Processor-specific x87 save/restore quirks also require a vendor-qualified policy;
the Linux restoration source contains an AMD workaround. No such processor parity
was established here. [Linux xstate documentation](https://docs.kernel.org/arch/x86/xstate.html),
[Linux FPU restoration source](https://raw.githubusercontent.com/torvalds/linux/master/arch/x86/kernel/fpu/core.c)

The SysV red zone belongs to intercepted code until protected. Align the callback
stack immediately before CALL, with stronger alignment if its stack argument
types require it; ordinary function-entry RSP assumptions do not apply to the
JMP-entered relay. Its unwind information must mirror the seam's actual CFA and
saved-register rules at every relay PC, including temporary stack movement and
both epilogues. Generated thunk pages need valid registered unwind descriptions,
not just CFI on a C helper. Normal callback return, signal interruption and
reentry must be covered; exceptions, longjmp/cancellation and debugger transparency
cannot be silently assumed. [x86-64 psABI register/stack/unwind rules](https://gitlab.com/x86-psABIs/x86-64-ABI/-/raw/master/x86-64-ABI/low-level-sys-info.tex),
[glibc nonlocal-exit details](https://sourceware.org/glibc/manual/latest/html_node/Non_002dLocal-Details.html)

PUSHFQ/POPFQ are not a literal full-RFLAGS round trip: RF/VM and privilege-dependent
bits have defined limitations. Save flags before flag-changing relay instructions;
restore ordinary arithmetic/DF state and use flag-neutral final instructions.
The first contract must explicitly exclude trap/debugger transparency unless a
separate mechanism proves it. [Intel PUSHFQ/POPFQ definitions](https://cdrdv2-public.intel.com/782151/253667-sdm-vol-2b.pdf)

Keep the original shadow-stack call/return relationship: JMP into the relay,
balanced real CALL/RET for its callback, JMP back. A fabricated return address and
RET continuation is unsuitable. If IBT applies, every indirect landing needs
ENDBR64. Prefer a nearby direct rel32 jump to each native continuation; an indirect
jump to `0x172d3c4`/`0x172e95f`, which are ordinary instructions, must not be reused
from the old trampoline. A far relay can return through valid ENDBR landing pads
near the engine followed by direct native jumps. CPU/ELF capabilities do not prove
thread activation; keep the actual Linux/glibc and per-thread status in the future
receipt. [Intel CET architecture](https://cdrdv2-public.intel.com/829568/829568-004.pdf),
[Linux shadow-stack activation and signals](https://docs.kernel.org/arch/x86/shstk.html)

## Startup, retirement and the smallest justified pilot

Adapt the existing exact-image/default-off startup pattern, with a source-reviewed
quiescence guarantee that no thread can execute the target code/page during
multi-byte patching. Retain original seven bytes, prepared branch bytes, mapped
hashes and permissions. Prepare everything before any patch. A partially failed
installation must stop the owned fresh process rather than expose a half-installed
observer. `__builtin___clear_cache` and a five-byte memcpy do not supply atomic
publication or an execution rendezvous.

For the minimum pilot, keep installed relay code, unwind metadata and storage for
the verified process lifetime. Retirement disables feed eligibility and uses a
state-preserving stock path; it does not unmap a relay that another instruction
pointer may still reach. Recovery is confirmed at owned process termination/reap.
Hot removal, arbitrary dlclose and restoration of live code bytes require a later
quiescent removal proof, not an ordinary preload destructor.

The next concrete source work is the assembly/local frame adapter and its bounded
Linux real-register harness. It should exercise the actual save/callback/restore
sequence with deliberately clobbered enabled user state, arithmetic flags, GPRs,
red-zone and stack canaries; test the init-state component case as well as nonzero
state. Compare architectural state, not uninitialized/reserved XSAVE bytes.
Validate the expected stock RAX change and the success whitelist through the same
consumer in this isolated harness, plus actual unwind/signal and CET behavior
under the admitted configuration. Compiler output and relay instructions need
independent review before native installation. No new predictor/transport/model
is necessary for that check.

After those gates, one bounded, owned fresh engine observation can justify the
first live seam check: install only the no-hit relay, cap at 64 observations for
one selected handler/thread, pass no custom packet, and always take stock resume.
Record image/relay pins, original-frame identities locally, XSAVE mask/size,
admitted CET/signal/stack configuration, observation count, decline reason,
bounded copied preservation evidence and owned cleanup. Publish no native object
or stack pointers to an external worker. Compare the short stock request's raw
output IDs and native counters with its matched stock control; no drafter or
packet transport participates. Unknown ownership prevents qualified packet truth,
but the disabled consumer needs no request dereference merely to replay the LEA.

That pilot would qualify only real frame preservation and the installed stock
continuation at this seam. It would not qualify constructor/reset/worker exclusion,
all preview/seal routes, a producer, or preview-to-next-no-hit readiness. Connect
the separate owner/reset/outcome adapter only after its exact mutation and worker
alias exclusions close. It must populate existing handoff inputs from copied
native observations and keep all qualification facts false until independently
proved. The user's standing lifecycle/measurement authorization remains valid;
these are source/implementation prerequisites, not a new permission request.

| Unmeasured quantity | Value |
|---|---|
| Actual enabled XSAVE mask/size and native state parity | null |
| Installed seam observations / custom selections | null |
| Preview-to-next-no-hit window / ready rate / cost C | null |
| Native/custom acceptance, Prefill, Decode, token rate, serving gain | null |
| GPU/NPU model, snapshot or contention measurements | null |

## Local evidence pins

| Source/evidence | SHA256 |
|---|---|
| `scripts/benchmarks/halogen0162_mtp_embedding_cache.c` | `4de8014f186ce7bc9e4507f127543b69564ee88d01ab97779aedc73fac4436d4` |
| `scripts/benchmarks/halogen0162_mtp_full_event_tap.c` | `f8ea59ef5903916527bae0a99fa6c5699d5a425cd70ba95255ad7f43f4aac8ce` |
| `scripts/benchmarks/halogen0162_mtp_route_tap.c` | `58c01bbc03e687746598bf09debec001c5cfa285944cc3361ccb88d0f7a6f17c` |
| `scripts/benchmarks/halogen0162_mtp_h_native_replace.c` | `899ef082b789d73c2d8eaefd07ca5483d69aff0090ad97ac453627e758c1e094` |
| Existing `halogen_pld_nohit/seam_contract.h` | `caa67ed65e991e2f8474e5ba16ae5c8a29cc74bc517d253fe95a330e152bc5f2` |
| Existing `halogen_pld_nohit/seam_contract.cpp` | `c03d638baee63cf1d26c69a8cca19dd5c06d4cede60ae46150dbbdcbc2adf0f7` |
| Existing `halogen_pld_nohit/native_outcome_handoff.h` | `5d4a42ad70edb14ae30f6c3043db4d889565031ef449de4ede9d6ce74536f835` |
| Existing `halogen_pld_nohit/native_outcome_handoff.cpp` | `9c642024ebd5a7b514a3acd598776f7657e5ff4ffcefad382e7647d7bef49cb8` |
| Frozen `halogen_pld_nohit/HANDOFF_REVIEW.md` | `ed9e9cb6ec5446eca2e954fa99b7cf222f22c1c2c319ee993850611487df4df5` |
| Retained `mtp-route-static-20261004/host-frames.txt` | `03b9bef6fd4182013dcec8ecb9c850dcc5c5ae474b57ecf2925934359115b923` |

The retained ELF/disassembly identities remain
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` and
`523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`,
respectively, as recorded in the existing native-owner and handoff audits. This
note adds no live image receipt. The primary references above establish ISA/ABI
requirements; they do not establish this machine's enabled state or close the
native ownership, installed-detour and serving proofs.
