# Paired-FC root-owned Windows/WSL/container launcher design

Date: 2026-10-04. Source-derived design; no launch, build, provider initialization,
model read, or qualification was performed for this note. ROOT owns implementation
and execution. The existing user controller PID 10048 and game PID 20004 remain
outside this launcher's authority. A live user engine is a deferral condition.

## Minimal implementation boundary

Reuse the full v2 service manifest, environment, admission, authenticated API and
progress lease. Add a small retained binary-pipe process owner, a pinned engine
bootstrap/identity reader, a sealed source bundle, and a persistent responder
holder. Do not use the 2-GiB component replay container as a full-model launcher.
Native echo is one fresh bounded run; screened NPU is a subsequent fresh run after
terminal cleanup and recovery. Each run has one large engine, one immutable arm,
one discovery and exactly four consumed request sequences. A failed/consumed epoch
is never reset or retried in that engine.

The proposed new mount destination is `/candidate/fc`; its source is a ROOT-created
and independently verified staging directory, recorded as an exact source in the
manifest. This is a design addition, not an existing mount. It contains adjacent,
unchanged `halogen_mtp_fc_relay.py`, `halogen_mtp_fc_transport.py`,
`halogen_mtp_fc_coordinator.py`, `halogen_mtp_fc_wire.py`, bootstrap/identity helper
sources and the ROOT-built constructor shim. Pin every file and derived entrypoint
before create, verify copied bytes again in the fresh container, and revalidate
before discovery and after the epoch. The four relay modules must satisfy relay
`verify_source`: regular, nofollow, nlink 1, bounded size and stable metadata/hash.
Stage once; do not overwrite sources while a container owns them.

`service.source_hashes()` covers backend scripts/patches/profile files, not this
benchmark bundle. Preserve its existing equality check and add a distinct sealed
FC source map with explicit guard validation. Include `/candidate/fc` in
`m['mounts']` so `service.owned(..., running=True)` supplies the exact enlarged map
to `startup_guard.EXPECTED_MOUNTS`. Added bindings cannot bypass the guard's exact
mount count/source/destination/read-only checks.

## Ordered executable lifecycle

1. Read managed state without taking ownership. Refuse if the existing user
   controller/engine is active, if cleanup/ownership is unresolved, or if the
   exclusive-host check finds another large engine/container. Acquire only the
   launcher's fresh lock and attempt directory. Generate independent UUID run ID,
   nonzero 16-byte nonce and epoch; use the nonce in the constructor directory.
   Do not stop an existing run to satisfy admission.
2. Start retained ownership and the 250-ms physical/commit monitor used by
   `halogen0162_fc_owned_run.py`: initial 22/22 GiB floor and continuous 18/18 GiB
   floor. Sample freshness must also obey `service.check_runtime_frame` (age <=2 s).
   These smaller guards do not authorize loading the large checkpoint.
3. In screened-NPU mode, initialize, compile, verify placement and warm the one
   persistent pair session now, before model load/discovery. Reuse the source
   checks in `halogen_npu_v2_d_native_projection_probe.py`, including the separately
   hashed same-source CPU gate, exact provider/runtime/model/data/receipt identities,
   `session.disable_cpu_ep_fallback=1`, disabled fallback, exact `e_norm`/`h_norm`
   inputs and both projection outputs. Pin successful screen/placement receipts.
   Its `run()` destroys the session in `finally`; it is not a reusable responder.
   ROOT must implement a holder that retains the session/resources and releases
   them on every cleanup path. Native-echo mode initializes no NPU session.
4. Perform full-server v2 admission with the resident responder already charged
   against headroom: requested 44 GiB physical /131 GiB commit, stable for60 s,
   within the existing240-s admission deadline. Recheck immediately before resume.
   `memory_budget.admission_floors(262144, 'v2')` returns44/131. Its default126 Ki
   service context returns44/127; seal context262144 for this requested full-capacity
   design. Keep18/18 runtime reserves throughout startup, transport and recovery.
5. Build `service.build_manifest` with pinned v2 checkpoint, explicit context,
   one slot, selected speculation/draft settings, added FC pins/mount and a reviewed
   derived entrypoint. Preserve `service.command`'s pinned image, `/dev/dxg`, host
   IPC/8-GiB shm,44-GiB memory and memory-swap limits, restart=no, owner/run labels,
   loopback8731 and all existing compatibility/preflight mounts. Add
   `HALOGEN_MTP_FC_QUALITY=shadow4-v1`, `HALOGEN_MTP_WIRE=D`,
   `HALOGEN_MTP_FC_QUALITY_DIR=/tmp/alloy-mtp-fc-quality-<noncehex>` and wave1.
   Add the shim to `LD_PRELOAD` without dropping the existing v2 preflight and
   private-registration libraries. Review and pin the final preload order.
