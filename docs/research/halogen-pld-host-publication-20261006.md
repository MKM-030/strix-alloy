# Host publication closure for the native PLD read interval

**The three named backend chains close for host-only reads under five empty optional model hooks and the established native worker exclusions.** Their ordinary descendants do not reach request release/reset, start a native host worker, or pass the selected request/record/aggregate/vector to a concurrent callable. This supports a concrete engine-local `NativeReadBoundary`; it does not qualify an installed capture, device-tensor snapshot, prefix acknowledgement or speedup.

This retained-source audit extends the frozen [positive scope](halogen-pld-positive-owner-scope-20261006.md), [owner serialization](halogen-pld-live-owner-serialization-20261006.md) and [worker exclusion](halogen-pld-native-worker-exclusion-20261006.md) reports. Those files remain unchanged. No new disassembly, compiler, tests, runtime, WSL, hardware, process or lifecycle action was used.

## The backend destinations are finite

A conservative graph follows every direct CALL and every direct tail JMP outside its containing FDE from `0x17d9eb0`, `0x178cf90` and `0x17ccba0`, stopping at the retained PLT. It covers 1,020 native FDEs and 76 import targets, with no unresolved internal entry. None reaches the previously identified request destructor/removal/completion/cancellation, model reset/import, slot remap, disk/indexed executor, copy-worker or worker-start targets. The graph deliberately includes branches that the narrow mode cannot take.

All 64 indirect JMP sites are signed-32-bit RIP-relative switch dispatches. The ten sites in `0x178cf90` use six-entry tables `0x45c90/45cc0/45c48/45c00/45c78/45ca8/45c30/45be8/45c60/45c18`; the four in `0x17ccba0` use `0x45dd4` (7), `0x45df0` (6), `0x45d9c` (7), `0x45db8` (7). All 87 entries stay inside their containing FDEs. Descendant dispatch destinations likewise stay inside their FDEs. In particular, `0x45f34/45f6c/45fa4` have unsigned index `<=6` guards; `0x4842c/4844c` have index masks `&7` at `0x18c878b/0x18ca0f0`. The latter eight-entry tables resolve entirely inside `0x18c8640..0x18c9fd8` and `0x18ca0a0..0x18cb64e`. ELF `.rodata` flags `0x32` exclude write permission. These jumps therefore introduce no hidden external destination.

The eight indirect CALL sites reduce to optional model hooks and one guarded wrapper:

| Actual model binding | Holder/function and reachable calls |
|---|---|
| Head `R14=M`, saved at `0x17d9ec2` | `M+0x270/+0x278`, call `0x17da289` |
| `0x177a2b0`, `RBX=M` at `0x177a2c3` | `M+0x2d0/+0x2d8`, guard `0x177a561`, call `0x177a585` |
| `0x179b7b0`, entry `RDI` saved at frame `+0x98` | `M+0x2f0/+0x2f8`, guard `0x179d635`, call `0x179d693` |
| `0x17a44d0`, entry `RDI` saved at frame `+0x128` | `M+0x2b0/+0x2b8`, calls `0x17a4d8b/0x17a62f6` |
| `0x17bd410`, entry `RDI` saved at frame `+0xe0` | Same `+0x2b0/+0x2b8`, calls `0x17bf96f/0x17c01f0` |
| Wrapper `0x1859210` | Its supplied holder `+0x10/+0x18` call at `0x1859237` is reached only after the same `M+0x2b0` guard at `0x17c0b95`, through call `0x17c0bb7` |

The forward route separately uses `M+0x290/+0x298`. Thus require all five holders `+0x270/+0x290/+0x2b0/+0x2d0/+0x2f0` empty. Successful construction binds `RBX=M`, zeros `XMM0` at `0x176b8af`, then zeros these pairs at `0x176ba3a/176ba2c/176ba1e/176ba10/176ba02`. The targeted apparent nonzero stores in `0x17712e2..0x1771466` address layer `L=*(M+0x4d8)+index*0xc68`, not `M`. Handler stores `0x171e0ee/171e0fe` address the transient stack object at outer `+0x990`; `0x172981b/172982b/172983b` address the freshly allocated `0x488` pending object. Record construction/moves address their supplied records. No serving-route binding to these model hooks was found. Nonempty holders remain outside this proof.

## The host objects do not become device destinations

The head receives `M`; its layer pointers derive from `M+0x4d8`. It writes temporary inline `M+0x1c3` at `0x17da1cc/17da3eb`, clears it at `0x17da1f4/17da3fc`, and returns normally at `0x17da460`. `0x178cf90` receives a tensor descriptor, tensor input/output buffers and scalar dimensions: head descriptors are `M+0x908/980/9f8/a70`. `0x17ccba0` receives descriptor `M+0x500`, residual/output-logit buffers and scalar dimensions/count. Neither receives `N`, `R`, `A` or the request vector. Backend caches retain tensor handles/keys or separately owned storage. For example, destructor registrations pass static cache `0x18dcfe0` at `0x178edab` and `0x18dd638` at `0x17da54d`; they do not register an owner-bearing serving callback.

Borrowed input IDs stop at synchronous `memcpy`: full head copies `count*4` bytes to `*(M+0x6b0)` at `0x17db364`; target forward does the same at `0x17dd20f`. Subsequent `hipMemcpyAsync` at `0x17db382/17dd22d` receives that model-owned source and device destination `*(M+0x730)`, kind 1, stream 0. The caller's token pointer is never published to HIP. Reachable imports include tensor allocation/copies/events/launches and backend configuration; they contain no thread-start, serving/socket sender, HIP host callback dispatch, `hipHostRegister` or `hipHostGetDevicePointer`. Reachable `hipHostMalloc` supplies separate owned scratch, not registration of inline `M` or the request vector.

