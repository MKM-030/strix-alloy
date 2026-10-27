# Halogen0.18.16: recovered serving rates and trained proposal path

The latest fully qualified8K MTP cohort remains **1858.90 Prefill /54.37 Decode
tok/s**, with **210/318=66.04% native-head draft acceptance**. A separate
8192-input/one-output serial cohort reaches **1906.29 Prefill tok/s**. Those
are different requests and must not be combined into one measured row.

| Actual input | Output | Mode | Prefill tok/s | Decode tok/s | Native-head acceptance |
|---:|---:|---|---:|---:|---:|
|8192|128|adaptive MTP|1858.90|54.37|66.04%|
|8192|1|serial PP1|1906.29|—|—|

Both use frozen nonrepetitive text, CacheOff/no_store, ThinkingOff, one slot,
32768 context capacity, chunk/max8192, OEM Performance1 and prefetchOff. Each
excludes one warmup and reports three measured runs. Independent RAW phase
intervals were checked against enclosing Windows QPC HTTP time. The original
historical48.42 Decode result used262144 context capacity; current values are
close numerical comparisons across different configurations, not a controlled
speedup percentage. See the immutable
[MTP report](../benchmarks/halogen01816-oem-performance-20261026.md) and
[PP1 report](../benchmarks/halogen01816-pf-pp1-20261026.md).

The continued implementation has not produced another serving-rate cohort.
It adds source-faithful CPU components for the real pretrained Inco DFlash2
architecture and has now executed its actual pinned weights:

- Context projection and five K/V projections:14 independent Root CPU tests,
  exact FP32/BF16 native/sequential source agreement. The former loose BF16
  comparison was insufficient and is retained as such. Corrected RMSNorm/RoPE
  preserves the source rounding order. Peak process working set997670912bytes
  stays below1GiB on the complete2048-row context test.
- Author-layout attention:9 Root CPU tests. All queries use the common
  block-end2048-key window; a per-query causal sliding mask would be wrong.
- Five-layer query backbone:10 Root CPU tests, including FP32/BF16 block4/8,
  residual/convolution/MLP/final-normalization order, empty initial context and
  independent original RoPE comparison at absolute position260000.
- Dense target-head/top16 and learned rank256 greedy proposal path:9 Root CPU
  tests against the original model and complete worker sampler. Synthetic
  vocabulary fixtures establish arithmetic only. A later Root-owned run loads
  the actual pinned81 BF16 tensors, checks all values finite, and executes the
  complete context/body/head/selector assembly with the local original Qwen
  embeddings and full output head. Empty and explicitly synthetic eight-row
  conditioning exercise block4 and block8. These are not native target HC
  features and do not establish learned acceptance or serving speed.
- Native callback source:30 owner checks,54 commit checks and16 HC-boundary
  checks. Root compiled the commit and HC cases with both MSVC and Linux GCC
  with warnings treated as errors. Actual socket reuse/close, zero-length/peek,
  fallback, reentrancy and partial-send fixtures pass in Linux. These fixtures
  use synthetic native frames, not a live engine attachment.

Additional source components now observe initial native Prefill chunks (22
checks under both MSVC and GCC) and an owned full canonical prefix (101 checks
under both compilers). The prefix observer copies the actual native prompt,
joins prompt plus first anchor, and compares the whole native history before
and after observed commits. A separate v3 CPU bridge now joins protocol byte
buffers, accepted phase observations, the initial constructor, full prefix,
miss slot and commit publication, with early owner identity before the first
miss. Root's Linux bridge and initial-owner fixtures pass90 and11 checks;
actual socket identity/reuse/close fixtures also pass after a separate test-only
correction for blocking zero-length PEEK. This remains source/fixture integration,
not installed native lifetime or writable-lease authority. The prefix observer's
initial allocation-capacity limit rejected a valid260K prompt
whose history capacity doubles to520000. V2 fixes that bound while preserving
the262144 logical-token read/copy limit; unused capacity is never read.

Current native raw HC is BF16 `[row,4,2560]`; means from completed layers
5,15,25,35,45 must be concatenated. Halogen can defer raw scatter into the next
layer's pre-step, so a simple layer45 return hook can capture stale data.
Actual source boundaries now distinguish those cases. No feature copy, GPU
completion fence or NPU publication is established by a host callback alone.
Saved dispatches use plain legacy HIP stream0; their host pending flags clear
before dispatch, so successful raw-producing launch evidence must additionally
join the completed callback before capture.

