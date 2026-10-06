# Checked-copy completion attempt — 6 October 2026

The completion attempt failed the full serving comparison and exited 1. The candidate recorded **+1.185202% Prefill and +2.168056% Decode against stock-before**, but these are **not qualified gains**: the matrix rejected a System PID4 Copy-engine sample and no stock-after measurement was run. Complete hit/skip coverage was not retained. The original server was restored ready, idle and open. The [earlier failed screen](halogen-checked-copy-screen-20261006.md) is preserved unchanged.

This report is a CPU analysis of retained responses and receipts. It performed no hardware/provider/engine operation, build, new test, installation or lifecycle action. The [JSON companion](halogen-checked-copy-completion-20261006.json) contains per-sample figures, exact identities and raw SHA256 pins.

The workload was exactly 16384 once-only natural input tokens from the retained War and Peace corpus plus trailing story task, 128 output tokens, capacity 262144, one slot, temperature 0/seed 1, Thinking Off, Cache Off, MTP depth 2/PLD 3,3 and arena/chunk 8192. Each completed window retained one excluded warmup and three measured requests. The consumer, projection rows and tolerances were unchanged. The candidate used `ready64-v1`/`fixed-v1`/`checked-copy-v1`, 52 original GPU rows, Origin 1 and capacity 64. It imported 266784 artifact bytes once, retained 327680 GPU row bytes and omitted per-hit event queries. No NPU executed.

| Retained three-request mean | Stock-before | Checked-copy candidate | Observed partial change |
|---|---:|---:|---:|
| Calibrated Prefill, tok/s |1185.759997|1199.813645|+1.185202%|
| Calibrated Decode, tok/s |35.966064|36.745828|+2.168056%|
| QPC request wall, seconds |17.469954400|17.202457667|−1.531182%|
| Native prompt time, ms |15163.366667|14886.700000|−1.824573%|
| Native decode time, ms |3908.700000|3798.200000|−2.827027%|
| Acceptance, measured total |186/387|186/387|Unchanged 48.062016%|

These are arithmetic means of all three measured per-request values from [stock samples](../../server/.local/optimization9h-20261004/checked-copy-natural16k-eddb92fa20a94e7882bf6a14e1f13f95/stock_before/measurement/samples.json) and [candidate samples](../../server/.local/optimization9h-20261004/checked-copy-natural16k-eddb92fa20a94e7882bf6a14e1f13f95/candidate_checked_copy/measurement/samples.json). Warmups are excluded from those means; no measured samples were removed. QPC request-wall totals were 52.409863200 and 51.607373000 seconds. The rates retain the existing guest raw-clock/Windows-QPC calibration. This incomplete comparison supplies no causal gain or general token-coverage claim. Target Prefill is outside the changed count1 MTP branch; no intended Acceptance improvement follows from exact projection reuse.

All eight raw response texts, including both warmups, were independently compared and hashed. They are identical 543-character texts with output SHA256 `bc179b2873f085833dbd1ec05e9aba7703957dfafafdab71bba3d3cfb2f32e4d`. Every response reports 16384 input/128 output tokens, 62/129 accepted drafts, `finish_reason=length`, Cache 0 and Disk-Restore 0. Request SHA256 `3893472a32bac55600fa874f915fbd5ef13c7b7c6a64bff1d25983cc06235fac` and prompt SHA256 `cbaeec7395187803e2e570d3f5554b45d2eb99e5fa80b61c370c7fe87390a663` agree throughout.

The [runtime observer](../../server/.local/optimization9h-20261004/checked-copy-natural16k-eddb92fa20a94e7882bf6a14e1f13f95/candidate_checked_copy/gpu-runtime.jsonl) recorded **System PID4 Copy 2.628345930526%** at **2026-10-06T10:07:29.2052859Z**, instance `pid_4_luid_0x00000000_0x00011884_phys_0_eng_1_engtype_copy`. Its process list was empty and its sole WSL VM worker identity was PID 20968, birth 08:59:26.9915840Z. The sample's ownership is unresolved: it is not proven to belong to Halogen or another application. The 2% Copy-engine rejection remains a failed admission; the sample was neither discarded nor relabelled as harmless.

