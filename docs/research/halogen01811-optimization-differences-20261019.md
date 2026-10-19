# Halogen patch and performance differences — 19 October 2026

The earlier speed has not yet been restored. This follow-up found and corrected a stale convenience launcher, ruled out a lost N-gram reader setting, and prepared the newly released 0.18.11 with fresh WSL adapter bindings. It contains no new inference measurements. The selected Gemma service was preserved throughout.

The [historical regression audit](halogen01810-historical-regression-20261019.md) binds the retained requests, configurations and timing records. Its same-8K-message comparison is 1866.53/48.42 reported prefill/decode tok/s and 7.05 seconds whole HTTP in the old 0.16.2 run, versus 1211.77/40.87 and 9.94 seconds in 0.18.10. The old engine also became slower without a version change. That rules out attributing the entire gap to an upgrade. API phase clocks remain independently unqualified; the whole-request gap is real. Different output trajectories limit a same-work decode comparison.

## Which patches are actually present

| Mechanism | Verified state | What it establishes |
|---|---|---|
| Private WSL mapping and host registration | Preserved from fast 0.18.5 into 0.18.10 and the new source port | The adapter still permits the required memory registration. It does not supply faster arithmetic kernels. |
| Hybrid device weight placement | The 64-GiB copy cap, 64-MiB transfers, reclaim policy and private mapping remain | There is no identified dropped residency patch. Allocation bytes do not prove physical residency or equivalent operating state. |
| Diagnostic GEMM routing override | Normal serving removes the diagnostic runner's override | The source does not accidentally force the diagnostic GEMM-disabled route during normal serving. Actual native dispatch still needs live evidence. |
| N-gram reader count | Fresh native getter audit proves missing variable means **64** in both 0.18.5 and 0.18.10; explicit values clamp to 1–256 | Omitting the old explicit `HALOGEN_NGRAM_GATHER_THREADS=64` did not reduce the native default. `HALOGEN_PREFILL_GATHER_THREADS` is absent in both retained binaries. |
| MTP depth2 / gate0 / PLD3,3 | Present in the actual 0.18.10 measured profile and manifest | No serial fallback was found. This does not prove every internal native backoff branch. |
| Confidence90, mode0 and NPU candidates | Rejected or experimental candidates remain disabled | They are not accumulated speed gains. Earlier unfavorable or incomplete results do not justify enabling them by default. |

The reader getter proof inspects exact ELF function boundaries, bytes and disassembly; it does not execute an engine. Source differences in the WSL registration patches concern version-specific image hashes, instruction locations and profiles. The normal service implementation otherwise retains its memory path. The new 0.18.11 hook was mapped separately against the extracted binary: eight finite functions and 1900 instructions were compared with 0.18.10. This finite proof does not establish every indirect callback or full runtime equivalence.

## Actual configuration and operating-state differences

The fast 0.18.5 natural16K run used a 4K arena, Vision Off and global Cache Off. The recent 0.18.10 run used an 8K arena, Vision On, and global Exact cache with request `no_store`. `no_store` is a request policy; it does not replace the global cache mode. Those differences have not been isolated as causes of the historical gap. A later rollback to 0.18.5 also failed to reproduce its earlier fast state.

The original 0.16.2 fast run used a 32768-token arena. The prepared arena comparison changes **both** `prefill_chunk` and `max_prefill_tokens` from 8192 to 32768 while holding the other current settings fixed. Only changing the chunk would not enlarge the arena. No gain is inferred before that comparison completes, and no high number from a different serial/decode workload is combined into a fictional joint result.

The retained [conditioned-control telemetry](halogen-conditioned-control-20261005.md) reports approximately 1634 MHz/54 W in its slow measured windows, versus 2677 MHz/136 W in a separate earlier control. The exact 48.42 tok/s Stock A cohort has no matched telemetry. These observations motivate capturing GPU clock, power and temperature alongside the next finite comparison; they do not prove throttling or prescribe a power/voltage change. The current Windows power scheme is `REV:N Performance`; a scheme name alone does not establish effective GPU behavior under load.

All 478 old shipped GEMM plan records survive byte-identically in 0.18.10. Missing old plan records are therefore not an identified cause. Their presence does not prove which native kernel or plan was selected in a live request. That remains an important distinction when comparing fast and slow operating states.

## Corrected launcher

`scripts/Start-Halogen-ServiceNow.ps1` previously defaulted to 0.18.8 and rejected explicit 0.18.10 before launching. The measured 0.18.10 cohorts used a different, verified managed path, so this defect did not cause their slowdown. It could, however, make a user's convenience command start an older version.

The correction admits 0.18.10 and 0.18.11 through every relevant version gate, preserves Fixed2/depth2/gate0/PLD3,3 and Thinking propagation, and changes the convenience default to the last runtime-qualified version, 0.18.10. The manage/controller additions only admit the separate 0.18.11 package. They do not change the active profile or restart Gemma. PowerShell parsing, declaration-only parameter binding and independent Python-AST/source review cover the correction; no launcher body was run by those checks.

## What 0.18.11 adds

[Upstream 0.18.11](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/v0.18.11/CHANGELOG.md) fixes lost draft-head context after relocation of a long conversation in the prompt cache. It can address decode degradation following that event. It does not establish the cause of our cold, no-store singleton gap. The author's [performance comparison](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/v0.18.11/docs/performance.md) is essentially flat for singleton work; its larger gains concern three/four simultaneous requests. Those aggregate rates are not per-request decode rates.

The exact linux/amd64 image is pinned to `sha256:a5797467d2bff173e0c661d9700292bd55eac305faff68c86261ae35385ad6ad`. Root extracted its binary/API, verified the fresh seam, built all four adapter products and installed the separate backend without an engine start or model download/rehash. Its live engine/provider qualification remains false. The convenience launcher therefore does not promote it automatically.

Gufo's [resident-runtime-buffer PR653](https://github.com/gufo-org/gufo/pull/653/files) is not a transplantable flag fix for this WSL adapter. Its native KFD queue path differs from DXG; the local DXG thunk gives `NonPaged` IPC/export semantics and rejects it for the inspected host-registration API. No unsupported pinning or driver modification was added.

The next hardware step is a single authorized, instrumented 0.18.11 arena comparison using the frozen 8K/16K requests, excluded warmups and three measurements per case. It must retain output hashes, actual token counts and acceptance scopes, and restore the selected Gemma service afterward. The already-asked specific Gemma interruption question remains the execution gate. No new token-rate or NPU speedup claim follows from this preparation.
