# Qwen3.5-0.8B PLD raw-ID checkpoint audit — 2026-10-05

**Result: a useful static checkpoint/replay path exists, but exact rollback is not yet qualified.** The pinned XRT DLL snapshots the persistent linear-attention convolution history and recurrent state, restores both position counters, rebuilds decode sequences, and restores RoPE position. This is substantially more than a length rewind. It could avoid a 512-token clear/rebuild after each rejected proposal. However, attention rollback leaves rejected K/V rows beyond the saved prefix, and the next cache DMA reads a padded span. The host binary programs the restored logical length, but this audit does not establish that the NPU attention firmware excludes every stale padded row. An unconditional claim that rejection needs no rebuild would exceed the evidence.

This was one bounded, read-only source/installed-binary audit, started at 2026-10-05 22:06:04 UTC and completed within 30 minutes. No DLL was loaded into a process, no model was instantiated, no weights were downloaded, and no compiler, test, NPU, GPU, or WSL work ran. Server 28392 and backend 23824 were untouched. Only this note was written.

## Exact artifacts and evidence boundary

Installed artifact: `C:\AI\runtimes\flm-1.0.7-npu-probe\portable\qwen3_5vl_npu.dll`, 2,316,288 bytes, SHA-256 `d77388dcd21fcd7422005d0f780a044142d525e3afaafef3bcb9e980b8c18501`.

It is byte-identical to `C:\AI\src\FastFlowLM-zip\FastFlowLM-1.0.7\src\lib\xrt\qwen3_5vl_npu.dll`. The bundled HRX DLL is different: SHA-256 `a7e1f04934c97c2d5f396126e533a1169d529ad7165834dee7a6ff9fb25cc431`. Findings below apply to the pinned XRT binary; they do not qualify HRX, another FLM version, a Linux library, or an arbitrary Qwen runtime.

The source root is `C:\AI\src\FastFlowLM-zip\FastFlowLM-1.0.7\src`. Source pins:

| File under source root | SHA-256 |
| --- | --- |
| `include\causal_lm.hpp` | `05cd261d55aaf072a1b45b36e8898ee13d1999f11a2dc49b54d5fea95a90b2e1` |
| `include\models\qwen3_5vl\qwen3_5vl_npu.hpp` | `2ba9537713f49a37fce917e5389a6bb5ba226b22d642c54db575e9f6b0c4082e` |
| `include\buffer.hpp` | `4188058e28e2081f0ad0d1e16fcfaaa5846cf2b5ab9f91e58257cea31e5cbda7` |
| `include\AutoModel\automodel.hpp` | `94147174a607a574dec2329c3693d85080a08725367314ec7d243b01603fbf98` |
| `common\AutoModel\modeling_qwen3_5vl.cpp` | `4940569f37a557b8863498f9fadc5aab06659294c43a67f3c7b4c0f83e1559b8` |

The public Qwen header declares `Impl` without its implementation (`qwen3_5vl_npu.hpp:143–144`). Private behavior was therefore traced in the installed DLL with the local `llvm-objdump.exe` at `C:\AI\runtimes\qwen3-omni-native\Lib\site-packages\_rocm_sdk_core\lib\llvm\bin`. All binary addresses below are **RVAs**, relative to PE image base `0x180000000`.

Retained entry evidence is in [exports](../../server/.local/optimization9h-20261004/pld-flm-qwen35vl-exports-20261005.txt), [checkpoint head](../../server/.local/optimization9h-20261004/pld-flm-checkpoint-head-20261005.txt), and [restore head](../../server/.local/optimization9h-20261004/pld-flm-restore-head-20261005.txt). Later bounded function bodies can be reproduced directly from the pinned DLL, for example:

```powershell
& 'C:\AI\runtimes\qwen3-omni-native\Lib\site-packages\_rocm_sdk_core\lib\llvm\bin\llvm-objdump.exe' `
  -d --no-show-raw-insn --x86-asm-syntax=intel `
  --start-address=0x18005f930 --stop-address=0x180060120 `
  'C:\AI\runtimes\flm-1.0.7-npu-probe\portable\qwen3_5vl_npu.dll'
