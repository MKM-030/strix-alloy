# Frozen full-device snapshot source review — 2026-10-06

## Verdict and scope

No source blocker was found in the frozen full-device snapshot additions or the selected-mode checker. This is a restricted source review of flags, snapshot ownership, clear/restore ordering, scalar authoritative replay, measured cost accounting, and retained partial-receipt compatibility. It does not establish full-mode state parity, GPU residency or transfer extents, serving acceptance, performance gain, or lifecycle restoration.

The reviewer read and compared source and retained artifacts only. The reviewer did not compile, execute the bridge or checker, load a model or DLL, use hardware or WSL, alter lifecycle state, install a hook, or use Git. The only new file written for this review is this report; frozen implementation, checker, README, and previous evidence remain unchanged.

## Frozen inputs

Paths below are relative to this bridge directory unless otherwise specified. SHA-256 pins identify the reviewed bytes.

| Input | SHA-256 |
| --- | --- |
| `bridge.cpp` | `8fce4c04b2eeea73f354ee2591c765bfaf610e789b1275883b5d21e7de0515aa` |
| `check_snapshot_screen.py` | `a8f4b0602e22b6830c4805a02bcddb11032616033d4e20bea37ccd674057d893` |
| `README.md` | `fbdad68d034ca8128754ea8729d9faaba0dbbfd4183c1f50c97af32a8fd3303a` |
| Retained measured partial `bridge.cpp` | `04b76e99569ed9dfa1249e8ac0c20c72ad4ced912d012f6477073dbcb5dd57d7` |
| Retained measured partial `check_snapshot_screen.py` | `35fb16aaf60280b0604a843febaa015e4dbce20e064b502117927f726fd210aa` |

The retained measured partial source directory is `C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/snapshot-partial-source-before-full-20261006`. A read-only unified comparison confirmed that the full addition selects flags and changes clear/restore behavior while preserving the existing partial dispatch and scalar snapshot replay policy.

The matched native source is `C:/AI/build/laurent-llamacpp-qwen4exp-rocmfpx`, revision `3466b48806f9fefe1162aa4053ffebcfcabe83aa`.

| Matched native file | SHA-256 |
| --- | --- |
| `src/llama-context.cpp` | `daab90ea408491c7d0f4b6e029f81ec8fcf81a8a2577475b0a300136ee0468dd` |
| `src/llama-memory-hybrid.cpp` | `b2b193c4a412a91b1fe15a3c239d3b2664b5208ff49d6dba244ff8fec0880f92` |
| `src/llama-memory-recurrent.cpp` | `35903c832ba321aad3fca8b2adf2d481f6ba41196478c6c8f248ffe2bd7d9d51` |
| `src/llama-kv-cache.cpp` | `e15fedb27d8a4cd6ca3bbc995fdbb9aa75e8f2c03e4522cf999fca228c0b29e7` |

## Mechanism and ownership findings

1. **Mode selection is explicit and default off.** `bridge.cpp:111–119` validates both optional selectors as booleans and rejects their simultaneous selection. The constructor also rejects both (`257–265`). Full mode uses only `LLAMA_STATE_SEQ_FLAGS_ON_DEVICE`, value `2`; partial uses `PARTIAL_ONLY | ON_DEVICE`, value `3`. A static assertion pins the public flag values. The manifest records both selectors, selected mode, and flags (`660–685`). The checker defaults to partial and requires an explicit full selector plus full mode/flags for `--mode full` (`33–48`).

2. **Private clear preserves the device snapshot storage in this matched source.** Context creation requests and verifies one sequence (`bridge.cpp:631–659`). Full rollback calls the synchronized private `llama_memory_clear(memory, true)` before state restoration (`454–484`, `504–510`). In the matched native source, `llama-context.cpp:3991–3996` delegates clear only to the memory object; hybrid clear forwards to attention and recurrent memory (`llama-memory-hybrid.cpp:138–140`). Attention clear resets its cells/heads and optionally its own `ctxs_bufs` (`llama-kv-cache.cpp:381–390`); recurrent clear resets its cell state and optionally its own `ctxs_bufs` (`llama-memory-recurrent.cpp:141–159`). These paths do not clear the context's separate `mem_storage`.

   ON_DEVICE save writes through `mem_storage[seq_id]` (`llama-context.cpp:3071–3083`), and restoration looks up the saved source-sequence storage (`3090–3127`). Thus the private memory clear does not erase the saved device buffers needed by the subsequent restore. The public header documents invalidation by the next save for the same sequence (`include/llama.h:947–952`). Clearing the bridge's host metadata does not release those context-owned buffers; their lifetime extends to replacement by another save or context destruction.

3. **Full restoration includes both memory components.** With PARTIAL_ONLY absent, the hybrid serializer restores attention and recurrent memory (`llama-memory-hybrid.cpp:190–201`). The bridge's full branch clears, restores with flags `2`, synchronizes, and checks native position `L - 1`. It does not execute partial-mode attention suffix removal (`bridge.cpp:466–483`). Partial mode retains recurrence restoration followed by suffix removal.