A separate HC-mean kernel has compiled to gfx1151 and passed one real Root-owned
GPU fixture:51200 output/guard words, zero byte mismatches,184320 explicit device
bytes. On the same adversarial selected rows, the local PyTorch2.13 GPU mean
agrees on all finite/zero/infinity bits;728 NaN payload-bit differences are
reported separately, with zero non-NaN mismatches. This covers one four-row,
tap3, tail selection, not every optional layout or the author's runtime build.
No native capture or engine gain follows from this component.

The four full-state miss relays pass430 independent Root Linux CPU checks.
A separate copied near-island implementation relocates and registers the actual
assembler FDEs, runs direct branches through its W^X code, and passes433 checks
including real libgcc unwinding. Not every enabled XSAVE component class was
deliberately poisoned. Neither fixture qualifies native startup quiescence,
first-save stack headroom, process CET policy, all four mapped native patches
or installed callback coverage.

The current no-head PLD control is staged separately and remains uninstalled.
It allows an independent proposer to reach the normal target verifier without
the native MTP first-ID match restriction. A new paired request must omit its
explicit drafter in both arms; the frontend rejects explicit MTP when no head
is loaded. External proposal acceptance needs its own commit ledger and must
not be relabeled as native-head acceptance.

The normal server stayed online with unchanged controller/backend runs
39495ebc603d49e1b984fdc3f198c139 /8d4d9f1c039c49e98afaa0e99b81c97d on8840/8731.
The new drafter payload was acquired once at the pinned revision and its full
1206140008-byte SHA256 matches
`d6723f2a359eaf33ec0c95f22ae8edda896774020c552296a85e1913b4d3186f`.
Existing models, drivers, BIOS, voltage, global WSL settings and the serving
profile remain unchanged. No candidate DSO was loaded into the engine.

