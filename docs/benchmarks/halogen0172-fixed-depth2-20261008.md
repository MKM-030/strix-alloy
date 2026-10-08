# Halogen 0.17.2: fixed MTP depth 2, matched 8K comparison

Actual input: **8,192 synthetic pseudoprose tokens**, including116 repeated ` a` prefix units for token calibration; context capacity: **262,144**. The previous description as non-repeated prose was incorrect. Output is a normally generated, non-copying story. v2 checkpoint, one slot, chunk/arena8192/8192, MTP2, PLD3,3, Cache Off, Thinking Off, temperature0/seed1. Each cohort has three measured repetitions and one excluded warmup. Timings and original requests are unchanged.

| Window | Serial TG1 prefill tok/s | MTP TG128 prefill tok/s | MTP TG128 decode tok/s | API MTP+PLD acceptance |
| --- | ---: | ---: | ---: | ---: |
| 0.16.2 before | 1284.94 | 1245.52 | 41.22 | 207/345 = 60.00% |
| 0.17.2 candidate-ready | 1232.58 | 1199.00 | 43.73 | 210/339 = 61.95% |
| 0.16.2 after | 1296.43 | 1257.59 | 40.55 | 207/345 = 60.00% |

Prefill-only and the prompt phase of TG128 are separate measurements. Acceptance combines API MTP and prompt-lookup draft counters; it is not isolated head acceptance. All serial/MTP and cross-version greedy output hashes agree.

| Metric | Candidate vs before | Candidate vs after | Candidate vs mean of baselines | After/before drift |
| --- | ---: | ---: | ---: | ---: |
| Serial TG1 prefill | -4.08% | -4.93% | -4.50% | +0.89% |
| MTP TG128 prefill | -3.74% | -4.66% | -4.20% | +0.97% |
| MTP TG128 decode | +6.10% | +7.85% | +6.97% | -1.63% |
| Serial TG128 decode | -1.17% | -1.83% | -1.50% | +0.67% |

These are observed matched-window differences, not an estimate of statistical significance from three repetitions. Raw API rates, calibrated means/stdev, excluded warmups, MTP/serial decode differences and exact file identities are in the companion JSON.

| Window | Measured host RAM minimum GiB | Measured commit headroom minimum GiB | All recorded snapshots RAM/commit GiB |
| --- | ---: | ---: | ---: |
| 0.16.2 before | 24.40 | 113.89 | 24.40/113.89 |
| 0.17.2 candidate-ready | 24.26 | 113.56 | 24.26/113.56 |
| 0.16.2 after | 24.63 | 114.05 | 24.63/114.05 |

Memory minima are sampled host RAM/commit values, not VRAM peaks. Startup admission remains 35/131 GiB and runtime reserve 18/18 GiB. This comparison does not prove startup sufficiency exactly at 35 GiB. No NPU gain was measured. The companion JSON records the pinned candidate image/engine/API and the separately verified original restoration.

The earlier candidate directory records a harness startup error with zero completed benchmark requests. It contributes no throughput or acceptance value; its evidence is preserved.

Two initial engine starts also failed: a 600-second N-gram checksum startup timeout and an auth_api check that still pinned the 0.17.1 API source. Root corrected the API pin to the extracted 0.17.2 SHA256; compiled artifacts were unchanged. These preserved startup records contribute no speed value. The successful start reused the complete retained N-gram checksum receipt after matching size, device, inode, mtime and ctime; the whole checksum was not repeated and model files were not modified. Correction and installation receipts alone do not qualify runtime; the table uses completed measured windows.

The overall GPU/NPU acceleration goal remains unachieved: compare the separate prefill/decode changes above, and no NPU serving gain has been measured.

Evidence: the private fixed-depth2-comparison contract and before/candidate-ready/after raw windows. Prompt SHA256: 0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1.

## Original server restoration

Original Halogen **0.16.2** was restored through the normal lifecycle and verified ready, idle and open at 2026-10-08T03:31:07.223739+00:00. Its persistent Windows PowerShell 5.1 console remains open with request tracing enabled. Controller/backend/console PIDs at verification: 37336/32576/33900. Startup admission is **35 GiB available RAM / 131 GiB commit headroom**; runtime reserve is **18/18 GiB**. No new benchmark requests were made for this readiness checkpoint. The automation remains paused.
