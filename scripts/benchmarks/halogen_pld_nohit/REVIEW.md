# Independent source review, 6 October 2026

The current contract has no identified correctness blocker within its declared
synthetic, trusted-caller scope. The proposed native success join initializes
the previously questioned constraint-pointer stack slot itself. This approves
the bounded source contract, not a live detour, authenticated wire consumer,
ready producer, snapshot adapter or serving change.

Review work consisted of local source/disassembly reads and hashes. No tests,
compiler, hardware, WSL, provider, engine or lifecycle operation was performed.
Only this distinct review file was created; implementation and existing design
documents were not edited. Execution and commit verification remain root-owned.

## Reviewed pins

| Source | SHA256 |
|---|---|
| `seam_contract.h` | `caa67ed65e991e2f8474e5ba16ae5c8a29cc74bc517d253fe95a330e152bc5f2` |
| `seam_contract.cpp` | `c03d638baee63cf1d26c69a8cca19dd5c06d4cede60ae46150dbbdcbc2adf0f7` |
| `contract_harness.cpp` | `240b923d075f6d872bcf96be771b7882f47aa58dd4048df1d1e99251bb4eaea5` |
| `run_cpu_harness.py` | `2f8d2bde3e3d12056d0824c191f04e3a8811ce87d5737a5a3aa901b4aa60ebca` |
| `server/winjob.py` | `3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c` |
| `server/host_frames.py` | `417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8` |
| Recurrent snapshot feasibility document | `94fe739f97762c567edd010ea8e7e09c91cfd95348635354fe92948503839b0c` |
| Retained `mtp-route-static-20261004/host-text-disassembly.txt` | `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` |

The last two paths are respectively
`docs/research/halogen-recurrent-snapshot-adapter-feasibility-20261006.md` and
`server/.local/optimization9h-20261004/mtp-route-static-20261004/host-text-disassembly.txt`.

## Native continuation: the suspected prerequisite is present

The pinned disassembly at lines 21501-21505 and 21550-21551 contains:

```text
0x172e95f  lea rax,[rbp+0x1e8]
0x172e966  mov [rsp+0x38],rax
0x172e96b  mov rdi,[rbp+0x1e8]
0x172e972  test rdi,rdi
0x172e975  je 0x172ea19
0x172ea19  mov r13d,ebx
0x172ea1c  jmp 0x172d3cc
0x172d3cc  mov r12d,r13d
0x172d3cf  test r13d,r13d
```

Thus success at `0x172e95f` recreates the LEA and `[RSP+0x38]` store that it
skips at the no-hit seam. For the required no-constraint case it initializes
R13D from the deliberately supplied EBX count, then R12D through stock code.
The original opening comparison and target verifier remain downstream.
There is no missing constraint-pointer prerequisite requiring another synthetic
stack write or GPR mutation. Jumping to `0x172e966` or later instead would need
a different contract; the current constant is the start of this initialization.

A fresh encoded direct-target scan found the eight seam entries
`0x172d38e`, `0x172d39a`, `0x172dcd7`, `0x172dcf9`, `0x172dd0e`,
`0x172dd31`, `0x172dda6` and `0x172ddc9`, with no encoded target inside
`(0x172d3bd,0x172d3c4)`. The insufficient-context path also falls through.
Computed entries, actual frame capture, executable installation, unwind,
signals and complete XSAVE restoration remain unqualified.

## Validation, mutation and synthetic preservation

`seam_contract.cpp:68-137` validates caller ownership/reset/currentness,
RBP/RSP binding, native gate truth, publication status, epoch, exact framing,
all header bindings, current-token definition, every proposed-token definition,
allowance and the entire one-shot ledger before the commit at lines 141-150.
The accepted range is strictly `1 <= n <= min(3,B)`; oversized counts decline
rather than truncate. Positive signed B is checked before its unsigned cast.
Token-limit validation bounds every bitmap index, and the window-origin checks
prevent underflow before checking the maximum 512-token extent.

Every decline leaves the ledger and proposal bytes unchanged and performs only
the displaced modular 64-bit LEA into saved RAX, preserving saved flags. Success
changes exactly `4*n` bytes at offset `0x360`, saved RBX and one ledger record.
The fixed storage, nonthrowing writes and absence of callbacks make that commit
sound under exclusive ownership. It is not an atomic multi-object transaction:
the caller must exclude resets, serialize ledger/frame access, retain all
lifetimes and publish an owned immutable packet with the necessary memory
ordering before entry. Boolean ready/ownership fields do not implement those
mechanics themselves.

The harness compares every synthetic GPR, saved RFLAGS, all 896 stack bytes
and the 1,024-byte opaque extended-state image. It checks unchanged ledger data
on declines, canaries outside the one- and three-ID destinations, final-header
and final-ID failures before mutation, stale epochs, reused rounds and ledger
exhaustion. Its stock continuation models the store/zero-count/TEST branch and
does not invent meaning for undefined AF. These are semantic data-image checks;
they do not exercise real registers, pointed-to request/model objects, a native
stack, an XSAVE image or a live control-flow transfer.

## Authentication and launcher scope

`TrustedAuthenticatedFrame` explicitly delegates cryptographic verification,
key trust and immutable publication upstream. The complete header and IDs must
be authenticated against the trailing HMAC; context epoch is separately trusted
envelope truth because it is absent from the wire header. The consumer checks
exact caller binding and replay state but never authenticates the digest. The
harness intentionally uses invalid synthetic HMAC bytes with an asserted trust
fact. Its GREEN result cannot establish full wire authentication, key handling,
transport security or acquire/release publication. Those are prerequisites for
any eventual native consumer, rather than defects hidden by this source scope.

The initially read launcher lost `error.owner` if `OwnedProcess` construction
failed while its internal setup cleanup also failed. The reviewed final runner
fixes this at lines 112-125: it recovers the attached owner, attempts close in
`finally`, and retains failed closes in `pending_cleanup` for an explicit retry
at lines 152-158. `owned_job_closed` becomes true only after close returns.
An unresolved retry records an error and leaves the closed flag false, so it
cannot produce a successful launcher result. Helper pins are checked before
import, and setup failures before child construction own no child handles.
This review did not execute or fault-inject that recovery path.

No additional machine-state fix is needed for the `0x172e95f` entry. The source
contract is suitable for the offline qualifier under its explicit assumptions;
actual native capture/restoration, authenticated publication, reset/lifetime
ownership and a useful ready packet still block live integration. No Prefill,
Decode, acceptance or token-rate gain is established.
