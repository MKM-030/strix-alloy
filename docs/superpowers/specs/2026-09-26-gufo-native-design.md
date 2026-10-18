# Optional GUFO backend on Windows

Status: native-Windows-first direction and this written specification approved by the user on 26 September 2026. Proceed to implementation planning and execution; approval does not claim implementation, a successful build or new benchmark results.

## Outcome and boundaries

Add an independently selectable, experimental GUFO backend for Qwen3.8 Flash Next to Strix Alloy. Keep Windows usable while inference runs. Retain the existing llama.cpp launcher, Halogen WSL2 deployment, model files and 27B option unchanged. Do not make GUFO the default or silently redirect existing clients.

This is the first implementation stage of the revised performance goal. Halogen tuning and individual Strix Llama kernel/state-management ports are subsequent experiments, not bundled into the first GUFO change. Source research for all three tracks is already available. GUFO is an inference engine with its own kernels and model reader, not a drop-in Halogen kernel.

Three approaches were considered:

1. **Optional native-Windows GUFO (selected):** use the Windows port, existing GGUFs and an isolated runtime. Avoid adding a second WSL compatibility adaptation before testing the new engine. The port and our IQ4_XS quantization still need qualification.
2. **GUFO through WSL2 first:** shares more environment with Halogen but adds unproven ROCm/WSL integration work. Retained only as a later alternative if native execution is technically blocked.
3. **Halogen-only tuning first:** smallest runtime change but does not satisfy the explicit GUFO support request. The new Halogen 0.14.0 entrypoint refuses WSL2, so it is not a drop-in replacement for our pinned 0.13.8 deployment.

## Isolation and provenance

- Integration worktree: `C:\Projects\strix-alloy-research\integration`, branch `codex/gufo-native-integration`, based on native Strix Alloy `55bb4ff3181daddc4754b3fa7f44877fe5bffe60`.
- The dirty original `C:\Projects\strix-alloy-clean` is not an editing target. Do not copy its unrelated uncommitted client/model changes into this branch.
- Preserve published Halogen baseline `6b35ef80445d426237f87175258c7ceab724b252` in `C:\Projects\strix-alloy-wsl2`.
- GUFO upstream reference: `gufo-org/gufo@d9a84f13f35d1f98da22886a12eb25dc7062e392`.
- Windows execution source: `pixmaate/gufo@cff564964e8506c0abb3e530cecb55332187ac6c`, branch `windows-port`.
- Source snapshots remain clean. Any required engine fix belongs in a separate working checkout and a recorded patch, not a silently modified reference snapshot.
- Record compiler, SDK, vcpkg revision/package versions, build options and resulting binary hashes. The fork documents TheRock 10.0.0; the existing shared SDK is 10.2.0. Try only explicitly recorded combinations. An incompatible result is a failed build, not permission to replace the shared SDK. Any required compatible SDK is installed in a separate directory after its download size and disk fit are established.
- Do not distribute model weights or proprietary AMD binaries. Preserve GUFO MIT attribution and actual third-party dependency notices. No public push or release is implied by this stage.

## Components and responsibilities

Keep the new entrypoint separate from `app/launch-flash-next.ps1`. The first integration exposes start, print-only, status and stop for GUFO without teaching the existing native launcher GUFO flags.

1. **Runtime setup:** a reproducible PowerShell entrypoint accepts explicit source, build, SDK and dependency locations, checks pinned identities, performs bounded-parallelism builds and records a build manifest. It does not install a service, autostart, driver or system-wide environment variables. CPU-only tests precede GPU runtime qualification.
2. **Model/profile validation:** an explicit profile names the first GGUF shard, every expected shard and optional shared MTP sidecar. Validate file sizes, GGUF metadata, architecture, shard identity and sidecar compatibility without reading the entire tensor payload for a routine preflight. Distinguish publisher-manifest hashes from locally recomputed hashes. Do not select the newest arbitrary file or convert HGN.
3. **Admission and lifecycle controller:** inspect host and WDDM memory before launching, reject unknown/unsafe profiles, own exactly the child process started for the run, wait for real readiness and save structured outcomes. This controller is separate from performance measurement.
4. **Benchmark client:** store full request parameters and raw responses/timestamps. Run explicit greedy and sampled controls, identify cold and cached requests, and separate HTTP timings from engine-reported timings. It must also work against a supplied local comparison endpoint without starting or stopping a server it does not own.
5. **Documentation:** a short optional-backend setup/use/rollback guide, configuration examples, provenance and a comparison report. Mark GUFO experimental until correctness and performance checks pass. No improvement claim before local measurements.

