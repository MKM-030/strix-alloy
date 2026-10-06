# Independent copied native layout review, 6 October 2026

**No blocking correctness issue was found in the frozen bounded copied-layout
decoder.** Its native field widths and aliases match the retained disassembly,
and its successful result supplies observation facts without granting handoff
qualification. This disposition covers the immutable owned-copy contract only.
It does not qualify a native capture, relay, installation or proposal producer.

The review read `native_capture_layout.h/.cpp`, `capture_layout_harness.cpp`,
`run_capture_layout_harness.py`, the frozen `CAPTURE_LAYOUT.md`, the retained
native-owner audit, the relevant retained instruction paths and the existing
RED/GREEN receipts. It rehashed local source/evidence. The reviewer created only
this file, changed no implementation or previous review, and ran no compiler,
test, WSL, engine, model, hardware, serving or lifecycle action. Existing execution
evidence below belongs to the coordinating agent's guarded CPU runs.

## Native field and frame checks

| Decoder observation | Retained native evidence | Disposition |
|---|---|---|
| Queue begin/end at outer `+0x170/+0x178`, exactly one `0x308` record | `0x172c21d..0x172c24e` loads both bounds and compares their difference with `0x308`. | Correct. Ordered extent and exact stride are checked. |
| Record request at `+0x10`, selected slot at `+8` | `0x172c254` checks the request; `0x172c285` reads a DWORD slot for slot select. `0x172d2a9` loads the actual request into RBP. | Correct. Record/request origins and record-slot/model `+0xa0` equality are checked. |
| Prefill begin/end at `+0x140/+0x148`, consumed at `+0x158` | `0x172c25f..0x172c278` uses QWORD endpoints, an arithmetic shift by two and a **QWORD** unsigned consumed comparison. | Correct width. The decoder conservatively rejects reversed, nonintegral or oversized extents and compares the full 64-bit consumed count. |
| Actual request/outer/record identities from RBP/RSP/R15 and outer `+8` | `0x172d2a9`, `0x172d2d8`, then the gate and lookup-miss paths. | Correct local aliases for all nine reviewed seam entries. The hash miss paths do not overwrite RBP/RSP/R15; later reuse of R15 belongs to other outcome paths. |
| Request model at `+0xd8` | `0x172d35d` obtains the model used for B; `0x172d3f2` obtains the model used for opening scope. | Correct alias. The decoder checks that pointer label against the supplied model-copy origin. |
| Target position at model `+0x220` | `0x172d367`/`0x172d3f9` read DWORDs; `0x177e588` and `0x17def32` write DWORDs. | Correct signed32 field. The adjacent `+0x224` is not included merely because reset clears both together. |
| Policy, width and scope fields | Native comparisons at `0x172d32f..0x172d3b7`, `0x172d3d8..0x172d40a` and the later MTP flag reads. | Correct widths: DWORD policy/suppression/width, QWORD sampler/constraint, BYTE phase/MTP flags. Requiring each MTP flag to equal one is conservative. |

The four required copies are checked for nonzero origin, bounded origin extent
and sufficient byte span before any fixed field read. Little-endian readers
avoid host alignment assumptions. The parser dereferences only its supplied
owned spans and tokenizer-definition object, never a native origin. The caller
must hold all of them immutable for the complete call, as declared by the header.

## Allowance, suffix and failures

The independently computed B agrees with `0x172d357..0x172d38b`:

```text
min(int32(model+0x14)-1, int32(request+0xf0),
    int32(model+0xf0)-int32(model+0x220)-1,
    int32(request+0x1e0)-1)
```

Widened arithmetic avoids C++ signed overflow; all potentially wrapping native
operands, including the opening `P+2`, must fit signed32. Invalid negative
position/capacity values are conservatively rejected. Saved R9 is compared by its
low32 bits interpreted as signed32. Inspection of all lookup-miss incoming paths
confirmed that R9D still holds B; the hit-copy temporary reuse at `0x172de10`
joins `0x172e95f` instead of returning to this seam. Valid nonpositive B remains
an observed stock-decline fact rather than becoming a decode failure.

The complete length comes from the ordered/aligned request vector boundaries and
is retained up to 262144 IDs. The independent native target position is not
derived from that length. The supplied suffix must have exactly
`min(length,512)` IDs and the exact native origin `end-4*count`; its tail must
equal current ID and every supplied ID must be defined. Length is positive
before the tail access. The origin subtraction remains within the already
validated vector extent. Successful output is built in zero-initialized local
storage, so unused ID slots are zero. Every failure returns before the sole
output assignment, preserving the caller's existing facts.

Work is bounded to fixed-field reads, one validation pass and one copy pass over
at most 512 IDs, regardless of the complete vector length. No allocation, lock, callback, native
mutation or handoff call is present in the decoder.

## Qualification and phase boundary

