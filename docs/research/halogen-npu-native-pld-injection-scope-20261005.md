# Native PLD token-proposer insertion scope — 5 October 2026

**A concrete private token-only insertion seam exists in the retained Halogen 0.16.2 binary.** Native prompt lookup constructs a host `int32` proposal block, checks its first token against the native MTP head, then passes the block to the existing target verifier and accepted-prefix machinery. A bounded independent proposer could supply these IDs while preserving that machinery. This is structural feasibility, not an implemented callback, a qualified detour, an NPU predictor, or a speed result.

The narrowest identified completion point is RVA **`0x172e95f`**, after the native context-token copy and before optional native constraint handling and the native-head opening check. It is an interior basic block of a large function, not an exported function with a callable PLD ABI. It is reached only after a native lookup hit; replacing IDs there neither removes the lookup search nor supplies proposals on no-hit rounds. Supporting those rounds requires a separately proved branch insertion.

This finding extends the retained [public-interface audit](halogen-mtp-public-integration-feasibility-20261004.md). Absence of a documented external drafter transaction does not disprove private insertion. The earlier [proposal seam audit](../../server/.local/optimization9h-20261004/npu-proposal-seam-audit-20261005.md) inspected supported surfaces and existing hooks; it did not inspect this complete decoder path.

## Pins and evidence scope

Rechecked locally during this audit:

| Retained file | SHA-256 |
|---|---|
| `backends/halogen-wsl2-0.16.2/.local/flash_serve` | `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` |
| `server/.local/optimization9h-20261004/mtp-route-static-20261004/host-text-disassembly.txt` | `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` |
| `server/.local/optimization9h-20261004/mtp-route-static-20261004/host-frames.txt` | `03b9bef6fd4182013dcec8ecb9c850dcc5c5ae474b57ecf2925934359115b923` |

The ELF is 26,052,768 bytes. RVAs and roles below come from the retained stripped host disassembly; role names are inferences from argument/data flow, not exported symbols. Its `.text` VA minus file offset is `0x1000`. The containing FDE is `0x171c260..0x17305ed`. The separate native MTP controller FDE is `0x173b630..0x173bb86`; it must not be mislabeled as the PLD producer.

Source/text reads and static hashes only. This audit creates only this document. No hardware, WSL command, network refresh, runtime import/execution, build, test, proposal feed, lifecycle action, model payload read, or continuation edit was performed.

## Exact native proposal and verification path

Here `request` is the object in RBP on the decoder path, `model=*(request+0xd8)`, `P=int32(model+0x220)`, and `d[0..n-1]` is the PLD proposal vector.

| Native instructions | Proven data/control behavior |
|---|---|
| `0x1749d10..0x1749f31` | Request-initialization FDE. RDI is the request, RSI the model and EDX the current token for the fields used here. It stores the model at `+0xd8`, current token at `+0x15c`, and the model's cached first proposal at request `+0x160`. This is a partial argument map, not a claim of the entire function prototype. |
| `0x1749e2c..0x1749e75` | Clears PLD width, host vector and hash state at request `+0x170..+0x1c0`. |
| `0x1749eb0..0x1749f06` | With positive PLD width and absent sampler, installs width from request `+0xec`; seeds supplied host context via `0x17592a0` at `0x1749efc`, then appends the current token via `0x1759550` at `0x1749f06`. |
| `0x17592a0..0x175953f` | Bulk context helper accepts PLD object in RDI, host `int32` context in RSI and count in EDX, with a further limit in ECX. Its vector append is at `0x17592d8..0x17592ec`. |
| `0x1759550..0x175972b` | FDE for single-token append: RDI=PLD object, ESI=token. Appends a four-byte ID to its vector, hashes a prior token window, and stores a continuation index in its hash map. This helper can reallocate the vector. |
| `0x172d32f..0x172d3b7` | Requires positive PLD policy, absent sampler (`request+0x150==0`), no PLD suppression counter (`+0x1d0==0`), positive row allowance and sufficient host context. Reads width at `+0x170`, vector begin at `+0x178`, end at `+0x180`. |
| `0x172da98..0x172dcac` | Hashes the latest host-token window using constants `0x14650fb0739d0383`, `0x100000001b3`, and shift 29. |
| `0x172dcac..0x172ddb0` | Finds an earlier continuation index through the host hash table at request `+0x190..+0x1a8`; lookup failure returns to the stock no-proposal branch at `0x172d3bd`. |
| `0x172ddb2..0x172de74`; sibling `0x172e914..0x172e95f` | Reads index `j` from node `+0x10`, sets `n=min(context_length-j, native_allowance)`, and copies context IDs beginning at `begin+j*4` to decoder stack `+0x360`. Scalar/unrolled and vector-copy paths join at `0x172e95f`. |
| `0x172e95f..0x172eaa6` | At entry RBP=request, RBX=n, stack `+0x360` holds IDs. Optional native constraint-object calls may truncate the eligible count. With no constraint object, `0x172ea19` sets R13D=EBX and returns to `0x172d3cc`, which sets R12D=R13D. |
| `0x172d3cc..0x172d425` | For the eligible MTP path, checks the opening proposal: cached native ID at request `+0x160` must equal `d[0]`. If absent, `0x172dd6e..0x172dd80` calls `0x17dcde0(model,current_token,offset=0,restore=0)` and caches its returned ID before comparison. |
| `0x172d5d3..0x172d618` | Constructs target inputs `[current_token,d[0],...,d[n-1]]` at stack `+0x980`. Calls `0x17dcfc0` at `0x172d618` with RDI=model, RSI=input pointer, EDX=`n+1`. |
| `0x172d630..0x172d650` | Compares `model+0x20[i]` with `d[i]` consecutively. RBX counts matching proposals `a`; a mismatch goes to `0x172d7bf`. |
| `0x172d7bf..0x172d80a`; first-mismatch sibling `0x172dabf` | Sets accepted target input count `k=a+1`; first mismatch uses `k=1`. Copies matched proposal IDs to stack `+0x1980`, appends target correction/bonus `model+0x20[a]`, then calls `0x17def00(model,k)` at `0x172d80a`. Full match retains `k=n+1`. |
| `0x172d87e..0x172d8f1` | Emits the shifted accepted/correction IDs through native output handling, appends emitted IDs to the PLD context at `0x172d8c8`, and updates current token from the correction at `0x172d8f1`. Stop/error branches remain native. |
| `0x172db6f..0x172e05d` | Eligible ordinary continuation calls `0x17dcc90(model, shifted_ids, k)` at `0x172e058`, with RSI=stack `+0x1980`, EDX=stack `+0x40`; caches its returned next first proposal at request `+0x160`. Native MTP/suppression flags gate this replay. It is not unconditional on stop/error exits. |

