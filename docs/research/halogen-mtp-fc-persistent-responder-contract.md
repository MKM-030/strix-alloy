# Persistent paired FC NPU responder source contract

This source implements the Windows ML provider side of the bounded count1-D
paired FC shadow protocol. It is not a benchmark result. No provider session,
model execution, native launch, import-based check or test was run by its author.
Every integration, native parity, full D/head, NPU, acceptance, transport and
performance qualification remains false.

## Root interface

Module: `scripts/benchmarks/halogen_mtp_fc_npu_responder.py`.

`plan_from_mapping(mapping)` is a pure decoder for independently frozen JSON:

```json
{
  "schema": "halogen-mtp-fc-runtime-plan.v1",
  "files": [
    {"path": "ABSOLUTE_PATH", "sha256": "INDEPENDENT_SHA256", "bytes": 123,
     "owned_identity": {"st_dev": 0, "st_ino": 1, "st_size": 123,
                        "st_mtime_ns": 1, "st_ctime_ns": 1}}
  ],
  "modules": [{"name": "EXACT_IMPORT_NAME", "path": "EXACT_PINNED_SOURCE_PATH"}],
  "import_directories": ["ABSOLUTE_SOURCE_DIRECTORY", "ABSOLUTE_SITE_PACKAGES"],
  "provider_directory": "ABSOLUTE_COPIED_PROVIDER_DIRECTORY",
  "work_directory": "ABSOLUTE_NEW_EXCLUSIVE_DIRECTORY",
  "setup_seconds": 300,
  "preparation_call_seconds": 30,
  "response_seconds": 0.15,
  "monitor_seconds": 0.01,
  "ort_version": "1.25.2",
  "numpy_version": "2.5.3"
}
```

Identity may also include `st_mode` and `st_nlink`. Runtime files and sources are
fully hashed and retained before provider bootstrap. The root must independently
pin the runtime/package files and every installed/copied provider inventory file;
the source never invents a pin from observed content. Exact module origins are
resolved before import without executing package initializers. Every concrete
parent initializer and the responder's own source require retained file pins.
Exact module origins are required for:

- `halogen_mtp_fc_admission`, `halogen_mtp_fc_wire`, `halogen_mtp_fc_coordinator`
- `numpy`, `onnx`, `onnxruntime`, `hgn_q4c_slice`
- `halogen_npu_expert_onnx`, `halogen_npu_v2_d_prepare_probe`
- `winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap`
- `winui3.microsoft.windows.ai.machinelearning`

Already loaded and newly imported concrete module origins in the `numpy`,
`onnx`, `onnxruntime`, `winui3` and `winrt` namespaces must occur in the retained,
independently hashed runtime/source inventory. The audit occurs before runtime
imports/bootstrap/session creation and after imports/bootstrap/session creation
and warmup. It rejects unpinned origins rather than deriving pins from discovery.
True namespace packages have no executable initializer. This checks the loaded
Python/extension module origins only; it does not establish a complete OS-loaded
native-library dependency closure or provider kernel placement. Rechecks use
retained fd/path identities and do not add a full runtime hash per proposal.

`PersistentFcResponder(plan, Hooks(...))` requires four root callbacks:

- `window_guard() -> True`: verifies the exclusive owned serving/NPU window.
- `reserve_check(admission: bool) -> dict`: freshly samples integer
  `available_bytes` and `commit_headroom_bytes`; admission requires 22 GiB,
  continuous operation 18 GiB.
- `live_guard() -> (container_pid, starttime_ticks)`: authoritative positive
  integer identity for the root-owned native process after late binding.
- `cancel_owned_job(reason: str) -> True`: signals mandatory external guardian
  cancellation of the owned responder/native job, including blocked calls.

The root sets `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` and `MKL_NUM_THREADS` to
`1` before Python starts. The responder never changes models, drivers, BIOS,
global WSL configuration, voltage or package installation state.

## Preparation and fresh late binding