4. **A snapshot belongs to exactly one pending committed boundary.** Save occurs before any speculative input when the proposal count exceeds one (`299–319`); save checks the current native position, exact metadata byte count, and the finite host metadata bound, then records epoch and committed length (`429–452`). Restore requires pending epoch, current epoch, saved epoch, and saved length to agree (`454–456`). The metadata and original owned committed row move to local owners before retirement; retirement clears proposal/feed state and advances the epoch (`425–427`, `457–461`). No further save is reachable while that proposal remains pending. Full checker receipts bind flags, sequence `0`, epoch, length, metadata bytes, clear ordering, and restored position (`67–91`).

5. **Published rows remain owned, and authoritative updates remain scalar in snapshot mode.** Every decode copies the complete native F32 row before another engine call (`516–559`). Append resolution moves the appropriate committed or speculative owned row before retirement (`321–346`, `360–389`). Snapshot-mode append replay decodes each suffix ID separately; restore replay also decodes one ID at a time (`379–381`, `485–486`). An empty restore resolution retains the original committed owned row. The new row/history are published only after successful restoration and replay. Count-one proposals do not consume native state and need no snapshot. Rebase/window-shift and failed-save paths retain the existing actual rebuild behavior outside the finite snapshot screen.

6. **Failures cannot silently qualify as snapshot success.** Save failure is recorded and removes the host snapshot. Restore failure records fallback and performs the actual rebuild (`447–451`, `492–495`). The checker rejects measured save failures, restore fallbacks, clear/rebuild calls, prefills, and calls from the other snapshot mode (`56–64`).

## Cost accounting and checker findings

The successful full path has separate clear and restore timers: `clear_engine` records its synchronized clear duration, and `restore_started` begins after clear returns (`bridge.cpp:466–484`, `504–510`). Decode dispatch, synchronization, logits readiness, owned row copy, and greedy scan have successive timers (`531–557`). They do not overlap on the accepted successful path. Failed restore wrapper timing can encompass prior work, but failed/fallback receipts are rejected before component qualification.

Command wall time covers the complete bridge operation, including snapshot save, private clear, restoration, synchronization, scalar replay, ownership work, and command overhead (`bridge.cpp:687–718`). Diagnostic F32 writes occur afterward and have a separate field (`720–738`). The checker validates finite nonnegative component costs and checks that their sum fits inside command wall time (`12–30`). It charges the initial measured seed prefill once plus every proposal and resolution command once (`96–102`), without adding native subcomponent durations again.

The charged component metric is therefore seed plus all 15 measured rounds. Startup/model loading, the earlier setup commands, diagnostic writes, manifest writing, and lifecycle work require their separate runtime receipts. The component metric alone is not total experiment wall time. The 64 MiB bound applies to host metadata; it does not measure or cap device snapshot allocation extents.

The selected-mode checker requires exactly 15 consecutive proposal/resolution pairs, one save first in every proposal, scalar measured updates, at least one exercised restoration, and full-mode clear/restore ordering. Its optional independent scalar control requires 37 scalar authoritative forwards, matching recorded source/model/backend/context/batch/thread/offload bindings, the same initial committed history and exact initial 993,280-byte F32 row, and exact history plus complete F32 row equality after every resolution (`check_snapshot_screen.py:49–137`). Without control, the checker returns `state_parity_qualified: false`.

## Retained partial evidence compatibility

Read-only inspection of the retained `vulkan-output.json` and `control-output.json` in `C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/snapshot-gpu-component-1a07c0ad3795401799c1accc7c7fe382` confirmed:

- The candidate selects partial mode; the three newly introduced manifest fields are absent and receive the intended partial defaults.
- All strengthened candidate/control binding fields exist and match.
- The retained candidate has 30 measured commands and the control has 37 measured scalar updates.
- Every cost field required by the new accounting logic exists and is finite and nonnegative; every recorded native cost sum fits its command wall time.
- Seed, proposal, and resolution wall times sum to `32.6397 + 164.3395 + 129.18 = 326.1592 ms`. The checker’s seed/measured diagnostic-write scope is `33.7666 ms`; the retained all-command write total uses a broader scope.

This schema compatibility does not change the retained partial result. The initial row and rounds 0 and 1 were exact; the first exact-row failure was round 2. The unchanged exact comparison still disqualifies that retained run. Greedy agreement does not replace complete row equality, and the full-mode additions do not establish a cause for the partial failure.

## Required evidence before a full-mode result can qualify

The parent must bind the built executable and native DLL bundle to these frozen source pins and use the same built output for the full candidate and independent scalar control. A full-mode result needs the exact initial and all 15 post-resolution rows to pass, including exercised rejected-input restoration with clear/restore receipts, complete measured costs, and the separately retained runtime/lifecycle evidence. Graph or scheduler state outside the serialized memory, physical residency, allocation extents, and any performance effect remain runtime questions. This source verdict provides no serving or pilot qualification.