The verifier ABI is independently visible in FDE `0x17dcfc0..0x17dd01b`: `void(model, const int32_t *inputs, int32_t count)` for this use; callers ignore the return value. It requires positive count, MTP enabled, `count<=int32(model+0x14)` and a nonzero current position. It sets `model[0]=1`, calls target forward `0x17dd020` with ECX=-1, then clears `model[0]`. The [state ABI receipt](halogen-mtp-full-head-state-abi-20261004.md) establishes that this verification flag bypasses automatic full-head replay, leaving explicit replay to the caller.

`0x17def00` requires `0<k<=int32(model+0x18)`, uses verification base `int32(model+0x1c)`, sets current position to base+k, snapshots the last accepted target residual, handles the native rejected suffix, and clears the verification count. Its state loops cover target layers 0–47. The PLD path therefore already supplies the target transaction sought by a token-only insertion. Its ordinary replay is now separately traced here; this does not qualify every main-decoder replay branch or establish universal native layer48 ownership.

## Bounds and opening-token rejection

At `0x172d357..0x172d38b`, the positive PLD allowance is:

`B=min(int32(model+0x14)-1, int32(request+0xf0), int32(model+0xf0)-P-1, Q-1)`

Here Q is the live native output allowance carried in R9D from the block setup at `0x172d25a..0x172d2c4`, also stored at request `+0x1e0`. The match-copy count is further bounded by available context suffix length. Do not enlarge B or native buffers from a packet count. The retained [flag audit](halogen-mtp-next-action-20261004.md) records stock `HALOGEN_PLD=3,3`, `0` disables, and K>3 exceeds the image's existing verification reservation. A first bounded design must remain at **at most three proposal IDs**, also respecting the native allowance and actual existing destination extent. Thus at most four target input rows are submitted. The flag evidence is retained documentation; this audit did not refresh upstream flags or observe a new allocation.

An opening mismatch at `0x172d425` or `0x172dd8d` jumps to **`0x172d42b`**, bypassing verification of that PLD block. With the native MTP path eligible, `0x172d655` continues through `0x172dad1` and calls the separate bounded native controller `0x173b630` at `0x172db61`; otherwise the native scalar/sampling/constraint fallback applies. The rejected PLD candidate does **not** skip builtin MTP, does not commit its IDs, and does not obtain acceptance merely by entering this seam.

Inserting at `0x172e95f` preserves the opening comparison and subsequent native gates. Overwriting only the suffix after a successful comparison could preserve its first ID, but is a different splice needing its own live-register proof. Overwriting the **whole** block after that comparison bypasses the native opening invariant; target verification alone is not proof that this change preserves every cache/replay/adaptation assumption. It is outside the smallest candidate.

## Committed context, ownership and epoch contract