The origin checks establish consistency of caller-supplied labels. They cannot
prove where the copied bytes came from, held lifetime, serial ownership, exact
native register capture, reset exclusion, tokenizer/model identity or installed
observer coverage. Consistent fabricated copies would still be accepted as
layout facts. `NoHitFacts` contains none of those qualification assertions, and
there is no method here that consumes a packet or sets `Qualification`.

The 512-ID suffix is likewise not a qualified canonical full prefix. Long-vector
length support requires the future adapter's complete authoritative seed and
full-prefix fingerprint outside the interior hook, bound to the same birth and
frontier, followed by observed append/seal continuity. Comparison with the
existing handoff frontier remains external. The older native-owner note's
initial complete 512-ID feed is not expanded into qualified long-context capture
by this helper.

The phase check has a precise limit: at the earlier round snapshot
`0x172d2f2`, native code can observe phase one and clear it at `0x172d2fb` before
reaching no-hit. Thus phase zero at this decoder cannot rule out that earlier
postseed phase reentry. The separate before-clear round observer must retire a
postseed phase-one feed; initial preseed completion must finish and be rechecked
at the gate. `CAPTURE_LAYOUT.md` already states that phase/preseed setup is
outside this helper. The harness's phase-one rejection exercises a supplied
no-hit copy, not coverage of the earlier native event.

These boundaries are documented, so no implementation change is requested for
the reviewed decoder scope. They remain mandatory obligations for any native
adapter that would grant capture or selection truth.

## Retained execution evidence

| Receipt | Compiler / harness exits | Retained harness output |
|---|---|---|
| `_artifacts/20261006-082958-capture-layout-red-c4212dae/result.json` | `0 / 1` | Missing decoder: 30 failures, 42 checks. |
| `_artifacts/20261006-083119-capture-layout-green-badadabe/result.json` | `0 / 0` | Frozen implementation: 0 failures, 42 checks. |

The current four reviewed source hashes match the GREEN receipt. Both receipts
report expected phase outcome, no errors, closed owned compiler/harness jobs and
no WSL/GPU/NPU/native-engine execution. GREEN's minimum physical availability was
33,872,969,728 bytes and commit headroom 132,612,157,440 bytes, above the documented
reserves; its maximum recorded sample gap was approximately 0.266 seconds. The
runner source pins the reviewed ownership/memory helpers and existing compiler,
launches finite owned children, checks reserves before launch/resume and during
execution, and retains cleanup state for retry.

The fixture lengths 8192/16384/131072/260000 deliberately use position `length+23`
and an independently expected B of 3. Other focused cases distinguish the consumed
QWORD, invalid frame/queue/suffix/token observations, phase, arithmetic and saved
B, while checking failure preservation. These 42 checks support the narrow
synthetic layout behavior; they are not exhaustive branch coverage or native
preservation, ownership, reset, installation or long-context integration proof.
No new acceptance, readiness, Prefill, Decode or serving measurement follows.

## Frozen pins

| Reviewed source/evidence | SHA256 |
|---|---|
| `native_capture_layout.h` | `e7ce7302eb98cfa09a2c7ee2b1747e8c2a88d4311de0dfbdf10a5a03ab7eee1a` |
| `native_capture_layout.cpp` | `88bb4c55c0fea429633c5f196a94e7126258ce9c8182b8892cbff4b7e4b8bac5` |
| `capture_layout_harness.cpp` | `01fe0d594006998f434af5558b8680d4cd7b302986a0898ef19deddddf4caa82` |
| `run_capture_layout_harness.py` | `47861310885d8066f35ce4ae7de491832ca9a52c0eb6e536d957ec416feb94cd` |
| `CAPTURE_LAYOUT.md` | `7d8c9b8ab3f6535d8a76e9bf15bdd83bb1c6bced69eb548bac11467c01f59fc9` |
| Native-owner capture-path audit | `22298553efca2962427f18a278f7c02ffc21c37d7e0c323191b11d0aa13b42e8` |
| Retained ELF `flash_serve` | `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` |
| Retained `host-text-disassembly.txt` | `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` |
| GREEN `result.json` | `4a2dba17c481b846a912ef3a410771c0bbfe2c8f1de97ff2cdcc8d39d6ab3f91` |
| GREEN `harness.stdout.txt` | `2efc7c0148a2e1dbe099238c5fe88821c6fb8c25824e874bd4a8985881e47863` |
| RED `result.json` | `7b3f3b3f02ecf4a22c27096dac377ff2c2c51ea7452d2c6ef6a333a0b3fb65d6` |
| RED `harness.stdout.txt` | `98b74d75fe7410e9ffd36b916c745bb70e0988908438efca577e1b928a17dfae` |

The existing frozen seam/handoff implementation and `HANDOFF_REVIEW.md` had no
diff during this review. This document does not reopen their accepted finite
synthetic scope or confer additional native qualification.
