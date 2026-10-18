# Halogen 0.17.3: phase handoff failure and repair

One fresh capture-only request submitted on 10 October at 04:04:11 UTC found
`DecodeBusy` as the first recorded C++ local loss. It used the frozen natural
16,384-token input, 128 requested output tokens, Cache Off, temperature 0/seed 1,
MTP2/PLD3,3, KV capacity 17,408, and arena/chunk 8,192. Provider and NPU were off.
The request returned HTTP 502 and is not a throughput measurement.

The first-failure dump contains 13 reservations: the zero-loss arm baseline,
`DecodeBusy` and its forwarded Lane loss, four `DecodeHcUnhealthy` losses and
their forwards, then `DecodeOutcomeGeometry` and its forward. The six recorded
Lane ordinals are contiguous; overflow, unfinished slots and unrecorded ranges
are zero. Reservation order does not establish general event-time order between
counters. The trace does not identify the exact live lock holder.

The diagnostic is emitted after the original failure closures, using an
independent once flag. Its winner need not be the first failed-transition thread.
`origin=unspecified` does not isolate the exact timeout branch. Native exit
rejected the outer entry; the worker retained `Held`, and the supervisor retained
`CleanupBlockedRetained`. Unlike the preceding compiler trial, this trial has
neither a native terminal receipt nor a worker retirement receipt. No fresh
ingestion totals, client completion, joint retirement or generation drain are
qualified.

The source permits the idle exporter to call `DecodeCapture::acquire()` before
the native outcome has finished. Both operations use the same lock, and a busy
lock records loss. Separately, synchronous ingestion publishes the next-entry
receipt before the exact borrowed slot is released. The next entry also takes
a locked Lane snapshot before waiting for that release. These are concrete
handoff races to repair; merely tolerating busy locks or extending deadlines
would leave the ownership ordering unresolved.

The prepared design publishes an exact outcome ticket after native dispatch
unlocks. Worker acquisition waits for that ticket. The next-entry receipt waits
for final ingestion and successful release of that exact slot, and the locked
Lane snapshot follows the release barrier. Immutable owners, loss counters,
fences, generations and retirement guards remain required. Focused fixtures
must exercise real operations before a fresh capture tests this repair.

The focused parent fixture compiled successfully and then reproduced both
contention directions using actual `DecodeCapture`, `Exporter` and retained
lease-bridge operations. Its controlled HC-copy/idle-acquire schedule produced
6 local losses, 6 Lane losses and 13 records. Its completed-slot fence-query/next
HC schedule produced 7 local losses, 7 Lane losses and 15 records. Both fresh
fixture processes returned the deliberate expected-failure exit 1, with zero
overflow and unfinished records; the verifier completed with exit 0. No direct
busy-flag or loss injection produced those outcomes. These demonstrate compatible
source races, without identifying the live diagnostic's lock holder.

Tool session 36886 ended with exit 1. Actual coordinator identities are closed;
the exact owned container is terminal. Emergency resource cleanup succeeded,
but capture retirement and historical memory recovery did not. Those failures
are preserved. Independent current admission at the unchanged 35 GiB physical
and 131 GiB commit floors allowed supplemental normal restoration. The runtime
was copied once from the verified terminal container. Restoration uses the
original 262,144-capacity serving profile and a visible PowerShell 5.1 console.
Supplemental session 96967 ended with exit 0. At 04:17:05 UTC, normal serving
was freshly verified ready/open, with controller 37588, backend 34704 and
console 21796. These are timestamped observations; current process identities
take precedence. The restoration coordinators were checked closed afterward.

The qualified natural 16K serving reference remains **1,833.70 prefill tok/s,
43.05 decode tok/s and 180/399 = 45.11% combined API MTP+PLD acceptance**.
This attempt supplies no new serving or NPU speed gain. Automation remains
paused; the acceleration goal remains active and unachieved. The unchanged
first-failure trial must not be replayed.

The completed repair also covers final CommonOutcome with no subsequent Entry:
the actual pre-RequestDestructor observer waits for the exact export release
before native Owner/Decode retirement. The 112-byte ticket contains the complete
88-byte Binding, capture sequence, round, source and rows. Fourteen atomic
payload words and a stable even version avoid a plain-payload seqlock data race.
Publication follows native dispatch unlock; idle polling with no outstanding
ticket performs no Owner/Decode/Lane inspection. Final ingestion remains pending
until successful exact `Step::Acknowledged` release. Entry waits using atomic
identity and release data before taking its original Lane snapshot. Existing
deadlines, loss, fence, owner, generation and retirement guards are preserved.