1. The root obtains factory-created `PreparedAssets` from
   `admit_assets(assets=..., receipts=..., bf16_payloads=...)` using fixed
   descriptor roles and actual immutable JSON/BF16 bytes.
2. `responder.prepare(prepared_assets) -> responder` retains and validates every
   admitted asset and runtime/source pin, rebuilds admission from actual retained
   receipt/fixture bytes, checks dependencies and complete provider inventories,
   then bootstraps Windows ML. Missing/failed CPU or NPU arithmetic receipts fail
   before bootstrap. Currently absent successful receipts are a real blocker.
3. Exactly one installed `READY` VitisAI catalog entry and one actual NPU device
   must match the admitted catalog/copied library. There is no
   `ensure_ready_async`, package acquisition or CPU provider fallback.
4. One persistent ORT session handles FLOAT `e_norm[1,2560]` and
   `h_norm[1,10240]`, returning FLOAT `e_projection[1,2560]` and
   `h_projection[4,2560]`. It uses a new exclusive cache/profile directory.
5. Twelve alternating frozen A/B preparation calls must meet the original Q8 GPU
   references at unchanged NPU tolerances (`rtol=.03`, `atol=.003`), exact BF16
   lattice, admitted NPU output hashes, stability and both-input variation.
   Strict fresh VAIML hw/stx context coverage and executed VitisAI-only profile
   checks must pass. `preparation_evidence` returns a detached JSON-compatible
   context/profile/warmup summary. These checks confer no runtime qualification.
6. Only after preparation does the root launch native discovery and construct
   `ShadowAdmission`. `responder.bind(shadow_admission) -> responder` recreates
   its fresh observation/model/epoch binding and matches the prepared session.
   Binding occurs once; process restart, model reset or epoch replacement requires
   closing and preparing a new responder in a new root-owned window.

This ordering is required because native discovery has a two-second arming
window. Provider session compilation must not be attempted within that pause.

## Live callback and cancellation

The transport uses `responder.callback(FcRequest) -> wire.ProjectionPair`
(the responder is also directly callable). Each callback validates the exact
fresh run/epoch/model/graph binding, authoritative native PID/starttime, body and
input digests, and the next sequence. It consumes that sequence before provider
execution. At most four sequences are accepted; retries/concurrent/reentrant
proposals permanently latch failure. Inputs are widened from exact little-endian
BF16 bytes without renormalizing or caching dynamic values. Both projections
must be finite FP32 on the exact BF16 lattice before exact BF16 bytes are returned.

A concurrent watchdog samples root window/reserve/liveness while native work is
blocked. Deadline/guard failure sets `RunOptions.terminate` for the active provider
run and signals external root-owned-job cancellation. External cancellation is
also mandatory during setup when no ORT RunOptions exists yet. A post-call
deadline check cannot replace either mechanism. Native response timeout is
200 ms; responder budget defaults to 150 ms and cannot exceed 180 ms. Reported
callback wall time is diagnostic, never a decode-speed or acceptance result.
An independent deadline timer also terminates a provider run when the guard
sampling callback itself is blocked; timer and sampling threads have checked
bounded joins.

Stable retained file/fd/path identities are checked around live proposals. The
source does not hash the large graph, raw weights or checkpoint per proposal;
full byte hashes are checked before bootstrap, after preparation and at teardown.

## Checked teardown and remaining qualification

`responder.close() -> dict` closes any unfinished profiling, releases its sole
session, unregisters the provider, closes the DLL directory, shuts down Windows
ML bootstrap, rehashes assets and closes retained handles. Failures are retained
in `cleanup_errors`; repeated close returns the recorded report. It refuses to
unload resources beneath an active native call and requires outer cancellation.
Each operation's watchdog is stopped with a bounded checked join.

The root must still obtain arithmetic admission receipts, run this responder in
the actual shadow native path, validate candidate versus original native outputs,
prove unchanged native lifecycle/seed/RMS/full-head behavior, then measure
nonrepetitive prefill/decode and MTP acceptance on frozen workloads. Profile,
partition coverage, provider preparation or transport echo alone cannot establish
any of those results.
