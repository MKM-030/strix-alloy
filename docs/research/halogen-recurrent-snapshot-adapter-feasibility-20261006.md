# Separate drafter snapshot adapter: source cost and serving feasibility

**Verdict: both the matched llama.cpp snapshot operation and a concrete native no-hit ready-packet entry are structurally implementable. Neither is currently qualified for serving.** The no-hit entry can remove the old hit-only coverage blocker; it is not an impossible seam. The next bounded development is an offline no-packet/packet seam contract and exact stock-instruction replay check, before snapshot hardware or a connected serving producer. Do not build or run a disconnected recurrent adapter solely for component coverage. No serving Prefill, Decode or acceptance improvement follows from this audit.

The earlier [snapshot mechanism note](halogen-next-acceptance-mechanism-20261006.md) remains the starting point. This audit adds the exact selected-state size, matched Vulkan copy granularity, the actual growing bridge source, and a structural no-hit insertion candidate. It does not reopen the defeated prompt-key tests.

## Matched source and state size

The source root is `C:/AI/build/laurent-llamacpp-qwen4exp-rocmfpx`, revision `3466b48806f9fefe1162aa4053ffebcfcabe83aa`. The existing audit's matched DLL/header boundary and DLL SHA256 `ecca09d1880e55bc3c353e09ab3e6569ebf5f41bf5f4c8c6976305777408492e` apply; no DLL was loaded here.

The actually measured growing bridge is the retained worktree file `C:/Users/Marcel/.codex/worktrees/npu-ready-embedding/strix-alloy-clean/scripts/benchmarks/halogen_llama_raw_id_bridge/bridge.cpp`, SHA256 `621d40e6c83c9589a2281716c75968117aea99a66b99c33e92c9105bacfca32a`. Its `resolve_replay` at lines 342-376 supplies complete authoritative outputs; its policy header is `replay_policy.h`, SHA256 `61583b40f4d569017e78ae5f5c5125f98bb8cd4425503e97824bb76f4a05049f`. The main checkout's earlier bridge at `scripts/benchmarks/halogen_llama_raw_id_bridge/bridge.cpp` has only accepted-prefix `commit`, so it must not be mistaken for the measured complete-resolution implementation.

The [GGUF metadata receipt](halogen-gguf-proposer-token-map-20261006.json), independently rehashed to `6f0e8b9202a77d8bfbcfd2dc2458ccd50bace665ff8d5bf9293709d0ca3dc24b`, binds 24 Qwen3.5 layers, full attention every fourth layer, convolution width 4, inner size 2048, state size 128 and 16 groups. The matched sources establish:

- `src/models/qwen35.cpp:19-26`: 18 of those layers are recurrent; the other six have full attention.
- `src/llama-hparams.cpp:183-232`: R contains `(4-1) * (2048 + 2*16*128) = 18,432` elements; S contains `128*2048 = 262,144` elements per recurrent layer.
- `src/llama-model.cpp:2529-2544` and `src/llama-memory-hybrid.cpp:52-64`: recurrent tensors are F32; one requested sequence has one recurrent cell with `n_rs_seq=0`.
- `src/llama-memory-recurrent.cpp:897-956`: partial state carries R and S for each recurrent layer, with no attention K/V payload. This Qwen3.5 model has no PLE recurrent row.

Thus one selected-sequence snapshot has **20,201,472 payload bytes = 19.265625 MiB**, split into 36 tensor copies. The ON_DEVICE host record has **460 bytes**: 8 bytes of magic/sequence ID, 4 of cell count, 8 of cell position/sequence metadata, 8 of transposition/layer count, and 24 type/row-size bytes for each of 18 recurrent layers. These are source-derived sizes for the pinned geometry, not instantiated residency measurements. Device allocation may include backend alignment beyond the logical payload.

`PARTIAL_ONLY | ON_DEVICE` is flags value 3. The relevant public calls are `llama_state_seq_get_size_ext`, `llama_state_seq_get_data_ext`, and `llama_state_seq_set_data_ext`, with sequence 0 and identical flags. `src/llama-context.cpp:2555-2576,3058-3127` excludes tensor payload from the ON_DEVICE byte-count record; the adapter must not mistake a successful 460-byte return for a 460-byte device snapshot.

