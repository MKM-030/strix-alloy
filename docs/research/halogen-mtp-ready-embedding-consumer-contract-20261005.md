# Halogen 0.16.2 ready embedding consumer contract

Date: 2026-10-05. This is a default-off source candidate for one immutable model generation. Host-only checks cover the cache, artifact codec, readiness, and sequence APIs. Native integration, NPU arithmetic, head parity, acceptance, and serving performance require separate root-owned receipts. The candidate emits those qualification fields as false. This document does not grant live admission.

Completed root-owned GPU controls are retained in
[the status report](halogen-npu-ready-embedding-status-20261005.md) and
[structured evidence](halogen-npu-ready-embedding-20261005.json). Both preserve
output and native acceptance, but both slow decode. The consumer remains off;
no NPU production or acceleration has been qualified.

## Route and scope

`scripts/benchmarks/halogen0162_mtp_embedding_cache.c` retains the old `gpu64-v1` M1-only behavior. The distinct mode `ready64-v1` borrows an already completed 5120-byte BF16 embedding projection at count1 head entry. It skips only the exact native embedding gather, embedding RMS, and E M1 launches. It retains the native FC dispatcher, including its first-call initialization and global side effects. At the Wire-D seed launch it substitutes only argument0, the embedding input, with the borrowed row. Native hidden input, seed destination, residual, state, history, model fields, and subsequent mixer outputs retain their original pointers.

The model's `+0xb00` output scratch is never rebound. Later mixer FCs write this scratch at head offsets `0x17dbe76` and `0x17dc017`, so using it as an immutable ready-row output would corrupt the imported rows. Ready rows are never passed as a kernel output. The row pointer is held by the exclusively owned serial head until the consuming seed launch is enqueued on the same default stream.

Only known native callers, count1, supported token IDs, the pinned single model/thread generation, Wire-D, and wave1 are eligible. Other counts, unsupported tokens, excluded callers, and retired generations use the original head. An armed hit with malformed kernel identity, dimensions, arguments, ordering, duplicate seam, or incomplete seed route fails stop with exit79; it never retries a possibly submitted candidate operation.

## Independent admission gates

Both compile gates default to zero. `gpu64-v1` needs `HALOGEN_EMBEDDING_CACHE_ENABLE_NATIVE_CANDIDATE=1`; `ready64-v1` needs `HALOGEN_EMBEDDING_CACHE_ENABLE_READY_CANDIDATE=1`. Defining one does not admit the other. An unset mode installs no detour. Native activation is limited to the exact `flash_serve --ck` executable and preserves the old full executable, full head, full FC dispatcher, ELF, mapped-span, prologue, and call-byte hash checks.

Required ready environment values:

| Variable | Value |
|---|---|
| `HALOGEN_MTP_EMBEDDING_CACHE` | `ready64-v1` |
| `HALOGEN_MTP_EMBEDDING_CACHE_READY_POLICY` | `fixed-v1` or `capture-v1` |
| `HALOGEN_MTP_EMBEDDING_CACHE_GENERATION` | Nonzero 32 lowercase hexadecimal digits |
| `HALOGEN_MTP_EMBEDDING_CACHE_MODEL_BINDING` | Nonzero 64 lowercase hexadecimal digits |
| `HALOGEN_MTP_EMBEDDING_CACHE_PROVENANCE` | Nonzero 64 lowercase hexadecimal digits |
| `HALOGEN_MTP_EMBEDDING_CACHE_IMMUTABLE` | `engine-single-generation-v1` |
| `HALOGEN_MTP_EMBEDDING_CACHE_DIR` | Fresh `/tmp/alloy-mtp-embedding-cache-<generation>` |
| `HALOGEN_MTP_EMBEDDING_CACHE_CAPACITY` | Optional integer1..64; default64 |
| `HALOGEN_MTP_WIRE` / `HALOGEN_LQ8_WAVE` | `D` / `1` |

`HALOGEN_MTP_FC_QUALITY` must be absent. Root owns other tap exclusions, checkpoints, runtime/context admission, model immutability, bounds, deadlines, reserves, and the original engine lifecycle. Cache generation binds the artifact and directory; it need not equal the service's separately generated run ID.

The model-binding digest names the root-owned receipt for the exact checkpoint/table/gamma/FC bytes and arithmetic. The provenance digest names the external origin receipt. The consumer compares these opaque bindings to the sealed artifact and retains live pointer/descriptor identities; it cannot infer numerical provenance from an arbitrary digest string. Row count, finite BF16, and matching digests do not prove model arithmetic or NPU parity.

## Policies and lifetime

