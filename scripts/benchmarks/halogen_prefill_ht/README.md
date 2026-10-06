# Frozen ordinary Prefill HT capture

The capture module was independently reviewed, compiled and successfully used
for one original ordinary DeltaNet QKV packed-trunk call on2026-10-06. It is
default-off and implements no replacement kernel. The separate `replay.c` was
compiled and used in one completed finite component screen. Neither tested path
qualified a speed gain; see
`docs/research/halogen-prefill-ht-component-screen-20261006.md`.
Root owns compilation,
independent review, hardware windows and the normal engine lifecycle. The final
original server must be restored ready and left open.

The finite source design and bounds are in
`docs/research/halogen-prefill-ht-frozen-replay-design-20261006.md`. The source
uses two pinned hooks: FC dispatcher `0x178cf90` and packed helper `0x17f8280`.
Both have the complete non-relative five-byte prologue `push rbp; push r15;
push r14`. Each trampoline executes those instructions and resumes at `+5`.
The full executable, ELF load mapping, full function hashes and 32-byte entry
signatures must match before either hook is used.

The FC thread scope accepts only return RVA `0x1791400`, the retained ordinary
DeltaNet QKV call. The packed helper must be called at return RVA `0x178cfc0`
with the same descriptor/input/output/dimensions, no nested FC scope,
`M8192/N10240/K2560` and `output_float32=false`. The original functions forward
once with their arguments and return value preserved, even if observation fails.
Activation/hook failures exit with code79 rather than run a partial hook setup.

## Independent receipt is mandatory

The constructor creates an exclusive owner-only directory. Root must create
`tensor.receipt` there, mode0600, regular file, one link, no symlink. Its exact
SHA256 is provided before engine startup in
`HALOGEN_PREFILL_HT_CAPTURE_RECEIPT_SHA256`. The file is loaded and verified
when root arms the observer. The following **format example is not a valid
receipt**; each placeholder must be replaced with independently pinned facts:

```text
schema=ordinary-qkv8192-v1
tensor=<exact diagnostic tensor name containing only letters/digits/underscore/dot>
store=<unsigned decimal store>
variant=<unsigned decimal variant>
mode=<independently bound actual unsigned descriptor mode>
N=10240
K=2560
packed_bytes=<declared exact tensor payload size>
checkpoint_sha256=<64 lowercase hexadecimal characters>
index_sha256=<64 lowercase hexadecimal characters>
```

Use ASCII/LF with one final newline and canonical decimal values without leading
zeros. The exact name is compared against the descriptor's bounded diagnostic
name. Descriptor mode, N and K must agree. No whole-model allocation is copied.
Only independently supported descriptor modes3/4 are admitted. The packed
length is taken only from this sealed receipt; it is never derived
from shape, guessed from mode or inferred from another tensor's format.

The independent loader audit in
`docs/research/halogen-prefill-ht-independent-audit-20261006.md` now binds
store16 to the descriptor initializer and `mode=(variant>>1)&0x7f`; the pinned
v2 variant4616 therefore supports expected mode4. The live mode must still
match the receipt exactly. The actual selected v2 tensor metadata is retained
in `server/.local/optimization9h-20261004/prefill-qkv-metadata-only-20261006.json`.

Root must separately establish that the receipt describes the current pinned
checkpoint and selected tensor and hold an exclusive immutable allocation
lifetime for the owned call. Before observer copies, the source queries
`hipMemGetAddressRange` for packed/signs/scales/X/Y and requires each whole
bounded span to fit its actual returned allocation. After original completion,
it queries again and requires the same allocation bases/extents and unchanged
descriptor identities. Missing/failed range queries or changed snapshots
invalidate the capture. These snapshots establish current coverage; they cannot
prove that an allocation was never freed and replaced between snapshots without
root's exclusive lifetime contract. A file-index store/variant alone does not
establish the live descriptor mode. Do not fill an unknown mode by guessing.
Absent or invalid independent tensor/lifetime binding must prevent root arming.

## Root-owned activation contract

Build after review with the existing Linux compiler/runtime, without changing
the model, driver or global WSL settings:

```text
gcc -O2 -Wall -Wextra -Werror -shared -fPIC -fno-optimize-sibling-calls \
  capture.c -ldl -lcrypto -pthread -o NEW_CAPTURE_SO
```

Set:

```text
HALOGEN_PREFILL_HT_CAPTURE=ordinary-qkv8192-v1
HALOGEN_PREFILL_HT_CAPTURE_DIR=/tmp/alloy-prefill-ht-capture-<fresh 32 lowercase hex>
HALOGEN_PREFILL_HT_CAPTURE_RECEIPT_SHA256=<exact canonical receipt SHA256>
```