## Copy cost and lifetime

`src/llama-context.cpp:2735-2828` groups saved tensors by their source backend buffer type, creates corresponding views/copies, and stores them in context-owned `mem_storage[seq_id]`. Stable shape/count/size/source views reuse the existing device buffer on later saves. Host view/context bookkeeping is still rebuilt. `src/llama-context.cpp:2867-2920` copies the saved tensors back on restore. Saving a second state for the same sequence overwrites the first device snapshot, as the header explicitly documents.

The selected bridge requests full Vulkan layer offload and offloaded K/Q/V. For those Vulkan recurrent buffers, `ggml/src/ggml-backend.cpp:487-509` calls the buffer copy method; `ggml/src/ggml-vulkan/ggml-vulkan.cpp:16889-16905` routes it to `ggml_vk_buffer_copy`. The same-device body at lines 9175-9188 creates a temporary transfer context, submits one buffer copy, waits its fence, resets the fence and cleans command pools. **Each save and each restore therefore executes 36 separately submitted, blocking tensor copies in this matched implementation.** ON_DEVICE avoids a host payload round trip; it does not batch the 36 transfers into one submission. This is a meaningful latency uncertainty before any serving contention.

The public save/restore wrappers synchronize the context before the operation (`src/llama-context.cpp:4172-4180`). Copy work happens in the local I/O object's destruction before the operation returns. Both wrapper synchronization and all copy/allocation work belong to candidate cost. A size query alone does not snapshot or synchronize the context.

There is no public snapshot-release operation in this matched API. Clearing the bridge's metadata vector or calling `llama_memory_clear` retires eligibility, but does not free the context's `mem_storage` buffers. With one sequence and fixed geometry this is one bounded reusable slot; it remains resident until context destruction. A context reset/rebase must invalidate the adapter record even when the storage remains allocated.

Normal serialization errors return zero, but the device path also has assertions/abort conditions for missing or mismatched storage. For example, the ON_DEVICE source-sequence lookup occurs before the local restore try block at `src/llama-context.cpp:3092-3107`, and restore-buffer mismatch aborts at lines 2907-2911. The adapter must never accept arbitrary serialized bytes, restore a retired record, or attempt to recover a process abort by continuing the same transaction. Process ownership remains a separate Root requirement.

## Smallest default-off adapter design

If a useful native consumer is established, the minimum bridge addition is an explicitly selected `recurrent_snapshot` resolution mode, default off, within the existing synchronous one-context/one-pending-round bridge. It retains sequence 0, context capacity 1024, window limit 512, `n_rs_seq=0`, greedy IDs in `[0,248069]`, and the existing native opening restriction. It does not change target arithmetic or weights.

The new record needs only owned metadata bytes, saved committed length, bridge epoch, context identity and an active marker. The existing committed `OwnedLogits` already owns its full 248,320-element F32 row; retain it until resolution rather than copying a borrowed llama logits pointer. The snapshot API does not save output logits, IDs or caller history.

1. At `propose`, after checking the committed memory position and before the first speculative scalar decode, save exactly once when draft count exceeds one. Query the metadata extent, allocate the exact bounded host record, and require the save return to equal that extent. Record the current epoch and committed length L. Do not overwrite this device slot while the round remains pending. Count one consumes no model input and needs no snapshot.
2. Proposal generation stays causal and records its IDs before any evaluation label or native outcome is supplied. Count three still performs two scalar speculative forwards. A new save must not occur between those calls.
3. On authoritative resolution, retain the existing append eligibility: the permitted consumed proposal prefix must exactly match authoritative outputs, opening reuse must be permitted, and no window eviction may occur. Only the new authoritative suffix is forwarded. Use scalar forwards for that suffix; the growing source currently calls `decode(suffix)` once, which can become a different arithmetic path when the suffix contains more than one ID.
4. Otherwise, restore the same record and require the full metadata return count. Restore recurrence **before** `llama_memory_seq_rm(memory, 0, L, -1)`, and require removal to succeed. `src/llama-memory-recurrent.cpp:161-245` rejects suffix rollback without a stored recurrent boundary. After restore its current position is L-1, outside the removed interval, so the recurrent part is retained and the attention part can remove the speculative suffix (`src/llama-memory-hybrid.cpp:143-149`).
5. Check the resulting public sequence position only after both operations. The hybrid public maximum is the minimum of attention/recurrent maxima (`src/llama-memory-hybrid.cpp:177-180`), so the position check alone is not proof of attention cleanup; the exact output oracle below is still required. Replay every authoritative output, including correction/bonus, with scalar positions `L+i`. For zero outputs, retain the already owned committed row. Move the saved row/record into local ownership before calling existing `retire()`, which otherwise clears IDs/logits and increments the epoch.
6. Publish the new committed IDs and owned final row only after complete replay succeeds; then retire the snapshot record. Clear, rebase, window eviction, context replacement and exceptions retire it too. Recoverable snapshot failures decline the optional feed and charge any actual conservative recovery. A clear/parallel-prefill fallback is not silently accepted as exact incremental parity. A failed finite qualifier stops; a future native consumer retains its complete stock path.

