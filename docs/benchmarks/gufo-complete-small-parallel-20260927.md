# GUFO: complete answers and two small sessions

**Update, 28 September:** the [two-session measurement is now complete](gufo-parallel-20260928.md): native decode 32.60/39.08 tok/s; 57.84 whole-group output tok/s, +16.84% versus the same answers sequentially. Both answers match C1; width-2 batching and cleanup are confirmed. Earlier unsuccessful admissions below remain historical evidence, not the current completion status.

27 September 2026. Native Windows GUFO, the existing IQ4_XS Flash Next weights and shared Q8_0 MTP sidecar. These are short real prompts, **not PP2048/PP8192 or a standard fixed-length TG benchmark**. The original [standard PP results](gufo-pp-20260927.md) and [ten-prompt Halogen-corpus measurements](gufo-halogen-mtp-20260927.md) remain separate.

## Complete-answer qualification

One 4,096-token session, greedy seed 42, thinking off, cache bypass, MTP draft 3/min 1/full vocabulary/length policy. After one warmup, six fixed requests received a 1,024-token output allowance. One repetition per request; no spread estimate.

| Task | Input / output tokens | Native decode tok/s | MTP acceptance | Answer review |
|---|---:|---:|---:|---|
| Merge sorted lists, `code_a` | 31 / 376 | 51.79 | 92.18% | Complete, correct by inspection; not executed |
| Irrationality proof, `proof_a` | 24 / 703 | 51.62 | 88.57% | Complete, correct parity contradiction |
| RAID replacement, `proc_b` | 30 / 1,024 | 37.70 | 70.60% | Truncated; contradictory hot-swap warning remains |
| Speculative-decoding explanation, `prose_b` | 28 / 531 | 36.68 | 67.85% | Complete; useful high-level explanation with overgeneralizations |
| German prioritization, `DE` | 115 / 39 | 54.34 | 90.32% | Correct German JSON answer |
| Arithmetic JSON, `ARITH` | 47 / 14 | 52.94 | 90.91% | Exact sum/product 42 |

Raising the output cap fixed the previous truncation of the code and proof. It did not fix the RAID answer: preserve this failure, and do not execute its instructions. Successful transport and native counters are not whole-model quality certification. This stage has no same-corpus AR control, so it cannot attribute semantic errors to MTP or prove MTP speedup. Very short answers are not sustained decode measurements.

The run ended with owned exit 0, all seven requests recorded and memory recovery confirmed. At least 45.269 GiB Windows physical memory remained available; sampled adapter-wide committed peak 67.488 GiB and shared peak 4.125 GiB. The engine reported 67,701 MiB device use after load (66.114 GiB / 70.990 decimal GB). These counters have different scopes and must not be added. They are not a two-full-context capacity measurement.

## Earlier two-session admission attempts (27 September)

**At this historical checkpoint, all three admission attempts stopped before any model process or generation request.** The reviewed workload is one warmup, then the same `code_a` and `proof_a` concurrently, two 4K session capacities, one shared model. Intended occupied contexts remain much smaller than 4K. The requested 256k/260k capacity target is not part of this stage. No C2 rate, allocation or batching-success claim follows from these three refused attempts; see the 28 September update above for the subsequent successful run.

The first C2 admission was rejected before process creation or inference (`original_baseline:rising_residual`). Its last five baseline samples included a 512-KiB upward shared/committed GPU-memory step. Available physical memory was about 51 GiB; no capacity floor was breached. No inference result exists from that attempt. Its result, telemetry, consumed verification marker and clean recovery are preserved under `small-c2-mtp-d3-20260927-v1-runs/20260927T194542Z-fdeb062133d446f6a2d0bd4621b0d447`, result SHA256 `2D5EBE733145123AEE52029526F8F80C1CCCB7F6FFCDECBF1930D48CA4905AB8`. No guard sensitivity or threshold was relaxed.

After independent diagnosis/review, one fresh admission used exactly the same workload, argv, floors and trend/stability guards. It failed `baseline_unstable:available_physical_bytes`: the eleven baseline samples spanned 545,472,512 bytes (520.203 MiB), exceeding the existing 512-MiB stability tolerance. Host commit also varied by 1,114,947,584 bytes, exceeding its 512-MiB tolerance; the physical check failed first. It also failed recovery confirmation. Because no valid current baseline was established, recovery fell back to the historical original baseline; host memory had not returned to that older reference. **`cleanup_confirmed` is false and the blocking latch is retained.** This is not evidence of a GUFO memory leak: there was no model process or HTTP generation. All 69 telemetry queries terminated, and a separate read-only check at 19:53:05 UTC found zero GUFO/probe processes and no listener on port 8836. Do not equate process absence with the guard's memory-recovery certification.

