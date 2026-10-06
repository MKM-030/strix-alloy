# Independent stock frame relay source review, 6 October 2026

**No remaining blocking source defect was found in the frozen stock-only core
under its documented entry, immutable-configuration and normal-return observer
contract.** This disposition was made from source before the coordinating
agent's standalone build/run. It supplies no native admission, installation,
real preservation or literal physical x87 metadata qualification. Subsequent
standalone artifacts have their own `FRAME_HARNESS_REVIEW.md` disposition.

The reviewer read `native_frame_relay.h`, `native_frame_relay.S`,
`native_frame_config.cpp` and `FRAME_RELAY.md`, compared the actual native entry
and CFA with retained disassembly/frame evidence, and rehashed the final freeze.
Only this review file was created. No implementation, earlier review, compiler,
test, WSL, runtime, model, hardware, serving or lifecycle action was performed.
The subsequently planned standalone harness is outside this core review.

## Capture layout and native frame

Let S be the intercepted original RSP and F the final integer-image base.
The assembly begins with ENDBR64, then a flag-neutral LEA reserves the original
128-byte red zone before its first PUSH. Its flags, 15 non-RSP GPR saves and one
original-RSP slot occupy 136 more bytes, so `F=S-264`.

| Image offset from F | Saved value |
|---|---|
| `0,8,16,24,32,40,48,56` | RAX, RBX, RCX, RDX, RSI, RDI, RBP, reconstructed original RSP |
| `64,72,80,88,96,104,112,120` | R8, R9, R10, R11, R12, R13, R14, R15 |
| `128` | PUSHFQ ordinary-flags image |

All live GPRs are saved before the first clobber. Reconstructing S from
`F+264` occurs after original RAX is saved, and uses no native pointer
dereference. The image matches the existing consumer's register order. During
restore, the populated RSP slot is skipped, every other GPR is popped in reverse
order, flags are restored, and a flag-neutral LEA restores S. The final displaced
`LEA RAX,[RBP+0x1e8]` is the intended GPR change; there is no proposal/native-stack
write or success route in this core.

The retained handler at `0x171c260` saves RBP/R15/R14/R13/R12/RBX and subtracts
`0x2648`. Its FDE is `0x171c260..0x17305ed`, with no intervening CFA change at
the no-hit seam. CFA is `S+0x2680`; native caller return and saved
RBX/R12/R13/R14/R15/RBP remain at CFA minus `8/56/48/40/32/24/16`. Live RBP is
the request, not a conventional incoming frame pointer.

The relay's CFI retains these native caller slots rather than substituting the
new live-register image. Each stack adjustment changes its CFA offset. Once
RBP becomes F, `CFA=F+0x2788` agrees with `264+0x2680`; that stable rule covers
dynamic alignment and the normal callback. The epilogue returns to the matching
RSP rule before restoring live RBP. Source rules are internally consistent;
generated FDE contents, their registration/placement and actual unwind/signal
behavior have not been checked. The different nested-controller frame is not
supported by this descriptor.

PUSHFQ precedes flag-changing work. CLD follows that flags capture and precedes
REP STOSB; POPFQ restores the admitted arithmetic/DF state. Final LEAs and JMP
do not change flags. RF/VM, privilege-dependent bits and debugger/trap behavior
are explicitly excluded. A normal SysV observer must return with its ABI
obligations intact; no exception, longjmp, cancellation or serving reentry is
admitted.

## Real xstate allocation and callback ABI

For admitted extent X, the save base is `A=align_down(F-X-128,64)`. Its image
ends no higher than `F-129`, while the six-field view occupies `F-64..F-17`.
These regions do not overlap. The view holds the original integer image,
aligned real XSAVE area, full mask, extent, S and architectural scope. The
synthetic consumer's 1024-byte opaque array is not used.

The complete X-byte standard image is zeroed on every invocation, including the
512-byte legacy region, 64-byte header and reserved bytes. XSAVE64 receives the
full 64-bit XCR0 mask through EDX:EAX. FNINIT and the callback MXCSR load occur
only after that save. The 64-aligned A is also 16-aligned immediately before
the genuine CALL, and the callback's return/stack/red-zone budget is explicitly
supplied. XRSTOR64 uses the same full mask after normal return, including
components whose XSTATE_BV bit is zero; callback-created init-state components
are not left live by an in-use-only restore.