The retained finite history ends at 293, so it requires no window eviction. A later rolling-window implementation needs its own rebase arithmetic contract. Merely setting `n_rs_seq=2` does not provide two-call rollback: the matched delta-net code records snapshots from the current microbatch, as already established in the earlier note.

## Exact incremental oracle and budget

The correct control begins with the identical 256-ID prefill, batch/ubatch settings, model, backend and raw greedy range. It then consumes only the authoritative output stream through **the same scalar incremental forwards** and never takes speculative mutations. Compare the initial owned F32 row and the complete 248,320-element row after each candidate resolution byte-for-byte against this control, with equal IDs and positions. A matching greedy ID or approximate row is insufficient. This is bounded numerical behavior evidence, not proof of every cache byte for arbitrary future inputs.

Do not compare the snapshot candidate to fresh parallel-prefill states: the retained bridge already has a parallel-prefill/incremental discrepancy. Do not retain old predictor-match counts when the resolution state path changes. Labels remain in the evaluator until proposals have been recorded; they enter each bridge only as authoritative outcomes afterward. Verification/control work and artifact I/O are recorded separately from candidate costs; candidate synchronization, owned-row copy and argmax remain inside candidate costs.

The old fifteen-round screen cost 514.1936 ms including its initial seed, against an optimistic cross-cohort allowance of 476.3834518 ms. Holding the old proposal costs and six successful append resolutions fixed leaves **266.9236518 ms** for fifteen saves, nine restores/removals and nineteen scalar authoritative replays on formerly rebuilt rounds. Those are reference counts from the old predictions, not predicted counts or latency for a new state path.

At those reference counts, save/restore alone means **864 blocking Vulkan copy submissions**, 484,835,328 logical copied bytes (462.375 MiB), and at least 969,670,656 bytes of payload reads plus writes (924.75 MiB), before driver overhead, replay, transport or target contention. Initial snapshot allocation and all final-round work must also be priced. There is no measured copy latency here and no defensible speed prediction from bandwidth alone.

## Native no-hit structural seam

The existing private entry `0x172e95f` is reached after a lookup hit and native stock-vector copy. Its existing selector in `scripts/benchmarks/halogen_pld_proposal_wire.py:197-221` caps replacement at `min(len(stock),3,native_allowance)`. With no stock IDs it declines. The retained exact-three opportunities are zero, so faster resolution cannot create consumption opportunities in that currently scoped interface.

A distinct structural no-hit candidate exists at **RVA `0x172d3bd`** in the same decoder FDE `0x171c260..0x17305ed`. Retained host instructions are:

```text
0x172d3bd  lea rax,[rbp+0x1e8]
0x172d3c4  mov [rsp+0x38],rax
0x172d3c9  xor r13d,r13d
0x172d3cc  mov r12d,r13d
```

This initializes a zero proposal count and joins the normal continuation. The first instruction occupies seven bytes, `[0x172d3bd,0x172d3c4)`. A complete direct-target scan of the retained disassembly found eight encoded incoming edges: `0x172d38e`, `0x172d39a`, `0x172dcd7`, `0x172dcf9`, `0x172dd0e`, `0x172dd31`, `0x172dda6`, and `0x172ddc9`. Insufficient host-context length also falls through from `0x172d3b7`. No encoded direct target enters the seven-byte instruction interior. This does not exclude computed entries or qualify a trampoline.

