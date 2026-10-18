# Halogen fixed embedding checked-copy consumer

Date: 2026-10-06. Source-only, default-off variant of the previously measured
`ready64-v1` whole-branch consumer. No build, host execution, hardware action,
engine parity, acceptance, or performance qualification was performed for this
variant. Root owns those checks and any separate admission.

The earlier fixed control already retained native FC dispatch, skipped exact
embedding gather/RMS/M1, and directly substituted the resident E projection at
the Wire-D seed. It lost Decode performance by 21.760142%, despite identical
output and native acceptance. This variant changes runtime host validation and
fixed-row readiness bookkeeping, not GPU arithmetic or the skipped branch.
The old absent/`maps-v1` policy and capture behavior remain available.

## Admission and exact scope

Both `HALOGEN_EMBEDDING_CACHE_ENABLE_READY_CANDIDATE=1` and the distinct
`HALOGEN_EMBEDDING_CACHE_ENABLE_CHECKED_COPY_CANDIDATE=1` must be defined.
The latter defaults to zero. Activation additionally requires mode
`ready64-v1`, ready policy `fixed-v1`, and explicit
`HALOGEN_MTP_EMBEDDING_CACHE_HOST_VALIDATION=checked-copy-v1`. The launcher plan
uses `ready.host_validation="checked-copy-v1"`; unknown values and any capture
combination are rejected. Activation records `host_validation` and
`per_hit_event_query`. Existing executable/head/FC hashes, call signatures,
exact code/global mapping permissions, prologues and detour installation checks
remain unchanged.

This is eligible count1 Wire-D MTP Decode only. Other counts/callers and fixed
token misses use the native head. Target Prefill is outside the optimization.
Identical projection rows are intended to preserve proposal IDs and native
acceptance; no acceptance gain follows from this source mechanism.

## Checked-copy ABI and ownership

Each checked self `process_vm_readv` uses at most eight vectors and at most
`MODEL_BYTES+128` (2960) bytes. All source/destination extents, total length and
vector count are bounded. The return must equal the entire requested byte
count; errors and partial reads are rejected without consuming the result.
The helper preserves native `errno`. Runtime data need to be currently
readable; adjacent readable VMAs are allowed. No mapping or pointer lifetime
result is cached. Activation's exact permission checks remain separate.

Entry copies the model's `0xb10` bytes (including its `0x78`-byte E descriptor),
token i32, Wire-D byte and guard byte. Eligibility, initial head values and
binding derive from the same copies. Null token pointers are rejected at entry
and at active context checks. Every existing context boundary takes a fresh
model/token/wire copy, including checks before and after native FC work.
Completion copies model/wire only and preserves the previous binding-plus-slot
rule: token readability or token/outer position equality at completion are not
newly required. The original live
descriptor address still enters the native FC dispatcher, preserving pointer
identity and native initialization/side effects.

Launch validation first copies the argument-cell addresses, then copies their
contents into owned slots. Embedding RMS width/groups use exactly four bytes;
all other observed cells use eight. Only those copied values are inspected.
Seed also freshly copies the native H output pointer. Its submitted three-cell
vector contains the checked E/H/destination values, changing only the E value.
A native M1 forwarded on a fixed miss likewise uses owned copies of its five
checked values. The HIP launch API's retained synchronous host-argument
consumption contract bounds their stack lifetime.

An entry read failure excludes the candidate before arming. Read/identity/order
failure after arming fails stop; there is no native retry of a partly submitted
candidate. TLS/head serialization, single thread/model binding, descriptor and
pointer identities, exact kernel/caller/shape/sequence checks and conservative
HIP allocation/context retirement remain in force. Imported GPU rows are never
outputs. Import drains the default stream before publishing valid fixed rows,
then sets a fixed-only synchronized flag. This policy has no row capture,
eviction or write path, so ready lookup can omit recurrent event queries.
Retirement clears the flag and drains before releasing rows. Capture mode keeps
its original event readiness queries and replacement rules.

Neither checked copying nor the old scanner creates an atomic model snapshot.
Arbitrary concurrent host writers, ABA remapping and lifecycle-interposition
bypasses remain outside the existing exclusive immutable-owner contract. The
fresh copied bytes remove unchecked CPU dereferences after a maps check; they
do not prove ownership against an uncooperative writer. Linux permits partial
and non-atomic transfers: see the
[Linux manual](https://man7.org/linux/man-pages/man2/process_vm_readv.2.html).

## Retained coverage and bounded decision

The fixed plan is
`C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/ready-embedding-fixed-plan-83abe75704d746ed80ad6ca0974c25fd.json`.
It freezes 52 original GPU projections, artifact SHA256
`3cf0bcb2f83db17c6cf7734568ebdd37d7a06f42dd8abcb472cb9f200e3afd48`,
266784 artifact bytes. The retained control allocated 64 slots, 327680 GPU row
bytes; 52 slots would contain 266240 row bytes, but this variant retains the
existing launcher capacity of 64.

The completed `cda6bf280e7242fd8b20c1cb5162ee56` before/after counters bracket
one warmup plus three measured requests. Hits and each gather/RMS/M1 skip/seed
rewrite delta are 292; fixed misses and retirements are zero. The existing
count1 trace and repeated response schedule imply 73 hits per request (219
measured hits), but the retained counter reads are aggregate, not separate
per-request observations. Each response accepted 69/115 drafts with identical
output hash. General token/prompt coverage is not established.

The old warmed hit performed 18 fresh maps scans. This implementation replaces
their live `/proc` generation, text parsing and subsequent raw reads with
bounded self-copy calls; an additional small seed-H copy is included. Exact
copy/syscall cost is unmeasured. Existing parser replay excluded filesystem
reopen and live map generation; its projected 161 ms saving across 292 hits
cannot qualify this separate mechanism. Serving must show that removed branch
cost exceeds lookup, checked copying and preparation/upload amortization.
The original E M1 component was 0.152995 ms (about 11.17 ms for 73 hits); full
gather/RMS/M1 branch cost remains unmeasured. No speedup is claimed.

## Focused root-owned host checks

The new test is `scripts/benchmarks/tests/test_halogen_embedding_checked_copy.c`.
It exercises actual self copying, adjacent readable VMAs, unmapped holes and
partial-read rejection, bad/overflowing ranges, exact 4-versus-8-byte launch
cells, copied-value ownership, fresh token/descriptor/device-token/wire/position
mutation checks, slot-only completion semantics and fixed lookup without event
queries/copies. The constructor is disabled by its inactive environment shim;
no HIP/engine activation occurs. These are proposed commands, not executed:

```text
gcc -std=c11 -O2 -Wall -Wextra -Werror scripts/benchmarks/tests/test_halogen_embedding_checked_copy.c -o /tmp/halogen-embedding-checked-copy-host-test -ldl -lcrypto -lpthread
/tmp/halogen-embedding-checked-copy-host-test
gcc -std=c11 -O2 -D_FORTIFY_SOURCE=2 -Wall -Wextra -Werror -fPIC -fno-optimize-sibling-calls -DHALOGEN_EMBEDDING_CACHE_ENABLE_READY_CANDIDATE=1 -DHALOGEN_EMBEDDING_CACHE_ENABLE_CHECKED_COPY_CANDIDATE=1 -c scripts/benchmarks/halogen0162_mtp_embedding_cache.c -o /tmp/halogen-embedding-checked-copy-source.o
```

Keep the original fixed artifact token IDs/row bytes, stock bookends, output and
acceptance accounting, preparation/upload costs and restoration receipts for
any later root-owned comparison. All tolerances and memory/deadline gates remain
unchanged.
