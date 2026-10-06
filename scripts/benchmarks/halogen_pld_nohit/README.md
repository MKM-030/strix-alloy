# Offline no-hit packet and seam contract

This directory supplies a **default-off, fixed-storage native semantic contract**
and a finite Windows CPU harness for the structural no-hit entry. Nothing calls
it from the engine. There is no detour, profile/shadow, packet transport, drafter,
model/provider import, GPU/NPU action, WSL action, production edit or serving gain
claim. The existing hit-only Python selector is unchanged.

`seam_contract.h` defines caller-owned saved-frame images, binding and tokenizer
truth, trusted publication, and a 64-entry one-shot ledger. `seam_contract.cpp`
has no allocator, callback, lock, wait, retry or runtime dependency. The harness
uses native C++ behavior checks; Python only guards the compiler/test children.

## Boundary and validation

The existing little-endian wire format remains `192 + 4*n + 32` bytes, where
`1 <= n <= 3`, magic is `HGNPLDP1`, and version is 1. The final 32 bytes remain
the existing HMAC-SHA256 field.

**Authentication is outside this consumer.** A caller must authenticate the
complete header and ID body against that digest, validate the integrity key's
trust, and supply a stable, owned, immutable publication before setting
`authentication_qualified`, `immutable_owned`, and `ready`. A boolean cannot
establish those facts. The synthetic fixture uses opaque digest bytes and
explicitly assumes this boundary; it does not test HMAC. Context epoch is a
trusted out-of-band envelope fact because the existing wire has no epoch field.
Its association with the authenticated frame must also be protected upstream.

The caller must independently establish current request/model/tokenizer/prefix
truth, reset exclusion, birth and round identity, serial ownership, and the
native allowance B. None may be inferred from a packet or native target
prediction. All supplied objects must remain immutable for the whole call,
except for the consumer's exclusively owned frame and ledger. The tokenizer
bitset records explicitly defined IDs with an exclusive caller limit of at most
248070; the target's 248320-wide F32 head is not a token allowance.

The consumer checks these facts and requires positive PLD policy and width,
absent sampler/suppression/constraints, sufficient context, positive B, and
matching saved RBP/original outer RSP identities. It then checks exact frame
length, magic/version/count, every nonzero binding, positive prefix/position,
the 1..512 token window, current token definition, every proposal ID, epoch,
`n <= min(3,B)`, and ledger capacity/reuse before any proposal write or ledger
consumption. It never truncates a packet. A decline cannot evict a ledger entry.
Successful consumption records `(birth_nonce, epoch, round_id)` once. Retiring a
ledger requires retiring every packet from its old birth; silent clearing or
eviction would defeat one-shot use.

## Retained seam and exact mutation

The retained decoder FDE is `0x171c260..0x17305ed`. The no-hit instruction at
RVA `0x172d3bd` is exactly seven bytes:

```text
48 8d 85 e8 01 00 00    lea rax,[rbp+0x1e8]
```

Disabled, absent or declined packets change only saved RAX to the 64-bit modular
value `RBP + 0x1e8`, preserve all RFLAGS and other supplied state, and return
stock resume RVA `0x172d3c4`. The retained next instructions store RAX at original
`RSP+0x38`, zero R13D, copy it to R12D and TEST it; JLE reaches `0x172d5ca`.
The harness compares this semantic continuation and does not assign meaning to
XOR/TEST's architecturally undefined AF.

A successful packet changes only its `4*n` ID bytes at original outer
`RSP+0x360` and saved RBX=n, then returns join RVA `0x172e95f`. This join itself
executes LEA RAX,[RBP+0x1e8] at `0x172e95f` and the `RSP+0x38` store at
`0x172e966`; it does not depend on the skipped no-hit LEA. With no constraint
object, `0x172ea19` copies EBX to R13D and `0x172ea1c` jumps to `0x172d3cc`.
The retained route then keeps the native opening comparison
(`0x172d41e/0x172d425`), target verification (`0x172d618`), accepted-prefix
commit (`0x172d80a`), output/stop handling and native replay. The contract never
returns a direct verifier jump or manufactures a native opening token.

The prior static audit found eight encoded direct incoming edges:
`0x172d38e`, `0x172d39a`, `0x172dcd7`, `0x172dcf9`, `0x172dd0e`,
`0x172dd31`, `0x172dda6`, `0x172ddc9`, plus fallthrough from `0x172d3b7`, and
no encoded direct target in the seven-byte instruction interior.

Retained source pins:

| Evidence | SHA256 |
|---|---|
| Native `flash_serve` | `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` |
| Host text disassembly | `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` |

See the [approved feasibility design](../../../docs/research/halogen-recurrent-snapshot-adapter-feasibility-20261006.md)
and [existing wire codec](../halogen_pld_proposal_wire.py). The saved stack and
opaque extended-state arrays here are synthetic images. Their equality does
not prove actual XSAVE preservation, unwind/signal behavior, indirect-entry
exclusion, atomic installation, native pointer lifetime, reset synchronization,
producer readiness, authoritative-output handoff or acceptance. Those proofs
are required before a real consumer/producer connection or hardware qualifier.

## Guarded host CPU build and test

From the repository root, use the existing Python and MSVC installation:

```powershell
python -B scripts/benchmarks/halogen_pld_nohit/run_cpu_harness.py --phase green
```

The runner uses the reviewed `server/host_frames.py` and `server/winjob.py`,
checking helper hashes before import. It starts only its own suspended children
in kill-on-close Windows jobs, requires both physical and commit reserves of
22 GiB before launch/resume, and samples the 18 GiB reserve every 250 ms while
they run. It has a 90-second compiler deadline and 10-second harness deadline;
reserve/telemetry/cleanup failures fail the run. Construction exceptions retain
and close an attached recovery owner. It never installs or discovers a compiler
outside the named existing BuildTools path. Build flags are C++20, `/W4 /WX`,
`/O2`, `/MT`; logs, objects and executable remain below `_artifacts/` here.

The four small contract groups cover stock LEA/continuation and unchanged saved
state; malformed last field/last ID and missing caller/publication truth; exact
one/three-ID writes with destination canaries and allowance limits; stale epoch,
one-shot rejection and finite-ledger exhaustion. The initial decline-only
scaffold compiled and failed 38 behavioral checks (RED), then the implementation
passed with zero failed checks (GREEN). These are CPU semantics, not serving
qualification.

Local run receipts retain source/executable hashes, exact owned child identities,
exit/cleanup evidence, minimum reserve observations and maximum sample gap.
`--phase red` is only for the historical failing scaffold or a deliberately
broken implementation; a passing current consumer is expected to fail that
runner expectation.
