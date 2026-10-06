# Independent ordinary QKV replay review, 2026-10-06

The source review found no execution or ABI blocker for one root-admitted
finite component screen. Runtime admission, actual correctness, timing and
restoration remain root's responsibilities. This review performed no build,
WSL, hardware or lifecycle action.

Reviewed file: `scripts/benchmarks/halogen_prefill_ht/replay.c`, initially
SHA-256 `697f28752a1a5d2f8c963d703904c1eb22328966caa7815ea4d83181d5aa9df3`.
Final released SHA-256 is
`8e3fccc515e6722d756b01c5f748317d255c1bd300db9d1f9b4327278a3d223b`.
The sole change renames the constant memory field to
`own_device_bytes_budget`. Reversing that rename independently reproduces
the initially reviewed hash exactly. This accurately describes a budget
even if allocation fails early. `git diff --check` is clean. README SHA-256
`7797f2b5e25205213d39f044045e5bd2e38914f03162f25d6136d48cf0be0b45`
also matches the reviewed three-arm contract and explicit component-only scope.

## Execution and evidence scope

- Constructor is inert without its exact mode. With the mode, it pins the
  complete pristine executable and all three helper extents, validates live
  code hashes, starts one worker and makes no hardware call before root's
  post-ready arm.
- Canonical receipt binds eight immutable fixture hashes. The completed
  capture's direct-original preparation caller and library operand relationship
  are checked. Captured host/GPU pointers are never reused as new-process
  addresses.
- The seven private GPU buffers have explicit byte sizes, allocation coverage
  checks and cleanup. A zeroed descriptor binds only the new packed/sign/scale
  pointers, mode4, N/K and a local diagnostic string. The owning initialized
  router and existing rotated scratch are read, never replaced.
- Stock uses `prepare_original` followed by the BF16 library helper, then full
  device completion. Native uses the complete original rotation and packed
  multiplication helper, then full completion. Cached-original separately
  prepares a private 50-MiB W exactly once outside all paired timing and uses
  the same router/library helper thereafter.
- Each output is poisoned outside timing, completed and read back as all
  167,772,160 raw bytes. Full output hashing and exact native16-bit word
  comparison occur outside timing. Stock mismatch and API failures stop the
  screen; a candidate mismatch retires that candidate. No tolerance changes.
- Qualification excludes initial library selection. Each qualified candidate
  receives two excluded balanced warmup pairs and eight balanced measured
  pairs against stock. The independent native/cached cohorts admit at most
  43 complete pipelines. An unqualified native candidate has no timed loop.
- Wall timing includes CPU submission through full device completion. The
  report distinguishes the excluded cached preparation and denies GPU busy
  time, serving substitution, token-rate and acceptance claims.

Same-process router and fixed shape/type permit this bounded comparison.
Stock selection stabilizes by clearing its candidate vector after selection,
as established in `halogen-prefill-ht-stock-route-20261006.md`. Opaque algorithm
identity across separate engines remains unbound. Exact qualification can
fail if a newly initialized engine chooses a numerically different stock
algorithm; that is a screen failure, not permission to widen tolerance.

Root must enforce reserve, exclusivity and final normal-server ready/open
state externally. In particular, the worker does not infer exclusivity from
an idle port or stop another inference thread itself.

## Launcher and lifecycle source release

Final reviewed launcher SHA-256:
`0d5051e8fda3aec520f24318a163f46318d10f6bc35650390ebf5f506ab4d10f`.
Final reviewed root-owned coordinator SHA-256:
`e68e57523a4df5470d9e72ac17c058cdc1635142e7d51079bc83b3c56e985a7c`.

The launcher checks immutable local and native fixture hashes by streaming,
pins the exact stock profile and dependencies, and adds only read-only replay
mounts and default-off replay environment. Its native read-only verification
explicitly uses root for the root0700 fixture and root0600 files; configured
revn backend launch and file permissions are unchanged.

