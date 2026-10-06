# Native no-hit byte-layout decoder

The default-off integration path now has a concrete bounded decoder for copies of
the pinned Halogen 0.16.2 request, model, queue record, outer stack and vector suffix.
It supplies observation facts for the existing outcome handoff. It installs no
observer, obtains no native memory itself and grants no capture/ownership/reset
qualification. `decode_nohit()` cannot call the handoff or select a packet.

## Exact input boundary

`ObjectCopy` holds an immutable owned byte span plus the native origin recorded by
the future capture adapter. The parser never dereferences that origin. Matching
origins show only internal layout consistency: a caller can fabricate all these
values, and the parser cannot establish their provenance. Real register capture,
held native lifetimes, exclusive ownership, actual copied-memory provenance,
reset/slot coverage and installed observer coverage remain external obligations.
The independent [native capture audit](../../../docs/research/halogen-pld-native-owner-capture-path-20261006.md)
describes the source of those observations. The future relay must preserve the
actual machine state; `NoHitCopies.gpr` is currently only a value-copy interface.

The decoder checks actual saved RBP/RSP/R15 origins, request-to-model and
record-to-request links, one queued record of stride `0x308`, the outer `+8` record
link and the selected slot. Prefill vector length comes from record
`+0x140/+0x148`; the consumed extent at `+0x158` is **QWORD**, matching the native
unsigned compare at `0x172c271`. Request and model layouts use fixed minimum sizes
`0x1f8` and `0x902`. The phase byte at request `+0x1e4` must already be zero at
the no-hit boundary; setup's preseed phase completion is not handled by this helper.

Complete vector length is calculated from request `+0x178/+0x180`, with ordered,
aligned begin/end/capacity pointers. Up to 262144 complete IDs are supported. The
supplied suffix must contain exactly `min(length,512)` IDs and have the exact
recorded native origin `end-4*count`; its last ID must equal request `+0x15c`.
Every copied suffix ID is checked against the supplied tokenizer definitions.
Unused output slots remain zero. Interior work scans at most 512 IDs, not the
whole prompt. The native target position is independently read from model
`+0x220`; vector length never substitutes for it.

This does not solve full-prefix provenance by hashing only the suffix. The actual
adapter still needs a complete authoritative seed copied/hashed outside the
interior hook, a qualified full-prefix fingerprint bound to that exact birth and
frontier, and observed append/seal continuity for subsequent frontiers. It must
compare this bounded suffix with the existing handoff frontier before consuming.
Long layouts are supported by this parser; real 8K/16K/128K/260K native capture and
handoff integration are not qualified by the synthetic harness.

## Allowance and gates

The copied no-hit facts preserve separate native policy, sampler, suppression,
width/context, constraint and opening-scope facts. Count admission remains in the
existing `consume_at_seam()`/`consume()` path. Model MTP flags are conservatively
required to be exactly one for the reported opening eligibility. No captured
flag turns into a handoff `Qualification` assertion.

Allowance is recomputed with widened signed arithmetic as

```text
B = min(model[+0x14]-1, request[+0xf0],
        model[+0xf0]-P-1, request[+0x1e0]-1)
```

All intermediate native signed32 operands must be representable; wrapping
operands are rejected even if a later minimum could mask the wrap. The low32
bits of the saved actual R9 must equal that independently computed B. A zero or
negative valid B is retained as an observed stock gate fact. Opening scope also
checks request MTP policy, continuation suppression, `P+2` capacity and model MTP
flags. Output is assigned only after successful decoding; failures leave it
unchanged. No native stack or register is mutated.

Retained source pins are the ELF
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`
and host text disassembly
`523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`.
Relevant source instructions are queue/prefill `0x172c248..0x172c289`, phase and
allowance `0x172d2f2..0x172d3b7`, opening scope `0x172d3d8..0x172d40a`, and
position writes `0x177e588`/`0x17def32` (DWORD); the latter field must not be
confused with adjacent `+0x224` merely because reset clears both as a QWORD.

## Focused execution evidence

The guarded Windows CPU runner reused the reviewed existing ownership, memory
and compiler setup. No WSL, GPU/NPU, native engine, inference or lifecycle action
occurred. It requires 22 GiB physical/commit before child launch/resume and
18 GiB continuously; both compiler/harness jobs are owned suspended jobs and
closed on completion. Source/tool/executable hashes and memory minima are retained.

| Receipt | Compiler | Harness | Outcome |
|---|---:|---:|---|
| [_artifacts/20261006-082958-capture-layout-red-c4212dae/result.json](_artifacts/20261006-082958-capture-layout-red-c4212dae/result.json) | 0 | 1 | Missing decoder: 30 expected failures, 42 checks |
| [_artifacts/20261006-083119-capture-layout-green-badadabe/result.json](_artifacts/20261006-083119-capture-layout-green-badadabe/result.json) | 0 | 0 | Implemented decoder: zero failures, 42 checks |

The harness deliberately gives target position `length+23` for complete lengths
8192/16384/131072/260000. Its independent fixtures catch length truncation,
position/length conflation, a mistaken DWORD consumed count, wrapping allowance,
wrong queued/frame origins, phase reentry and invalid suffix/token facts. These
are synthetic copied layouts, not live engine captures. The harness supplies no
native ownership, cryptography, full-prefix hash, reset, frame relay, install,
signal/unwind or useful producer readiness proof.

## GPU, NPU and CPU assessment

This is bounded CPU metadata work: fixed field checks and at most a 512-ID copy.
Moving it alone to GPU/NPU would require extra publication/transfers and does not
provide a useful independent proposal. Those devices remain candidates for the
connected proposal producer after native integration and readiness are qualified.
The decoder neither separates weights nor changes ordinary target Prefill.
Improved proposals could increase accepted tokens and Decode, but this helper
has not produced them. No actual new Prefill tok/s, Decode tok/s or native
acceptance value exists for it; all remain unmeasured.