6. Create a fresh container; retain its full64-hex ID, exact UUID name, image,
   labels, manifest and create receipt. Recover an ambiguous create only by that
   exact name+labels+image with a unique full-ID result. Start the host lease guard
   as a retained owned child and wait for its initial arm/lease progress. Preserve
   the container `python3 /candidate/lease_supervisor.py ... /bin/bash
   /candidate/entrypoint-wsl-candidate.sh all` contract. The45-s progress lease
   requires observed renewal and kills/reaps its launched process group on loss.
7. Start `docker start -a <fullCID>` through retained `OwnedProcess`, preserving
   suspended-create -> job assignment -> identity recording -> resume. Follow its
   separate logs, supervise startup and keep the lease guard/memory monitor alive.
   Existing `service.serve()` uses detached start/ordinary `Popen`; that behavior
   alone does not implement this retained-child requirement.
8. Obtain the independent bootstrap identity described below from this exact
   container and verify current engine exe/start ticks/UID. Confirm health and
   configuration, stop startup cache advice before inference, and validate the
   constructor's activation/packet-directory metadata. Do not issue any request
   that can enter the MTP head until the responder and resident relay are ready.
   Existing serial readiness probes must be reviewed for this condition.
9. Launch one retained `docker exec -i` relay with captured identity and four
   exact source hashes. Wait for verified initialization/readiness before the
   first MTP request. Submit only the bounded root-owned discovery/request workload.
   Consume HELLO and send ARM on these same resident pipes within the native2-s
   discovery wait; then respond to sequences0..3 within the native200-ms deadline.
10. Collect native/relay/bridge/provider outcomes and exact receipt hashes; then
    perform the exact-ID cleanup below. Echo success supports only the observed
    transport/native-echo result. Provider screen success and any four returned
    projections do not establish word parity, acceptance or token-rate gains.

## Independent native identity at the owned launch site

The pinned `.local/entrypoint-wsl.sh` `all` branch directly backgrounds
`${_hg_flash_serve:-/usr/local/bin/flash_serve} --ck ...` and retains `ENGINE_PID=$!`.
There are usages but no assignment of `_hg_flash_serve` in this source. Do not
assume a multiword wrapper fits this variable. First run `service.service_entrypoint`
to retain its original-source hash and exact five auth-API substitutions. Then
apply a second pinned, exact-count transformation only to the single `all` serving
launch site, leaving its arguments, `$!`, readiness, traps and reaping intact:

```text
python3 /candidate/fc/engine_bootstrap.py <sealed run/nonce/receipt arguments> -- \
    /usr/local/bin/flash_serve --ck "$HALOGEN_CHECKPOINT" <unchanged serving argv> &
ENGINE_PID=$!
```

The new bootstrap verifies its own pinned source and sealed command, records
`os.getpid()`, Linux `/proc/self/stat` field22 start ticks and actual `os.geteuid()`,
then `os.execv`s the pinned engine path. PID/start ticks survive this exec. Publish
an exclusive0600 launch receipt at a separate container-local proposed path
`/tmp/alloy-mtp-fc-launch-<noncehex>.json`, binding run ID, nonce, bootstrap hash,
sealed engine argv and identity. Do not precreate the constructor's quality
directory: its C constructor requires an exclusive0700 mkdir itself.

A pinned identity reader invoked only inside the retained fullCID checks that
receipt and the current `/proc/<recordedPID>/stat`, effective UID and engine exe.
Retain this independently created tuple before discovery. Match the discovery
packet against it; do not learn the authoritative PID from `observed.bin`, a log,
an arbitrary external PID or `Docker State.Pid` (which identifies the supervisor).
The existing relay `ProcessGuard` verifies the26,052,768-byte engine ELF hash once
before waiting for observation and compares current start ticks/live state through
the epoch. Use same-UID execution based on the captured actual UID. No UID or
absolute Python interpreter path has been established by source; `python3` is the
existing supported command name and its resolved identity must be recorded by ROOT.

## Resident binary pipes and arm rendezvous

Proposed relay argv, constructed as an argv array rather than shell text:

```text
C:\Windows\System32\wsl.exe <configured WSL argv after executable> docker exec -i
  --user <capturedUID> <fullCID> python3 -u -B
  /candidate/fc/halogen_mtp_fc_relay.py
  --directory /tmp/alloy-mtp-fc-quality-<noncehex>
  --engine-pid <bootstrapPID> --engine-starttime <bootstrapStartTicks>
  --uid <capturedUID> --lifetime-seconds 45
  --self-sha256 <relaySHA> --transport-sha256 <transportSHA>
  --coordinator-sha256 <coordinatorSHA> --wire-sha256 <wireSHA>
```