The05:28UTC source refresh found the same official Halogen release and the
same AMD driver package. The rediscovered Gufo fork has the exact same HEAD as
the previous saved review; no new transferable candidate was established.
Its advertised code/JSON rates are different workloads, and some of its fast
paths change numerical precision. [Fork source](https://github.com/mikealanni/gufo)
and [official AMD release notes](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-10-1.html).

Installed canonical native owner/prefix state, initial-prompt and verification
feature capture, complete trained device execution and the frozen engine
comparison remain required. CPU arithmetic and isolated GPU mean tests do not
establish learned quality, acceptance, useful NPU overlap or tok/s. Raw receipts
are saved under
`server/.local/halogen-update-20261025/primary01816/native-npu-continuation/`.
The full optimization goal remains active and unachieved.

## Complete trained GPU proposer and incremental context continuation

Root has now executed the complete trained81-tensor GPU proposer with the
authenticated original248320-by2560 BF16 target head and original anchor/mask
embedding rows. Staged ownership releases CPU body tensors before loading the
separate head. The actual component retains about2.57GB of GPU allocations;
minimum observed Windows physical availability was20531388416bytes, above the
18GiB runtime floor. No candidate was installed into the serving process.

The original rowwise query body was independently compared against pinned
upstream AST methods on the same GPU:10240/10240 output words agree exactly.
An empty-context body ABA test measured8.3591ms before,6.8488ms with batched
query attention,8.9137ms after; all10240 output words remain identical in that
checked case. These QPC forward-plus-wait intervals supersede the earlier
inconsistent isolated GPU-event timing; they are not serving token rates.

Complete block4 proposer measurements include body, full vocabulary head,
top16 and learned rank256 selector. Each reports one excluded warmup and three
Windows QPC forward-plus-completion samples:

| Private conditioning | Eager mean ms | Captured replay mean ms |
| --- | ---: | ---: |
| Empty, prefix0 |14.2199|12.2102|
| Explicitly synthetic8 rows, prefix8 |13.2798|12.4260|

Captured/eager tokens and edge-score tensors agree exactly. Independently
extracted original source edge/path methods also agree exactly on the same
device. The synthetic8-row context preparation separately measured
1.6851/1.5989/2.0047ms. There are no real native target features in these cases,
no engine Prefill/Decode comparison and no learned acceptance measurement.
Captured graphs here freeze each case's positions and window; they cannot be
replayed at new positions without an explicit persistent-input integration.

The previous same-container, same-provider4096-byte GPU memory/event IPC test
passed with real worker read/write visibility and clean close-before-free.
The host WSL Torch import now also succeeds with optional `amdsmi` disabled
only in that fresh process, reporting Torch2.13.0+rocm10.0.0/HIP7.15.26333 and
`device_initialized=false`. Neither result proves targetHIP7.14-to-worker7.15
IPC compatibility or real native feature publication.

A new private mirrored2048-row context ring retains only actual committed
INPUT rows, including the old anchor and accepted proposals and excluding
bonus/correction. Eight bounded CPU checks pass, with a separate source
review of generation, rollover and block4/8 visibility. It uses80MiB BF16
storage and avoids reprojecting the entire old context when the eventual
native owner supplies only the next1..4 committed rows. GPU numerical parity,
real owner binding and completion/lifetime remain unmeasured. The separate
greedy-walk helper passes five exact source CPU tests; no GPU speed claim is
made for its smaller argmax/point-mass allocation change.

The new default-off native composition joins the relay helper, one Bridge
dispatcher and raw-HC launch proof to the strict mean kernel. Its59 CPU
boundary checks use substituted dispatcher/enqueue endpoints. Actual
site-specific owner/commit/HC relays and startup publication are being added;
the composition fixture is not a live installation.

Raw evidence is retained in `native-npu-continuation/` under
`real-query-body-source-gpu-oracle-v2`, `real-query-body-batched-aba`,
`real-complete-proposer-gpu-v2`, `owned-ipc-pair-once` and
`host-worker-import-once`. The first complete-proposer entry stopped before
creating a GPU child because System Copy traffic was1percent. A separate
explicit fixture admission permits only PID4 Copy traffic up to1percent;
the successful v2 receipt actually records no such traffic. Games, foreign
GPU work, memory guards and normal lifecycle checks remain enforced.

The later normal serving run exited independently through its18GiB runtime
guard after physical availability reached17.997GiB. Its saved container is
terminal and its exact dead ownership lock was archived rather than deleted.
Normal lifecycle restoration uses a fresh authenticated launch receipt; no
measurement restart is inferred from an observation timeout. Recovery state
and current identities are recorded in continuation-current.json.

The official11:00:39UTC refresh found unchanged Halogen0.18.16 and AMD26.10.1;
the next source refresh is not due before13:00:39UTC. The heartbeat remains
paused. The full GPU/NPU acceleration goal remains active and unachieved.

Normal restoration subsequently completed and was freshly authenticated:
controller26856/run318c012b34824850a1a548a841331075 and
backend37136/run577aeaa6891b4a929acfd30cb19270ca, same baseline profile SHA
2ed5fcc7b648972d97e04ccce0d8eca90e4232283b5076b3537d72c34fdbf475.
Two old, terminal Root console launchers27564/27836 were closed; the current
online console17712 was retained. No experiment GPU/Torch child or persistent
sidecar remains loaded.

The19-callback candidate links independently on Linux with undefined symbols
rejected. After correcting the libc feature-header ordering and a CPU fixture
indentation warning, the substituted helper passes383 checks and default-off
loading in /bin/true succeeds. The separate composition's59 checks and complete
Linux link pass too. These builds do not qualify19 native full-state/unwind
executions, the startup transaction, complete helper stack budget or owned
feature staging. The candidate remains uninstalled; its unfinished scope is
recorded in current-native-callback-relays/ROOT-STATUS.md.

Marcel's direct authorization in the Voice chat permits coordination. Root
revalidated the ready generation and confirmed no own experiment allocations
remain. Voice owns its speech services; coexistence is not yet qualified from
roughly24GiB physical availability and the unchanged22GiB request floor.
During the agreed Voice window there are no model restarts or GPU/NPU tests.
CPU/source development of the exact-runtime IPC worker fixture continues,
unexecuted. Importer termination must be established by a real lifetime
primitive before exporter free or context exit; an acknowledgement Boolean
alone is insufficient.

The Voice window was subsequently released. The loaded-server IPC attempt
stopped at the22GiB entry check before any child started. A new private
steady-window wrapper now passes10 bounded CPU tests, including advancing
positions and the source's expanded-row mask stride(0,1). Its four frozen
graph dependencies remain unchanged. Independent source review found no
remaining blocker; this CPU result alone supplied no GPU qualification.

Root then used an authorized normal stop for a model-free runtime test. The
actual old engine/container exited, but the normal180-second physical-memory
recovery ended below its earlier baseline. This failure is preserved under
`native-npu-continuation/target-torch-ipc-isolated-once`; no hardware child ran
in that attempt. After exact dead controller/backend/container verification,
Root archived the exact dead ownership lock and resumed from the terminal
state, without another stop, a fabricated ready receipt or a lowered floor.

The resumed targetHIP7.14-to-hostTorch7.15 owned4096-byte memory/event test
**passed**. The worker read the exported bytes, performed the GPU XOR and
released its DLPack alias/imports. Actual pidfd termination of the importer
and exporter was established before the sleep-only runtime holder stopped.
The source fixture remains byte-for-byte pinned. This proves this owned
runtime transport, not native target-feature ownership or a useful NPU path.

The complete pinned trained GPU proposer subsequently passed its advancing
prefix qualification with one capture at8192 and replay at8192,8193,260000.
Every case uses2044 changed synthetic target-feature rows, a changed ordinary
anchor and its original embedding. All six proposal fields, GPU RoPE/mask
values and mask stride match the original complete eager API exactly.
One eager/replay warmup per case and two capture warmups are excluded;
each case retains three alternating eager/replay sample pairs.

| Synthetic absolute position | Eager compute+stream wait, ms | Replay compute+stream wait, ms |
|---|---:|---:|
|8192|24.7766|23.8916|
|8193|24.4675|23.6668|
|260000|25.0438|24.2860|

These intervals exclude synthetic context construction and separately
reported private-input copies/waits of roughly0.39-0.48ms. GPU event stream
intervals are also saved and are not kernel-only durations. No interval is
converted into engine tok/s. GPU peak allocation since setup was2861360128
bytes; the observed Windows physical minimum was29420855296bytes. The
owned Windows child exited0, all imported allocations are terminal, and no
experimental helper remains. Raw evidence and exact source snapshots are in
`native-npu-continuation/target-torch-ipc-isolated-resumed-once/`.

**Current restoration limitation at12:29UTC:** normal startup was refused
because available physical memory was about31GiB versus the human-specified
35GiB floor. The server is offline at this receipt; the earlier ready identity
must not be reused. The startup floor has not changed. A direct async question
offers30GiB startup with the unchanged18GiB runtime guard, or freeing RAM while
retaining35GiB. Voice has a bounded one-compiler CPU-only build window; no
speech/model/profile activation was authorized. The full acceleration goal
remains active, with no new integrated Prefill/Decode/acceptance result.

The independent saved-evidence audit subsequently passed45 checks and16 hash
comparisons. Including private copies, pooled host wait over9 pairs is25.2168ms
eager versus24.3651ms replay (3.378% lower). GPU elapsed-stream event means
increase under replay; no faster-kernel or engine-throughput claim follows.

One separate disposable all-true-mask-elision spike was source-reviewed and
executed once. It failed during the first8192 capture warmup with HIP invalid
argument reported by a later tensor operation. The exact failing kernel was
not attributed. No full comparison/latency result exists; the spike is closed
and no qualified source was changed. Evidence is in
`native-npu-continuation/steady-mask-elision-owned-once/decision.json`.

The bounded normal restoration did create a genuine new controller generation,
71644874d290440282133788b707496d, and backend generation
a037e22f484345deaf10ff0c83fdb51a. The backend never created a model container:
its unchanged35GiB physical admission did not stabilize within240seconds
(last32.12GiB). Cleanup/recovery are both true. The observer then lost the
already exited controller's parent lookup; that observation error is not a
reason to restart or a successful ready receipt. At13:00:44UTC restoration
remains unfulfilled, with no experiment process or model engine active.

Source review identifies the first actual feature-integration obligation:
bind a serialized Bridge-to-Stage request-generation lease during PF taps,
before initial() creates the ready frontier. The existing tracker proof has no
request birth/generation, and the weak owned-stage provider is absent. Current
startup remains Observe and does not install the four PLD miss entries. The
qualified private GPU proposer/IPC therefore cannot yet establish native
external acceptance. This is an implementation gap, not a measured NPU gain.

At13:40UTC the first actual early-PF generation binding is implemented in an
isolated `current-pld-native-attachment-v5` source package. The same locked
Connector Birth registry now exports the real PF identity atomically with its
native phase confirmation, while later Decode/inner/model/slot fields remain
unknown. Bridge retains that owner only after the existing Prefix observer
has copied the actual prompt, then joins the existing PF Observer Scope by
request/controller, prompt interval, model, slot and scope sequence. It does
not create an early Frontier. Initial later joins the same generation, model
and processed-input position to the genuine first Frontier.

Independent review caught two concrete faults: reusing a revoked lease ID
within one still-live GEN birth, and a final reentrant-fault/output-commit gap
after prefix hashing. Their deterministic regression run first failed3/126,
then passed126/126 after fixes. A Bridge-local monotonically increasing lease
incarnation survives drop; overflow refuses further grants. Output assignment
now follows final fault checks. Test-only fault checkpoints are absent from
production builds. Adding the pre-bind expected socket identity produces the
final127/127 CPU checks. The unchanged legacy Bridge/Initial suites also pass
96+11 against the final source. Frozen v4 remains byte-identical.

The new v5 C accessors perform actual kernel SO_COOKIE checks before and after
early binding, pending access and Initial-joined access. A real Linux socket
fixture first failed9/30 checks against three false API stubs; the implemented
path passes all10 modes,256 checks total. Raw dup2 replacement is refused
before bind, pending access, Initial and joined access. Real cancel bytes,
positive-sized EOF, terminal, close and reset revoke pre-Initial ownership.
Caller outputs and errno remain unchanged on refusal. These are actual local
socket operations with synthetic native frames, not installed engine callbacks
or GPU feature completion. Exact source/logs/native-timeout receipts are in
`native-npu-continuation/prefill-dispatch-linux-{red,green}/`.

Separately, `observer-v3` fixes the actual multi-chunk scope defect: only a
validated successful PF ChunkReturned clears per-forward state while retaining
the enclosing PF request Scope. Real retirement and rejected returns still
drop both. It exports the already-observed Scope and attaches each PF proof
to its admitted Chunk.scope. The same host fixture fails27/161 checks on the
frozen v2 and passes205/205 on v3, covering8192+4096+4 under one scope followed
by Verify, missing taps, invalid returns/launches, retirement and fresh scope
IDs. All original observer-v2 pins remain unchanged. Root serialized these
compiler windows with Voice; its single separate CPU build is also terminal.

The root receipt is
`native-npu-continuation/prefill-generation-root-qualification/receipt.json`.
No model start, GPU/NPU experiment or new engine benchmark occurred for these
source corrections. The normal server remains offline after the preserved
35GiB admission failure; no stale ready receipt is adopted, no startup floor is
lowered, and the explicit30/35GiB question remains unanswered. The latest
qualified engine results remain1858.90 Prefill/54.37 Decode tok/s and66.04%
native acceptance for8192→128, plus1906.29 Prefill on separate8192→1 PP1.
Native composition-to-Stage wiring, dedicated storage, actual HIP completion,
immutable publication and full engine verification remain unfinished. The
full optimization goal stays active and unachieved; the heartbeat stays paused.

The next isolated `composition-v3` source now connects the actual v5 lease APIs
and the larger observer-v3 Scope/Proof API to Stage begin/acquire/submit/join
and logical revoke. Its C exports are versioned `composition_v3_*`, preventing
an old smaller Stage provider from accidentally satisfying the new ABI.
The source fixture first failed60/91 checks against decline stubs, then passed
191/191 under strict MSVC. Its compiler/fixture processes were all terminal by
14:02:20UTC; minimum physical/commit availability was34.7075/185.0678GiB.
These tests substitute external Bridge/Tracker exports and therefore qualify
hook order, job construction, lease checks and ABI only.

**This candidate is not integration-ready.** Independent review identified a
real interface gap: the bool HC-Proof result cannot distinguish a normal
Scope-only/no-proof event from a Tracker retirement at a rejected PF core
return. Five successful enqueue submissions alone must not permit Stage.joined.
The actual already-validated native PF chunk-return/drop result must cross the
Tracker boundary and be required by the adapter. It must never be labelled GPU
completion. Root also identified unsafe actor handling in the candidate:
reentry, null/alias and pre-lock fault branches call fail/revoke before owning
the busy lock, and public retire does not acquire it. A foreign caller could
therefore race non-atomic lease state. Only the current lock owner may mutate
or revoke that state; a contending caller may set the atomic fault and return.
Both findings remain open, with no live installation or source promotion.
Evidence: `native-npu-continuation/composition-v3-msvc-20261026T135116Z/`.
The new observer-v3 plain interposer Scope wrapper exists but is not yet built
or live-qualified. Its distinct native_v3 symbol avoids the old smaller Proof
ABI; both native observations and original HIP forwarding use one TLS Tracker.

The saved-data ROI review confirms171 actual native head rounds,318 drafted,
210 accepted and384 output tokens over the three qualified requests, with no
lookup/grammar proposals. Decode phase advancement is381 tokens because the
first token of each request is its initial anchor. Native rate reporting keeps
the original128-token numerator and is not silently recomputed. Summed Decode
phase time is7099.292945ms, giving41.516333ms per whole native round; this is not
an isolated verifier duration. If that whole round cost remained unchanged and
the measured private24.3651ms external proposal component were added serially,
a fixed-three proposer would need more than2.53568 accepted proposals per round
(about84.52%) to break even on additional tokens per time. This is explicitly
a hypothetical decision calculation, not a tok/s prediction or measured gain.
Removed native drafting, extra verifier width, contention and learned external
acceptance are unknown. Full context reconstruction is excluded from those
24ms, so incremental context state remains essential. The full BF16 drafter
head is a significant1.270GB traffic item, but its latency dominance is not
established. Earlier failed native shortlist/Q8 experiments remain closed.

## Typed native return and actor correction, 2026-10-26

The isolated observer-v4 exports the actual frozen PF result, the actual
Tracker retirement-epoch change and matching admitted forward identity. A
PF-only return whose Tracker forward was rejected deliberately has sequence
zero. The host fixture records RED384/17, targeted stale-sequence RED384/1 and
GREEN384/0. Its plain Linux wrapper now builds in the full real source closure;
no image bind or launch was exercised.

Composition-v4 consumes that typed observation before Initial join. Five
enqueues alone cannot complete a chunk: a matching successful native return
must advance contiguous coverage from zero to prompt_rows. Rejected/retired or
Disabled status before join, missing/duplicate returns, wrong return PC,
Scope/sequence/base/rows and incomplete taps are refused. Verify PF changes
after join remain separate. Status RED462/16 -> GREEN457/0 includes four real
host-thread actor cases; five fewer checks reflect early refusal before
acquisition assertions. Separate actor RED211/8 -> GREEN211/0 confirms that
contenders do not enter substituted mutable Bridge/Tracker exports or revoke
while the owner is inside Stage.begin. Frozen v3 is unchanged.

The complete11-TU real Linux source builds as one DSO with --no-undefined, no
test macros/stubs, older observers, relay assembly or startup code. Its real
default/unbound CPU fixture passes13/13, including private socket forwarding.
ABI/link/disabled behavior are checked. Native binding, HIP launch, Stage
allocation and GPU completion remain unexercised. Receipts are under
native-npu-continuation/composition4-status-{red,green}/ and
composition4-linux-full-default/. All compiler/fixture windows are terminal.

Independent review found no remaining early-join bypass in this correlation
path. Integration limits remain: repeated outer PF invocations create new
Scope sequences which v5 cannot continue under one lease; Bridge cancel/EOF,
close/reset notify Stage only on a later composition callback or explicit
retirement. Contention requests a permanent fault, not synchronous quiescence.
Stage storage remains leased until actual GPU completion. A relay's local
Offer may finish after dispatch releases the actor and retirement occurs.
Consume mode needs a synchronized native-consumer grant before installation.
These limits are recorded in composition-v4/STATUS.md. No hardware experiment
was added solely to extend gates.

The normal server remains offline after the unchanged35GiB restoration failure;
the existing30/35GiB question remains unanswered. This source work made no
admission retry, startup-floor change, speech unload, device/model operation,
new benchmark, commit or push. Qualified1858.90/54.37/66.04% and separate
PP11906.29 values are unchanged; the broader optimization goal remains active.

## Bounded private Stage storage provider

`primary01816/current-native-stage-v1` now implements the previously missing
private storage provider behind composition-v4 Stage. Its explicit injected
backend allocates two BF16 concat slots and four producer/reader event objects
at startup. Maximum requested buffer storage is400MiB (two8192x12800-word
buffers); the host fixture models those requests and does not allocate actual
large buffers. One acquire-to-submit reservation binds the complete lease,
Scope, admitted forward, raw descriptor and exact Job. Five successful distinct
tap enqueues record a producer event; only its successful current-incarnation
record followed by actual backend Complete permits a private read lease.

Partial enqueue/revoke records a producer drain; missing/failed record retains
storage without readiness. The reader must enqueue all uses before recording
its own completion event. Logical revoke, host token drop and shutdown do not
free pending writers or readers. A full two-slot pool declines without waiting.
Cleanup is confined to explicit startup-failure/shutdown paths. Methods require
one serialized owning host thread and local Stream0; no concurrent worker,
foreign stream or async GEN authority is invented.

Root retained strict MSVC RED41/28 against a decline stub, then GREEN412/0
against the implementation with an unchanged test file. Linux GCC also builds
and passes412/0. All use the injected fake backend, with no device/model calls.
Native Init/return authorization remains in composition-v4; provider joined
metadata is not a completed five-tap proof or GPU readiness. Independent source
review found no blocking defect under the explicit backend/serialization
contract. Tests do not inject teardown failures or model real stream work
epochs, and their per-tap source addresses differ from the actual Tracker's
fixed raw allocation. Thus no actual HIP resource or in-engine qualification
follows. The strong retry-safe teardown contract is not established for a raw
HIP error result; a real wrapper must quarantine ambiguous release results.

The pinned target HIP headers confirm why current-event record flags matter:
an event never recorded can query Success, pending-event rerecord is undefined,
event destruction is not a memory fence, and hipFree implicitly synchronizes.
Those local header facts guided the source contract; they were not hardware
measurements. The next direct step is an explicit same-process target-runtime
backend and finite owned-output fixture, followed by actual native integration
and full-engine verification when admitted. No new hardware diagnostic was
started solely to extend gates. Stage storage is a completed source step;
actual GPU allocation/fences/publication and useful NPU benefit remain open.

The due15:02UTC official check found byte-identical Halogen tag/main/changelog
metadata (v0.18.16, f4c474d8b1d679fabda8685a629ea9681ffaa967). Official AMD
26.10.1 GPU/NPU package metadata is unchanged. The bounded Reddit check returned
previously observed mechanisms, with no new transferable implementation delta
established. Raw official bytes and the bounded observation are retained under
`native-npu-continuation/source-check-20261026T1501Z/`; next check is not before
17:02:11UTC. Nothing was installed and no new benchmark follows from the check.

## Explicit target-HIP mapping and real owned GPU output

The concrete HIP7.14 mapper is implemented in current-native-stage-v1, using
caller-supplied typed function pointers and an already-loaded mean function.
It performs no lookup, runtime initialization or device selection at load.
An optional explicit startup device check runs once. Allocation/event tables
are bounded to two/four entries; ambiguous release results are quarantined,
and retries do not repeat raw HIP releases. Hidden partial startup resources
are exposed by independent mapper-held counts. The Provider teardown contract
is clarified to retain safe-repeat bookkeeping without assuming physical
validity after an ambiguous release. No Provider function logic changed.

The strict pinned-header GCC mapper fixture records RED26/14 -> GREEN92/0
with an unchanged test after a formatting-only compiler-warning repair.
The first failed compile is preserved; it was never counted as expected RED.
The standalone actual-device main also compiles cleanly. A separate fresh
reviewer found no blocking source issue in Provider, mapper or fixture cleanup.

Root then ran one finite standalone fixture at15:42UTC using the pinned normal
image and target runtime SHA6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5.
The main used its own81920-byte raw allocation, two102400-byte output slots
and four events. One slot received all five tap submissions for four synthetic
rows on local Stream0. Runtime and all input/executable hashes were verified
before execution. Actual producer completion granted a private read lease;
logical revoke plus shutdown remained Held while that reader was open. Actual
reader completion then permitted cleanup. All51200 output BF16 words matched
the independent retained stdlib oracle exactly, with zero mismatches.

The real main reports41 checks/0 failures, all raw/output storage freed, all
events destroyed, module unloaded and runtime closed. Docker exit0 and PID0
were observed before removing the exact owned container. Minimum sampled
physical/commit availability was32279527424/193233510400 bytes, above22GiB entry
and18GiB runtime guards. The process/argument/input/guard/memory evidence and
actual stdout are retained in `native-npu-continuation/owned-stage-device-once/`.
No second trial was started. Raw actual output bytes were not separately saved;
the pinned main compared them directly against the retained expected file.

This is real target-runtime owned-buffer/fence/readback qualification for one
four-row clean path. It is not native HC capture, a cross-process/native GEN
grant, repeated full-size buffer reuse, a fault-injected hardware qualification,
an NPU execution or an engine benchmark. No component milliseconds are converted
to token rates. Actual model Prefill/Decode/acceptance and NPU delta remain
unchanged/unmeasured respectively. No server start or admission retry occurred.
Normal serving remains offline with the35GiB start requirement and the pending
human choice; another question now includes the observed Codex-app memory load.

## Repeated outer-Prefill scope correction and activation decision

The new isolated composition-v5 keeps the first Scope as the canonical
generation lease while preserving the true later observed Scope in every
proof and native return. Each later outer Scope passes real Bridge processing
first, advances exactly one sequence between validated partial returned
forwards, and rechecks the unchanged canonical getter. Coverage and Stage.begin
are not restarted. Initial retains canonical identity with genuine late owner
enrichment. Provider-v2 separately tracks actual per-forward capture Scope;
canonical lease comparisons, reservations and storage/event lifetime remain
strict. Frozen v4/Bridge/Observer/provider-v1 packages are unchanged.

Root reproduced the source failure before implementation: composition strict
MSVC RED1251/47 and provider RED967/8. With the same new regression files,
composition now passes1313/0 on MSVC and GCC, provider1064/0 on both, and the
real-thread actor fixture456/0. GCC's first composition attempt failed on two
inherited same-line loop indentation warnings in a copied legacy fixture.
The failure and original bytes are retained; a whitespace-only repair preserves
normalized source bytes. Both final compilers pass the repaired fixture. The
real13-TU Linux DSO includes Bridge/Observer/Adapter/provider/typed HIP mapper,
links with no undefined symbols, and passes13/0 default/unbound checks.
Independent paired review found no blocking source defect. No device, engine,
callback installation or startup binding was exercised by these checks.

The activation review is explicitly no-go. Retained callbacks.h/helper/startup
and build_native_callbacks.py still select the old composition-v2/observer-v2
path, whose Stage lacks the new begin/joined/revoke hooks. Its weak owned-stage
hook is not a compatible safe connection. This fix does not supply that missing
typed native connection, and no alias/cast workaround or retry of the rejected
callback task is included. The private proposer24.3651ms also excludes complete
native feature/context preparation and publication, and no trained acceptance
has been measured. Its serial break-even greater than84.52% is hypothetical;
neither it nor source tests establish a net engine speedup. Do not add further
standalone gate work as a substitute for a reachable useful engine mechanism.

Qualified full-engine figures remain1858.90 Prefill /54.37 Decode tok/s with
210/318=66.04% acceptance on8192 actual input/128 output tokens. Separate serial
PP1 remains1906.29 Prefill tok/s, near the historical1925.16 PP1 figure. These
workloads and historical context-capacity differences remain explicitly
separate. The new source correction contributes no measured token-rate delta.
The immutable benchmark JSON is unchanged. Server restoration remains required;
the35GiB startup floor and pending30/35GiB choice have not been changed. Own
host compilation/fixture processes have completed; no new model admission,
model unload, driver/firmware/settings change, commit or push was performed.


## Supported API route feasibility

The independent read-only audit found no external draft-ID, prediction-input or
verification operation in pinned0.18.16 serve_api.py (SHA4de61615e067ec6a4883e1d1f70c5c0937373162d1c5167352383dd9c4aa90f1).
GEN serializes prompt IDs plus an engine-owned drafter selection and controls;
Responses extras do not reach its explicit ChatReq shim. The project gateway
adds no verifier endpoint. The historical authenticated native health advertises
only serial/mtp for this checkpoint, not native dflash2. That saved health is
not current liveness. This closes the independent supported-API alternative;
no prototype, callback workaround, runtime test or admission attempt follows.
Evidence: native-npu-continuation/supported-api-route-audit/receipt.json.


## Authorized30GiB startup boundary, superseding earlier35GiB status

The human explicitly authorized30GiB startup with18GiB runtime reserve. Only
the installed0.18.16 v2 startup policy and corresponding metadata/tests/source
pins were changed. Launcher commit131GiB, context-dependent backend commit,
vision+1GiB, w4b policy and runtime18/18GiB remain unchanged. Existing budget
regressions first fail at the changed boundary and then pass4/4. Direct actual
runtime-guard boundary checks still reject either physical/commit one byte
below18GiB. No binary, model, driver, global WSL setting or callback changed.

One normal visible launch passed outer30/131GiB admission at30.49GiB free.
The backend then waited240s for stable warm30/124GiB at context32768. It failed
regularly at29.51GiB before model creation. Both controller/backend PIDs are
absent, cleanup/recovery true,8840 closed; only the verified own failed console
was closed. No readiness, benchmark or sufficiency of exactly30GiB is claimed.
The human was asked to free about1GiB RAM; no further floor reduction or repeat
launch is authorized by elapsed time. Evidence: native-npu-continuation/
admission30-authorized-20261026/receipt.json.

The due source check fetched seven official URLs successfully at18:00:56UTC.
Halogen remains0.18.16 and AMD metadata is unchanged. Gufo commit2e499c3 broadens
GPU greedy verification eligibility for constrained tool-call intent; it is new
relative to the saved Gufo audit but predates the previous source-check time.
It is not a proved transferable Halogen mechanism or a run-ready candidate.
Raw source pins are retained and verified; next check not before20:00:56UTC.

## Normal serving restored after confirmed RAM release

The human confirmed RAM release and start with30GiB. Fresh host availability
was53.3GiB. One normal visible0.18.16 launch passed admission and reached
authenticated gateway/native readiness on8840 with the unchanged32K profile.
Controller21152/run c6f65f5ff8ae499882b6cf3b6ed7c566 and backend22012/run
78c099e99d244ec89457a5850462c1e5 are the new identities. A short actual public
API request returned OK (2 output tokens), with unchanged PID identities and
healthy status afterward. This is a serving smoke test, not a benchmark.

The instance and its visible console remain open. Startup30GiB and runtime
18/18GiB are retained; this start with greater free memory does not prove
sufficiency at exactly30GiB. Existing readiness and response evidence is in
native-npu-continuation/admission30-after-RAM-release-20261026T1838Z/
launch.ready.json and smoke-result.json. A subsequent optional combined
protocol script was rejected before execution by automatic policy review;
it was not repeated. No additional ancestry validation or combined receipt
from that script is claimed. Current status was recorded by plain file edit
using the already verified evidence. Full acceleration remains unqualified.
