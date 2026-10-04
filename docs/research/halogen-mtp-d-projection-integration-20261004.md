# Count1 wire-D projection publication before native seed-add

The concrete first implementation is a new disabled-by-default **two-output
shadow publication shim**, with exact-version detours on full-head entry
`0x17db310` and FC dispatcher entry `0x178cf90`. The full-head detour supplies
validated TLS identity. The dispatcher detour observes embedding FC, calls the
original embedding and hidden FCs exactly once, and publishes both candidate
BF16 projections at the hidden-FC return boundary, before the original head
launches seed-add. Native normalization, seed-add, layer48, head history,
vocabulary projection, proposal caching, accepted-prefix replay and target
verification continue through the original code.

This is an implementable source-derived seam, not a completed implementation
or hardware qualification. No new C, packet helper or responder was written
for this audit. No engine, WSL, provider, GPU, NPU, model/checkpoint payload,
launch, compilation or test was performed. The user-owned server remains
outside this work. Full D/head/NPU/acceptance/speed remain unqualified.

## Evidence and exact-version pins

The audit reads retained disassembly text, ordinary sources and existing
metadata. Engine/code hashes below are the previously sealed contract, not a
new payload read. The text/source hashes were rechecked with `Get-FileHash`.

| Evidence | SHA256 |
|---|---|
| Native engine, 26,052,768 bytes | `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` |
| Original gfx1151 code object | `45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83` |
| `host-text-disassembly.txt` | `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` |
| Existing complete-MLP publication C | `91fead8839c6135ec45b7b47032b3b7c0a5c0812bbac3fedbad0d30a17bd445d` |
| Existing complete-MLP quality wire | `77e9cc365ce850faa2bbb98a490fe98dd5a50b0210be61bd0a2372c971ce71de` |
| Existing hidden-RMS head/TLS tap C | `4d612044fb5e84932726d8a4568d2ca3bd463832eeab875376d7c286c8640603` |
| Existing native FC dispatch note | `e6f0ef9eb1cb1c73dc13df9aaf1a95977e97eee50cb8be85fe9dda5c9faa48c0` |

Static evidence is in
`server/.local/optimization9h-20261004/mtp-route-static-20261004/`:
`host-text-disassembly.txt`, `host-frames.txt`,
`kernel-registrations.json` and `cpu-d-input-static-audit.json`.
The [FC dispatch audit](halogen-native-d-fc-dispatch-20261004.md) supplies the
normal store7 route and exact shader contract. The
[head-state ABI](halogen-mtp-full-head-state-abi-20261004.md) supplies the
controller/history map. The existing
[quality publication receipt](halogen-mtp-quality-publication-source-20261004.md)
describes its separate complete-MLP seam; that source and packet protocol stay
unchanged.

## Exact call chain and pointers

Use `base` for the native ELF load bias and `model` for the full-head's first
argument. `*(model+offset)` and `*(base+RVA)` are **host-held device pointer
values**, not host tensor storage. Read those fields only after validating
host mappings. Do not follow device pointers with CPU `memcpy`.

The head `0x17db310` has observed SysV ABI
`int32_t head(void *model, const int32_t *tokens, int32_t count, int32_t position)`:
RDI=model, RSI=host token pointer, EDX=count, ECX=ABI position, EAX=proposal.
Its FDE covers `0x17db310..0x17dc289`; `.text` file offset is RVA minus `0x1000`.
Its previously sealed function SHA is
`132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20`.

| Stage | Exact instruction or return boundary | Inputs and outputs |
|---|---|---|
| Embedding gather | launch `0x17db449`, return `0x17db44e`, identity `base+0x18d5b40` | Table `*(model+0x4f0)` and device token `*(model+0x730)` -> `*(model+0x6c8)` |
| Embedding RMS | launch `0x17db517`, return `0x17db51c`, identity `base+0x18d5160` | **In place** at `*(model+0x6c8)`; raw gamma `*(model+0xae8)`; width2560/groups1 |
| Embedding FC | setup `0x17db520..0x17db540`; call `0x17db543`; **return `0x17db548`** | Descriptor `model+0x908`; e_norm=`*(model+0x6c8)`; e_projection=`*(model+0xb00)`; N2560/M=count/K2560 |
| D branch | `0x17db54f` compares A; `0x17db558` compares D | Require actual byte `*(base+0x18dccc0)=='D'` and initialized guard `*(base+0x18dccc8)!=0` at the FC seam |
| Whole-row hidden RMS | launch `0x17db62d`, return `0x17db632`, identity `base+0x18d5160` | Source `*(model+0x6d0)` and raw gamma `*(model+0xaf0)` -> h_norm=`*(base+0x18db210)`; width10240/groups1 |
| Hidden FC in D | setup `0x17db636..0x17db659`; call `0x17db65e`; **return `0x17db663`** | Descriptor `model+0x980`; h_norm=`*(base+0x18db210)`; h_projection=`*(base+0x18db228)`; N2560/M=4*count/K2560 |
| D continuation | `0x17db665` confirms D; `0x17db67a` jumps to `0x17db9bd` | No projection consumer between hidden FC return and seed setup |
| Native seed-add | setup `0x17db9e0..0x17dba5b`, identity load `0x17dba4b`, common launch `0x17dbb91`, return `0x17dbb96` | e_projection=`*(model+0xb00)`, h_projection=`*(base+0x18db228)` -> residual=`*(model+0x6d0)` |
| Original head remainder | layer48 call `0x17dbbe1` -> `0x17d9eb0` | Native layer48 attention/MLP/HC, history and vocabulary continuation |