`server/winjob.py` currently supports exclusive stdout/stderr files and devnull
stdin; it has no pipe API. Extend it or add a reviewed equivalent retaining the
same suspended-before-job-assignment discipline. Inherit only the child stdin
read end, stdout write end and separate stderr handle via its explicit handle
list; parent pipe ends must be non-inheritable. Retain every process/thread/job and
pipe handle through cleanup. Expose raw unbuffered binary reader/writer; no PTY,
text decoder, newline translation, shell pipeline or per-request process launch.
`runner.invoke`/`runner.docker` use captured text/strip and cannot carry these frames.
Use them only where bounded textual metadata is appropriate, with child ownership
added for commands that outlive a synchronous call.

`transport.bridge_loop` currently expects exact observation and coordinator before
it reads HELLO. Add a reviewed first-HELLO adapter: boundedly read/validate the
520-byte HELLO frame on this pipe, decode its464-byte observation against the
independent nonce/PID/start ticks, construct `CanonicalBinding`s and
`ShadowCoordinator`, then replay that exact encoded frame through a prefix reader
to the existing bridge. Alternatively refactor first-HELLO initialization explicitly.
Do not retrieve observation with a second `docker exec` in the2-s arm window.
Canonical assets/receipts and callback/session must already be sealed and resident.

Native echo callback is exactly `request.native_projections`, returning the
existing immutable `ProjectionPair`. Screened NPU converts the already-normalized
inputs and returns both finite BF16 projections from its existing session. It does
not redo RMS or seed-add. `coordinator.respond` burns a sequence before the callback;
timeout/failure latches abort and cannot retry those inputs.

The56-byte outer header wraps HELLO464, ARM120, REQUEST51424 and RESPONSE25856.
The latter is224 bytes identity/binding +25,600 projection bytes +32 digest bytes.
The200-ms native deadline includes request publication, both pipe crossings,
compute, response validation and atomic publication. Outer Windows I/O/callback
deadlines must interrupt blocked operations through retained ownership and join
reader/writer workers; bridge `live_guard()` alone cannot interrupt a blocked read.
Keep cached live full-container and memory attestations fresh with independent
owned monitors; do not add expensive Docker startup or full ELF hashing per frame.

## Remote cleanup and failure ownership

Serialize cleanup with the guard. Latch `coordinator.abort`, cease request
admission, request/confirm guard quiescence and keep the reserve monitor active.
Reinspect the fullCID and exact name/image/run-owner labels, mounts/environment and
resource contract before any daemon mutation. Stop only that admitted container
(`docker stop -t 0 <fullCID>` for failed bounded transport), inspect again and
require `State.Running=false`, `State.Pid=0` and `runner.validate_terminal`.
Closing the Windows job proves local WSL/client cleanup; it does not prove Docker
daemon container or in-container exec cleanup. The container terminal proof is
required independently.

Snapshot only the owned launch/packet receipts through the same exact container
identity before removal; use bounded binary collection when bytes must be hashed.
Remove exactly the proven terminal fullCID, and prove that exact ID is absent.
Close/reap retained start/relay/metadata owners, close pipe ends and join I/O workers.
Use the existing unchanged memory-recovery baseline/threshold; finish the lease
guard only after proven terminal state and recovery, then close its retained owner
and responder/provider resources. Preserve lock, handles and evidence if cleanup
or recovery is unresolved. Never stop by image/process name, guessed PID, ID prefix,
container-name prefix or adopt the user server. Ambiguous ownership fails closed.

## Source anchors

- `server/winjob.py`: `_startup_info`, `OwnedProcess`, `verify_live_identity`, `close`.
- `scripts/benchmarks/halogen0162_fc_owned_run.py`:22/18 admission/monitor,
  retained docker-start owner, ambiguous-create recovery, exact terminal cleanup.
- `backends/halogen-wsl2-0.16.2/scripts/service.py`: `environment`,
  `service_entrypoint`, `source_hashes`, `build_manifest`, `command`, `owned`,
  `admission`, `check_runtime_frame`, `guard`, service startup/cleanup.
- Backend `memory_budget.py`, `startup_guard.py`, `lease_supervisor.py`, `runner.py`.
- Backend `.local/entrypoint-wsl.sh`: `all` direct engine child and `$!` ownership.
- `halogen0162_mtp_fc_quality_publish.c`: constructor/discovery/2-s arm/200-ms reply.
- `halogen_mtp_fc_{relay,transport,coordinator,wire}.py`: packet/pipe/epoch contracts.
- `halogen_npu_v2_d_native_projection_probe.py`: initialization, placement screen,
  exact native FC comparisons and existing one-shot resource destruction.
