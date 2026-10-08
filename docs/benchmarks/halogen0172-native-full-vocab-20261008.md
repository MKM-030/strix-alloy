# Halogen 0.17.2: native full-vocabulary MTP comparison

The single native `HALOGEN_DRAFT_VOCAB=0` candidate establishes no qualified serving gain and remains disabled. The normal 0.17.2 server is restored, ready and open in its visible request-log console.

Linked stock → candidate → stock, with one excluded warmup and three measured requests per window. The before arm reuses the immediately preceding I4R stock-after four requests, with unchanged run/profile/request identities recorded in baseline-link.json. It is not a fresh independent baseline. Each request has exactly8,192 synthetic input tokens and128 normally generated output tokens, temperature0, seed1, Thinking Off and Cache Off. Input is finite-vocabulary pseudoprose with116 repeated ` a` prefix units for token calibration; it is not natural prose or a wholly repetition-free prompt. Output is a non-copying story. Capacity262144, MTP2/PLD3,3 and chunk/arena8192 are unchanged. V2 mode remains at its default.

| Window | Prefill tok/s, normalized | Decode tok/s, normalized | Raw API Prefill | Raw API Decode | Request wall s | Acceptance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| before | 1233.35 | 42.55 | 1233.35 | 42.55 | 9.6808 | 210/339 = 61.95% |
| candidate | 1232.12 | 39.99 | 1232.12 | 39.99 | 9.8882 | 207/345 = 60.00% |
| after | 1233.35 | 42.68 | 1219.35 | 42.22 | 9.6781 | 210/339 = 61.95% |

Compared with the two stock means, candidate Prefill changes by -0.10%, Decode by -6.17% and whole-request time by +2.16%. Individual samples, spread, clock factors and memory minima are retained in the JSON.

Acceptance is the combined API MTP/PLD counter. The greedy output matches for all twelve requests. That establishes parity for this frozen workload; it is not a general numerical equivalence or quality claim.

Normalized phase rates use contemporaneous guest MONOTONIC/RAW calibration validated against Windows QPC. Calibration covers the whole request, so phase rates assume uniform clock scaling. Raw API rates and independent end-to-end QPC times are retained separately. A guest timestamp offset is not a restart reason.

Stock-after repetition3 has a material MONOTONIC/RAW factor1.034577215; its phase correction is not measured separately. The stock-after normalized phase means are estimates and are not promoted as new post values. Linked stock and candidate factors are approximately1; their descriptive Decode difference is about−6.03%. Independent QPC wall regression remains about+2.16% against both stock means. No extra run was added to erase clock variation.

The candidate uses the existing original HT4 MTP projection over all248,320 rows, instead of the reduced group (48,082 rows for English). It bypasses added BF16 staging and Q4 repacking, reuses the original head/logits/scratch and leaves target projection/verification unchanged. The single control changes shortlist coverage, representation/kernel and skipped initialization together. The result does not identify excluded English tokens or isolate one of those causes. The normal manifest records the exact setting and pinned engine/image; no runtime kernel dispatch capture was made and no individual GPU kernel speed is claimed.

No custom kernel, binary patch, extra preload, weight edit, NPU helper, driver installation or startup-floor study occurred. The 35/131GiB startup floors and18/18GiB runtime reserves were retained. Game/competing GPU-load observations precede each window.

The historical48.42Decode tok/s result remains a0.16.2 result. It is not relabeled as0.17.2. This completed candidate will not be repeated unchanged. The broader acceleration goal remains unachieved.