Both FC calls enter **the same dispatcher at `base+0x178cf90`**. The directly
observed six register arguments are:

| Register | Width/type used by dispatcher | Meaning |
|---|---|---|
| RDI | host pointer | Weight descriptor |
| RSI | device pointer | BF16 input |
| RDX | device pointer | BF16 output |
| ECX | int32 | N/output columns |
| R8D | int32 | M/row count |
| R9 | int64 | K/input columns (head writes R9D=2560, zero-extending) |

A C detour should use this ordinary ABI, e.g. a `void`-returning FC function
pointer with `(void *, const uint16_t *, uint16_t *, int32_t, int32_t, int64_t)`.
The head consumes no FC return value: `0x17db548` immediately loads a global,
and `0x17db663` immediately zeroes ESI. The generic dispatch's successful
epilogue `0x178ee70..0x178ee7e` also leaves no stable success value. Do not
invent an FC result code. Preserve native `errno` around observer work.

Count1 sizes are e_norm/e_projection=5120 bytes each and
h_norm/h_projection=20480 bytes each. Hidden RMS normalizes the entire
10240-element row once; its FC handles four contiguous2560 streams with the
same matrix. All four projection/input buffers are raw little-endian BF16
u16. NPU graph output FLOAT values must first pass shape, finiteness and
BF16-lattice checks, then become exact high16 words; publishing FP32 bytes
or FP16 words would corrupt the native boundary.

The native seed kernel is
`_ZN7halogen12_GLOBAL__N_116k_hyper_seed_addEPKtS2_Pt`, registered identity
`base+0x18d5b58` (registration `0x1851ce8`, GPU entry `0x24bc00`). Its kernel
arguments are the addresses of the head's stack-held e_projection,
h_projection and residual pointers, built at `0x17db9f5..0x17dba1d`.
For count1, it broadcasts the 2560-element embedding across four streams,
adds the already rounded e/h BF16 projections in FP32 and stores BF16 RNE.
The new projection shim must return to the original instructions and leave
this arithmetic native. Seed-add is not qualified by the projection graph.

## Prologue bytes and detour boundaries

The retained text and FDE identify these exact entry signatures:

```text
head 0x17db310 (file offset0x17da310), first32:
55 41 57 41 56 41 55 41 54 53 48 81 ec 98 00 00
00 b8 ff ff ff ff 80 bf 00 09 00 00 01 0f 85 31

FC dispatcher 0x178cf90 (file offset0x178bf90), first32:
55 41 57 41 56 41 55 41 54 53 48 83 ec 48 4c 89
cb 45 89 c5 89 cd 49 89 d6 49 89 f7 49 89 fc 4c

embedding FC call at0x17db543: e8 48 1a fb ff
hidden D FC call at0x17db65e: e8 2d 19 fb ff
```

The dispatch FDE covers `0x178cf90..0x178efa7`. Its first five bytes are the
three whole instructions `push rbp; push r15; push r14`, with no relative
addressing. The existing shim/tap pattern can copy those five bytes into an
original-call trampoline, then use an absolute indirect jump to entry+5.
A near RX thunk within signed32 displacement allows the entry's five-byte
E9 detour to reach a far C hook through an absolute jump. The same applies
to the head's identical firstfive bytes.

A future constructor must pin the engine and validate both original entry
signatures, ELF load segments, full head extent/hash, dispatcher extent and
both callsite bytes before installing either detour. Root must add the
dispatcher function hash from an independently guarded bounded binary read;
this audit does not invent it from a new payload read. A partial installation
or an already patched entry must fail before serving, not compose blindly
with an older tap. Install only in an owned process before work begins; the
existing five-byte write is not a concurrent hot-patching protocol. Keep the
original C/wire sources and old receipts sealed.

