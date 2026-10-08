# Halogen 0.17.2: native I4R fallback comparison

The single native `HALOGEN_I4R_LAST=0` candidate establishes no qualified serving gain and remains disabled. The normal 0.17.2 server is restored, ready and open in its visible request-log console.

Stock → candidate → stock, with one excluded warmup and three measured requests per window. Each request has exactly 8,192 synthetic input tokens and128 normally generated output tokens, temperature0, seed1, Thinking Off and Cache Off. Input is finite-vocabulary pseudoprose with116 repeated ` a` prefix units for token calibration; it is not natural prose or a wholly repetition-free prompt. The output is a non-copying story. Capacity262144, MTP2/PLD3,3 and chunk/arena8192 are unchanged. V2 mode remains at its default.

| Window | Prefill tok/s, normalized | Decode tok/s, normalized | Raw API Prefill | Raw API Decode | Request wall s | Acceptance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| before | 1216.95 | 43.54 | 1216.95 | 43.54 | 9.7026 | 210/339 = 61.95% |
| candidate | 1230.52 | 42.48 | 1230.52 | 42.48 | 9.7057 | 210/339 = 61.95% |
| after | 1233.35 | 42.55 | 1233.35 | 42.55 | 9.6808 | 210/339 = 61.95% |

Compared with the two stock means, candidate Prefill changes by +0.44%, Decode by -1.33% and whole-request time by +0.14%. Individual samples, spread, clock factors and memory minima are retained in the JSON.

Acceptance is the combined API MTP/PLD counter. The greedy output matches for all twelve requests. That establishes parity for this frozen workload; it is not a general numerical equivalence or quality claim.

Normalized phase rates use contemporaneous guest MONOTONIC/RAW calibration validated against Windows QPC. Calibration covers the whole request, so phase rates assume uniform clock scaling. Raw API rates and independent end-to-end QPC times are retained separately. A guest timestamp offset is not a restart reason.

The candidate uses a complete existing native alternative, including a routing change, four projection/activation/fold stages and optional native preparation. Source analysis found lower register/LDS use in its projection kernels but also additional launches and explicit intermediate traffic. This was a concrete computation hypothesis, not an inference from a mode name. The static resource difference did not establish a serving benefit. The normal manifest records the exact setting and pinned engine/image; no runtime kernel dispatch capture was made and no individual GPU kernel speed is claimed.

No custom kernel, binary patch, extra preload, weight edit, NPU helper, driver installation or startup-floor study occurred. The 35/131GiB startup floors and18/18GiB runtime reserves were retained. Game/competing GPU-load observations precede each window.

The historical48.42Decode tok/s result remains a0.16.2 result. It is not relabeled as0.17.2. This completed candidate will not be repeated unchanged. The broader acceleration goal remains unachieved.
