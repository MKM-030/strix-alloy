# PLD prepared embedding prefix with native correction — 7 October 2026

The next distinct decode candidate is a **round-owned four-row embedding slab**.
Prepare the real native PLD draft IDs during target verification, then consume
the already resident accepted prefix with one late native correction row. This
can remove prefix rows from the native multirow embedding branch while keeping
the full native hidden, seed, layer48 and history work. There is no established
acceleration. The finite original-GPU batch-versus-tail component now passes
exact arithmetic parity, but finds only0.2–17.6µs mean branch budget across
six fixed cases, with order/outlier sensitivity. NPU mixed-row numerical
quality, early completion and concurrent contention remain unmeasured. The
[result report](halogen-npu-pld-mixed-embedding-result-20261007.md) retires this
candidate for the current effort.

The new [offline planner](../../scripts/benchmarks/halogen_mtp_pld_mixed_embedding_plan.py)
implements the bounded row/identity contract with `enable_offline_split=False`
by default. It copies host token IDs, calculates the split and byte offsets,
and returns whole-native fallback on stale or unusable metadata. It has no I/O,
pointer access, native patch, provider, device execution or timing. Its flags
always leave native skipping, device execution proof and speed claims false.
`ClaimedPublication` is metadata, not evidence that an upload or event happened.

The [finite native component](halogen-npu-pld-mixed-embedding-component-20261007.md)
now has sealed C source and a pinned image wrapper. Root's owned compilation
passed with `-Wall -Wextra -Werror`; root's subsequent finite GPU run passed
120/120 recorded exact-parity pairs. Its original-GPU prepared prefix isolates
batch-versus-tail arithmetic and budget without establishing an NPU producer
or live skip. Independent offline output/statistical checks support retirement
of this candidate, not a live implementation.

## Producer window and replay mapping

The pinned retained disassembly is
`server/.local/optimization9h-20261004/mtp-route-static-20261004/host-text-disassembly.txt`,
SHA256 `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`.
The engine is the unchanged 0.16.2 image, SHA256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
Role names below are inferred from retained argument/data flow.

Use the ordinary verifier entry `0x17dcfc0(model, host_inputs, count)`, only
when its caller return is **`0x172d61d`** from the PLD call at `0x172d618`
(text lines20319–20334). At that point constraints and the native opening-token
gate have already run; the host input is `[current,draft0,...,draft(n-1)]`.
Copy at most three draft IDs, preserving their order and duplicates, and invoke
the unchanged original verifier exactly once. The input stack/vector pointer
must not escape. The earlier copy join `0x172e95f` offers additional lead time,
but an interior basic-block detour is unnecessary for this first contract.

Verifier `0x17dcfc0` sets `model[0]=1`, calls target forward at `0x17dcfef`,
then clears the flag at `0x17dcff4` (lines193786–193804). This suppresses the
target's automatic head replay. Target layers0–47 run before predictions
complete; they provide the candidate preparation window, with no measured
duration or assured physical GPU/NPU overlap.

Native matching at `0x172d630..648` counts `a` accepted drafts. It forms shifted
tokens `[draft0,...,draft(a-1),correction]`, commits `k=a+1` at `0x172d80a`,
and the normal continuation calls `0x17dcc90` at `0x172e058` (lines20339–20344,
20431–20450,20976–20978). The helper invokes the full head at `0x17dcd4f`,
return **`0x17dcd54`**, with count `k` and verification base position
(lines193624–193631). Native stop/error/suppression paths can skip this replay.

For `a=0`, `k=1` contains only the correction, which was unknown when the
producer started. The first contract leaves that call completely native.
For `a=1..3`, require every proposal row already uploaded in its original order
and the upload event complete. Retain the actual native allowance; never enlarge
the three-draft/four-replay reservation. The correction stays native even if its
ID equals a prepared draft, keeping one simple missing-tail rule.

## Private slab and exact branch reduction

