# Offline NPU preparation and the native embedding consumer — 5 October 2026

The smallest distinct consumer opportunity is a **precomputed count1 embedding projection that skips the entire token embedding GPU branch and supplies the native seed-add input directly**. The existing M1-only cache still runs gather/RMS and launches a D2D copy on hits; its retained measurements showed no useful saving. Reusing that consumer unchanged would repeat the rejected path.

This is a bounded source finding, not an implemented or measured optimization. No hardware/provider operation, model/tensor/engine binary read, build, test, engine lifecycle action, or product source edit was performed for this note. The evidence is existing source, reports and narrow excerpts of retained disassembly. The unrelated FC candidate files were untouched.

## What currently consumes preparation

The early token producer writes `raw.u16`, `norm.u16`, `e_norm.f32`, `e_high.f32` and `e_low.f32`, plus packed input fixtures (`halogen_mtp_early_token_producer.py:293–322`). It produces no projected result or upload. The portable RMS adapter has the same boundary (`halogen_mtp_early_token_native_rms_producer.py:71–99`). Both complete receipts explicitly leave live publication/upload false.

The embedding-only graph takes `e_high/e_low[1,2560]` and returns `e_projection[1,2560]` (`halogen_npu_early_embedding_graph.py:23–29`). That output is FLOAT on the BF16 lattice; a consumer artifact would need its exact 2560 little-endian BF16 words. The existing probe is a frozen A/B diagnostic, not a producer for the prepared token list.

The current native cache exposes only `init/apply/reset/close` (`halogen0162_mtp_embedding_cache.h:54–60`). Hits copy device row to original output with HIP kind3; misses invoke the original FC and capture its actual output with another kind3 copy and completion event (`halogen0162_mtp_embedding_cache.c:105–150`). There is no import, host output publication, `.npy` parser or external embedding cache option in the tracked backend. The paired wire also carries late normalized embedding **and hidden** inputs, not immutable token-only prepared rows (`halogen_mtp_fc_wire.py:15–23`); it is unnecessary for offline precomputation.

The retained private loader does contain a different external-file path. After loading/converting `embed_tokens.weight` at `0x1770a3d` and storing its device pointer at `model+0x4f0`, it queries an environment name at literal RVA `0x41470`, opens a file, requires exactly `0x4bc80000` bytes, reads that file into CPU allocation and performs a kind1 copy into the existing table. Those bytes equal `248320*2560*2 = 1,271,398,400`, a full raw BF16 table. The literal name is not available in the retained text. No `.npy` header parser appears in this path. It executes **after** the original conversion and changes neither serving gather/RMS nor FC work; it is not a serving speed path for normalized or projected cache rows. Evidence: retained `host-text-disassembly.txt:93490–93551`.

## Existing hooks expose the necessary count1 inputs

The native full head has ABI `int32(model, host_tokens, count, position)` at `0x17db310`. The existing `cached_head` detour already reads the token and binds immutable table, embedding gamma, normalized input, projection output, seed and FC descriptor before calling the original head (`halogen0162_mtp_embedding_cache.c:293–329,406–425`). There is no separate whole-embedding function: the branch is inline in that head.

For the count1 wire-D branch, the current head/FC detours and kernel interposer can distinguish these operations:

| Operation | Kernel identity / return RVA | Checked user arguments |
|---|---|---|
| Embedding gather | `0x18d5b40` / `0x17db44e` | table `model+0x4f0`, device token `model+0x730`, output `model+0x6c8` |
| Embedding RMS | `0x18d5160` / `0x17db51c` | input/output `model+0x6c8`, gamma `model+0xae8`, width2560, groups1 |
| Embedding M1 | `0x18d6690` / original launch return `0x17fdba0` | exact original Q8 weight/input/output/K/N, grid160/block256/default stream |
| Native hidden RMS/FC | return `0x17db632` / `0x17db663` | remain original; hidden RMS shares the RMS identity but has distinct caller, pointers and width10240 |
| D seed-add | `0x18d5b58` / `0x17dbb96` | `args[0]`: embedding projection; `args[1]`: native hidden projection; `args[2]`: native residual |