## Validated TLS provides identity; the FC ABI provides tensors

The hidden FC call can carry all requested data, but **not through its six
arguments alone**. RDI=`model+0x980` permits a checked descriptor identity;
it is not a substitute for the outer full-head lifetime or ABI position.
Never recover model from RBX or reach into the native stack for position.

1. The head wrapper uses its typed arguments, validates readable model
   `[model,model+0xb10)` and one readable host int32 token, count1, nonnegative
   ABI position, MTP byte `model[0x900]==1`, and a known head caller. Exact
   known **return addresses** are `0x17dcc08`, `0x17dcd54`, `0x17dcf49` and
   `0x17de236`, from calls at `0x17dcc03`, `0x17dcd4f`, `0x17dcf44`, and
   `0x17de231`. Unsupported counts remain native. Entry may precede lazy
   wire initialization; require actual D/initialized guard at FC, not an
   assumed entry default.
2. Allocate a bounded context for this invocation: run/sequence, model,
   token, ABI count/position, outer model-position `+0x220`, slot `+0xa0`,
   reset/epoch identity if supplied by root, e/h call counts, saved typed FC
   arguments and four tensor pointer values. Set `_Thread_local active` only
   around one `original_head` invocation. Save/restore previous TLS and track
   head depth, as in the existing hidden-RMS tap. The original head executes
   exactly once and its int32 result/errno are returned unchanged.
3. FC wrapper obtains `__builtin_return_address(0)` **in the wrapper itself**
   and converts it to RVA after a base/bounds check. Ordinary C calls to the
   original trampoline originate in the shim and are not eligible FC sites.
   At return-RVA`0x17db548`, require descriptor=`model+0x908`, X/Y matching
   model fields, N2560/M1/K2560, actual D/guard, exactly one e call, stable
   host fields and normal store7 descriptor shape; record those values.
   Call the original e dispatcher once. All other dispatcher calls remain
   native, including head-mixer FCs at `0x17dbd01` and elsewhere.
4. At return-RVA`0x17db663`, require live TLS, exactly one prior e call and
   exactly one h call, descriptor=`model+0x980`, X/Y matching globals
   `+0x18db210/+0x18db228`, N2560/M4/K2560, stable model/token/slot/wire,
   and unchanged e pointers. Validate host descriptor spans of0x78 bytes,
   descriptor `+0x00==0`, `+0x30==0`, `+0x10!=0` for the qualified normal
   Q8 route; root must bind both descriptors' raw weights to the qualified
   model/assets. Require overflow-safe tensor spans and pairwise separation
   of e_norm, h_norm, e_projection and h_projection, and separation from
   seed destination. Span arithmetic alone does not prove GPU allocation;
   checked HIP copies and later root qualification are also necessary.
5. Before and after sync/copy/wait, recheck all identity fields and pointer
   slots. `model+0x220` at this seam is still the **outer** position: the head
   installs its ABI position only at `0x17dbbad`, after seed-add. Bind request
   position to TLS ABI position and separately retain/check outer position.
   At head exit require one matched e/h pair, restore TLS and decrement the
   all-forward in-flight count even on disabled or unsupported paths.

TLS distinguishes threads but does not make the global scratch buffers
private. Root must prove one serial owned request and account for **all**
full-head calls, including excluded multirow calls. Any nested/overlapping
forward invalidates publication for the active epoch. A writing shim needs a
specified fail-stop/serialization policy if an overlap occurs after a device
write; a mutex protecting only sample allocation is insufficient. Preserve
default stream ordering and use checked `hipDeviceSynchronize`/`hipMemcpy`
before any host capture or candidate publication.

The qualified Q8 route has embedding identity `base+0x18d6690` and hidden
identity `base+0x18d66f0`, with GPU entries `0x2d1200/0x2d7800`, respectively.
Normal dispatch uses wrapper `0x17fd9a0`; M1/M4 wave path is selected with
`HALOGEN_LQ8_WAVE` unset/default1 or explicitly1. Both launch grid160x1x1,
block256x1x1, shared0/default stream. A later skip mode must be restricted
to this route; arbitrary quant override descriptors are not admitted.

## First publication: original once, then replace the two outputs

At matched hidden FC entry, invoke the original h dispatcher exactly once.
After its completion and checked device synchronization, e FC is also complete
and neither output has been consumed. Capture e_norm5120, h_norm20480,
native e_projection5120 and native h_projection20480; validate finiteness and
stable identity. There is no need to replay the full head for a shadow sample.