Allocate a private **4×5120 = 20480-byte** BF16 projection slab before the owned
request. Producer rows0..n-1 correspond exactly to the native proposal IDs;
row n reserves the all-accepted bonus. After complete upload, producer writes
are closed and exclusive consumer ownership permits native correction output
to overwrite row a, which is either the first rejected draft or the reserved
bonus. The ready prefix needs no recurrent copy or extra assembly launch.

This first native implementation would be confined to observed **wire D**:

| Retained seam | Proposed local operation after a complete prefix claim |
|---|---|
| Token host/H2D copy `0x17db364/382` | Leave the original full `k*4` staging copy unchanged. |
| Gather call `0x17db449`, return `0x17db44e`, identity `0x18d5b40` | Keep the original table pointer; set token pointer to `model[+0x730]+4*a`, destination to `model[+0x6c8]+5120*a`, and grid `(1,1,1)`. |
| Embedding RMS call `0x17db517`, return `0x17db51c`, identity `0x18d5160` | Set input/output to that same tail row, width2560/groups1, grid `(1,1,1)`, retaining native gamma. |
| E FC call `0x17db543`, return `0x17db548` | Invoke unchanged dispatcher `0x178cf90(model+0x908, native_input+5120*a, slab+5120*a, N2560, M1, K2560)`. Preserve its initializer and normal dispatch machinery. |
| D hidden RMS/FC `0x17db62d/65e` | Leave the original full `k` hidden rows and hidden FC `M=4*k` unchanged. |
| D seed call `0x17dbb91`, return `0x17dbb96`, identity `0x18d5b58` | Rewrite only embedding argument0 to the private slab; preserve native hidden/seed pointers, stream0, block256 and full grid/count `k`. |
| Layer48 call `0x17dbbe1`, continuation/count/cache publication | Leave the full `k` rows and all native state/history behavior unchanged. |

Keep head R14D=`k`; reducing that register would corrupt hidden/state work.
Do not rebind `model+0xb00`: later mixers/vocabulary reuse that scratch. The
wire-D path consumes its E output directly through the seed argument at
`0x17db9e0..0x17dba5f` (lines192515–192540), allowing the local slab argument.
Other wire paths can transform E before seed and are outside this candidate.

Static row independence is supported by the original shaders:

- Gather `0x24b61c..660` reads token index `4*workgroup_id`, derives source
  `token*0x1400` and destination `workgroup_id*0x1400`; there is no cross-row
  arithmetic. Pointer-offset plus grid1 therefore selects the correction row.
- RMS `0x22d218..25c` derives the input row from width times workgroup ID;
  width2560/groups1 leaves gamma and within-row reduction unchanged. Its LDS
  reduction stays inside the workgroup. Offset input/output plus grid1 selects
  the tail without normalizing accepted-prefix rows again.
- Native M4 FC has independent per-stream accumulators and no cross-stream
  reduction, as retained in [the accumulation audit](halogen-native-fc-accumulation-20261004.md).
  M2/M3 registrations exist at identities `0x18d66b0/0x18d66d0`; registration
  alone does not prove batch output parity with M1. The subsequent finite
  original M2/M3/M4 versus composed-prefix/native-M1 component passed exact
  parity on the frozen A/B fixture rows; no NPU or live-row equivalence follows.
- Seed `0x24bc1c..34` advances E by `workgroup_id*0x1400`; hidden/output advance
  by `workgroup_id*0x5000`. It adds that E row across its four native streams,
  so a contiguous slab of k rows fits the original full-count seed interface.

The gather/RMS/seed disassemblies are the existing `k-embed-gather-`,
`k-rmsnorm-grouped-`, and `k-hyper-seed-add-gfx1151-disassembly.txt` files in the
same pinned static directory. This review read those retained text files;
it performed no new disassembly command, WSL operation or device run.

## Metadata, fallback and finite next implementation

The planner binds a nonzero request nonce, model generation, table/gamma/weight
source epoch and one-shot round ID, plus base position, exact copied draft
sequence, replay caller, wire and slab publication metadata. Wrong caller,
epoch, round, position, prefix, row order, incomplete event, absent lease or
unclosed producer writes returns the full native gather/RMS/FC plan. Malformed
bounded input raises `ValueError` before any split. No late readiness wait is
allowed. Validate and arm before the first modified gather; after native work
has been removed, a failure cannot resume in the middle using stale scratch.