Head/gather/RMS/FC construction is retained at text lines192146–192325; D seed arguments at192515–192605. The seed shader's signature is `const uint16_t*, const uint16_t*, uint16_t*`; it reads the first two arguments and stores through the third. `model+0x6c8` and token-device `model+0x730` have no later read within this head beyond the skipped embedding branch.

An already completed cache hit can therefore suppress only the exact gather, embedding RMS and M1 launches, and substitute the ready row in the seed-add's **first argument**. Native hidden computation, residual, layer48, histories, controller and acceptance continue unchanged. This source relationship avoids needing a private mutable head/rollback transaction. It does not itself qualify the new substitution or its output quality.

Do not rebind `model+0xb00` for the entire head: later mixer FCs write that scratch (`0x17dbe76`, `0x17dc017`) and final vocabulary work uses it. The seed argument substitution keeps those later operations on their original allocation.

## Smallest actual implementation gap

The gap is one new consumer mode across the existing hook bodies, plus its bounded startup artifact import:

1. An offline producer uses the qualified input preparation and existing embedding-only NPU session to emit a bounded token-to-projection artifact while the GPU engine is absent. It needs model/table/gamma/FC-weight/arithmetic identity, token IDs and BF16 result rows. The current scripts stop before this operation.
2. The engine owner imports those completed rows into private GPU allocations once after the HIP context exists and before timed serving, then binds their immutable lifetime to the live model generation. The existing64-row bound is327680 bytes, before events/runtime overhead. It does not require Windows/WSL shared-address aliasing or GPU/NPU concurrency.
3. Head entry selects only an already ready, same-generation count1 row. The kernel hook suppresses only the verified embedding launches and redirects the seed input; a miss executes the entire original branch immediately. Count>1 remains original.

For a preloaded first hit, retain original FC dispatcher execution and suppress its validated M1 launch, or establish an original miss before activation. Simply bypassing the dispatcher on that first hit would assume its lazy initializer/global side effects already occurred. Retaining the host dispatcher is the conservative source change and still removes the three GPU launches. Existing native cache hits bypass it only after original-output capture.

This mode has not been implemented. It still needs real engine validation and an output/acceptance-matched full-engine comparison to establish speed. A new isolated paired-FC accuracy series, the raw-table override, or another metadata gate framework would not implement the consumer gap.

## Early readiness and cost boundaries

For a dynamic producer, tokens are available at Target entry `0x17dd020`, before layers0..47. Automatic head replay uses shifted input IDs and a known next ID for nonfinal chunks; negative next-token sentinels leave the last row unknown. Verification entry already knows draft IDs, but accepted replay's correction remains unknown until target completion. Consecutive draft heads have no assured trunk lead. The pure planner encodes these exact cases (`halogen_mtp_early_token_schedule.py:62–98,101–149`). No retained measurement provides Target-entry-to-embedding-consumer lead `W`.

Offline precomputation removes that live lead requirement for entries already prepared, and avoids the currently unsupported Windows overlap. It trades one-time preparation/init/upload and bounded cache coverage against removed GPU work. The existing embedding-only NPU mean is0.9674 ms session and2.104775 ms complete diagnostic call, with approximately24.386 seconds cold initialization. The current original embedding M1 component is0.152995 ms; the full gather+RMS+M1 branch cost is not measured. These values do not establish engine tok/s or a full-branch speed bound.

The corrected portable RMS helper matches the exact64 retained original native rows; broader native RMS/`v_rsq` parity remains unproved. Existing NPU embedding A/B outputs pass frozen tolerance but differ in847/858 BF16 words, and no full-head proposal/acceptance result exists. The new consumer must be evaluated as its actual engine change, not promoted from those component receipts.
