# Halogen 0.16.2: regular 8K PLD comparison after reboot

The completed stock → prompt lookup off → stock comparison finds **no useful
PLD-off gain**. Retain stock `HALOGEN_PLD=3,3`. Both fresh stock controls restore
regular MTP decode to approximately **48.3 tok/s**, with **60% acceptance**.

| Cell | Serial PP8192/TG1 | MTP PP8192/TG128 | MTP decode TG128 | Serial decode TG128 | Accepted / drafted | MTP request wall |
|---|---:|---:|---:|---:|---:|---:|
| Stock A, PLD3,3 | 1873.178 | 1866.537 | 48.424 | 36.726 | 207 / 345 = 60% | 7.0541 s |
| PLD off, PLD0 | 1925.160 | 1884.410 | 48.232 | 36.992 | 207 / 345 = 60% | 7.0226 s |
| Stock B, PLD3,3 | 1923.585 | 1885.854 | 48.280 | 37.029 | 207 / 345 = 60% | 7.0166 s |

Rates are tok/s and means of three measured repetitions after one warmup per
cohort. The frozen workload is **8192 actual input tokens**, greedy prose,
seed1, thinking off, cache Off, native MTP depth2, default adaptation
`32,0.35,64`, one slot and **262144-position capacity**. Capacity is distinct
from occupied input; this is not a new 128K/260K input measurement. Decode is
the regular continuation, not the predictable synthetic output from the older
approximately 65 tok/s report. Prefill and decode are calibrated against the
retained host monotonic clock.

PLD-off decode is 0.396% below Stock A and 0.100% below Stock B. Its request
wall is 0.447% shorter than Stock A but 0.084% longer than Stock B. Acceptance
is identical in all cells. The descriptive bootstrap comparisons in the
[sanitized evidence](halogen0162-pld-stock8k-20261004.json) retain variation;
these small differences do not qualify an improvement. The PP8192/TG1 value
also shows stock drift, so PLD-off's higher value than Stock A is not promoted.
Acceptance is the combined speculative accepted/drafted counter, not a
separate native draft-head accuracy measurement.

All 12 request/prompt/output hashes, actual counts and finish reasons match
across all three cells. Serial and MTP continuations match within each cell.
This establishes deterministic parity for this fixed prompt; it does not
establish full-logit equality or a new broad quality-suite result.

All three cells completed with unchanged sealed sources and normal managed
cleanup/recovery. The complete matrix took **16.03 minutes**, including engine
loads and stops. Minimum observed physical availability was **28.318 GiB**;
minimum commit headroom was **123.348 GiB**, above the 18-GiB floor. The final
controller is stopped; post-run process inspection and Docker inventory found
no remaining owned inference process or running container.

The prior same-scope attempt failed before model creation at the corrected
44-GiB backend admission. It recorded approximately 42–44 GiB available,
no requests and normal cleanup. The user then rebooted at 16:49:41 Europe/Berlin.
The fresh post-WSL check recorded 50.444 GiB physical availability and
209.103 GiB commit headroom. Original failure evidence and its latch were
archived, not rewritten as successful measurements. These successful loads
do not prove that exactly 44 GiB is sufficient: they began with greater
headroom. No model, driver, BIOS, voltage or global WSL setting changed.

The earlier regular stock reference was 1661.018 PP8192/TG1 and 47.060 MTP
decode, also 207/345 accepted. Fresh stock values are higher, but the reboot
and intervening system state prevent attribution to a new inference
optimization. No comparable GPU temperature/power stream was captured for
this matrix, so no thermal or overclocking explanation is claimed.

Retained matrix: `server/.local/optimization9h-20261004/pld-stock8k-bookend-1742f9e165de45bea641446004e9733e`.
Plan SHA256: `6d253e8eaa0fef3ecc4ce6d5fdca4e3f86e9e20ec11cdf08161a75c3d1f8dbe6`.
This measurement establishes neither NPU integration nor a higher MTP
acceptance rate. Those parts of the optimization goal remain open.