The pure planner does not enforce one-shot use or lease lifetime. A later owned
native adapter must publish once, close producer writes, retain the slab until
the original seed has completed on its stream, and retire it on reset/cancel/
epoch change. The metadata contract cannot itself prove those facts. It also
cannot turn frozen A/B NPU tolerance into live full-head proposal equivalence.

The implemented finite native component compares original k-row embedding
and exact tail gather/RMS/M1 plus full-k seed for k2/k3/k4, using immutable
raw A/B inputs in a private two-row table and original-GPU prepared prefix
rows. Its IDs0/1 are synthetic fixture indices, not live vocabulary IDs.
Root's finite owned run compared exact outputs and actual branch time with
initialization outside the measured interval. Exact parity passed; the small
and order/outlier-sensitive branch budget supports retiring this candidate
without a live hook or producer. Another ready64/parser/eventquery cohort supplies
neither this row split nor the missing batch-minus-tail budget. Only afterward
does a PLD producer/native adapter and matched engine A/B have a defensible cost
target. Existing v1/v2/v3 handoff sources remain frozen.

## Concrete timing budget

Let `B(k)` be original full-k gather+RMS+E-FC time, `T(1)` the proposed native
correction gather+RMS+E-FC time, `C` incremental validation/seed-rewrite cost,
`J` concurrent producer/transport contention charged to the request, and `W`
the actual early window through completed slab publication. A ready mixed
round can save only **`B(k)-T(1)-C-J`**. On a missed publication, savings are
zero and preparation/lookup/contention still count. Because this contract never
waits, useful coverage requires publication latency `L<=W`; it does not credit
a late result by silently stalling replay. Sum costs over all rounds, including
rejected drafts and discarded publications, and divide by actually committed
output tokens for the engine decision.

The measured scalar FC alone is **0.152995 ms**, excluding full gather/RMS.
It is incorrect to claim `a*0.152995 ms` saved: a stock batch may share decoded
weights. The finite component now measures B(k)means0.1657–0.1878ms and
T(1)means0.1655–0.1702ms across these six fixed cases. One ideal scalar FC removal per
~24-ms output is only ~0.64%, before overhead. This mixed candidate changes the
replay workload, but its measured branch margin remains only0.00020–0.01760ms.

Root's v3 frozen-scalar handoff succeeded at mean NPU **1.3307 ms**, pipe
**2.4231 ms**, full staged **6.1337 ms**. The staged path is about **40.1×**
the scalar FC budget and exceeds it by **5.980705 ms**. These component means
neither measure an embedding-only batch producer nor bound production latency;
they show why synchronous scalar insertion is unsupported. Reusing that exact
staged path for one row would need at least its observed6.1337-ms lead time,
plus any missing producer preparation, to be ready without a replay stall.
No current receipt supplies W or concurrent C/J. The finite component supplies
only the isolated B(k)-T(1) observations described above.

Prune synchronous scalar/hidden NPU insertion, another ready64 cohort, and
full-head replacement without a complete state transaction. The actionable
result is the preserved default-off mixed-row contract and successful finite
arithmetic component. Its microsecond-scale timing margin does not justify a
live/NPU cohort; retire this candidate with no claimed acceleration.

## Offline verification

The focused test module is
`scripts/benchmarks/tests/test_halogen_mtp_pld_mixed_embedding_plan.py`.
Nine tests cover default-off behavior, all a1/a2/a3 offsets and full counts,
a0 fallback, duplicated draft IDs, repeated correction IDs, stale metadata,
unusable publication, bounded token/position/allowance validation and immutable
plan revalidation. They use standard-library Python on Windows and no device
or provider imports. The initial missing-planner run failed all nine assertions;
the implemented planner then passed all nine. The pure function returns plans
only; these tests qualify no upload, arithmetic output, native hook or speed.