Normal target verification synchronizes at `0x17dde45`, then checked readback `0x17ddef8` writes predictions to inline `M+0x20`. Full head synchronizes at `0x17dc128` and reads back to its own stack at `0x17dc153`. Those host writes complete before successful return. Commit `0x17df272` is still `hipGetLastError`, not a wait: authoritative output IDs/prefix can be captured after commit, but device tensor completion cannot be inferred. No tensor, host staging allocation or driver-owned buffer belongs in the read spans.

## A real issuer can bind the paused native stack

Main constructs `M` at `main RSP+0x6d8` (`0x171a127/171a13f`). Retained CFI gives main CFA offset `0x1250` at both construction and synchronous handler call; intervening temporary pushes are balanced. Main forms `A` at `main RSP+0x180`: stores its model pointer at `0x171b3b8` and cache pointer at `0x171b3c5`, then passes `A` and connection `main RSP+0x2e8` at call `0x171ba1a`.

Handler CFA is outer `RSP+0x2680`, equal to this caller's main RSP. Therefore a trusted real seam frame binds saved return `*(outer+0x2678)==image_base+0x171ba1f`, `A==outer+0x2800`, `M==outer+0x2d58`, connection `outer+0x2968`, and `*(A+0)==M`. Successful constructor return precedes aggregate formation; its exceptional path does not enter the accept loop. This supplies model construction/lifetime provenance without a new model-constructor detour. Main cannot destroy its model while the synchronous handler is paused.

The minimal separate issuer for [the capture adapter](../../scripts/benchmarks/halogen_pld_nohit/native_owner_capture.h) is concrete:

1. Enter only from the qualified real no-hit/outcome adapter. Validate the actual caller/frame binding above and the one-record native queue; bind `R=R15`, `N=RBP=*(R+0x10)`, completed prefill and selected slot. The native queue move ownership and main call hold these objects throughout the pause.
2. Establish the actual known progress data/callable and null `A+0x130`, five empty model hooks, absent disk holder with startup provenance, completed construction timer, no indexed work, and successful return from every relevant copy-worker scope. Source facts must become observations of this handler, not user-supplied flags. Retire before nonempty command dispatch `0x171c696`, release/reset/import/remap, pending publication, hook activation or unsupported phase reentry.
3. Privately construct the nontransferable `NativeReadInterval` only during that owner-thread pause. Supply the exact bounded host spans (`N:0x1f8`, `M:0x902`, `R:0x308`, outer `0x180`, checked last `<=512` vector IDs), real register image and trusted immutable token definitions. Call `observe()` into preallocated owned storage, then end the interval before resuming native work. External preparation receives only owned values.

Successful request birth and full-prefix continuity remain separate. Install the mapped birth/release/reset observations and complete a separate owned full-vector acknowledgement before qualifying a handoff seed. `PrefixAcknowledgementAuthority` cannot be minted from this interval, suffix equality or a generation comparison. Positive `B>0`, `Q>1` and controller width `<=3` remain as established in the positive report; a `Q==1` cohort cannot qualify custom admission.

The current stock-only installer copies real registers and dereferences no native object. This audit supplies its next read integration boundary, not an implementation or runtime qualification. CPU is appropriate for bounded copies and host outcome publication; GPU remains native tensor work. Independent GPU/NPU drafting still needs state/tokenizer parity, completion and contention evidence. Evaluate total target time per actually committed token, including preparation, transfer, verification, replay, capture and fallback; all performance/placement results remain unmeasured.

## Evidence pins

Pinned inputs: ELF SHA256 `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`; retained text `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`; frames `03b9bef6fd4182013dcec8ecb9c850dcc5c5ae474b57ecf2925934359115b923`. Paths are in the owner serialization report. The following bytes were independently compared with ELF file offset `RVA-0x1000` and retained text; table entries were read directly from ELF identity-offset `.rodata`.

| RVA | ELF bytes |
|---|---|
| `0x171a127` | `48 8d bc 24 d8 06 00 00` |
| `0x171a13f` | `e8 bc 16 05 00` |
| `0x171b3b0` | `48 8d 84 24 d8 06 00 00` |
| `0x171b3b8` | `48 89 84 24 80 01 00 00` |
| `0x171b3c5` | `48 89 84 24 88 01 00 00` |
| `0x171b93f` | `4c 8d b4 24 80 01 00 00` |
| `0x171b947` | `4c 8d bc 24 e8 02 00 00` |
| `0x171ba1a` | `e8 41 08 00 00` |
| `0x176ba02` | `0f 11 83 f0 02 00 00` |
| `0x176ba10` | `0f 11 83 d0 02 00 00` |
| `0x176ba1e` | `0f 11 83 b0 02 00 00` |
| `0x177a561` | `48 83 bb d0 02 00 00 00` |
| `0x177a585` | `ff 93 d8 02 00 00` |
| `0x179d635` | `49 83 bd f0 02 00 00 00` |
| `0x179d693` | `41 ff 95 f8 02 00 00` |
| `0x17a4d8b` | `ff 90 b8 02 00 00` |
| `0x17bf96f` | `41 ff 96 b8 02 00 00` |
| `0x17c0bb7` | `e8 54 86 09 00` |
| `0x17db364` | `e8 17 7d 0f 00` |
| `0x17db382` | `e8 89 83 0f 00` |
| `0x17dd20f` | `e8 6c 5e 0f 00` |
| `0x17dd22d` | `e8 de 64 0f 00` |
| `0x18c878b` | `83 e0 07` |
| `0x18ca0f0` | `83 e2 07` |