Send one request to the Windows responder and receive one **paired** response.
Only after complete packet validation and a final identity/epoch check copy
both candidates H2D, then synchronize. If either H2D or synchronization fails,
restore **both** saved native outputs, then synchronize; failure to restore
terminates the owned process (the existing quality shim uses exit79).
Missing/invalid/stale/timeout responses cause no device writes and retain both
original outputs. Invalid packets/capture errors disable further samples.
The hook then returns to `0x17db663`, allowing the original seed-add and head
remainder to execute once. Report both original and published hashes plus
copy/sync/result/restore counters; publication adds intrusive waits/copies and
cannot qualify speed.

This reuses the safety **pattern** of
`halogen0162_mtp_quality_publish.c`, not its MLP pointer or packet body. That
source hooks MLP`0x17bd410`, publishes one complete5120-byte result to
`*(model+0x6d8)`, and binds native routes; it cannot carry the four FC buffers.
The existing `HGNMLPQ1/HGNMLPR1` packets and `halogen_mtp_quality_wire.py` must
remain untouched. A new FC protocol should have distinct magic/version and
an exact fixed body:

| Proposed payload | Bytes |
|---|---:|
| e_norm, then h_norm | 25600 |
| Native e_projection, then native h_projection | 25600 |
| Shadow request body total | 51200 |
| Candidate e_projection, then candidate h_projection | 25600 |

A concrete proposed **new**224-byte header is
`<8sIIiiiIiiiI16s16sQQ32s32s32s32s>`, with these fields in order:
magic8 (`HGNFCPQ1` request / `HGNFCPR1` response), version1, body bytes,
sequence, TLS ABI position, slot, reserved0, ABI count1, token, outer model
position, wire uint32=68 (`D`), run nonce16, model/reset epoch16, native model
pointer uint64, reserved uint64=0, model-binding SHA32, graph-binding SHA32,
input-binding SHA32 and request-binding SHA32. This yields51424-byte shadow
request and25856-byte paired response including its final32-byte digest.
This layout is proposed for root review, not an existing accepted wire contract.

Model-binding is the SHA of a root-supplied canonical qualification manifest
covering native engine, checkpoint/assets, model instance and reset epoch.
Graph-binding is the SHA of a root-supplied canonical qualification manifest
covering graph/data/lineage, same-source CPU gate, NPU hardware profile and
provider identity. Exact canonical manifest bytes must be pinned by the
coordinator before arming. Input-binding hashes e_norm||h_norm (25600 bytes).
Request-binding hashes the first192 header bytes followed by the51200-byte
body. Response echoes every identity/binding field, changing only magic and
body byte count; its final digest covers its entire224-byte header and25600
candidate bytes. Sequence must be0..3; reserved fields zero; token and both
positions nonnegative; model/epoch/qualification identities must match the
armed coordinator. Both BF16 arrays must pass exact length/finiteness checks.
Never dereference the transported model pointer; it is an identity check.
Sequence+position+slot+run alone would not bind a persistent responder to a
changed model/reset epoch. Obtaining a trustworthy reset epoch is still a
lifecycle requirement, not an observed native reset hook from this audit.

Use bounded regular unchanged/no-follow files, exclusive synced temporaries,
atomic no-overwrite publication, complete request-binding digest and response
digest, finite BF16 checks and a small hard call cap. A distinct armed content
and disabled-by-default mode prevent accidental MLP/FC protocol confusion.
The old200-ms cooperative response wait is a bounded reference, not an NPU
latency promise. Root's external job/container deadline and22/18GiB reserves
remain mandatory. Resolve transport first: the C directory currently lives
in process/container `/tmp`, which is not automatically Windows-visible.
Do not assume Linux ownership/nlink/renameat2 semantics work across a Windows
bind mount; qualify a narrow bridge and actual atomic publication semantics.
The responder owns a persistent already qualified NPU session; never acquire
or compile providers inside this native head hook.

## Later skip mode: static feasibility and remaining proof

**Skipping only hidden FC** is statically possible: e FC stays original,
and the hidden hook waits for a paired NPU result before calling original h.
On missing/invalid response it calls original h once, leaving original e
untouched. On successful publication it can skip h; computing native e still
costs time. This requires a new explicit mode, separate receipts and a
fallback/publication failure contract because no native h result was saved.

**Skipping both FCs** requires the e hook too. At `0x17db543`, save its typed
arguments and defer the call without publishing an output. Let native hidden
RMS run. At `0x17db65e`, both normalized inputs are ready, so one request can
obtain both projections. The inspected instructions between e return and h
entry neither read nor overwrite e_projection; hence deferring e FC does not
alter a consumer before the paired publication. This establishes a local
control/data seam, not a demonstrated speedup or complete dispatch proof.