The replay-controller adapter subclasses the original `Gateway` before
construction and replaces the factory class in the original gateway module's
globals. The imported `controller.load_config` function is verified to use
those same globals. `Gateway.__init__` therefore registers the subclass's
inference handler, which returns 503 throughout that measurement-controller
process. Authentication, health, model listing and backend probes are inherited.
The manifest records `inference_gateway_blocked=true`, and the coordinator
requires it before arming. Normal restoration starts a fresh original
controller process without this adapter; production gateway files are untouched.
Root's exclusive ownership still covers direct backend access.

The coordinator retains 44-GiB physical/131-GiB commit stable startup
admission, the continuous 18-GiB reserve guard and fresh 22-GiB arm admission.
It submits no inference request. Partial completion-file writes remain pending;
an observation threshold seals the same worker and continues it without restart.
It exports only five small files, independently checks hashes, exact run order,
qualification/retirement, balanced pair counts, arithmetic means and owned
cleanup, then uses the normal lifecycle to restore stock ready/open. Pending
live process identities are retained if readiness observation times out.

The only changes since the first complete launcher/coordinator review were
the factory subclass, gateway source pin, manifest flag and its coordinator
check, before the separate identity correction below. Reversing those changes
independently reproduced reviewed prior hashes
`44dd6722879e61f0becb45fce99ff840bd106b655e942205c47442ff02335df3` and
`7a44d99e08be9d66bd7c4f082f0adbed6b3e9a75df985ca1929291655aff9c57`.
`git diff --check` is clean. This release permits one root-admitted finite
component screen, not a token-rate, acceptance or integration claim.

Root's subsequent pre-hardware dry run exposed a Windows Python3.12
fd/path `st_ctime_ns` disagreement on the same unchanged 7,342-byte plan:
fd-before/after reported change time, while path stat reported birth time.
The minimal correction uses explicit `st_birthtime_ns` on Windows and
`st_ctime_ns` on Linux for cross-fd/path identity, retaining device, inode,
size and modification time. A separate `unchanged_fd` comparison also
retains strict descriptor-before/after ctime on both platforms. Both bounded
raw reads and streaming hashes use those two checks. Reversing exactly this
helper and its two call-site changes reproduces the previously released
launcher hash `d4dc585042a2d0f8803a6240f2d7275fc2c34a2986e0900b8396bf82ba12b15a`.
The coordinator remains unchanged; diff checks are clean. Root owns the
actual-file regression and resealing before any hardware screen.

## Already completed restoration-admission receipt

The first post-capture `restored-stock/startup-admission.json` has SHA-256
`f7cace4624ba640a06511d529cf28aa5afd55791d06223dbafd77a28efea125c`.
All 240 recorded frames were below the unchanged 44-GiB physical admission:
42.09075 to 43.91025 GiB, with a best shortfall of 96,366,592 bytes.
All commit headroom frames exceeded 131 GiB: 196.98160 to 198.89822 GiB.
The source checks this admission before `subprocess.Popen`; no normal stock
controller was launched by that first attempt. This receipt describes that
completed attempt only, not root's subsequent recovery or current handles.

## Startup-fix review addendum

Source-only review releases the narrow constructor guard in `replay.c`,
SHA-256 `63890d4da04b045e85bfba4ae93f46cc2be145616c991eae3bb5804fd97ada83`.
It copies the successful capture's bounded `/proc/self/cmdline` check:
only `flash_serve` with argv1 exactly `--ck` proceeds to configuration,
executable/helper validation, exclusive trace creation and worker creation.
The pinned entrypoint's startup `--resident-gib` probe is excluded; its
actual serving invocation begins with `--ck`. Source, binary and plan seals
remain required by the launcher.

The root-owned coordinator `owned_replay.py`, SHA-256
`734c37651a95fb7343d7ed6c77c4c1bd0f62b83e93310c89241175d00394669f`,
received a narrow restoration patch reviewed by `prepared_weight_cache_scope`.
Measurement launches retain strict `stopped_preflight`. Only stock restoration
uses `restoration_only=True`, accepting a failed terminal only with the exact
controller/backend identity links, recovered backend, absent runner lock and
exclusive host. Reserve checks, unchanged stable startup admission and GPU
preflight remain intact. This source release does not establish completed
restoration.

