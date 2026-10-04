# Halogen 0.16.2 full MTP head: residual and state ABI

The complete MTP head has a concrete four-stream residual input, token/position input, and persistent head history. Native speculative verification skips automatic head replay; eligible ordinary target forward and an explicit accepted-prefix replay in the greedy controller both call the head. A full NPU head can retain native target verification, but needs its own persistent state transaction and bootstrap/cache interfaces. The contract below is a source-derived integration proposal; cache ownership and exact native head rollback remain unproved.

## Binary pin and provenance

- Engine: `backends/halogen-wsl2-0.16.2/.local/flash_serve` (WSL retained copy `/home/revn/halogen-re/flash_serve0162`).
- SHA-256: `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`; size 26,052,768 bytes.
- Full head forward: RVA `0x17db310..0x17dc289`; function SHA-256 `132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20`.
- RVAs below are from the stripped host ELF; `.text` VA minus file offset is `0x1000`. Role descriptions are inferred from instructions and registered kernel signatures, not exported function names.
- Source evidence: retained `server/.local/optimization9h-20261004/mtp-route-static-20261004/{host-text-disassembly.txt,host-frames.txt,kernel-registrations.json}` and `scripts/benchmarks/halogen0162_mtp_tap.c`. This documentation task performed no capture, compilation, tests, model/checkpoint read, provider change, or hardware action. The first root-owned state attempt failed before engine startup and obtained zero samples; its [negative receipt scope](halogen-mtp-state-tap-source-review-20261004.md#root-owned-failed-attempt-and-post-exit-scope) remains intact. A separate successful metadata capture below supplies eight runtime entry records. The existing full-event tap remains unchanged.

`*(model+offset)` means a pointer stored in a host object; the pointed-to tensor is on the device. Widths marked raw u16 establish storage, not a decoded numeric format.

## Residual, token, and position seam

The observed ABI of `0x17db310` is `int32_t(model, const int32_t *tokens, int32_t count, int32_t position)`.

| Input/state | Host field and device extent | Width/use evidence |
|---|---|---|
| Four-stream target residual | `*(model+0x6d0)`; 20,480 bytes/token (`0x5000`), `4 x 2560` raw u16 | Target forward publishes its last row from `+0x6d0 + (count-1)*0x5000`; copy at `0x17ddf68`. This is distinct from the 5120-byte MLP input at `*(model+0x6e8)`. |
| Accepted residual snapshot | `*(model+0x50)`; 20,480 bytes; `int32 model+0x58` position tag | Target forward `0x17dd020` runs layers 0..47, then D2D-copies the last residual row to `+0x50` and tags it from `model+0x220` (`0x17ddf32..0x17ddf7b`). Helper `0x17dc990` publishes the same seam. |
| Head residual continuation | `*(model+0x6d0)`; `int32 model+0x5c` produced row count | Full head leaves produced residual rows in `+0x6d0` and sets `+0x5c=count` at `0x17dbbf8`. For offset >0 with at least two produced rows, wrapper `0x17dcde0` copies the last head-produced residual row into row zero (`0x17dce51`). |
| Token IDs | ABI host `int32[count]` -> host staging `*(model+0x6b0)` -> device `*(model+0x730)` | Host copy `0x17db364`; H2D copy `0x17db382`, exactly `count*4` bytes on stream 0. |
| Token embedding | Table `*(model+0x4f0)` -> `*(model+0x6c8)`; 5120 bytes/token, 2560 raw u16 | Registered `k_embed_gather` identity `0x18d5b40`, launch `0x17db449`. Embedding projection descriptor `model+0x908` maps `+0x6c8` -> `+0xb00`, dimensions 2560 x2560 (`0x17db543`). |
| Residual/embedding preparation | Norm pointers `*(model+0xae8)` and `*(model+0xaf0)`; residual projection descriptor `model+0x980` | Full forward normalizes/projects the embedding and incoming residual, then seeds/adds into `+0x6d0` before layer48. Globals `0x18db210/228/230` are transient scratch, not independent persistent inputs. |
| Position | ABI `int32 position`; current position `int32 model+0x220` | Original position saved at `0x17dbb9a`, ABI position installed at `0x17dbbad`, restored at `0x17dbbe6`. Wrapper supplies `model+0x220 + offset - 1` (`0x17dcf44`). |

The wrapper restores snapshot `+0x50` -> residual `+0x6d0` at `0x17dcf23` when the snapshot tag matches the current position. Accepted-prefix helper `0x17def00` sets `model+0x220 = model+0x1c + accepted_count`, copies residual row `accepted_count-1` to the snapshot at `0x17def6e`, and retags it at `0x17def81` when MTP and snapshot storage are enabled. Ordinary target-forward snapshot publication is additionally gated by native path flags; it is not an unconditional end-of-forward contract.

## Native controller, wrapper, and replay lifecycle

The greedy controller at `0x173b630` obtains the first proposal through helper `0x17dcb40` or wrapper `0x17dcde0`, then generates later proposals through the wrapper with offsets1 through `depth-1`. It verifies target inputs `[current_token, draft1, ..., draft_depth]` through `0x17dcfc0` (`0x173b6f6`). If `a` drafts match the target predictions in `model+0x20`, it calls accepted-prefix helper `0x17def00` with **`k=a+1` target input rows**, not `a` matched drafts (`0x173b764`). First mismatch gives `k=1`; all drafts matched gives `k=depth+1`. Output contains the `a` matched drafts plus target prediction/correction `model+0x20[a]`.

Verification wrapper `0x17dcfc0` sets `byte model[0]=1` at `0x17dcfe4`, calls target forward `0x17dd020`, then clears the byte at `0x17dcff4`. Target forward tests bit0 at `0x17ddfa1` and jumps to `0x17de257` when set, **past** the automatic head call at `0x17de231`. Verification therefore leaves target residual rows available in `model+0x6d0` for the accepted-prefix snapshot.

The greedy controller subsequently performs explicit accepted-prefix head replay on its normal continuation path. After target commit `0x173b764`, it calls helper `0x17dcc90` at `0x173bb5e` with `count=k=a+1` and shifted tokens `[matched_drafts..., target_correction]` from stack `+0x30`. The helper restores the valid same-slot 768-byte carry snapshot, snapshots the last accepted target residual row, and calls the full head at `0x17dcd4f` with those target residual rows, `count=k`, and `position=current_position-k` (the verification base). It caches the returned first proposal, last shifted token and current position. Output-stop and adaptive speculation-suppression paths may skip replay. The [accepted-prefix replay receipt](halogen-mtp-accepted-prefix-replay-20261004.md) supplies the exact argument chain and a minimal CPU-only private cache schedule check. Skipping automatic replay inside verification does not mean the controller omits this explicit replay.

Eligible ordinary target forward can run automatic head replay. Besides MTP enabled, it requires `model+0x901 !=0`, `model[0]` bit0 clear, `model+0xa4 ==0`, and global `0x18dcd28 !=0` (`0x17ddf88..0x17ddfc1`). It creates shifted tokens `[input_tokens[1:], last_target_prediction]`, restores saved carry and invalidates its position tag, and calls the full head with target residual rows, `count=target_row_count`, and `position=current_position-count` (`0x17de21c..0x17de231`). The returned proposal is cached at `+0x40`, its input token at `+0x44`, and current target position at `+0x48` (`0x17de236..0x17de249`). A persistent full NPU head must handle this multirow/bootstrap path or use an explicit state resynchronization contract; count1-only interception is insufficient.

Wrapper `0x17dcde0` has effective ABI `int32(model, token, offset, restore_flag_in_CL)` and requires MTP byte `model+0x900 ==1`. For `offset==0 && restore==0`, it can return a cached first draft when `+0x40 >=0`, `+0x44 ==token`, and `+0x48 ==current_position`, without a full-head call. Positive offsets invoke carry-save helper `0x17dca10` and use the last produced head residual as continuation. The offset0 restore path restores the 768-byte carry snapshot when its slot is valid, invalidates tag `+0x70`, and restores the target residual snapshot when `+0x58` matches current position. Its full-head call uses one scalar token, `count=1`, and `position=current_position+offset-1` (`0x17dcf44`, return RVA `0x17dcf49`).

The full head temporarily installs its ABI position at `model+0x220`, changes the execution flags, dispatches layer48 at `0x17dbbe1`, then restores outer position/flags at `0x17dbbe6..0x17dbbf1`. It publishes continuation row count and final-row vocabulary projection/token selection. Native head-logits cache tags are `+0x60=slot` and `+0x64=position+count` (`0x17dc0f0..0x17dc103`). A replacement returning only token IDs must not mark these GPU logits valid unless it also publishes compatible logits; a greedy-only path needs explicit invalidation of incompatible caches.

Accepted-prefix helper accepts `0<k<=model+0x18`, where `+0x18` is verification row count and `+0x1c` is its starting position. It advances current position to `+0x1c+k`, snapshots target residual row `k-1` when MTP/snapshot storage are enabled, and swaps saved target conv/recurrent pointers and partial-pool carry. Its loops stop at `0x30` layers (`0x17defa9`, `0x17df03b`, `0x17df089`), covering layers0–47. Partial acceptance also restores other native scratch snapshots; it clears verification count at `0x17df27f`. There is no corresponding layer48 history commit/discard loop. This helper can remain authoritative for target state while a private NPU head receives a parallel acceptance notification.

## Layer48 history

Let `T = *(model+0x4d8)` and `L48 = T + 48*0xc68 = T+0x25380`. Dispatcher `0x17d9eb0` reads the byte `L48[0]`: kind 1 calls attention/indexer `0x179df80` (`0x17da135`); otherwise it calls DeltaNet/conv/recurrent `0x1791030` (`0x17da148`). The separate successful root-owned metadata capture observed kind1 in all eight selected count1 entries, establishing the attention/indexer branch for this captured cohort. It does not establish all reset, bootstrap or workload paths. Allocation also explicitly provisions layer48 K/V when `model+0x900` enables MTP.

| Attention/indexer state | Device pointer field | Proven extent and publication |
|---|---|---|
| K history | `*(L48+0xb98)` = `*(T+0x25f18)` | Contiguous row: 1024 bytes =512 raw u16. Destination adds `position<<10`, copy uses `count<<10` (`0x17a0b90..0x17a0bbb`). Allocation capacity is `int32 model+0x21c *1024` bytes (`0x176ed71..0x176ed8d`). |
| V history | `*(L48+0xba0)` = `*(T+0x25f20)` | Same 1024-byte row; publication `0x17a0bcb..0x17a0bee`; same capacity (`0x176ed95..0x176edad`). |
| Compressed indexer keys | `*(L48+0x4f8)` = `*(T+0x25878)` | 256 bytes =128 raw u16 per pooled row (`0x179ba34`); `k_block_pool` publishes at `0x179bafa`, positions grouped by4. Total pooled-row capacity unresolved. |
| Indexer carry | `*(L48+0x500)` = `*(T+0x25880)` | Exactly 768 raw bytes: allocation `0x176eddc..0x176ede1`, native save/restore copies `0x300` bytes. Interpretation as three leftover key rows remains inferred. |
| Carry snapshot | `*(model+0x68)`; position tag `int32 +0x70`, slot tag `int32 +0x74` | Current carry -> snapshot at `0x17dca56`; snapshot -> current carry at `0x17dcaec`, then invalidates position tag. Save keys against `model+0x220` and `model+0xa0`. |

These histories are produced by preceding head attention/indexer work; the target-layer residual publication does not copy them. The 768-byte carry snapshot does not cover K/V or compressed-key history. If runtime kind is not 1, `*(L48+0xb88/b90)` (absolute `T+0x25f08/25f10`) are the alternative conv/recurrent state inputs; their live extents and lifecycle remain unresolved for this seam.

## Ownership and rollback gap

The contiguous K/V map is not universal. At `0x17a0935`, `byte model+0xa4 ==1` selects `k_kv_scatter_rows` with a by-value `FdRows` descriptor; other paths also read owner metadata through `*(model+0x108)` and use slot indirection. A raw K/V pointer does not prove which rows a draft owns.

Accepted-prefix rollback `0x17def00` iterates only target layers 0..47 and swaps saved conv/recurrent/indexer pointers. Layer48 history commit/discard and FD slot lifetime have not been established. A future draft must isolate mutable head state and define how an accepted prefix commits it and a rejected suffix discards it. An approximate NPU draft may emit token IDs for native target verification without matching internal MLP FP32 exactly; that does not remove the state/position/rollback contract. No performance claim follows from this map.

## Minimal private NPU head integration contract

Keep native target forward, verification, accepted-prefix helper, and output emission authoritative. Own private mutable head state per model, slot, and reset epoch; initialize it from the same defined history as the native head. For observed kind1, the transaction must cover K/V logical length and writes, compressed-pool rows including an incomplete four-position boundary, carry and pooling phase, continuation residual, position, and cached-proposal tags. A private contiguous cache can avoid native FD storage dependence only by owning its storage, initialization, and history semantics. The unresolved non-kind1 conv/recurrent state prevents treating this kind1 contract as universal.

| Proposed interface | Required behavior |
|---|---|
| Initialize/replay `(tokens, residuals, count, position)` | Bootstrap private history and handle eligible ordinary multirow head calls. Define reset/slot/epoch invalidation. |
| Begin speculation `(base_position)` | Create a checkpoint or versioned append transaction before speculative mutations. Include carry and the partially filled compressed-pool boundary. |
| Step `(token, position, residual_or_local_continuation)` | Produce proposal and continuation, retain position-tagged writes, and keep proposal-cache tags coherent. |
| Accept `(k, new_target_position, accepted_target_residual, correction_token)` | Record `a=k-1` matched drafts, select committed writes by their positions, discard the rejected suffix, and restore or repair the pooled boundary/carry. Rebase the next first step using the native accepted residual snapshot and correction token at `new_target_position-1`. |
| Reset/invalidate | Drop incompatible histories and proposal/logits caches, or replay a defined history before resuming. |

`a=k-1` is not by itself a safe number of head calls to commit. The first wrapper call uses `base_position-1`; a cached first proposal may have already been produced by ordinary or accepted-prefix replay and generates no new full-head call. Store explicit positions and transaction versions rather than equating accepted target rows with head calls. On the qualified greedy continuation path, explicit accepted-prefix replay can rewind a private cache to the ABI `position` and append `count` shifted accepted rows, rebuilding the private pooled boundary and carry. Its use and skipped paths require qualification. The exact native handling of previously speculative layer48 writes remains unproved; this proposed private transaction must define coherent semantics instead of claiming native equivalence from the target helper.

| Replacement boundary | Native behavior reusable | Additional requirement |
|---|---|---|
| NPU MLP inside native layer48 | Entire native head/wrapper/cache/history lifecycle | This is partial offload; native attention and state remain in use. |
| Full-head forward hook with native wrapper | Native controller and wrapper residual/cache path | Publish compatible `+0x6d0` continuation rows and `+0x5c` count, handle bootstrap/cache calls, invalidate or publish logits, and add an independent private-state acceptance transaction. This retains GPU/NPU residual transfers and native carry copies; the 768-byte snapshot cannot restore the private head. |
| Dedicated NPU wrapper | Native verifier, accepted target state, and output controller | Replace first-proposal cache, continuation/carry machinery, bootstrap, and acceptance interfaces. Continuation/history can stay local; the accepted target residual still supplies the next block's boundary input. |

Fallback to the original GPU head after private NPU advancement requires coherent native head history or explicit reset/replay. Calling it with stale K/V/pool/carry is not a valid fallback contract. State correctness does not impose internal FP32 parity on approximate proposals: native target verification remains the output authority. Neither the failed zero-sample attempt nor the later metadata-only capture validates these full-head integration alternatives.

## Metadata-only observer and remaining observation

The separate observer `scripts/benchmarks/halogen0162_mtp_state_tap.c` and launcher are implemented and root-built/reviewed; the [state observer note](halogen-mtp-state-tap-source-review-20261004.md) records both the failed pre-engine attempt and the later successful metadata capture. Runtime kind and entry scatter flag are now observed for eight selected count1 calls; FD attention launch identities were also observed. Raw FD descriptor content, slot ownership and lifetime remain unobserved. The full-forward records contain ABI count/position, `byte L48[0]`, `byte model+0xa4`, `int32 model+0xa0`, `int32 model+0x220`, and pointer presence/values for `model+0x108` and the four head history fields. The observer validates that the host layer table contains descriptor48 before reading it and never follows those device-pointer values.

For active FD metadata, the observer counts native kernel identities within the full-forward TLS scope. `k_kv_scatter_rows` is `base+0x18d5338`; FD attention identities are `base+0x18d5348/0x18d5350`. The scatter launch constructs its third argument as a **160-byte host `FdRows` object** (`rsp+0x290..0x32f`, construction `0x17a09b0..0x17a0aff`, argument address `0x17a0b06..0x17a0b0e`). Optional `copy160-v1` mode copies only this fixed-size host argument from `args[2]` into a preallocated record, once per selected count1 call, before forwarding the original launch. It retains raw metadata and never follows embedded device pointers. Observation is bounded to eight calls, harvest occurs after the request, and the observer adds no HIP copy, synchronization, or native-state write. The completed run remains separately instrumented with unmeasured observer overhead. Absence of an FD kernel must be reported with the entry flag and observed kind, not treated alone as proof of contiguous ownership.

## Successful runtime metadata capture

Root's separate retained run is
`server/.local/mtp-state-20261004/mtp-state-capture-a04197fc0a0e4e4cbaccec5f956dcf21`.
Its `result.json` records `passed=true`, unchanged source pins, output matching
the stock request, and successful cleanup/recovery. The request had 8192 input
and 128 output tokens, depth 2, v2, capacity 262144 and cacheOff. This publication
read the saved receipts; no capture, weight read, hash loop or hardware call
was repeated.

| Observed metadata | Result |
|---|---:|
| Selected complete count1 records | 8 |
| L48 kind 1 / entry `model+0xa4=0` | 8 / 8 |
| Original native kernel launches in selected scopes | 331 |
| FD attention identity launches | 8 |
| Scatter launches / exact-callsite scatter launches | 0 / 0 |
| Raw host `FdRows` descriptors captured | 0 |
| Observer HIP calls / device-pointer dereferences | 0 / 0 |

Caller return RVAs were `0x17dcd54` for one record and `0x17dcf49` for seven.
The full request observed 115 full-forward calls, 73 count1 calls and 42 other
counts; the bound skipped 65 further count1 calls. The five-file export was
9234 bytes. Raw descriptor copy was enabled, but no matching scatter launch
occurred, so no raw descriptor was captured. FD attention was observed while
the entry flag was zero; that flag alone does not define cache ownership.

The trace inventory records `records.json` SHA256
`c205a7959dc3f329ec1eac78e213ba0de3475fa848fcac6014f97d672b3264f2`
and `complete.json` SHA256
`7af9ce24b43508ead8fba8eb32e3844af9cc5b741cc8a5034e316c5cbb0a3e51`.
These pins were copied from the retained inventory, not rehashed here.
This confirms observed branch/mode and launch metadata, with unmeasured
observer overhead. It supplies no timing, FD lifetime, commit/discard,
acceptance or NPU-speed result. Private head transactions and native target
verification still require integration.
