# Halogen0.17.2 native worker page-order scope

Static proposal only, 2026-10-08. No interception is implemented or deployed.
The preserved ordinary sources remain unchanged. Engine SHA-256:
`ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913`.

Evidence is the existing preparation directory
`server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008`:
`ple0172-native-worker-candidate-v1/source-delivery.json`, its source handoff,
and `ple0172-prefetch-static-v2/worker-run-1865530.txt`, launcher, wait, and
consumer disassembly. Worker extent is `0x1865530..0x1865e2f` exclusive;
sealed code SHA-256 is
`f905b0035b1f131fe93aa95d9a66599669614456e29927c2f52ca78cbea25b9f`.

## Why the ordinary interception misses this route

At `0x17ec00e`, nonzero model `+0x7c0` routes to `0x17ec0cb`; after the ordinary
D2H, `0x17ec0c0` separately tests for value 1. The prefetch route calls
`0x17eeb20` at `0x17ec0d0`, then jumps to `0x17ec987`, bypassing ordinary seam
`0x17ec18c`. Removing the ordinary adapter's flag check would not alter that
native branch. The next scope therefore targets copy-mode native workers.

## Exact worker splice and ABI

System V x86-64 worker entry `0x1865530` receives a 32-byte state in `rdi`.
State `+8` is model, `+0x10` is context, and `+0x18` is captured signed native
row stride. Context `[0]` is output; null output is warm mode and stays stock.

| Site | Proposed selected behavior |
|---|---|
| Launcher `0x18011e0`, before first thread start | Select once per context/generation, before workers can take different paths. Keep native thread count and states. Page sorting defaults off; a separate proposed opt-in is `PLE0172_NATIVE_WORKER_PAGE_ORDER=1`. |
| Copy entry `0x1865ab4` | The final ID store is actually `0x1865aa4`, at `[r13+0x78]`. After the nonnull-output branch, all 16 IDs for this token exist, and no raw row copy has started. Leave preceding native scalar instructions and reservations unchanged. On selected contexts, skip only the 16-copy block and resume token progression at `0x1865791`. |
| Exit convergence `0x1865d72` | Before the original completion epilogue, selected workers enter a context-owned ID-arrival/planning/copy phase. This site includes normal exhaustion and cancellation exits. Keep native completion pending until every producer has arrived and all selected page work has finished or cancellation cleanup is complete. |
| Consumer after native wait `0x17eeb90`, before H2D `0x17eecc1` | Require the matching generation's successful terminal copy state after native joins. Failure or partial output must fail the request before H2D. |

At `0x1865ab4`, `r12=model`, `r13=&native_ids[token*16]`, `r15=token`, stack
`+0x18=state`, and stack `+0x10=output`. The native scalar block has reused
`rbp`; the skip must restore it from stack `+0x18`, set `rcx=r15`, and resume
`0x1865791`. That continuation increments the token, compares stack `+0x48`
reservation end, and reloads total tokens and token pointer from stack
`+0x40/+0x30`. A wrapper must preserve the live machine state and stack;
these are internal machine bindings, not a callable C function at the splice.

## Bounded source delta

Use a new context/generation coordinator and the sealed scheduler's page
segments. The original worker keeps its `lock xadd` reservations of 16 tokens
at `0x18655b5` and its signed token/history/EOS, multiply/XOR, signed division,
and native ID stores. Native IDs remain in original token/head order. The last
ID producer elects one planner; publication makes every ID visible before
planning and makes descriptors visible before existing workers claim disjoint
source pages and scatter into the original output. No additional thread pool.

The sealed `native_page_worker_0172.h` supplies useful generation, cancellation,
planner, and terminal-state contracts. Its `Batch::run_worker` recomputes scalar
IDs, so it is not the entry to use when preserving the original inline math.
Adapt its coordination into a phase entered after native ID production.

Each native state executes the original `0x1865d89..0x1865df2` epilogue exactly
once: mutex `context+0x68`, countdown `+0xc0`, final timestamp `+0xe8`, and CV
`+0x90`. Preserve native wait `0x1801e80`, its timed callbacks/cancellation,
thread joins, context swaps, and original output/mapping lifetimes through H2D.
Bind sidecar cancellation/wakeup to retirement, reset, destruction, and partial
launch failure; drain workers before reuse. Warm gate `+0xf1/+0xf8` cannot serve
as the new phase barrier. Planning failure after token reservations cannot
restart the fused worker with an exhausted cursor.

Qualify the actual selected metadata owner: direct mapper `+0x2d0`, otherwise
override/default `+0x290`, table `+0x758`, rows `+0x768`, and captured stride.
Pinned getter `0x1792620` supports those routes; no offset mismatch was found.
The preserved scheduler is fixed at 160 bytes per row. Native dtype10 uses
stride160/encoding0 and extent `align_up(rows*160,64)+4`; native dtype13 uses
stride90/encoding1 and extent `rows*90` (`0x178c531..0x178c570`). A 90-byte
owner needs a separate stride-aware schedule implementation; it must not be
admitted through the preserved fixed160 contract. A filename containing `w4b`
does not establish the currently selected metadata dtype.

## Expected utility and limits

The splice reaches the native copy-mode path that the ordinary interception
bypasses. Ordering mapped source pages may reduce repeated page access and
scatter locality costs while retaining native IDs, raw output, GPU unpack,
RMS, FC, and native workers. It may also add an ID-phase barrier and sorting
cost. If gather time is already hidden by prefetch, request latency may not
improve. Static evidence establishes the dataflow and scope, not a gain or a
ready-to-install interception. This artifact adds no gate series or diagnostics.