Use small focused files and the repository's PowerShell-oriented packaging conventions. A Python standard-library module may implement model metadata parsing, pure admission arithmetic and HTTP measurement; Python then becomes an explicit dependency of the optional research controller, not a new requirement for the unchanged published llama.cpp runtime.

## First runtime profile

- Native Windows, localhost only, separate default port `8836` and model alias `gufo-flash-next`.
- Exactly one session, context capacity 4096, no MTP, no projector/vision auto-discovery and no disk prompt-cache configuration.
- The pinned loader searches for `mmproj-BF16.gguf` in both the resolved model directory and its parent even when `--mmproj` is omitted. Reject the first profile if either candidate exists; recheck immediately before process creation. Do not move user files or invent a `none` argument. Supporting a colocated projector requires a separately reviewed explicit-disable engine patch.
- Reuse the existing Unsloth UD-IQ4_XS three-shard set, revision `38bb39ee97821de2c9009abb7e93950eec396e66`. Its GUFO reader exists but this quantization is not yet qualified in the port.
- Initial completion: a short fixed public prompt, explicit temperature 0, explicit sampling/penalty fields accepted by the API, thinking off and at most 64 generated tokens. Reject or record unsupported parameters instead of silently dropping them.
- No public/network-facing bind and no existing endpoint changes. Do not launch if a model process, active guest allocation or occupied port makes ownership or memory accounting uncertain.
- Clear unexpected inherited `GUFO_*` experiment settings in the child environment; set only the recorded allowlist. SDK/DLL paths are scoped to the child process/build. Never mutate permanent PATH or HSA variables.
- Launch without a visible helper console. Preserve logs and return errors instead of hiding failed startup.

## Memory admission and stop behavior

### Approved measured-margin amendment, 26 September 2026

After reviewing the allocation audit, the user explicitly approved bounded
staged native GPU tests using measured safety margins once the build and guards
pass review. Keep the49GiB prelaunch floor,24GiB Windows physical stop floor,
explicit commit reserve and no concurrent inference model for qualification.
Start with limited probes, then one4k AR session; record model/build/profile
identity, audited application allocations and empirical runtime allowance.
Unknown components must be investigated and assigned justified margins, not
silently counted as zero. A reviewed measured policy may acknowledge unresolved
future WDDM placement rather than require a mathematical placement guarantee.
The dedicated-free subtraction is only a conditional/minimum-spill estimate,
not a maximum shared-memory bound. Monitoring and cleanup cannot eliminate
driver-freeze risk. This amendment governs any stricter placement-proof wording
below; it does not itself qualify a profile or bypass remaining implementation
and review gates.

The last three-full-260k Halogen attempt froze the computer and required a hard power-off. Its observer did not stop allocation in time. A kill threshold, pagefile, Windows process limit or sum of GPU budgets is not a physical memory reservation.

GUFO's source loads weights and shared scratch before its session-capacity check. The integration must therefore complete an independent check **before process creation**:

