# BN64 engine followup: source-only resolver cache

Decision recorded 2026-10-09. Admit one separate source-only mechanism: cache the exact next `hipLaunchKernel` target lazily in the interposer, with thread-safe publication. This is a concrete removable host operation, not a prediction of serving gain. Do not repeat the unchanged v2 cohort, relax guards, activate the adapter, or perform profiling, diagnostics, builds, hardware work or requests under this decision. No adapter is implemented here; root retains execution, lifecycle, STATE and Git ownership.

All paths below are relative to `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008`.

## Completed engine evidence

`bulk-bn64-engine-comparison-v2-resident-fix/cohort-analysis.json` now contains the complete stock-before/candidate/stock-after analysis. Its SHA-256 is `5e216b5af4dce05f59bed5946513d25d1d74c4186b98d731cc6f0eaa1891c862`; the adjacent `cohort-report.md` SHA-256 is `e8519f4e0c53674c06a63d1d8f4e5dd2c9a257771982da034217a927f772366d`.

The frozen workload is synthetic pseudoprose with 8192 input tokens from 116 repeated calibration units and 128 ordinary output tokens, one excluded warmup plus three measured requests per arm. Output and combined native MTP+PLD acceptance are identical across arms: output SHA-256 `0fbe27247d33d2829aa90b66964ff3bb946679be7ce79b379e2555f60ec74fa6`, measured acceptance 210/339. This is neither natural long-input nor NPU evidence.

V2 stock-before reuses exactly the four completed v1 stock-after requests, with zero new baseline requests. Those shared observations must not be double counted as independent samples across the two experiments.

| Arm | Native Prefill tokens/s | Native Decode tokens/s |
|---|---:|---:|
| Stock-before | 1234.141 | 44.443667 |
| BN64 candidate | 1173.972667 | 44.246333 |
| Stock-after | 1142.177667 | 41.311333 |

The candidate/stock-before pair is qualified by the recorded parity, complete windows, native audit and 0.1% clock tolerance. Its raw deltas are Prefill **−4.875321%** and Decode **−0.444008%**: it provides no observed engine gain. Stock-after has monotonic/raw scaling near 1.083333 while before/candidate remain near 1.0. The three-arm bracket and candidate/after pair fail clock comparability; candidate/after and pooled-stock deltas are descriptive arithmetic only. No clock normalization or acceptance-times-decode metric is used.

The audit proves 192 completed native64 transactions across all four candidate requests, including warmup, with zero rollback and zero failure. The logged `rejected=158167` counts stock-forwarded launches in the cumulative audited prefix. It includes startup and ends at the last commit record; it is not an exact measured-window launch total or an error count.

## What the component evidence does and does not explain

In `moe-bulk-bn64-component-v2-batched/host.c:226-243`, each event interval enqueues four consecutive items+GU+DN+fold operations and divides elapsed time by four. HIP pointers are resolved once and dispatch uses `hipModuleLaunchKernel`. Item, guard and full-word checks occur outside both timed intervals. Sorting and rotation are excluded, and operands are synthetic and already transformed.

For uniform512x160 routing, native128 mean 86.1353124 ms versus native64 mean 70.57032777 ms is an 18.0703874% time reduction, equivalent to a 22.05599% throughput ratio. These are different quantities. This fixture does not prove actual model route distribution, full-engine cost, or the cause of the observed deficit.

The v2 adapter's successful path adds two explicit NULL-stream synchronizations and eight D2H calls per completed transaction: raw histogram 2056 bytes, IDs 2048, prefix 2052, counts 8, and four 4096-byte guards. Thus 192 completed transactions require 384 explicit sync calls, 1536 D2H calls and 4,329,216 copied bytes. These are source-derived counts, not measured durations or a removable timing budget. All these checks remain required. The earlier instrumented event brackets likewise do not isolate kernel cost or support multiplying sampled brackets into expected savings.

## Independently removable operation

`bulk-bn64-engine-candidate-v2-resident-fix/adapter.c` remains sealed at SHA-256 `714b90cf716a0ed2b82deb949394ff4154798a0fadd6c421c39aadd7e3c8c24d`.

At lines 74-77, `required()` invokes `dlsym(RTLD_NEXT, name)` and exits 127 if the target is missing. Line 265 calls `required("hipLaunchKernel")` on every intercepted launch, before the unconfigured/owner/nesting fast path at line 268. Successful transactions, stock-forwarded launches and fast-path launches therefore each resolve the same next symbol again. Rollback already dispatches through the saved `native_launch` pointer at lines 229-233.

A lazy cache can remove the repeated successful symbol lookup after initial publication without changing kernel selection, routing checks, copies, synchronization, audit or rollback. The evidence establishes that repeated operation and its removal; it establishes no resolver duration, phase attribution, share of the deficit or likely speedup.

## Contract for a separate source candidate

- Resolve the same `RTLD_NEXT` target from this adapter DSO. Do not substitute `RTLD_DEFAULT`, a direct native-library symbol or a module-launch API. Preserve the current interposer chain.
- Use thread-safe publication. A plain shared-pointer read outside its protecting mutex is a data race. Racing initial resolutions are acceptable if they publish the same target; do not introduce a recursive initialization deadlock with `pthread_once` or a resolver-held lock.
- Save errno before lookup and preserve every current saved-errno/native-errno restoration path, including fast forwarding. Preserve the missing-target diagnostic and `_exit(127)` behavior.
- Retain assignment of a valid saved target before any transaction can invoke rollback. Preserve the existing mutex, nesting, owner/thread, phase, shape, ABI/pin, capture, route, count, guard and fail-closed contracts.
- Retain the resident-query constructor skip and avoid new constructor HIP or native-target resolver work. The existing crypto-symbol resolution and hash verification remain required.
- Establish that the next target remains loaded and lookup scope is stable for the process lifetime. Unloading/replacing a target or changing lookup scope would change the semantics of a fresh lookup and must not be assumed away.

The independent source review from `/root/prefill_new_mechanism_scope/window_inventory_review` agrees the repeated next-symbol lookup is removable and calls out the same publication, errno, rollback, recursion and target-lifetime constraints. It performed no edit, test or execution.

Recommendation: retain stock for serving and defer unchanged BN64 execution. A separate resolver-cache source diff is independently justified for review under the contract above; this note does not qualify a gain or authorize another cohort. If that semantic contract cannot be proved, defer the cache as well. No sealed source or evidence was changed and no analyzer was executed for this note.

Root's closing disposition is that this measurement cycle is complete, the normal server is ready and no changed candidate is activated. The broader goal remains active and unachieved. Actual resolver cost in the engine was not captured; the concrete per-launch redundancy supports source-design followup only, with no proven return on the change.
