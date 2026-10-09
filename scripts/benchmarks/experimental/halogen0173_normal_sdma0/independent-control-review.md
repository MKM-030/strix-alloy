# Independent SDMA comparison control review

Source-only review, 2026-10-09. No new material launch/control/window defect was found in the requested scope. This is a source review, not execution, measurement, runtime readiness or gain qualification.

`launch.py:25-33` receives the unchanged normal manifest, requires the pinned 0.17.3 image/context/single slot/preload chain and SDMA1, rejects BN64 environment markers, and changes only `environment.HSA_ENABLE_SDMA` from `1` to `0`. It records separate candidate metadata. `62-69` validates the original normal controller command and constructs one fresh `CandidateChild` through the normal `JobChild` superclass. `server/owned_child.py:10-13` creates and resumes one fresh `OwnedProcess`; no existing process owner is reinitialized. `server/controller.py:317-363` confirms the translated normal service arguments, and candidate `79-82` preserves those arguments for the pinned profile. The normal singleton/controller/service paths remain in use, including the existing startup floors at `launch.py:73` and the standard service lifecycle.

`control.py:27-46,63-83` binds saved controller/backend identities and the controller run ID, uses the normal stop request, and waits for the corresponding terminal controller/backend and cleanup/recovery receipt. Candidate and stock manifests require the correct SDMA value and candidate marker. `86-100` starts the normal visible after console after terminal cleanup.

`window.py:68-108` pins profile, prompt, request and client identity. Before supplies the output/counter/finish baseline; all four requests in every arm must match it. `116-176` keeps one excluded warmup plus three measured rows, entry/runtime reserve receipts, unchanged controller run ID, authenticated idle health, exactly four new completed requests and no added cancellations. Reported Prefill/Decode means are the native API values; no clock normalization or acceptance-times-rate metric is introduced.

The material reporting limit is explicit: `window.py:167` sets `passed=True` for completed collection/equality checks. It does not implement the plan's 0.1% clock qualification. `scripts/benchmarks/clock_probe.py:16-23` retains per-request MONOTONIC/RAW and RAW/QPC evidence but its generic RAW/QPC guard allows a 10 ms floor or 0.2% plus handshake uncertainty, and it does not gate MONOTONIC/RAW spread. **Agreed disposition: the final analyzer must separately apply the plan's 0.1% clock comparability/RAW-QPC criterion to the retained rows before any native-rate serving-gain qualification. Keep raw rates and clock evidence separate; do not normalize, repeat an incompatible completed cohort, or modify the sealed collection client.** No final analyzer source was present in WORK at this review, so implementation of that future guard is not claimed here.

All eight existing `seal.json` input byte counts and SHA-256 values matched during read-only verification. Inspected source references below are repository-relative to `C:/Projects/strix-alloy-clean`; no existing file was edited.

| Input | Bytes | SHA-256 |
|---|---:|---|
| WORK/launch.py | 4450 | `16f8e8eca306b4cb568adaa8bbef6505a4cd39b7953c21e77dab4d4b8d4a06f4` |
| WORK/control.py | 7048 | `65260373ae2033839aae989dc9b6d10b665f310584a7020d4ba91d73fa10151e` |
| WORK/window.py | 12061 | `f7142d05e8c490d032a1ef485e1b7e535b82641ac726ffdf32506e6a474ca3b0` |
| WORK/plan.md | 2041 | `ea709cb83b865418ecd5dddac10c2529c57149be7cd15cb609813c6afd46bb1d` |
| WORK/seal.json | 2208 | `00237a35ba069fd5a53e4ea9da68b90f849b5197cadf8c6d4ef18f2c0bcaa04b` |
| server/owned_child.py | 1968 | `6f75520f65c76941ec4306915929fd529ec7f46bd0fd20bd6f01f82afb749f10` |
| server/controller.py | 31934 | `fb53a9c47e1abaffb1a597a2f50434621a850870bc0280e1f6a4576cf128c7fc` |
| scripts/benchmarks/clock_probe.py | 1709 | `a3f32a4c5c7e423c47ceebdd2f0fe0cd1860d7840c9fd0de10756e887c70a05e` |

WORK is `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/normal-sdma0-comparison-20261009`. Only this new review was authored. No imports of target scripts, tests, builds, analyzers, hardware, API, lifecycle, STATE or Git operations were performed.