```

## What checkpoint and restore actually preserve

`Impl::checkpoint` is at `0x56150–0x56770`; its public wrapper at `0x56770` loads the `Impl*` from object offset `+0x30` and tail-calls it. `Impl::restore` is at `0x5f930–0x60120`, with the equivalent wrapper at `0x60120`.

The persistent per-layer buffers are the vector at `Impl+0x400`. Checkpoint host buffers are the vector at `Impl+0x160`; each buffer wrapper occupies `0x38` bytes. On first checkpoint, the implementation allocates host snapshot storage for every layer whose index modulo four is not three. Subsequent checkpoints overwrite the single saved point.

For each such linear layer, `0x56680–0x5671c` synchronizes the entire XRT BO from device, copies the persistent buffer's meaningful even byte length into the host snapshot, and synchronizes the BO back to device. At `0x56722–0x5673b`, it sets the snapshot flag at `+0x98`, saves current counter `+0x558` into `+0x9c`, and saves `+0x55c` into `+0xa0`. It returns the first saved counter.

The constructor's linear buffer size and `get_linear_cache_size` (`0x5ad80–0x5adb0`) use the same descriptor expression:

```text
2 * ((desc[0x2c] + desc[0x30] + desc[0x34]) * (desc[0x50] - 1)
     + 2 * desc[0x4c] * desc[0x48] * desc[0x40]) bytes
