# Independent native64 adapter source review

Reviewed 2026-10-09 by the independent draft scope, with a separate read-only ABI/capacity reviewer. Final source: `adapter.c`, SHA256 `714b90cf716a0ed2b82deb949394ff4154798a0fadd6c421c39aadd7e3c8c24d`.

**No outstanding ABI, item-capacity, or launch-transaction finding was identified in this bounded source review.** This is source evidence only. No adapter build, module load, hardware execution, numerical equality, or performance result is claimed. The root owns those stages and the engine lifetime.

## Pinned scope and ABI

The adapter is default off and requires the exact 0.17.3 engine SHA256 `af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7` and unchanged embedded native object SHA256 `18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039`. The bounded route is N8192, mode1, output flag1, device0, noncapturing stream0, with the original launch shapes and return-address checks.

The 152-byte projection aggregate has eight-byte fields at 0x00/08/10/18, the exact inline FP32 codebook at 0x20..5f, then m0/m1/input/permutation/items/count/output at 0x60/68/70/78/80/88/90. The 56-byte item aggregate has scalar argument offsets 0/8/16/24/32/40/48; rows is four bytes at24. The 64-byte fold aggregate has offsets 0/8/16/24/32/40/48/56; tokens is four bytes at16. Host argument decoding and replacement pointer arrays preserve these layouts and their alignment padding.

Native64 item scan/count anchors are e002c0..e002d8 and e008ac..e008dc. GU/DN count guards are e01100..e01140 and e16300..e16340. C64=1792 accommodates the finite histogram segment sum `sum(ceil(rows/64))`; payloads are 143360/286720 bytes and GU/DN grids are 8960/17920. The native count guards exclude unused capacity blocks. Synthetic guard bytes surround only the adapter-owned item arrays.

All seven descriptor/symbol registration pairs were checked directly in the staged 0.17.3 host disassembly:

| Kernel | Descriptor RVA | Registration call RVA |
|---|---|---|
| items128 | 18f92b0 | 187782e |
| GU128 | 18f92d0 | 18778e6 |
| DN128split2 | 18f92d8 | 1877914 |
| items64 | 18f92a8 | 1877800 |
| GU64 | 18f92b8 | 187785c |
| DN64split2 | 18f92c0 | 187788a |
| fold | 18f6bc0 | 186f3c0 |

Launch return-address pins are items17d2e97, GU17d354a, DN17d43aa, fold17d462c. Mode/flag pins are18fcca0/18fccd8. Engine and embedded-object hashes were independently recomputed. No host text or native device-code patch is performed; registration passes through and the adapter selects already registered native handles.

## Transaction closure

The item transaction saves the original item/count bindings before replacing only the two item-array pointers. GU and DN save their original projection aggregates and record the attempted phase before submitting the native64 launch. Candidate grids are local copies. Original function, grid, block, arguments, shared-memory size, and stream are retained as const aliases for stock forwarding.

Any interrupted or rejected active transaction first replays native128 item generation and every attempted GU/DN prefix on stream0 at the original grids, then synchronizes before stock continuation. A successful rollback disables the candidate. A failed replay or synchronization sets the fatal latch, preventing later intercepted launch continuation. The void unregister hook exits127 if its active rollback fails, rather than continuing teardown after failed restoration. A registration conflict sets disabled, and the next intercepted launch restores an active transaction before forwarding.

The original native fold and original fold arguments remain the consumer. Successful fold submission closes the transaction; it is not an execution/equality certificate. Explicit shutdown and process-exit reclamation remain root-owned lifecycle choices.

The initial review found replacement-handle forwarding, replacement-grid forwarding, omitted replay of failed projection attempts, stock forwarding after rollback failure, and unregister continuation after rollback failure. The final source resolves all five. The speculative `hipMemGetAddressRange`/`contains` admission checks were removed. The host argument-copy fallback through `/proc/self/mem` introduces no device allocation-extent prerequisite.

## Exact activation payload bounds

The independent finite native64 load analysis is `../prefill-bulk-moe-retile-scope-20261009/host-route-proof-v1.activation64-exact.md`. GU64 reads are contained in `[0,41943040)`; DN64 reads are contained in `[0,104857600)`. Both require zero activation prefix or suffix padding. The earlier conservative guarded-fixture envelope is not a model allocation requirement or adapter admission condition. Actual-model allocation capture and a universal arithmetic proof are not prerequisites for this source review.

## Portability addendum

The final source differs from the reviewed `b9cd2fe36303682b16ba3ebe084cd51b2d2ebb2741a33f4bf134c48c63063e02` snapshot only by assigning the diagnostic `write()` result to `ssize_t written` and explicitly discarding that variable before `_exit(127)` in `required()`. This resolves the root compiler's `warn_unused_result` under `-Werror` without changing control flow, ABI, launch transaction, or allocation behavior. The final source hash and this line were checked read-only. No tests, builds, hardware work, or adapter edits were performed by this reviewer for the addendum.

## V2 resident-query exclusion

This derivative preserves the reviewed 0.17.3 serving pins, ABI, capacities, payload bounds, guards and rollback code. Its only adapter delta adds a bounded `/proc/self/cmdline` check and returns from initialization when argv[1] is exactly `--resident-gib`, including its NUL terminator. Unknown arguments retain the previous pinned behavior. The check occurs after opt-in/executable-path checks and before engine hashing or exclusive log creation. Thus the normal entrypoint's short resident-size helper cannot claim the serving audit log. The serving command's argv[1] is `--ck`, so it continues the prior initialization path unchanged. The source reader uses128 bytes; the actual pinned argv[0] plus helper argv[1] fit within that prefix. Missing/unreadable/truncated command lines do not add a serving admission gate. No build, test, hardware, API or lifecycle work was performed by this source author. The separate source-only constructor review is `independent-resident-skip-review.md`, SHA256 `19fc71eefd285b457c4ffe4a2d83e0e2b1b671e1176ad8555aa70e562c379824`, with no outstanding finding.