`0x172d32f..0x172d3b7` has already gated positive PLD policy, absent sampler and no suppression, and computed the native allowance in R9D:

`B = min(model[+0x14]-1, request[+0xf0], model[+0xf0]-P-1, Q-1)`.

A separately qualified no-hit ready-packet shim could decline zero/negative B, absent policy width, insufficient context, constraints, unknown epochs and unready packets; validate an independent proposal of `n <= min(3,B)`; copy its IDs into original RSP `+0x360`; deliberately set saved RBX=n; and resume through `0x172e95f`. That existing route preserves constraint processing, the native first-head equality at `0x172d41e/0x172d425`, target verification at `0x172d618`, accepted-prefix commit at `0x172d80a`, output stop handling and ordinary native replay. A declined packet replays the original instructions, retains zero R13D and follows stock control flow.

This is an explicit algorithm/interface scope extension: on a no-hit round `stock_n=0`, so the old hit-only selector and its tests cannot authorize a positive count. The allowance/reservation, machine-state and lifecycle proof must belong to the new shim. The scope also retains sampler/constraint exclusions and the native opening gate; manufacturing its first ID from native target predictions is not an independent prediction.

**No current implementation supplies this interface.** The producer is a Windows Vulkan child, while the engine is a Linux/SysV process in WSL; packet transport, ready publication and the consumer's fixed-storage, nonblocking implementation are absent. The offline Python selector allocates/locks and cannot simply be called from an interior native detour. The existing [lifecycle audit](halogen-npu-pld-lifecycle-ownership-20261005.md) still leaves in-place reset/worker ownership and complete XSAVE/unwind/installation mechanics unqualified. No authoritative-outcome callback or sufficiently early committed-prefix publication has been qualified to resolve the drafter and have a packet ready at this next no-hit boundary. If the producer is late, this scope must immediately use stock behavior; waiting would add the producer to target latency.

Thus there is a concrete **static** insertion candidate, but no ready native callback to attach the snapshot adapter to today. Source proof of a writable proposal buffer does not establish useful readiness, accepted IDs or complete serving time.

## Next bounded development: offline no-hit seam contract

Make one default-off, finite source implementation for the new no-hit entry, for example `scripts/benchmarks/halogen_pld_nohit/seam_contract.cpp`, with a synthetic CPU contract harness. This is native-interface development, rather than another disconnected prediction pass. Do not modify the existing hit-only selector or reinterpret its stock-count cap. No live detour, profile, transport or drafter launch is part of this step.

The caller supplies immutable synthetic request/model fields, the original outer-frame base, an already-owned ready packet, and explicit birth/round/prefix truth. The no-hit consumer validates into fixed bounded scratch and returns either the exact original continuation or a bounded replacement. It neither owns a model runtime nor waits for one. Missing packets, disabled mode and every decline must execute the seven displaced bytes unchanged and resume at `0x172d3c4`; the native store/XOR/join then preserves the stock zero-proposal path. A successful packet may change only the `4*n` proposal bytes at original RSP `+0x360` and the deliberately saved RBX count before routing to `0x172e95f`.

Its offline oracle should cover:

1. **Exact no-packet replay:** pin the first instruction bytes `48 8d 85 e8 01 00 00`, its seven-byte boundary, all eight encoded incoming edges and the fallthrough. Check that replay gives RAX=`RBP+0x1e8`, preserves every other live register/vector image and RFLAGS at the resume point, and touches no stack memory before the original next instruction. Continue the retained store/XOR/MOV/TEST sequence in the semantic harness and compare stock zero-count control flow. XOR's architecturally undefined flag bits are not invented as meaningful equality requirements.
2. **Stock decline:** disabled, no packet, incomplete publication, zero/negative B, invalid width/context extent, constraints, unknown birth/reset state, reused round, mismatched prefix/model/tokenizer, malformed framing and out-of-vocabulary IDs all preserve the stock continuation and all native proposal bytes. Validate the whole packet before any write, including a failure in its last field.
3. **Successful bounded packet:** reuse the existing documented immutable framing (192-byte header, `4*n` IDs, 32-byte HMAC; total 228-236 bytes) without exposing native addresses. Require exact caller binding, one-shot consumption and `1 <= n <= min(3,B)` from caller-owned native allowance truth. Check canaries around the proposal destination, saved stack/register images, and request/constraint/target-prediction fields. Do not enlarge verification reservations or copy a manufactured native opening token.
4. **Branch continuation:** prove a decline resumes at `0x172d3c4`; a success reaches `0x172e95f` and retains the existing constraint/opening/target verifier route. Do not jump directly to target verification or bypass the opening comparison. The fixed-storage selector cannot use the Python selector's lock/allocation behavior inside a detour.