`fixed-v1` additionally requires `HALOGEN_MTP_EMBEDDING_CACHE_READY_ROWS` and `HALOGEN_MTP_EMBEDDING_CACHE_READY_ROWS_SHA256`. The path must be absolute, with no symlink, dot, dot-dot, or empty components. The opened file must be regular, owned by the serving effective UID, single-linked, and have no write permission bits. Its bounded captured bytes and the same opened descriptor must both match the supplied SHA256. Device/inode/size/mode/owner/link/mtime/ctime must remain stable across the read. Exact artifact length, reserved zeros, generation, model binding, provenance, capacity, unique token IDs, origin, and finite BF16 words are validated before detours are installed.

Import H2D occurs once at the first eligible head, when the native HIP context/model binding exists. Import records completion events and drains the default stream before rows become visible. Root must issue warmup outside timed serving. A fixed miss performs the full original gather/RMS/E M1 route with no capture or eviction. Imported rows remain unchanged throughout the generation. This policy makes GPU-prepared and externally NPU-prepared static controls use the same fixed token set. Fixed serving performs no file polling or per-head D2H.

`capture-v1` refuses either import environment variable. A miss always launches the original E M1 exactly once and may capture its native projected output by D2D plus completion event. A readiness race between entry lookup and E FC still runs original M1. Pending rows are misses; they are never borrowed or overwritten while incomplete. Ready hits borrow the completed row directly. The bounded cache can replace completed slots; capture-policy rows are not a fair fixed-set performance control until exported and replayed with `fixed-v1`.

As before, any external HIP free, context switch/destruction, device switch, or reset conservatively retires the cache, drains before freeing, and fails stop if it occurs during a head. Root must guarantee the single immutable device/context generation and no interposition bypass. The shim does not claim exhaustive HIP driver/reset interception.

## Artifact ABI `HGNERC01`

All integers and BF16 words are explicitly little-endian. Header size128, row size5120, record size5128. Exact total length is `128 + count * 5128`, with count1..64 and maximum328320 bytes. Trailing bytes are rejected.

| Header offset | Bytes | Meaning |
|---:|---:|---|
|0|8|ASCII `HGNERC01`|
|8|4|Version1|
|12|4|Header size128|
|16|4|Row size5120|
|20|4|Count1..64|
|24|4|Origin1: native GPU capture; origin2: externally prepared row|
|28|4|Reserved zero|
|32|16|Exact generation bytes|
|48|32|Model binding digest bytes|
|80|32|Provenance digest bytes|
|112|16|Reserved zeros|

Each record contains token ID u32 at0, reserved zero u32 at4, and 2560 BF16 words at8. IDs are unique and in0..248319. Every word must have exponent bits unequal to `0x7f80`; infinity and NaN are rejected. Finite zero, subnormal, and signed values are supported.

## Capture harvest before stopping

The service's lease stop can use SIGTERM/SIGKILL, so a destructor alone is insufficient for artifact availability. In an idle capture process with a bound live model, root creates the exclusive owned regular0600 file `<cache directory>/ready-export`, containing exactly the32-character generation plus one newline (33 bytes). Root then invokes one serial request that reaches the existing MTP head on the bound engine thread. An excluded count>1 head can trigger harvest too.

At head entry, overlapping/nested ownership is rejected before inspecting the trigger. Capture mode checks the trigger's bounded content and stable file identity, drains the stream, exports and encodes actual captured rows, then publishes exclusive0600 `ready-rows.bin`, `ready-rows.json`, and `capture-result.json`, fsyncing the files and directory. Metadata includes artifact SHA256, exact bytes, generation/model/provenance, origin1, and count. The trigger is consumed once. A duplicate or corrupt trigger fails stop. Remaining heads in that capture process run native. Root must copy/verify the exported binary and seal a readonly artifact before a separate fixed run.

Normal destructor export is retained as a fallback for a live, initialized, unharvested capture process on the bound thread. Retired or uninitialized caches have no export. An empty capture set cannot produce a valid artifact. No signal handler, background worker, lifecycle change, or request-body patch was added. Destructor-only result availability is not guaranteed by a forced stop.

Fixed mode returns before the trigger's filesystem check. Root can retrieve the preserved static `uint64_t` symbols `ready_hits`, `native_fixed_misses`, `gather_skips`, `rms_skips`, `m1_skips`, and `seed_rewrites` by bounded idle reads from the exact process/loaded SO identity. Do not strip the SO symbol table. Counters are written only by the serial head owner. A completed successful direct hit increments each of the four skip/rewrite counters once. Fatal in-progress heads can leave partial counters and must be rejected. Normal finish also publishes `result.json` and `ready-result.json`.

## Pinned native launch evidence

The retained host text disassembly is `server/.local/optimization9h-20261004/mtp-route-static-20261004/host-text-disassembly.txt`, SHA256 `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`. Pinned engine SHA256 is `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`. These source claims use retained text only; this agent did not read engine/model payloads or operate hardware/providers.