Load through the normal owned preload/lifecycle. No mode means no host hooks,
directory, staging, worker or capture. Exported HIP wrappers still forward to
the original runtime when the shared object is loaded. Existing full executable
and mapped function hashes also reject already altered hook targets.

After readiness and receipt validation, create an exclusive owner-only `armed`
with the exact content `ordinary-qkv8192-v1-ready\n`. Submit one frozen
non-repetitive ordinary Prefill request with a genuine8192-token chunk. Root
must ensure exclusive workload ownership and current physical/commit reserve;
the capture adds at most about264 MiB host staging and writes at most300 MiB.
There are no observer device allocations. After the request has fully returned,
create an exclusive owner-only `harvest` containing
`ordinary-qkv8192-v1-harvest\n`.

The observer completes prior work, copies only packed/signs/scales/X, forwards
the original packed helper, completes it and copies its original Y. Device data
is preserved as raw native16-bit words; no conversion or numerical tolerance
is used. The observer adds two device synchronizations, five D2H copies and ten
bounded allocation range queries.
Capture/file export overhead is diagnostic and must never become a token-rate
measurement. The worker waits at most30 minutes for harvest; missing harvest
does not authorize restarting the request or engine.

## Fixture and limits

A valid fixture requires `complete.json` with `passed=true`, one original packed
call, complete inputs/reference, successful parent request and root's external
checkpoint/allocation/lifecycle evidence. Partial files are invalid fixtures.
Binary files are:

- `packed.bin`: exactly the declared receipt size, maximum64 MiB.
- `signs-u16.bin`:5120 bytes; `scales-u16.bin`:20480 bytes.
- `x-u16.bin`:41943040 bytes; `y-reference-u16.bin`:167772160 bytes.
- `descriptor-before.bin` and `descriptor-after.bin`:120 bytes each. These
  contain diagnostic process addresses and must not be reused as live pointers.

`records.json` includes per-payload hashes, pinned caller lineage, actual
descriptor mode, current router and rotation/partial pointers/capacity before
and after, HIP kernel submission function/grid/block/shared/stream/caller
geometry, and original library
submission handle/stream/pointers when present. Source-global values are current
observations; their scratch/router allocation provenance remains unbound. The
five copied tensor allocation bases/extents are recorded separately. The capacity is
labelled in16-bit **elements**, as established by the retained allocator audit.

The opaque library algorithm byte extent and identity, the exact packed-weight
preparation branch, and native environment controls remain explicitly unbound.
An observed library submission is not relabelled as original-weight preparation.
There are at most16 recorded kernel submissions,16 files including external
triggers/receipt, and300 MiB total output. A limit breach invalidates the fixture.
No additional diagnostics are launched by this source.

## Relevance to throughput

GPU is the intended later comparison: complete stock preparation/matmul versus
the existing native packed HT rotation/multiply pipeline on this frozen data.
CPU supplies metadata and correctness checks. No supported equivalent NPU
packed-HT/GPU-buffer boundary is established here, so this capture supplies no
reason to insert the NPU into this operation.

The completed capture is retained under
`server/.local/optimization9h-20261004/prefill-ht-capture-9ac79c0cb8c4479189d101c12e6f588f/trace/`.
It records one unchanged M8192/N10240/K2560 operation with mode4, two observer
synchronizations, five D2H copies and ten successful allocation range queries.
The preparation launch returned to `0x17ecd6a`, grid20x80, block512, stream0.
The one library submission uses the captured X as B and captured Y as C/D,
stream0. The independent route audit therefore binds the direct original
preparation-plus-library branch. The parent request output matched the frozen
reference. The root coordinator restored the original server ready and open;
its first restoration admission timeout is retained in the run evidence.
Neither capture completion nor restoration is a speed improvement.

Only an independently reviewed full replay can show a component win. Only a
subsequent comparable engine cohort can establish actual Prefill tok/s, Decode
tok/s and accepted/drafted counts. This candidate addresses ordinary Prefill;
it claims no Decode or acceptance gain. A later replay still requires a freshly
initialized router, current live scratch and exclusive allocation lifetime;
exact raw Y preservation remains the default output contract. None of those
throughput results is claimed by these files.

## Default-off full replay contract

`replay.c` consumes the frozen exported fixture in a later exclusive initialized
owned engine. It installs no host hooks, submits no serving request and captures
no new model data. It pins the full executable plus original preparation
`0x17ec6e0`, library helper `0x18c6b80` and native HT `0x18092f0` hashes and ELF
mapping before creating a worker. The constructor makes no hardware call.

Three separate GPU pipelines are screened:

- Stock: original preparation into an own50-MiB weight plus original library
  multiply and full device completion, every call.
- Native HT: original rotation plus original packed multiply and full device
  completion, without changing the engine's HT threshold or native controls.