The [CPU compilation receipt](../../server/.local/optimization9h-20261004/prefill-ht-replay-preparation-6f5b91efe2514cf9a08543bced966798/compile/result.json)
records successful `-O2 -Wall -Wextra -Werror` builds and exit0 for the
constructor regression. The [raw five-case probe receipt](../../server/.local/optimization9h-20261004/prefill-ht-replay-preparation-6f5b91efe2514cf9a08543bced966798/compile/constructor-regression-stdout.txt)
records `passed=true` and `GPU_calls=false`. With the real replay shared
object preloaded into a tiny CPU executable named `flash_serve`, no arguments,
`--resident-gib --ck unused`, `--ckx` and `--ckpt` reach its normal main;
exact `--ck` exits79 at the expected missing-configuration check. This verifies
constructor gating without launching the engine or reaching hardware work.

These receipts establish CPU build and startup-guard behavior only. They do
not establish a successful component hardware replay, exact GPU output,
component timing, Prefill or Decode token rate, or speculative acceptance.
The guard changes no computation; cached-original's potential Prefill benefit
still requires qualification and includes a separate 50-MiB resident weight
whose one-time preparation is excluded from paired timing.

## State-observer and pending-receipt review addendum

Source-only review by `prepared_weight_cache_scope` releases the narrow
observer correction in `owned_replay.py`, SHA-256
`6d077dad04c1124d6f2deb0adfbb4d3be980896ebea783398668341f5056f074`.
The privately loaded lifecycle uses the existing controller's bounded
one-second state reader; production controller and global lifecycle sources
remain unchanged. At readiness, a timeout or classified Windows access/sharing
error verifies the retained live controller identity and reserve guard, then
continues observation of the same process. It does not launch a replacement.
PID/profile/backend/cache/context checks remain unchanged and no unavailable
snapshot qualifies readiness.

The immediately preceding draft, SHA-256
`8682e5b04ccc40e6c22aecfab820ef487e17974c9e6682bb2adebba40e48a935`,
was blocked because its final receipt unconditionally reread both state files
through a raw reader. A still-denied file could therefore abort receipt export
after the second readiness observation exhausted, despite correctly retaining
`pending=True` and skipping stop.

The released correction centralizes the narrow classifier: a Windows
`PermissionError`, access/sharing codes5/32/33 or errno13, and an exact resolved
`server/.local/current.json` or backend `.local/current-service.json` path.
Each final optional state snapshot now uses the bounded controller reader.
A classified exhausted read records `None` plus explicit
`state_observation_errors` with `observation_unavailable=true`. Verified
controller identity, profile, command and previous backend run are retained
independently for recovery. This permits the pending result and continuation
receipt to be written while the owned engine remains live. Invalid JSON,
unrelated paths and other exceptions are not suppressed.

This addendum is a source release only. The reviewer performed no hardware,
WSL, live-process or lifecycle action and edited no coordinator source or plan.
Root owns the extracted-function mock cases, actual terminal cleanup,
restoration and any later admitted component replay. No new arithmetic,
component timing, token rate or acceptance result follows from this review.

## Final export-path correction and component audit

The completed screen exported supplemental results after the original
coordinator's destination `work/replay` collided with its lifecycle directory.
The failed coordinator receipt remains failed. The five small files copied from
the exact stopped container match the pre-stop inventory hashes and pass the
unchanged output/schedule validator. `/root/prefill_startup_review` independently
verified the 23-call schedule, all stock/cache output hashes and balanced orders.
It recommends retiring both tested paths: native failed exact qualification and
cache mean 23.2392 ms exceeds stock 22.8911 ms before serving overheads.

`/root/prepared_weight_cache_scope` released corrected coordinator SHA256
`028987ca7b26f6831bde3a851b7d25f825c49f2686237412edefa28c1c042b57`.
The one-line change selects `work/replay-results`, retaining exclusive mkdir.
All consumers use the local destination or take a directory parameter; no fixed
consumer of the previous path was found. Root's execution of the actual extracted
statements reproduced FileExistsError before the fix, then preserved lifecycle
evidence and rejected an existing result destination after it. This check used
no engine or hardware. The correction does not qualify any serving speed gain.