Synthetic semantic checks can establish packet/buffer and stock instruction behavior without loading the engine. They do not by themselves qualify the actual shim's full XSAVE preservation, unwind/signal behavior, atomic installation, indirect-entry exclusion or concurrent lifetime safety. Those remain separate source/implementation proofs before any runtime installation.

Keep transport absent until explicitly designed and qualified. The consumer must never start a drafter, wait for a reply, retry, or introduce an always-running producer as a side effect. Later producer startup and proposal scheduling need an explicit default-off policy and complete readiness costs. A resolved authoritative-output handoff is required before a useful snapshot hardware qualifier, so this bounded seam work has a direct path toward serving feasibility rather than assuming an unseen transport layer.

## Placement and next decision

| Placement | Applicability and decision |
|---|---|
| GPU/Vulkan | The matched API and R/S copy path exist; it has the best retained proposer cost. The additional 19.265625 MiB slot and 36-copy fences share the GPU/DDR with Halogen in any integration. No copy or contention gain is measured. Keep default off pending a usable native consumer and exact incremental qualification. |
| CPU | The same APIs can keep recurrent data in CPU buffers, avoiding Vulkan submissions but adding CPU memory-copy work. Prior proposal-plus-one-append cost already exceeds the optimistic allowance; recurrent rollback alone gives no basis to rerun that route. |
| NPU/FLM | This llama.cpp device snapshot proof does not transfer to the XRT engine. Its checkpoint audit has different BO synchronization, padded-attention restore and caller-ABI requirements; prior proposal/append cost also fails the allowance. No new NPU implementation or run is justified here. |

The serving decision remains off. First implement and verify the bounded offline no-hit seam contract above. It can remove the structural zero-hit restriction while preserving a stock-identical absent-packet path. Then qualify reset/epoch ownership, authoritative-output handoff and ready publication before any snapshot hardware qualifier. If those prove usable, the snapshot adapter can remove the old realization's nine prefix rebuilds, and one joint prediction/complete-resolution qualifier can evaluate actual costs and changed predictions. The 36-copy fences are a potential bottleneck, not evidence that the unmeasured snapshot path is slower. Any later adoption must compare complete matched target time per actually committed token, including all fallbacks, retained native work, transport and contention. Snapshotting directly supplies no target Prefill improvement or predictor training.

## Additional source pins and scope

| File under matched llama.cpp source root | SHA256 |
|---|---|
| `src/llama-hparams.cpp` | `2195a283715e6ec0ab7cf6f2e109622e3a79bdd25a0ef620b89813c42c97eeaa` |
| `src/models/qwen35.cpp` | `552b8c0d671a540c455f11042e1438e6d573e3de3486515be6ce8a8e41da0acc` |
| `src/llama-model.cpp` | `addfc4cfa439a0114c780d0b7ba93edde13ca668000843587d116fc854369321` |
| `ggml/src/ggml-backend.cpp` | `76e1b42abecb92958ddaa2499616daaadfe48b067a8360d5f2d722028d704d0c` |
| `ggml/src/ggml-vulkan/ggml-vulkan.cpp` | `c2a2b15bedae21a91e5bbe683416155fd25ed2161612368b09b2947f89d3045b` |

The context/recurrent/hybrid source hashes independently match the earlier mechanism note. The retained ELF and disassembly pins remain `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` and `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` from the prior independent review.

Only this new design document was created. Actions were local PowerShell source/document reads, hashing, and standard-library CPU parsing/arithmetic of retained receipts and disassembly. No DLL/model runtime, compiler, GPU/NPU, WSL, serving request, process/lifecycle action, production/seal edit, staging or commit occurred. No adapter code or disconnected prototype was created.