- Read fresh Windows available physical memory and commit headroom, adapter identity, adapter-aggregate local/shared usage, per-process GPU usage where available, and current profile settings. Store each counter's provider, scope, adapter LUID, PID where applicable and sample timestamp. Missing/failed/stale readings reject the start.
- `QueryVideoMemoryInfo` reports the calling process's budget/usage, not adapter-global free memory. An external helper's `Budget - CurrentUsage` cannot establish GPU occupancy, physical capacity or GUFO reclamation. Keep such budgets separately labelled; derive a conservative shared-spill bound from audited aggregate counters and the model envelope. Do not substitute the helper's budget when aggregate usage is unavailable.
- Model GPU demand includes post-conversion weights, shared scratch, lazy workspaces, eagerly allocated session state, MTP when requested, allocator margin and load-time transients. Account separately for pinned host buffers, snapshots and file-cache behavior. No double counting dedicated and shared UMA as two physical banks.
- Omitting disk cache does not disable RAM prompt snapshots, and `cache_prompt: false` bypasses lookup but still permits cache population. Bound retained plus in-flight snapshot geometry for the selected session count and context. The source limits cache entries by session count as well as a host-memory budget; neither ignoring snapshots nor assuming they always consume half of RAM is correct.
- Use a source-pinned conservative model-specific envelope, with its components and uncertainty recorded. An unbounded or unexplained component is not silently treated as zero; it blocks qualification until audited or bounded.
- Preserve at least the existing conservative **49 GiB Windows prelaunch floor and 24 GiB predicted post-load/runtime physical headroom**. Include shared GPU demand in the host-side subtraction and preserve explicit commit headroom. Do not inherit the old 12 GiB emergency threshold as a new permission to consume the remaining RAM.
- A memory-qualification review must accept the complete envelope before the first model load. There is no override to force an unqualified profile through the public launcher.
- Keep the current 64 GiB carve, WSL configuration, driver, pagefile and security settings. Small-context MTP is already expected to spill beyond dedicated memory with these weights; that must be accounted for, not fixed by silently changing the carve.

Use a unique run directory and single-instance lock. Store executable identity, PID, process creation time, resolved model/profile identity and endpoint. Stop only the owned process after rechecking identity; do not kill by image name or trust a stale PID file. A startup timeout or failed `/ready` check triggers bounded owned-process cleanup and a failed outcome, never a background orphan presented as success. `/health` alone is insufficient. Readiness requires `/ready`, the expected `/v1/models` identity and a successful small completion.

The launcher may return after readiness only after handing ownership to a long-lived guardian. The guardian holds the single-instance lock and pressure observer for the server's entire lifetime. It owns a non-inherited Windows Job Object with kill-on-close behavior; create the child suspended, assign it to the job before any weight loading, then resume it. Failed job assignment aborts before resume. If the guardian crashes or is terminated, closing its sole job handle terminates the owned child. This is lifecycle cleanup, not a GPU-memory cap or proof against a driver hang. Offline tests must exercise guardian death, startup-handshake failure and stale ownership. An unconfirmed cleanup result prevents another launch.

The controller observes pressure while running and aborts its own workload on a floor breach or loss/staleness of required telemetry; documentation states that this is secondary protection, not the basis for admission. Verify process exit and reclaimed memory with correctly scoped host, adapter and owned-process counters before considering the run cleaned up or starting another engine. Do not erase failed-run logs.

## Staged experiments

1. Offline parser/admission/argument/ownership/HTTP-client tests, including fake servers and processes. No GPU or real model required.
2. Pinned build, focused GUFO CPU tests, help/invalid-argument checks and DLL/runtime provenance. Require `qwen38_flash_next_mtp_sampling_test` and `qwen38_flash_next_prompt_lookup_test`; record their actual registered CTest names, execution counts and exit codes. Zero selected tests or any unexpected failure fails the gate. Broader known Windows exclusions must be named, not silently skipped or called a full-suite pass. Do not run broad diagnostic GPU allocation tests.
3. Reviewed AR 4k smoke profile, with memory sampling, small real answers and verified shutdown. If rejected by admission, report the exact missing bound or insufficient resource; do not keep retrying.
4. Single-session AR at 8k/16k capacity, then MTP with the existing shared Q8_0 sidecar and full vocabulary, only after separate fit review. Compare length policy and survival separately; English/code-only vocabulary pruning and prompt lookup remain labelled optional experiments, not German-language defaults.
5. Matched PP2k and PP8k, with sufficient context capacity for input/template/output; PP32k requires a separately reviewed larger profile. Send cache bypass and request exactly one output token. HTTP PP is the server-reported actually processed input-token count divided by monotonic wall time from request submission through the complete response; this includes the one-token generation and transport overhead. Log full logical, cached and newly processed counts separately; reject a cold row with cache hits or an unknown numerator. Engine PP is a distinct metric. Three measured repetitions per condition, counterbalanced order, recorded warmup and actual token counts. Do not label configured capacity as occupied context. Causal engine A/B comparisons require matching weight identity, tokenizer/template, request and host settings. Halogen HGN versus GUFO IQ4_XS or native PROJFIX is a labelled deployment comparison, not an isolated operating-system/kernel effect.
6. Representative short code, prose, German and tool-use generation: explicit greedy control and thinking-mode temperature 1, top-p 0.95, top-k 20 where supported; stable integer seed list, equal output budgets, meaningful-answer checks and MTP acceptance. Report incomplete reasoning/tool calls and early EOS.
7. At most two small sessions after single-session qualification. For aggregate decode, count native tokens over the same fixed 20-second interval while both sessions remain active; otherwise mark the interval invalid. The pinned GUFO HTTP API exposes filtered text deltas and final totals, not the required per-token boundary counts. Until separately audited instrumentation supplies those counts, report this metric as unavailable. Never count SSE messages, retokenize visible text or sum differently timed whole-request rates as a substitute. Whole-request throughput may be reported separately with its timing definition. Test cached continuation separately from raw prefill.

