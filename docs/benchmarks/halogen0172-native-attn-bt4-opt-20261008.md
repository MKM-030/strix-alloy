# Halogen 0.17.2: native Attention BT4 OPT0 comparison

The sole native `HALOGEN_ATTN_QS_BT4_OPT=0` candidate establishes no qualified serving gain. It remains disabled; the normal server is ready and open with its visible request-log console.

Stock → candidate → stock. Each window has one separately excluded warmup and three measurements: 8,192 actual synthetic input tokens, 128 normally generated output tokens, temperature 0, seed 1, Thinking Off and Cache Off. The input is finite-vocabulary pseudoprose with 116 repeated ` a` calibration prefix units. The output is a non-copying story. Capacity 262144, MTP2/PLD3,3 and chunk/arena 8192 remain fixed.

| Window | Raw API Prefill tok/s | Raw API Decode tok/s | QPC request wall s | Combined acceptance |
| --- | ---: | ---: | ---: | ---: |
| before | 1157.22 | 43.94 | 10.0734 | 210/339 = 61.95% |
| candidate | 1237.42 | 43.13 | 9.5956 | 210/339 = 61.95% |
| after | 1225.98 | 43.00 | 9.6908 | 210/339 = 61.95% |

Independent read-only review rehashed all 21 retained raw input files and reproduced environment, output, accounting and timing calculations with no material mismatch. Its sealed assessment is attached to the JSON.

Candidate versus pooled stock, descriptively: raw Prefill +3.85%, raw Decode -0.79%, independent whole-request QPC wall -2.90%. Against stock-after only, raw Prefill is +0.93% and raw Decode +0.30%; QPC wall is -0.98%.

These are not established gains. Stock Prefill drifts +5.94% between bookends; stock-before Prefill standard deviation is 118.15 tok/s. Its first measurement is retained, not discarded. The after-only difference is small relative to observed variation. No additional cohort was run to erase the unstable baseline.

Candidate repetition 2 has MONOTONIC/RAW factor 1.00829194765. Applying whole-request calibration gives candidate means 1240.79 Prefill / 43.25 Decode tok/s, assuming uniform phase scaling. These normalized candidate phase rates and related deltas are estimates, not qualified post values. Raw rates, every clock endpoint and independent QPC times remain in the JSON. Both stock windows have factors approximately 1. A timestamp offset is not a restart reason.

All twelve requests, including warmups, have identical full emitted-text hashes and 70 accepted / 113 drafted tokens per request. Acceptance is combined API MTP+PLD, not isolated native MTP. This proves output/accounting parity for this frozen workload; internal logits, state and general numerical equivalence are unproved.

Bounded source inspection identifies a complete native attention alternative with 140 versus 168 VGPRs, unchanged 27 SGPRs / 14928-byte LDS / zero spills, identical argument layout, buffers, grid, block and one launch. Lower register pressure was the concrete hypothesis. No new runtime dispatch capture or individual GPU timing was taken. No custom kernel, binary patch, extra preload, weight edit, NPU helper or startup-floor study occurred.

The unchanged normal lifecycle restored the original profile after measurement. This candidate will not be repeated unchanged. The full acceleration goal remains unachieved.