Root executed the focused corrected CPU fixture successfully on 10 October:
normal Entry, final pre-destructor barrier and failed sink all passed in separate
processes. Real production dispatch, HC copies, export, synchronous ingestion and
acknowledgement were exercised with explicit CPU backends and synthetic cold
Request/pre-consumed-prefill prerequisites. This is not live provider ingestion
or hardware qualification. The first compile failed solely because the fixture
passed an `int` literal to the `u64` atomic-store template; original source and
failure evidence were retained, and only that literal was corrected.

The canonical native build then rebuilt all 27 units and audited the three
byte-preserved relay islands. The image is 384,256 bytes, SHA256
`758f182ef3633da282f0162ce8f882cbdd6c4b11fa2aba2d905aa66982a9cb2c`.
Independent native, fixture and generated-launch source reviews found no material
blocker. The one fresh phase-handoff capture in tool session 26033 is terminal
with exit 1. Its prepared runtime session was `1ac23104aa9b48819471613db5549597`;
its actual native receipt session was `7051c33c1f23dfe0c06afa583751cb2a`.
The frozen natural16K/128 request completed HTTP 200, with exactly one completed
gateway request and no cancellation. This capture-only run reports zero draft
tokens and is not an ordinary MTP performance cohort.

The native terminal receipt is `FailedRetained`. It records 16,384 prefill rows,
126 decode rows and 254 fence-qualified ingested packets; 127 native common
outcomes and zero request destructors were recorded. No worker-retired receipt
exists. The failure dump has three reservations: baseline, one local
`DecodeOutcomeGeometry` loss and its forwarded Lane loss. No `DecodeBusy` appears
in that dump; overflow, unfinished slots and unrecorded ranges are zero. This
does not sample the raw failing native status or identify its precise conjunct.

Source inspection identifies a concrete terminal-status mismatch: the native
output helper can increment the actual transported row count successfully and
then return status 1 at the output-length limit. The capture predicate currently
accepts only status 0. The native finalizer publishes the final response before
destroying the actual Request, so a completed API response can precede the
pre-destructor barrier. This is a source-evidenced repair candidate, not a claim
that the runtime raw status was directly observed as 1.

Native/worker retirement and generation drain remain unqualified. Emergency
resource cleanup succeeded; historical baseline memory recovery failed and was
preserved. A separate admission at unchanged 35/131 GiB floors restored normal
262,144-capacity serving. At 05:00:03 UTC it was ready/open with controller
37816, backend 28832 and visible console 36636. Exact coordinator identities
were subsequently checked closed. The terminal runtime was retained once and
the fresh ready-proof pointers were rebound. There is no new serving or NPU
speed gain. A narrow fresh terminal-status derivative is being prepared; this
completed trial will not be repeated unchanged.

The terminal-status derivative is now built. All 77 production sources were
compared: 76 are byte-identical, with only the exact acceptance predicate changed
from status 0 to status 0 or 1. Existing committed-row, transported-row, identity,
loss, lease and fence guards remain required. Root's actual-adapter parent case
compiled and reproduced rejection; the seven separate corrected cases passed,
including terminal destruction, ordinary continuation and failed-sink release.
The canonical build rebuilt 27 units and audited the three preserved relay
islands. Its image is 384,256 bytes, SHA256
`44a29affef538dbf31eae560308202be01bc08487115b8f703798b3b7926e768`.
The generated launch's 303-file source verifier passed. These are CPU/build
results; actual runtime retirement and any speed gain remain unqualified.

The preceding normal server subsequently stopped when its direct Windows memory
guard sampled 17.730 GiB physical reserve, below the unchanged 18-GiB floor.
Cleanup and historical recovery passed, but its failure latch retained the owned
lock. Root verified the original owner identities closed, the exact owned
container terminal, both ports free, and five current frames passing unchanged
35/131-GiB start admission before releasing only that exact lock. The original
guard failure and outcome remain preserved under backend run
`e2a564404b8646c899d6c344ae5ca96a`. The subsequent restore is recorded separately
under `normal-guard-exit-recovery-20261010`; no memory floor was lowered.