Before any candidate write, missing/invalid/timeout responses can fall back
by calling saved original e dispatcher and original h dispatcher **once
each** through their trampolines, synchronizing, then returning. Never use
preexisting e/h output bytes as backup: they may belong to an earlier head.
Partial H2D failure in skip mode has no saved current native outputs. It
needs a separately qualified recompute-both-originals recovery while inputs,
descriptors and epoch remain intact; if HIP/context integrity is uncertain,
terminate rather than letting seed-add consume ambiguous data.

The generic dispatcher has lazy environment/route initialization and alternate
paths: e.g. `0x17f8df0` checks initializer byte`0x18dd3c8` before descriptor
`+0x00`; Q8`0x17fd9a0` checks initializer byte`0x18dd1a0` and selection
`0x18dd198`; generic entry has initializer`0x18dd090`. Skipping calls bypasses
those side effects. First shadow mode retains them. Later skip mode must
prove allowed initialized state and no required side effect for the admitted
raw-Q8 route, or initialize it once through an explicit root-owned native
qualification step. It must not return early for an arbitrary dispatcher
caller/descriptor. Exact observed native kernel IDs in shadow receipts are
the useful admission evidence; descriptor pointer arithmetic alone is weak.

## Native lifecycle retained, and unresolved state/rollback limits

Because FC is stateless and seed-add/head remainder stay native, this seam
does not introduce a second attention cache or a private full-head state
transaction. Native layer48 still owns histories and produces/caches native
logits from the published projections. Return the original full-head result;
do not synthesize tokens, logits tags, continuation count or acceptance.
Before seed-add, paired native-output restoration can resume this same head
without having advanced layer48. After seed-add or layer48 writes, restoring
FC buffers is no longer whole-head rollback: never rerun the full head to
repair a failed sample or compare two candidates within the same state.

Native verification `0x17dcfc0` suppresses automatic head execution inside
target forward. Target accepted-prefix helper`0x17def00` remains authoritative
for target layers0..47. The controller later calls accepted-prefix head replay
through`0x17dcc90`/`0x17dcd4f`, often with count>1; ordinary target forward can
also invoke multirow head replay at`0x17de231`. Count1-only shim scope must
fall through on these other counts and record exclusions. Native bootstrap,
cached first-proposal bypass and reset behavior remain authoritative; the
responder's stateless FC arithmetic still needs per-model/reset identity.

The existing state note's unresolved native layer48 K/V, FD slot lifetime,
pool/carry and speculative suffix rollback semantics remain unresolved. Native
ownership avoids inventing new state machinery; it does **not** independently
prove those semantics or demonstrate unchanged acceptance after approximate
projection publication. Matched greedy output/acceptance runs and native
accepted-prefix lifecycle observations are required. Any future full-head
NPU path has additional private cache/rollback obligations and is outside
this stateless projection seam.

## Concrete next implementation after root reviews this seam

Add new FC-only C and wire/coordinator sources, keeping existing sources and
failed evidence sealed. Implement the head TLS wrapper plus generic dispatch
wrapper in **original-once shadow mode only**, with the exact caller/argument
checks above, bounded paired packet protocol, both-output backup/restore,
checked cleanup and counters. Do not include a skip flag in the initial
implementation. Root separately pins/binds the graph's explicit
BF16-rounded-original-decoded-FP32 lineage and actual native FC oracle,
including same-source CPU success before NPU admission.

After source review and bounded build qualification, root first exercises
unarmed/absent/invalid/stale/timeout and paired restore/fatal paths in an
exclusive owned window. Then qualify the transport, persistent responder,
strict hardware attribution and paired numerical output screen. Publication
quality/acceptance comes before a separate skip-mode source and rollback
qualification. Only matched end-to-end wall-time can later establish whether
FC offload plus transport beats original GPU FC execution.

## Subsequent root CPU preparation

The [retained root preparation](halogen-embedding-native-d-preparation-20261004.md)
has now independently read the exact sealed ELF and supplied the missing FC
dispatcher hash: `f8f9d77041011251d11d0b97d7298926aa053d5435310826a00c408e5bff24e9`
for 8215 bytes at file offset `0x178bf90`. The head hash and unique executable
PT_LOAD mappings match the prior contract. The engine was not executed.

The [paired packet codec](halogen-mtp-fc-packet-protocol-20261004.md) is now
implemented with the documented four-hash 224-byte header. Nine focused
offline tests passed, and an independent source review found no concrete
protocol blocker. This remains separate from an armed coordinator, native
publication, transport, provider initialization and runtime qualification.