256k/260k and larger parallel capacity remain part of the broader goal, not the first integration's default or mandatory stress test. No repeat of three full contexts under the previous controls. Later allocation expansion needs a separately reviewed safe plan.

## Tests and acceptance

Offline regression cases include incomplete/wrong/mixed shard sets, incompatible sidecar, unknown model geometry, projector discovery in either the model directory or parent, missing or mis-scoped memory counters, inadequate headroom, shared-memory subtraction, overflow/negative counter input, occupied port, stale PID, process exit before readiness, readiness timeout, guardian death, malformed response, unsupported sampling field, unavailable token-window counters, unexpected alias and cleanup failure. Print-only must not load weights or create a server.

Correctness checks precede throughput: simple exact-answer prompts, short English/German text, code and tool-call shape; repeated conversation and interrupted-stream reuse before caching or concurrency claims. GUFO's Q6_K output re-encoding and different draft RNG consumption mean cross-engine sampled byte identity is not the acceptance criterion. Do not infer full model-quality equivalence from a few answers.

Success means the optional backend can reproducibly start, serve correct useful responses, shut down without an orphan, and produce auditable matched measurements while preserving host headroom. Report all repetitions, spread, TTFT, HTTP PP, engine PP/TG where available, common-window decode, actual input/output tokens, cache state, MTP acceptance, settings, source/build/model identities and peak memory. Retain failures and regressions. If it is not faster, report that result; the goal is evidence-backed tuning, not a guaranteed headline.

## Rollback and non-goals

Stop only the owned GUFO process and stop selecting its dedicated endpoint. Existing launchers, drivers and models remain unchanged. Build/runtime directories are separate and can be removed later by explicit path after review; no recursive delete is part of routine stop.

Do not use nearly full `D:`: its old empty-drive authorization is stale. Do not repartition disks, disable Windows security, alter BIOS/VGM, stop unrelated services, replace an active model, restart Windows/WSL or publish anything as part of this stage. Do not rewrite the dirty main checkout or run downloaded setup scripts without review.

## Sources

- [GUFO Windows source](https://github.com/pixmaate/gufo/tree/cff564964e8506c0abb3e530cecb55332187ac6c), especially `docs/WINDOWS.md`, model loader/executor, session budgeting and `docs/SERVER.md`.
- [GUFO upstream benchmarks](https://github.com/gufo-org/gufo/blob/d9a84f13f35d1f98da22886a12eb25dc7062e392/docs/models/qwen3.8-flash-next/BENCHMARKS.md).
- [Strix Llama results](https://github.com/rulith-dev/strixllama/blob/b8220f22e26f4184fc4884aa2244e80048ff4b38/docs/results.md).
- [Halogen 0.14.0 changelog](https://github.com/peonist-ai/halogen-flash-server/blob/c8270bb31cd824a0bf53fe9ecf80059c13e7a5bf/CHANGELOG.md).
- [Microsoft's per-process DXGI budget contract](https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_4/nf-dxgi1_4-idxgiadapter3-queryvideomemoryinfo).