The one fresh terminal-status runtime trial is now complete. Tool session 77231
returned exit 1 solely because historical memory recovery failed; the capture
itself completed and qualified. The exact natural 16,384-token request produced
128 output tokens, HTTP 200, one completed gateway request and no cancellation.
Native state is `GenerationDrained`: 16,384 prefill rows, 127 decode rows, 255
fence-qualified ingested packets, 127 common outcomes and one actual Request
destructor. The final capture sequence and ingested round are both 127. Worker
state is `Retired`; supervisor state is `Retired`, all owned children are reaped,
and `capture-cleanup.json` records qualified retirement without emergency cleanup.
The lifecycle's retained runtime was copied into the trial evidence once, with
22 files. Native/worker joint retirement and generation drain are now qualified
for this single request. This result does not qualify other requests or model
training, an NPU producer, or a faster consumer.

The instrumented request took 45.505 seconds and had zero draft tokens. Its raw
API rates, 1,031.725 prefill and 4.352 decode tok/s, describe serial capture only;
they are not ordinary MTP/NPU performance results and must not replace the
qualified serving reference above. Acceptance is undefined for zero drafted
tokens. Provider and NPU remained off.

Historical memory recovery required 35.997 GiB and ended at 35.958 GiB. Its failed
receipt is preserved. Separate unchanged 35/131-GiB admission allowed normal
restoration. At 05:29:38 UTC the original 262,144-capacity server was freshly
ready/open with controller 38796, backend 2272 and visible console 35288.
Coordinator identities were checked closed, raw evidence and the current ready
binding were sealed in `dflash-checkpoint-20261009/terminal-status-runtime-checkpoint.json`.
The serving acceleration goal remains active and unachieved. This successful
capture trial will not be replayed; next work is normal 0.17.4 qualification and
a useful independent acceleration consumer.

Local evidence under
`server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/`:

- `dflash-root-first-failure-trace-build-20261010/build/first-failure-cpu/{red,green}/receipt.json`
- `dflash-root-first-failure-trace-build-20261010/build/root-linux-build/build-receipt.json`
- `dflash-root-first-failure-trace-compiler-map-advice-launch-20261010/trial/first-failure-trace.log`
- `dflash-root-first-failure-trace-compiler-map-advice-launch-20261010/trial/retained-startup-runtime.json`
- `dflash-root-first-failure-trace-compiler-map-advice-launch-20261010/trial/supplemental-normal-restore-admission.json`
- `dflash-checkpoint-20261009/first-failure-restore-running-checkpoint.json`
- `dflash-checkpoint-20261009/first-failure-terminal-checkpoint.json`
- `dflash-root-phase-handoff-preparation-20261010/build/actual-parent-red/receipt.json`
- `dflash-root-phase-handoff-preparation-20261010/build/actual-candidate-green/compile.json`
- `dflash-root-phase-handoff-preparation-20261010/failed-round-type-source/`
- `dflash-root-phase-handoff-preparation-20261010/build/actual-candidate-green-round-type/receipt.json`
- `dflash-root-phase-handoff-build-20261010/build/root-linux-build/build-receipt.json`
- `dflash-root-phase-handoff-source-review-20261010/{review,green-review,launch-review}.md`
- `dflash-checkpoint-20261009/phase-handoff-build-checkpoint.json`
- `dflash-root-phase-handoff-compiler-map-advice-launch-20261010/launch-change-receipt.json`
- `dflash-root-phase-handoff-compiler-map-advice-launch-20261010/trial/root-tool-session.json`
- `dflash-root-phase-handoff-compiler-map-advice-launch-20261010/trial/client-complete.json`
- `dflash-root-phase-handoff-compiler-map-advice-launch-20261010/trial/first-failure-trace.log`
- `dflash-root-phase-handoff-compiler-map-advice-launch-20261010/trial/retained-startup-runtime.json`
- `dflash-root-phase-handoff-compiler-map-advice-launch-20261010/trial/supplemental-normal-restore-admission.json`
- `dflash-root-phase-handoff-compiler-map-advice-launch-20261010/trial/restored-ready.json`
- `dflash-checkpoint-20261009/phase-handoff-terminal-checkpoint.json`
- `dflash-checkpoint-20261009/terminal-status-build-checkpoint.json`
- `dflash-checkpoint-20261009/terminal-status-runtime-checkpoint.json`
- `dflash-root-terminal-status-compiler-map-advice-launch-20261010/trial/client-complete.json`
- `dflash-root-terminal-status-compiler-map-advice-launch-20261010/trial/retained-startup-runtime.json`
- `dflash-root-terminal-status-compiler-map-advice-launch-20261010/trial/supplemental-normal-restore-admission.json`
- `dflash-root-terminal-status-compiler-map-advice-launch-20261010/trial/restored-ready.json`
