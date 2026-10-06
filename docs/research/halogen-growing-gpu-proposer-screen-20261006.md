# Growing GPU drafter: complete correction cost

The distinct growing256-to512 GPU drafter was implemented and measured once on the frozen raw-ID continuation. It remains disabled: complete core cost was **34.280 ms/round**, above the deliberately generous **31.759 ms/round** planning allowance. No Halogen Prefill, Decode or native-acceptance gain was measured or adopted.

| Component | Measured mean |
|---|---:|
| Initial256 prefill, paid once | 28.941 ms |
| Three-ID proposal, two consumed speculative inputs | 10.148 ms |
| Complete resolution, all15 rounds | 22.202 ms |
| Append resolution, six rounds | 4.717 ms |
| Both-cache rebuild resolution, nine rounds | 33.859 ms |
| Seed-amortized proposal plus complete resolution | 34.280 ms/round |

The pass contains an excluded `prefill256 â†’ propose3 â†’ resolve` warmup, one measured initial prefill, then 15 chained count3 proposals and complete current-round authoritative replay operations. All 37 authoritative IDs were applied; history ended at 293. There are 45 predictions,44 label positions and one unscored final third ID. Every correction is included, including opening-rejected proposals and the final round.

The model made22 exact prefix matches out of44 scored positions;19 occur in rounds with offline opening-reference equality. These are **offline label matches**, not native draft acceptance. The retained stock trace already has 22 accepted draft IDs. Actual native hit/count/readiness eligibility and target contention were not measured. In particular, round 12 matches all three future labels but its retained round commits one ID and fails offline opening-reference equality; it correctly rebuilds.

The rejection allowance assumes at most four target outputs per round against 37/15 retained stock outputs and uses a historical 48.2804 tok/s reference. It is an optimistic cross-cohort planning ceiling, not measured native seam time or a speed prediction. The complete core already exceeds it before packet transport or main-model contention. No live engine cohort is justified for this realization.

The AMD Radeon 8060S Vulkan realization requested and logged 25/25 layer offload; CPU-host output handling remains visible. Startup, excluded warmup, F32 snapshot I/O and full child duration are recorded separately in the JSON. Snapshot writes took46.455 ms across all 34 commands and are excluded from command cost. The prior full-F32 append/fresh numerical discrepancy remains a known separate-model limitation; no original projection tolerance was relaxed.

Device assessment: GPU has the best measured independent-proposer cost but this growing policy still fails; earlier CPU 45.09 ms and NPU 67.68 ms proposal-plus-one-append proxies already fail the generous budget. Those routes were not rerun. This mechanism supplies no target Prefill improvement and removes no target weights. The small independent model has its own weights. NPU-local SRAM is not additional exposed GPU memory.

Root normally stopped the exact original controller, ran one finite Vulkan child with 22 GiB admission and 18 GiB runtime floors, closed the owned job, and restored the original with unchanged 44/131 GiB stable 60 admission. The original is **ready/open on port 8840**, with the same 262144-capacity arena 8192 profile. No observation timeout triggered another start. The standalone adapter is not integrated into the original server; no engine injection or driver change was made. Automation remains paused and the full acceleration goal is unachieved.

Raw evidence: `C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004\growing-gpu-component-debbe529453644b0b6b87b2fbedcddcd`. Exact source/model/DLL/command pins, individual drafts, native calls, timings and current server identities are in the [JSON](halogen-growing-gpu-proposer-screen-20261006.json).