This is an architectural save/restore design, not a raw-byte equality or physical
x87 metadata proof. AMD APM Volume 2, Rev. 3.44, March 2026, section 11.5.10
distinguishes the conditional older error-pointer behavior from XSaveErPtr
support; even with CPUID `0x80000008.EBX[2]` set, a save without pending #MF can
zero pointer fields. Generic full-mask restore therefore cannot establish
literal preexisting error-pointer parity. The current configuration refuses
literal physical metadata scope for **every** vendor and conservatively refuses
AMD without that feature bit. [AMD APM Volume 2, section 11.5.10](https://docs.amd.com/api/khub/documents/sD1_QL~h4Afq2_tvzxqqSQ/content)

FS/GS bases and supervisor CET state are not supplied by user XSAVE. Their
preservation relies on prohibited mutation and valid control flow. A PKRU-enabled
observer must preserve access to the image/view/stack through restore, as the
document explicitly requires. No observer implementation or compiled call tree
exists in the reviewed core, so those obligations remain unresolved.

## Startup bounds, concurrency and continuation

Startup discovery checks XSAVE/OSXSAVE before XGETBV(0), records vendor and CPU
identity, validates XCR0 against the supported user mask, requires x87/SSE,
checks AVX512 dependencies, and bounds standard extent `(0xD,0).EBX` to
576..65536 bytes. Enabled nonlegacy component extents must be inside that area
and nonoverlapping; supervisor/XFD-capable and unknown enabled components are
refused. The recognized mask includes x87/SSE/AVX/AVX512/PKRU. No feature
permission is requested. A successful result is only an architectural candidate;
every refusal leaves `enabled=0`.

The finite required headroom formula includes the 264-byte capture, X, 128-byte
allocation gap, worst 63-byte alignment loss, complete callback budget and signal
reserve. The enabled path compares original S with the supplied stack range and
that requirement before xstate allocation or callback. **The initial 264-byte
capture occurs before those checks, including on disabled/unregistered/nested
bypass.** Its writable headroom must therefore already be guaranteed for every
entry. `FRAME_RELAY.md` explicitly states this prerequisite rather than claiming
the later check proves it. Actual mappings, permissions/residency, guard pages,
signal stack/policy and CPU migration remain unimplemented startup obligations.

Each invocation uses its own stack image, so the relay has no shared xstate/GPR
scratch. The sole shared configuration must be immutable during all entries and
published only under complete quiescence. There is no hot enable/disable/remove
protocol. The external observer must separately satisfy its concurrency and
normal-return contract; stack-local images alone do not prove an observer sink
or signals safe.

The assembly marks its observer and stock-resume symbols hidden and uses a
direct CALL and direct JMP in source. It contains no RET continuation, fabricated
return address, indirect interior jump or fallback. The entry has ENDBR64; the
balanced genuine callback CALL/RET preserves the original shadow-stack ownership.
The required stock symbol must resolve directly to `0x172d3c4`, or a reviewed
near landing pad whose onward native branch is direct and in range.

**Both `halogen_nohit_frame_observer` and
`halogen_nohit_native_stock_resume` are unresolved in this core.** Source visibility
and branch spelling cannot prove the emitted/link-resolved target is stock or
exclude an accidental PLT/veneer/indirect route in a future artifact. Final
relocations, branch instructions/targets and rel32 ranges must be inspected in
that artifact before interpreting a run. Actual CET thread activation and
installation are unqualified here. No compile/link/native/install success is
claimed by this source disposition.

## Review findings and final pins

The author resolved the concrete provisional scope issue: literal physical x87
metadata requests formerly succeeded for Intel; the frozen configuration now
refuses them universally before discovery. Documentation now places CLD after
flags capture and before image initialization, matching the assembly. The final
stock-mutation wording is narrowed to intended GPR/native-stack effects, keeping
architectural xstate canonicalization distinct. No further source change is
requested for the documented core contract.

| Frozen source/evidence | SHA256 |
|---|---|
| `native_frame_relay.h` | `f6aaf827d5187a3eb47bda94bf9f19d6eae29664251ede96c29b7d84e9c74cbe` |
| `native_frame_relay.S` | `b9bbbe04ce46a5c61fefa08fbdac56fcaffd5c9489e7c764c1e9dd4ae8d0fba5` |
| `native_frame_config.cpp` | `8bcc5d760cc6204a7896d8a1ddd866f1bb6b63fdb6a6584a5587a9e65447b57d` |
| `FRAME_RELAY.md` (source scope plus subsequent harness note) | `f3db49aab6bac77f856528940bebebda781b0c59530d808fa0b8ce4c542df999` |
| Native frame adapter plan | `46b79139e5cd35c352809fe540131189e047625b8a33b83518207b544169b52f` |
| Retained ELF | `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` |
| Retained host text disassembly | `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` |
| Retained host frames | `03b9bef6fd4182013dcec8ecb9c850dcc5c5ae474b57ecf2925934359115b923` |

The existing seam/handoff source pins and `HANDOFF_REVIEW.md` /
`CAPTURE_LAYOUT_REVIEW.md` remained unchanged. This original source review
established no actual XSAVE mask/extent, real register/xstate parity, linked
stock continuation, native observations, installation, producer readiness or
serving measurement. Later standalone build/run evidence is recorded separately
and does not expand this native qualification boundary.
