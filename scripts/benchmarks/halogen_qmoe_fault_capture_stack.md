# Bounded caller metadata collector

This separate source retains the refresh collector's three `DWORD __cdecl`
exports and same-thread pre-Run callback contract. It changes the fault schema
to `halogen_qmoe_av_stack_v1`. No build, DLL import or execution is claimed here.

The ordinary start/refresh checkpoints capture `GetCurrentThreadStackLimits`
alongside the immutable module map. VEH unwinds only that checkpoint thread,
using a private `CONTEXT` copy, `RtlLookupFunctionEntry` and
`RtlVirtualUnwind(UNW_FLAG_NHANDLER)`. A metadata-free leaf reads one return slot
within the recorded stack bounds. Unwind steps require positive stack advance,
at most 64 KiB per step, and stack addresses within the checkpoint bounds. At
most 12 frames are emitted as RIP/module-base/offset metadata; no raw stack or
instruction bytes, tensor values or model values are emitted. Unknown code
modules stop further unwinding. Worker-thread faults retain frame 0 only.

SEH catches unwind metadata/stack read failures and records a reason and the
secondary exception code. Recursive VEH entry skips the existing writer gate.
The original context/exception are never changed; the original exception still
continues searching. This is best-effort metadata, not a validated debugger or
a guarantee that every internal OS unwind read stays within a checked range.
Damaged stack state, missing/changing modules and unwind metadata can truncate
or invalidate a trace. Per-frame paths should be resolved separately on the
ordinary host after the caught fault, retaining that later-observation scope.

Use ordinary MSVC x64 `/TC /O2 /W4 /WX /MD /LD` with the existing pinned compiler
and SDK include/library directories; link `kernel32.lib`. Do not reuse the
refresh collector's `/NODEFAULTLIB` or `/ENTRY:DllMain` flags: the ordinary CRT
entry and x64 SEH runtime support are intentional. `DllMain` itself stays empty.

Update the new probe/resolver bounds to eight records of **16384 bytes** each
(131072-byte file maximum), pin the separate collector DLL/source, and resolve
each `unwind_frames[*].rip` after the fault. Keep the collector loaded for the
process lifetime. No helper receipt ABI or callback signature change is needed.
