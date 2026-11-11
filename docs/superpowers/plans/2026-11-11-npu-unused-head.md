# Skip unused NPU output computation: implementation plan

> For agentic workers: implement with independent source work and review. Root alone builds the native bridge and runs hardware. No new engine comparison is authorized by a source test alone.

**Goal:** Reduce real NPU catch-up latency by omitting the output head only for already-authoritative intermediate tokens whose logits are discarded. Improve whole-engine speed only after exact component parity and a separate complete comparable experiment.

**Architecture:** Preserve scalar recurrent forwards, layer completion, hidden-input synchronization, context updates, final row-producing forwards and state ownership. In a separate default-off helper bridge, temporarily suppress the exact FLM 1.0.12 forward's head start/wait calls; restore original instructions before a full forward or any return. The loaded DLL and call sites must match the inspected immutable binary. Do not change the installed DLL on disk, model weights, driver or normal GPU server.

**Tech stack:** Existing MSVC x64, Windows PowerShell 5.1, Python 3.12 parent/3.13 native child, FLM 1.0.12 Qwen3.5-0.8B-NPU2. Private preparation is `server/.local/halogen-update-20261110/primary0201/stateful1012-core-append-v1`.

## Evidence and alternatives

The existing scalar catch-up reduces host row/snapshot work, but still runs the full output head on intermediate true tokens. Scheduling-only savings are bounded by just 3/3/4 extra forwards in the measured live requests. Batched prefill already failed numerical parity and was slower. Repeating it, changing gate thresholds, or merely accelerating the sampler is excluded.

Exact PE evidence pins Qwen DLL `81b9349b5eb6cc7af277a41fad3a5dd7aa71321a82f8a484e7a980d80c334fad`. Impl forward is RVA `58110..58422`; the independent head is an `xrt::run` at Impl+530. Constructor and command DMA analysis bind only logits output, read-only weights and hidden input. The command's DDR writes target logits only; unproven AIE scratch/control effects require native parity. Evidence remains in `npu-unused-head-investigation-v1` and `stateful1012-catchup-v2/skip-head-source-review`.

## Constraints and review focus

- One native engine/actor thread in the private child. No external process hooks, broad XRT import replacement, or installed binary mutation.
- Default remains stock. Enabling the candidate requires an explicit per-engine selector, exact loaded-module file identity and guarded instruction bytes.
- First candidate skips **only** head start/wait at RVA58358/58393. Keep both hidden-input and logits-output synchronization initially; isolate the matrix-compute change.
- Restore instructions, original page permissions and instruction-cache visibility on normal and exception paths. Refuse unknown bytes, nested use, another thread or a second native instance. Restoration failure must be terminal and reported; never report normal cleanup after failure.
- New native export for mode selection: `sl1012_set_append_head_skip(void*, int)`. Existing exports and actor interfaces remain unchanged. Add an observation export for restored/skip counts if needed by qualification.
- Component clocks are not engine tok/s. Failed runs and timeouts remain recorded. NPU remains disabled in normal serving.
- Startup30/131, runtime18/18 and NPU-entry22/22 GiB limits remain. Two fresh idle GPU observations and game checks before hardware. Existing normal server identities must remain unchanged during the component.

## Tasks

- [ ] Write CPU tests for guarded code-scope restoration, unexpected bytes, wrong thread/nesting, default-off mode, and exceptions before implementation. Compile/run CPU-only tests to record the missing behavior, then implement and rerun.
- [ ] Create separate bridge sources and Python binding under the private preparation directory. Copy unchanged actor/state-owner files exactly. Add hash/path guards before enabling the new mode. Source agents may compile only accelerator-free test fixtures; Root builds the actual bridge.
- [ ] Independently review exact call sites, lifecycle and failures. Root verifies all source/DLL pins, CPU tests, exports/dependencies and source drift before hardware.
- [ ] Adapt the existing bounded catch-up component to compare stock append-only versus head-skipped append-only with identical already-recorded true IDs. One excluded warmup and three measured runs per mode, alternating, one native engine, seed512 and128 commits. Retain complete endpoint BF16 rows and unchanged exact comparisons against stock; keep seed/capture/state I/O outside commit timing exactly as before. Within the same child, add one unmeasured correctness replay with commit groups `(1,2,3,4,6)` inside each 16-token span, since live batch lengths vary. Compare its same nine endpoints; report its nine rows separately from the 72 timed-run rows and never include it in either mean.
- [ ] Run that **one** finite component only after the above gates. Preserve terminal handles and verify closure plus unchanged online GPU server. Reject on any mismatch, invalid cleanup, reserve breach or absent useful cost reduction. No automatic retry.
- [ ] Publish source/results and select the next action from actual evidence. A further live Stock/NPU/Stock comparison requires a credible improvement in NPU arrival and newly frozen inputs; the previous incomplete series is not filled in or repeated as if unchanged.