| Operation | Kernel RVA | Native launch return RVA | Native argument contract |
|---|---:|---:|---|
|Gather|`0x18d5b40`|`0x17db44e`|table `model+0x4f0`, device token `model+0x730`, output `model+0x6c8`|
|Embedding RMS|`0x18d5160`|`0x17db51c`|input/output `model+0x6c8`, gamma `model+0xae8`, i32 width2560/groups1|
|E M1|`0x18d6690`|`0x17fdba0`|descriptor weight+0x10, native E input/output, K=N2560|
|Wire-D seed|`0x18d5b58`|`0x17dbb96`|E `model+0xb00`, H `*(base+0x18db228)`, destination `model+0x6d0`|

Gather/RMS/seed use grid1,1,1; block256,1,1; shared0; streamNULL. E M1 uses grid160,1,1; block256,1,1; shared0; streamNULL. These shapes are independently derived from push configurations: `r15=0x100000100` at0x17db38f and `r12=r15+count-0x100` at0x17db39c..3a0; count1 gives0x100000001. Gather0x17db3a7..3bd, embedding RMS0x17db452..468, and Wire-D seed0x17db9bd..9d3 pass preserved r12/r15, z1, and zero shared/stream. The RMS width/group are DWORD stores at0x17db492/49a. The seed D path constructs exactly three arguments at0x17db9e0..a1d and jumps from0x17dba5f to the shared call0x17dbb91.

The old full-head hash covers the exact gather/RMS/seed call bytes, and ready activation additionally checks each call signature and the expanded readable kernel-registration span. The hidden RMS call at0x17db632 shares the RMS identity and is always forwarded. The hidden FC seam at0x17db663 always executes native. Successful armed order is gather→embedding RMS→E M1→seed, with exactly one E/H FC. Hidden/state work between E M1 and seed is retained.

## Host validation and limits

Fresh mapping checks now group at most eight ranges in one scan, preserving
single-VMA containment, permissions, overflow checks, and current model/token
comparisons. Argument-vector memory is checked before copying its pointers;
the copied pointees are validated in a second fresh scan before dereference.
No mapping snapshot persists across seams. Warmed complete hits use 18 scans
instead of 39; warmed misses use 9 instead of 19. The separate focused host
check `scripts/benchmarks/tests/test_halogen_embedding_maps.c` reproduced the
old scan-count failure and passed the grouped scanner with real mapping,
permission, unmapped-hole, extent, and current-binding checks. The source also
passed optimized Werror shared-library compilation and the fixed GPU cohort.

Fixed-row launcher preflight now checks serving UID 0 and no writable mode
bits, including their stability across the read. UID 0 is retained evidence
from the pinned image, unchanged no-user-override launch, and owned
`flash_serve` effective UID. A captured 0600 file is not a valid fixed import;
the root control used a separately sealed root-owned 0444 copy.

The focused test `scripts/benchmarks/tests/test_halogen_ready_embedding.c` uses libc mock allocations/copies/events and includes the core-only source. It checks pending fallback, ready lookup without copy, fixed lookup immutability, guaranteed original capture despite changing readiness, import/export, exact binary roundtrip through maximum64 rows, reserved fields, trailing/truncated extent, model/provenance/generation mismatch, invalid origin/count/token, duplicate IDs, nonfinite BF16, reimport failure, and malformed/duplicate sequence failure.

Host commands use the existing WSL compiler, without HIP/engine linkage or hardware access:

```text
gcc -std=c11 -O2 -Wall -Wextra -Werror scripts/benchmarks/tests/test_halogen_ready_embedding.c -o /tmp/halogen-ready-embedding-host-test
/tmp/halogen-ready-embedding-host-test
gcc -std=c11 -O2 -Wall -Wextra -Werror -fPIC -fno-optimize-sibling-calls -fsyntax-only scripts/benchmarks/halogen0162_mtp_embedding_cache.c
gcc -std=c11 -O2 -D_FORTIFY_SOURCE=2 -Wall -Wextra -Werror -fPIC -fno-optimize-sibling-calls -DHALOGEN_EMBEDDING_CACHE_ENABLE_READY_CANDIDATE=1 -c scripts/benchmarks/halogen0162_mtp_embedding_cache.c -o /tmp/halogen-ready-embedding-host-source.o
gcc -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined scripts/benchmarks/tests/test_halogen_ready_embedding.c -o /tmp/halogen-ready-embedding-host-sanitized-test
/tmp/halogen-ready-embedding-host-sanitized-test
```

The focused optimized test and ASan/UBSan test each exited0. The full native source passed syntax-only and optimized fortified object compilation with Werror. The object was not linked or loaded. Owned files passed `git diff --check`; they remain unstaged.

These checks do not execute detours, native kernel submission, file-trigger export through a running engine, provider preprocessing, NPU preparation, complete-head parity, acceptance, or serving benchmarks. Root must independently qualify all of those and compare original native serving, GPU-prepared fixed rows, and NPU-prepared fixed rows on identical predeclared tokens/settings. Preparation latency and transfers belong in the result; no speedup is claimed here.