- Cached original: one own50-MiB original prepared weight, prepared once outside
  the measurement; each steady-state call uses the original library multiply
  plus full completion. This is a separate cache candidate, not native HT.

One stock, one native and one cached qualification are excluded. Each admitted
candidate gets two excluded balanced warmup pairs and eight balanced measured
pairs against full stock. The absolute cap is43 pipeline calls, with no retry or
extended diagnostic series. Every completed output is compared as full raw
native16-bit words to the captured Y. A stock mismatch or API error aborts the
screen. A native mismatch retires only native; the independent cache candidate
can proceed. No tolerance is widened. Retired/partial cohorts have null timing
means and cannot qualify as a component result.

Both original library arms reuse the same initialized router and fixed shape;
qualification excludes initial plan selection and warmup stabilizes that plan.
Opaque algorithm bytes need not be exposed for this limited within-process
comparison. The source still reports their identity as unknown. It checks the
existing live native scratch coverage and stable current pointers/default
controls, without rebasing any engine global. Seven own HIP buffers have a
327705600-byte allocation budget, including two separate50-MiB prepared weights;
host staging is390620160 bytes. Root must account for this under the existing
22-GiB admission and18-GiB continuous reserve. Input/output file bounds remain
300 MiB per directory. Successful protocol completion requires all own
allocations to be released; cleanup failures are reported and invalidate it.

Root build after independent review:

```text
gcc -O2 -Wall -Wextra -Werror -shared -fPIC replay.c \
  -ldl -lcrypto -pthread -o NEW_REPLAY_SO
```

Set:

```text
HALOGEN_PREFILL_HT_REPLAY=ordinary-qkv8192-v1
HALOGEN_PREFILL_HT_REPLAY_DIR=/tmp/alloy-prefill-ht-replay-<fresh 32 lowercase hex>
HALOGEN_PREFILL_HT_REPLAY_FIXTURE_DIR=<absolute immutable captured trace directory>
HALOGEN_PREFILL_HT_REPLAY_MANIFEST_SHA256=<canonical replay receipt SHA256>
```

Only `flash_serve` with exact first argument `--ck` activates the constructor.
Startup CLI probes such as `--resident-gib` do not create a directory or worker.
The serving constructor creates an owner-only0700 output directory and `activation.json`.
Root writes owner-only0600 `replay.receipt` with the following canonical ASCII/LF
content, eight actual input hashes and a final newline:

```text
schema=ordinary-qkv8192-replay-v1
stock_route=direct-original
packed_sha256=<packed.bin SHA256>
signs_sha256=<signs-u16.bin SHA256>
scales_sha256=<scales-u16.bin SHA256>
x_sha256=<x-u16.bin SHA256>
y_sha256=<y-reference-u16.bin SHA256>
descriptor_sha256=<descriptor-before.bin SHA256>
records_sha256=<records.json SHA256>
complete_sha256=<complete.json SHA256>
```

Only after current readiness, reserves and exclusive hardware ownership are
established, root creates exclusive owner-only0600 `armed` containing
`ordinary-qkv8192-v1-replay-ready\n`. Fixture files must be immutable regular
owner-only0600 files with one link in an owner-only0700 directory. The worker
waits at most30 minutes for arm; a timeout does not authorize a duplicate run.

The worker writes `replay.json` and `complete.json`; no harvest trigger is used.

The Windows coordinator exports these small files to an exclusively created
`replay-results` directory, separate from the `replay` lifecycle directory.
Top-level `passed` describes completion of the finite screening protocol. Each
`comparisons[].qualified` separately determines whether a candidate has a full
exact-output cohort; a numerical rejection remains explicitly retired.
Qualification, warmup, each measured pair, hashes and word mismatch examples
are retained. Timing is CPU submission to full device completion; upload,
output poisoning, file export, D2H validation and comparisons are outside that
interval. Cached preparation's separate cold cost and resident bytes are
reported, so its steady-state timing cannot be presented as an amortized
engine token rate.

GPU applicability is concrete for these original pipelines. CPU supports file
hashing, admission and exact output checks. This screen establishes no supported
NPU packed-HT consumer or direct GPU-memory interface, so it does not add an NPU
producer. Any component win still needs a later controlled serving integration
and actual Prefill/Decode/native-acceptance measurement before claiming a gain.

Assess GPU, NPU and CPU applicability after every development, as specified in
[the accelerator selection policy](../../../docs/research/halogen-accelerator-selection-policy.md).
The primary outcomes remain actual serving Prefill tok/s, Decode tok/s and native
accepted/drafted counts on frozen nonrepetitive workloads. Exact faster arithmetic
does not by itself improve draft acceptance. Component timings remain separate.