```

The helpers establish the state coverage: `_move_linear_kv_cache` (`0x61780`, arithmetic at `0x617ed–0x61801`) uses the first term for convolution history. `_move_s` (`0x619e0–0x61e30`, size arithmetic at `0x61a4d–0x61a5d`) uses the second portion after that history; its two DMA operations at `0x61b1c` and `0x61d19` exchange old and updated recurrent S state. `_gen_linear_sequence` (`0x60bb0–0x60d10`) calls the convolution, receive-cache, and S helpers. Snapshot copying covers this full persistent buffer, including both portions, rather than only attention K/V.

Restore returns `-1` when the snapshot flag is absent (`0x5fbb9`). With a snapshot, it synchronizes persistent buffers, copies saved meaningful bytes back for linear layers (`0x5ffcb–0x6000b`), and synchronizes the updated BOs to device. At `0x6000c8–0x6000e5`, it restores both counters and calls `set_context_length(saved_first, saved_second)`.

That setter (`0x60130–0x604d0`) writes both counters, regenerates context and per-layer decode sequences with `N = saved_first + 1`, resets/builds the XRT run list, and tail-calls `_set_rope_rms_weights` at `0x604c2 → 0x52070`. Thus replay position is reprogrammed along with persistent linear state.

| State | Observed coverage | Qualification |
| --- | --- | --- |
| Linear convolution history | Full meaningful persistent buffer copy out/in | Statically supported |
| Linear recurrent S | Same buffer, including S region | Statically supported |
| Two context/position counters | Saved and restored explicitly | Statically supported |
| Decode sequence, run list, RoPE position | Rebuilt by the restore setter | Statically supported |
| Full-attention committed K/V prefix | Retained in place; no prefix snapshot | Append-only transaction required |
| Rejected attention rows | Remain between saved and current lengths | Logical-length masking unresolved |
| Output logits | No checkpoint/restore copy | Caller must own a deep copy |
| Token history, last token, sampler/RNG | Outside engine snapshot | Caller must own or separately restore |
| Snapshot validity after request reset | Internal flag survives `clear_context` | Caller must track request/epoch validity |

## Attention suffix is the remaining exactness gate

The six full-attention layers are selected by `layer % 4 == 3` in the audited 24-layer configuration. Restore does not save/reload their prefix. It zeros their K and V suffixes at `0x600031–0x60008f`, using **current speculative counter `+0x558`**, before the saved counters are restored. Let `c` be the saved consumed-prefix length and `d` the current speculative length. Rows `[c,d)` are not erased by this path; zeroing starts at `d`.

The next replay token does overwrite the expected first append row. `_receive_kv_cache` (`0x62680`, arithmetic at `0x626a9–0x626b4`) computes `(N-1) * KV_width`. Restore's regenerated `N=c+1` therefore writes row `c`. `_gen_sequence` passes the same N to receive-cache and move-cache helpers (`0x60f67–0x60fc6`).

However, `_move_kv_cache` (`0x61300–0x61780`, arithmetic at `0x6132e–0x6133c`) rounds N upward to a multiple of sixteen before forming its DMA span. After replaying the first token, rows after `c` can still contain rejected drafts within that padded span. It is incorrect to claim that physical DMA reads only the restored prefix.

There is positive host-side evidence for the intended logical bound: `set_context_length` calls `gen_set_context` with exact `N=c+1`; `gen_set_context` (`0x588b0–0x58a70`) puts that N into NPU write commands at offsets `0xd000` and `0xd120` (`0x58936–0x5893d`, `0x589f1–0x589f8`). This audit did not establish the executed attention kernel/firmware's treatment of those values. Therefore **stale padded rows being excluded is a required, unproven condition**, not an observed exact rollback guarantee.

For example, a checkpoint at consumed length 509 followed by three consumed drafts leaves rows 509–511. Restore retains those rows. The first authoritative replay overwrites row 509 but may DMA all 512 rows. Correct logits depend on ignoring stale rows 510–511. A future authorized parity qualification must include such cases within and across sixteen-row boundaries; merely reading the restored length is insufficient.

## Caller-owned logits, history, and raw IDs

`Impl::forward(int)` (`0x56e40–0x57160`; wrapper `0x58470`) embeds the supplied ID, executes/waits for NPU layers, starts/waits for the LM head, synchronizes output from device, increments both counters, and sets the next position (`0x5708e–0x570a3`). Its return at `0x570ed–0x57135` is a shallow mapped buffer using engine output fields `+0x4d8/+0x4e0`. Later forward calls can overwrite those bytes.

The source agrees: `buffer.hpp:354` allocates owned host storage, `:362–364` declares a shallow copy constructor, `:465` returns the element count, and `:511–515` deep-copies bytes with `copy_from`. Saving the returned `buffer` object by ordinary copy is **not** a saved logits snapshot. A raw adapter needs owned next-token logits at the committed prefix, independent of the reusable output BO.

AutoModel separately holds `lm_engine`, sampler, `token_history`, `checkpoint_his`, `last_token`, and `total_tokens` (`automodel.hpp:154–182`). Its Qwen insertion code restores the engine and explicitly restores history/counters at `modeling_qwen3_5vl.cpp:294–308`. These are caller actions, not engine snapshot semantics. High-level generation also inserts think/newline tokens even with thinking disabled (`:329–376`), then forwards/samples through the text generation path. A raw committed-ID proposer must bypass those additions and own its exact token sequence, valid-ID policy, and sampler. Stateless greedy argmax is the simplest initial policy; stateful sampling would require its own rollback contract.

`clear_context` (`0x567d0–0x568a0`) sets both counters to zero and clears persistent buffers, but its complete body does not clear snapshot flag `+0x98`. The inspected setter also leaves that flag alone. An adapter must invalidate its own saved epoch on clear, rebase, request replacement, capacity change, or model replacement, and refuse restore until a fresh checkpoint exists for that epoch. A saved DLL snapshot can otherwise refer to a preceding request.

## Conditional transaction without a per-rejection prefix rebuild

Subject to attention-mask qualification and a matching instantiated caller ABI, the following contract uses the observed mechanism:

1. Consume the authoritative committed window into the proposer, including the current target token exactly once. Own-copy the logits for its next token, own the committed IDs/position, and checkpoint this fully consumed prefix.
2. Independently predict at most three IDs from the proposer's logits, feeding predicted IDs only as needed to obtain subsequent proposer logits. Do not checkpoint a speculative state over the committed snapshot.
3. Let the existing native target verifier determine the authoritative accepted IDs and its correction or bonus ID. The native gate/verifier/commit/replay remains authoritative.
4. Restore the proposer to the committed snapshot, then feed those authoritative output IDs in order, including the correction/bonus. Own-copy final logits, advance caller history only by those authoritative IDs, and take a fresh checkpoint for the next round.
5. If a round commits no IDs, restore and reuse the saved owned logits only while its request/epoch remains valid. Cancellation/reset cannot reuse a prior epoch's snapshot.

For three draft IDs, authoritative replay may contain up to four IDs. Reserve capacity for both proposal and replay before opening the transaction. Do not evict, overwrite, resize, or rebase the committed prefix while its snapshot is active. A rolling 512-token window still needs a separate eviction/rebase strategy; checkpoint does not remove that requirement. This audit does not establish a ready raw-ID service, a safe live reset/cancel integration, or an instantiated-object parity result.

The existing tokenizer finding is separate: [tokenizer compatibility audit](halogen-npu-pld-tokenizer-compatibility-20261005.md). The proposed package is pinned there to immutable commit `1d16e5eaa2508889fb88eb1bfab1921a30a1a466`, branch `flm_q4k_high_precision`. Tokenizer mapping does not qualify checkpoint state or the caller ABI.

## Windows ABI and version pins

The PE vtable at RVA `0x10c4e0` contains fifteen entries matching the exact `causal_lm.hpp` order. Zero-based slots/RVAs are:

```text
0 destructor 0x4e430       1 forward 0x58470       2 prefill 0x5ee10
3 set_context 0x604d0     4 load 0x5eda0          5 updateMax 0x60a30
6 clear 0x568a0           7 getK 0x5acb0          8 getV 0x5b0f0
9 getLength 0x5a940      10 checkpoint 0x56770   11 restore 0x60120
12 supportsSpec 0x7e80   13 speculate 0x60560    14 lastSpecPrime 0x33680
```

Checkpoint and restore are at vtable offsets `0x50` and `0x58`. The last three are the appended default speculative methods: false, empty IDs, and zero respectively. The final address has an exported alias to a generic synchronization method; that alias does not establish a different slot contract. Older Linux vtable-size assumptions in source comments cannot be substituted for this parsed Windows table. These defaults do not provide this model with a draft head.

The exported methods use Windows C++ ABI and return `buffer<biovault::bfloat16_t>`, not a plain C integer/array API. The raw Impl forward body receives `RCX=this`, `RDX=hidden result-buffer storage`, and `R8D=token ID`. A caller needs matching pinned headers/import library, XRT backend definitions, MSVC/STL and bf16/buffer layouts, and runtime dependencies. Correct static slot identification is not a loaded caller qualification. Neither a constructor call nor a cross-boundary buffer lifetime was tested here.

Imported XRT operations used above were mapped from the PE import table: BO sync IAT RVA `0x10a4f0`, BO size `0x10a5c8`, run-list reset/execute/wait/add `0x10a4f8/0x10a508/0x10a500/0x10a510`, and run wait/start/destructor `0x10a558/0x10a560/0x10a568`. `buffer.hpp:305–316` confirms device sync direction meanings.

## Costs and GPU/CPU applicability

Checkpoint is not free: each linear-layer BO is synchronized both ways and its meaningful state is copied to host. Restore synchronizes the persistent buffers, restores linear state, zeros attention suffixes, sends BOs back, rebuilds sequence/run state, and then requires authoritative replay forwards. BO sync uses `bo.size()` while memcpy uses meaningful bytes; `buffer.hpp:127–133` rounds device allocations to 1 MiB. Padding can therefore increase traffic. Restore work on full-attention buffers scales with allocated maximum context, not just the number of rejected IDs.

Using the candidate metadata shape (18 linear layers, 16 heads, 128-wide key/value state, convolution width 4, and q/k/v widths 2048), the constructor expression implies about 1,085,440 meaningful bytes per linear layer, or 19,537,920 bytes (18.63 MiB) across eighteen layers. This is a static shape estimate, not measured device residency, transfer timing, or memory usage of an instantiated model. No latency or speedup conclusion follows from it.

The transaction algorithm transfers to CPU or GPU proposers only if their engines preserve all mutable state: recurrent/convolution state as well as attention caches, positions, and caller sampler/history/logits. A context-length rewind alone does not restore Qwen3.5's linear state. CPU snapshots and GPU copies would have their own storage and synchronization costs, which were not measured. **This pinned FLM DLL is an NPU/XRT engine; it is not a GPU or CPU proposer backend.**

The next qualification boundary is concrete: matching Windows caller/object ABI and parity of restored/replayed logits against a fresh authoritative replay, including stale padded attention rows, reset epochs, zero accepted drafts, partial acceptance, and all accepted drafts plus bonus. Those checks were deliberately not executed in this source-only audit. Until they pass, retain the conservative rebuild/fallback behavior and treat checkpoint/replay as a candidate optimization, not an enabled exact path.