The native context vector is seeded during request initialization and extended through output paths, including `0x172d8c8`, `0x172d53d`, `0x172d76d`, and the separate controller's `0x173b825`. It is host token data; pointers are borrowed only within the current boundary and may change on append. The first scope should copy a bounded validated prefix into privately owned protocol storage, never lend a native vector or stack pointer to the Windows worker.

No monotonic native request/reset epoch or externally callable acceptance notification was established. Request pointer, model pointer and position alone cannot prevent stale response reuse. A future protocol needs a separately generated request-initialization nonce, one-shot round ID, exact committed-prefix length/fingerprint, current token, target position, tokenizer/model identity and bounded count. Validate all of these again before touching the stack IDs; stale, absent, malformed, timed-out or exhausted input must leave the complete original vector/count and native control path available. Native cancellation, in-place reset/context replacement and slot transitions still require an explicit ownership map before any asynchronous feed is integrated. Constructor and destructor anchors below are concrete, but do not prove that every cancellation waits for an external callback or that every reset destroys the object.

A stateless independently trained token proposer can avoid owning Halogen's native layer48 K/V, pool and carry because the native head and native replay remain intact. A stateful external proposer still needs its own prefix/accept/discard/reset semantics, or must rebuild only from the authoritative committed prefix. Target-layer rollback does not roll back external model state. A pointer or count-only feed is insufficient.

The proposer must predict from genuinely available committed context. Target predictions at `model+0x20` after verification, future output files, a saved answer, and captured future target rows are forbidden candidate inputs for a performance claim. Native first-head output is used by the existing opening **gate**, not as an oracle that manufactures a matching independently predicted block. CPU fixtures may qualify packet/ABI behavior only and must be labeled accordingly. There is currently **no trained Qwen-compatible NPU predictor** in this retained work.

## Bounded follow-up static pin and ownership anchors

The one bounded follow-up requested by root read only 28 bytes from the already pinned ELF at file offset `0x172d95f`. They exactly match all five instructions of the basic block `[0x172e95f,0x172e97b)`:

`488d85e80100004889442438488bbde80100004885ff0f849e000000`

SHA-256 of those 28 bytes: `3e95f9f01d988fb7353cc764ab0c899ae21196ac545c54593eb342423d1fdf83`.

The first instruction alone spans `[0x172e95f,0x172e966)` and is exactly `48 8d 85 e8 01 00 00`. A complete retained-text direct-target scan found **two encoded incoming edges** to `0x172e95f`: `ja` at `0x172de2c` and `jmp` at `0x172de74`. The third predecessor is the vector-copy fallthrough after `jne 0x172ddf5` at `0x172e959`. No encoded direct call/jump target enters the interior of the 28-byte block. This scan proves direct predecessors in retained text; it is not proof against arbitrary computed jumps or a qualification of a runtime trampoline.

| Entry/branch ABI detail | Static evidence and implementation consequence |
|---|---|
| RBP=request, RBX=positive stock count n | Both copy branches derive RBX from the same bounded suffix count; RBP remains the request. These are live values, not ordinary call arguments. |
| Original RSP + `0x360` | Completed host `int32[n]` proposal array. Keep the original stack base across any helper call; offsets relative to a pushed/helper stack are different. |
| Original RSP + `0x38`, `0x980`, `0x1980` | The native block installs the constraint-object address at `+0x38`, then uses `+0x980` and `+0x1980` as constraint state scratch. Later verification/accepted output also uses these areas. A helper must not retain or overwrite them. |
| First five instructions | LEA into RAX, store `+0x38`, load constraint pointer into RDI, TEST RDI, then conditional branch. RAX/RDI and condition flags are overwritten before first native use; preserve all machine state in a proposed shim unless a separately complete liveness proof permits less. Other general/vector registers and outer stack locals have not been proven dead. |
| No constraint object | `0x172e975→0x172ea19→0x172d3cc`; native count passes through. This is the simplest bounded integration scope. |
| Constraint object present | `0x172e982/0x172e9a7/0x172e9f8` invoke vtable `+0x10` for the empty prefix and successively longer proposal prefixes. Sentinel -2 truncates the eligible count. Vtable `+0x18` restores/materializes state (`0x172ea45`), then `0x17e7b50` receives bounded state entries at `0x172eaa1`, before returning to `0x172d3cc`. Exact vtable ownership/error semantics remain opaque; a first adapter must preserve this branch untouched or decline injection when the pointer is present. |

Concrete request-lifetime anchors found within the bounded follow-up:

| Anchor | What is proved |
|---|---|
| Allocation and initialization at `0x172024c..0x17202a9`, second site `0x172a3c5..0x172a422` | Allocates exactly `0x1f8` request bytes and calls `0x1749d10`. These are usable birth anchors for a separately generated nonce; pointer reuse must start a new nonce. |
| Request destructor FDE `0x17590c0..0x17591af` | RDI=request. Frees the PLD linked nodes at `request+0x1a0`, hash buckets at `+0x190`, and token vector at `+0x178`, then other request-owned buffers. Its vector release is `0x1759138..0x175914e`. This is a concrete epoch-end anchor. |
| Replacement at `0x17202ba..0x17202d7` | Installs a newly initialized request, destroys the old request at `0x17202ca`, then frees exactly `0x1f8` bytes. |
| Pointer-replacement helper FDE `0x1749ce0..0x1749d04` | Swaps a holder's pointer, destroys the prior nonnull request at `0x1749cef`, and frees it; called after the second initialization at `0x172a436`. |
| Further destructor sites `0x17322ec`, `0x1734d8d` | First follows loading a holder's request at `holder+0x10`; second is a move/replace helper that takes ownership from a source and destroys the destination's previous request. These show additional replacement/cleanup anchors. Their full cancellation/stop causes were not proved. |
| Constructor exceptional cleanup `0x1749f1c` | Calls `0x17591b0` with the PLD subobject, followed by other request cleanup. A nonce must not become eligible merely because initialization began. |
| Native stop/error output branches | Identified return/stop handling around `0x172d8dc..0x172d943` and `0x172e813..0x172e826`; they can bypass ordinary replay. A complete externally driven cancellation/acknowledgment path was not identified in the bounded scan. |

**Readiness verdict:** an offline finite CPU packet/buffer adapter is now implementable against an explicit caller-supplied birth nonce, round/prefix identity, immutable stock vector/count and a privately owned reply. Validate the whole reply before returning a replacement vector/count; cap the replacement at `min(stock_n,3,native_allowance)`, decline the constraint-object branch initially, and leave the original bytes/count unchanged on every rejection. It must neither access target-prediction buffers nor call the verifier itself. This is useful protocol/ABI preparation for a genuine independent proposer and can use clearly labeled synthetic CPU fixtures.

Native runtime injection is **still unqualified**: machine-state preservation/installation, exact reset and cancellation races, and external-state acceptance/failure semantics remain missing. Constructor/destructor hooks alone do not prove asynchronous response safety. A pure offline adapter need not wait for those engine proofs; enabling an actual feed does. No implementation, shim, runtime observer or fixture was added by this audit.

## Learned PLE features are a different operation

| Mechanism | Data and result |
|---|---|
| Learned PLE | `layers.1.ple.ngram_embedding.weight`, storage10 FP8 global scale, shape `[128,2500012,160]`, payload **51,200,245,764 bytes = 47.684 GiB**, including a four-byte scale. Loader stores its source at engine `+0x678`; serial/worker gathers copy learned feature rows for model computation. |
| Native PLD | Request-owned host `int32` context vector, short-window hash map, and copies of earlier context **token IDs** into a speculative proposal block. Native target predictions determine acceptance. |

The PLE constants are retained in [the extractor](../../scripts/benchmarks/halogen_ngram_extract.py) and [the CPU/SSD audit](halogen-cpu-ssd-opportunities-20261004.md), including gather RVAs `0x17d80ce/0x17d80fc` and worker `0x1847cb0/0x1847d3b`. Reading or moving those learned weights does not create next-token proposals or improve PLD accuracy. PLD IDs are not a compressed representation of that table. Neither route supplies trained drafter weights automatically.

## Performance condition and smallest next static step

No useful token rate can be inferred from this seam or from isolated H-projection timings. The required matched comparison is:

`sum(new round time) / actually committed output tokens < sum(stock round time) / actually committed output tokens`

New round time must include independent proposer work, readiness and transport/validation, retained native opening-head work, unchanged target verification/commit/replay, rejected proposals and fallback, output/stop handling, and any target/NPU memory or scheduling contention. Missed ready responses and initialization/rebuild costs must be amortized over the actual request. More proposed tokens or a higher accepted fraction alone do not prove the inequality. A feed confined to native lookup hits may improve proposal suffixes, but pays the original lookup work; its performance case is different from accelerating the small CPU hash/copy itself. No accepted-count or latency distribution for a genuine NPU proposer is available.

The requested bounded static pin/branch/lifetime-anchor step is completed above. The smallest remaining static engine step is tracing in-place reset and cancellation into these ownership anchors, with their queue/slot synchronization, before an asynchronous native feed is enabled. A separate default-off, finite offline CPU protocol/ABI adapter can now be made concrete using the explicit contract above. Its eventual native scope starts with existing PLD-hit opportunities and preserves all native verification/commit/replay. A no-hit splice or bypass of the first-head equality is additional work, not an implied extension of this receipt.

There is no justification here for another live vector-H cohort or for an oracle proposal benchmark reported as NPU gain. The retained H vector decision and the new token-proposer candidate have different inputs, computation and cost boundaries.