Second admission evidence: `small-c2-mtp-d3-20260927-v1-admission2-runs/20260927T195059Z-ffb612d8d505475685dbaea057a67255`; result SHA256 `D2137DEC6DC4DA7014B206325161144A634611C3B325D8A692FDD37E8CB72A4F`. This checkpoint was followed by the separately reviewed active-desktop attempt below; original evidence and latches remain unchanged.

Independent saved-artifact audit: `C:\Projects\strix-alloy-research\reports\small-c2-admission2-audit-20260927.md`, SHA256 `6CAF317703D65D44CE85785F11CB29F80F4F4FB5BE95684220A109C4AFCEA9DE`. It confirms the admission/recovery diagnosis and zero model/HTTP work; it does not clear the latch.

### Reviewed active-desktop attempt, 20:37 UTC

The renewed user instruction led to a narrow reviewed correction: classify the exact prior no-model outcome without claiming memory recovery, and allow bounded desktop variation in a fixed eleven-frame window. This adds physical/commit variation reserves of 1/2 GiB, requiring 50 GiB free physical memory and 91 GiB commit headroom before launch. The 73/4/20 GiB model envelope, runtime 24/12 GiB floors and post-model recovery rules remain unchanged. Default launchers and historical failure latches are not bypassed globally.

The actual launch attempt refused on its **first** fresh frame: 49.786701 GiB free physical memory, **218.417969 MiB short of the reviewed 50 GiB admission requirement**. Commit headroom was 207.299442 GiB. This was `desktop_baseline_admission:desktop_physical_reserve`, not a measured GUFO allocation failure. No child, model load or HTTP request occurred. All 59 telemetry queries terminated (60 serialized rows include one duplicate pending-after-exit frame). Memory recovery against the historical baseline was again unconfirmed; the new `incomplete.json` remains. A subsequent read-only process/port check found no GUFO or probe process and no listener on port 8836. No retry or threshold reduction was performed.

Evidence: `small-c2-active-desktop-20260927-v1-runs/20260927T203739Z-df3bb0bc60474298a15928a86e934e54/result.json`, SHA256 `36D2835AEB1190E46574AE0BF4115FD67A935384B5BEF444BF9C1A17C72BB252`. Independent audit: `C:\Projects\strix-alloy-research\reports\small-c2-active-desktop-audit-20260927.md`. C2 throughput and memory capacity remain unknown. The immediate prerequisite is sufficient fresh desktop headroom, not another model benchmark or a claim that GUFO uses more RAM than Halogen.

For the future matched comparison, the two C1 requests produced 1,079 native output tokens over 21.797 seconds from first submission to last completion: **49.502 end-to-end output tok/s sequentially**. This is a reference only, not a C2 measurement.

Group end-to-end throughput uses total native output tokens divided by first HTTP submission to last HTTP completion, including prefill, queueing and unequal tails. A fixed-window aggregate decode rate remains unavailable: no SSE-chunk counting or sum of per-request rates is substituted.

## Evidence and safety

Raw local C1 evidence: `C:\Projects\strix-alloy-research\reports\complete-answer-mtp-d3-20260927-v1-runs\20260927T193706Z-3afd151ef6a94b3e9b31a692f572e892`.

Result SHA256 `303D2148F8625D5A468D278C4EF513070D6D3EDE797511BDCB8F3ABD474B2DE2`. Independent audit: `reports/complete-answer-mtp-d3-20260927-v1-audit.md` in the research workspace.

Pinned source `cff564964e8506c0abb3e530cecb55332187ac6c`; executable `E7F5B899C54C747EE5038C0598016394D2A70F25EE69AFBB1E02859FD223D943`; TheRock 10.2/gfx1151. Exact source/model/sidecar/runtime identities, complete argv, request bodies, responses, counters and memory observations are retained in each run manifest/artifacts.

The user-approved minimum remains 49 GiB physical before launch, 24 GiB physical during runtime and 12 GiB commit reserve. The original 73/4/20 GiB GPU/host/shared envelope requires 89 GiB fresh commit headroom; the active-desktop variant additionally requires 50/91 GiB prelaunch for its variation reserves. Owned process tree only; fresh telemetry and five-frame memory recovery. No BIOS, carve, driver, persistent system settings or public deployment changed. These guards reduce risk; thresholds are not reserved memory or a driver-freeze guarantee.
