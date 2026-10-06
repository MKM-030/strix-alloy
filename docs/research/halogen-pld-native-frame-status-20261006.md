# Real CPU frame-relay qualification, 6 October 2026

The new stock-only native frame relay builds and passes its single focused Linux
CPU qualifier: **three real-register cases, 18 checks, zero failures**. It remains
default off and absent from Halogen. This closes a real architectural-state check;
it does not establish native installation or a serving improvement.

The [machine-readable evidence](halogen-pld-native-frame-status-20261006.json)
retains both receipts, all eight source/helper pins, executable hash, emitted
instruction/CFI/ELF logs and exact stdout. Root built once, inspected the linked
artifact, then ran that same hashed executable once. No unchanged rerun followed.
The independent [core review](../../scripts/benchmarks/halogen_pld_nohit/FRAME_RELAY_REVIEW.md)
is a source review, separate from the subsequent root execution. The
[qualifier/launcher review](../../scripts/benchmarks/halogen_pld_nohit/FRAME_HARNESS_REVIEW.md)
independently checks source and retained artifacts; the reviewer ran no test.

The observed CPU was AMD family 26, model 112, stepping 0; XCR0 was `0xe7` and
the standard XSAVE extent was 2,432 bytes. Disabled/noninitial, enabled/noninitial
and enabled/init cases used the actual six-save native-shaped stack frame and
the same assembly relay. They independently checked GPRs, original RSP, ordinary
arithmetic/DF flags, all 128 red-zone bytes, exact observer count and scoped
x87/SSE/AVX architectural restoration. The continuation applies the stock RAX
LEA. Literal physical x87 pointer metadata is explicitly refused and unqualified.

The linked relay is 290 bytes at `0x13a0..0x14c2`. Its observer CALL and mock-stock
JMP resolve directly, without a PLT/indirect native branch. Generated CFI retains
the native CFA `0x2680`, uses captured-frame CFA `0x2788` and restores the matching
rules through the epilogue. The stack is non-executable. These are standalone
artifact observations; executing unwinds/signals, active CET and a real engine
continuation remain unqualified. MXCSR was initial; enabled AVX512 components
were compared but not deliberately made noninitial/clobbered. PKRU was absent
from this observed XCR0 mask.

Build reserve minima were 33,505,841,152 physical bytes and 132,188,332,032 commit
headroom bytes; execution minima were 33,582,903,296 and 132,302,245,888 bytes.
Maximum recorded sample gaps were 0.266 and 0.235 seconds. All retained Windows
jobs/handles closed; finite Linux timeout stages returned normally. This does
not prove closure of escaping descendants or externally cancelled WSL work.
No GPU/NPU runtime, model, serving request or server lifecycle ran.

CPU owns this register/control path. Moving these tiny checks to GPU/NPU has no
demonstrated benefit; those devices remain separate possible proposal producers.
The relay does not separate weights or change ordinary target Prefill. New
Prefill tok/s, Decode tok/s, native acceptance and all serving deltas are
**unmeasured**, not zero. The normal server stays ready and open.

The next connected implementation is the explicit native-copy/owner boundary in
the [live connection report](halogen-pld-live-capture-connection-20261006.md),
including actual lifetime/reset/outcome observations and a pre-seam acknowledged
full prefix. A stock-only observing invocation precedes any useful proposal
producer and frozen serving comparison. The full acceleration goal is unachieved.