The candidate's retained Guest-UTC warmup bracket ends 10:07:29.1590564; measured request 1 begins 10:07:29.1859608 and ends 10:07:46.5818038. The observer timestamp nominally follows these first two boundaries by 46.229ms and 19.325ms. Measured request 1's Windows-QPC bracket is 155895.3868361–155912.6357716. **This does not establish whether the underlying GPU activity occurred exclusively during warmup or measured request 1.** The watcher records Windows UTC after `Get-Counter`; request UTC comes from WSL `time.time()`. GPU-QPC, the original PDH timestamp and its integration interval were not saved. Guest-UTC and QPC are not continuously equivalent: candidate request 3 spans 44.602820 seconds in Guest-UTC versus 17.124542 seconds in QPC. This timestamp limitation does not replace the retained raw/QPC request calibration or permit filtering.

The [matrix receipt](../../server/.local/optimization9h-20261004/checked-copy-natural16k-eddb92fa20a94e7882bf6a14e1f13f95/matrix-result.json) records `passed:false`, `RuntimeError: Runtime GPU interference contaminated window`, `original_ready_open:true`, `recovery_pending:false` and no adoption claim. Root's executor session 97096 exited 1. Candidate after-counters and stock-after samples are absent, so no nonzero complete hit/skip/miss coverage or stock bookend comparison can be claimed.

Normal candidate stop and original restoration completed. The [final-ready receipt](../../server/.local/optimization9h-20261004/checked-copy-natural16k-eddb92fa20a94e7882bf6a14e1f13f95/final-ready.json) records gateway/controller PID 27772, backend PID 24596, container `6b7a2377c786511d87d58f766eb0ca04364edf89494820eea650cb8d3605204f`, both phases ready, active requests 0 and open:true on port 8840. The restored stock profile SHA256 is `1f97d1a2a59ef75bbc2927adee943f8d0f0ca75f82a1a0012b7c06a71d6e09c6`; preload contains only the original preflight and hybrid shim, without the checked-copy consumer.

| Raw receipt | SHA256 |
|---|---|
|Matrix result|`2d87b50ac5f9bbde7b5ef795af5b3da9be7736965a8b4bb53c9c393442c52572`|
|Stock samples|`13fcecdf6a85d74adbab13a9bbc3edd9d9dd51a9184dbc35814cbd3401c66ead`|
|Candidate samples|`b725bf038863bd2b91ce371b08bb47c41155cb4ec27bf30d25a29c216c604952`|
|Candidate GPU runtime|`b6fcec9bc8089a9ef4b59306c95816b9982c43a20a96f07f54c060a9b439eaf4`|
|Final ready|`863603b0390e8170f6efa566fd816928d114d1578176f335d945f84ee434973d`|

Root's subsequent authenticated public health receipt at 2026-10-06T10:20:16.7277973Z returned HTTP 200, status ok and context 262144, with requests 0, draining:false and completed 2. See the [fresh public-health receipt](../../server/.local/optimization9h-20261004/public-health-restored-6840445985dd402c8d8cf421c96b5f36.json), SHA256 `4fe075d58e024a3e4988a3713161cc9f25a36e24d45d95359387642b40cbce20`. This report reads that receipt; it issued no health or inference request.

The different investigation now is **supported Windows GPUView/ETW attribution**, to resolve the System Copy-engine event's provenance and time interval. Microsoft documents GPUView analysis of ETL video/kernel events, GPU command-buffer submissions and driver command-buffer timing. [Microsoft GPUView documentation](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/using-gpuview). This is a documented investigation direction, not evidence that attribution or trace capture has succeeded. The separate [attribution assessment](halogen-gpu-copy-attribution-20261006.md) records root's read-only capability checks: WPR has the GPU profile and no recording is running, but the current process is not elevated and lacks SeSystemProfilePrivilege; GPUView/WPA were not found on PATH or the checked standard WPT paths. Those checks are not an exhaustive inventory. This reporting pass installed no tool and collected no trace.

No observer weakening or unchanged retry is recommended. No NPU production or origin comparison is qualified by this failed consumer comparison. The full acceleration goal remains unachieved.
