# Halogen and GUFO: backend-specific MTP tuning

Implemented and measured on 1 October 2026 on the existing BOSGAME Ryzen AI Max+
395, 128 GiB Windows/WSL2 host. Starting repository HEAD:
`f221eaba0a34fa7503b663aa751fdcbe6f6863e4`. Prior uncommitted PROJFIX work is retained.

## What changed

`server/draft_profiles.py` generates separate, opt-in profiles from existing
Halogen or qualified GUFO configurations. It preserves checkpoint paths, native
binary/DLL pins, authentication, capacity, slots, timeouts and memory placement.
It requests at least 18 GiB physical/commit reserve and preserves a stricter one.
No NPU work, driver change, new model download or engine binary patch is involved.

Halogen receives a validated optional draft depth through controller ->
Start.ps1 -> service.py -> `HALOGEN_MTP_DEPTH` in its container manifest.
The old environment remains unchanged when no depth is selected. The source
manifest was updated for the reviewed service change, not for a changed engine.
GUFO receives its own `--draft-tokens`, `--mtp-draft-vocab`, and `--mtp-policy`.
The GUFO-specific options are refused for Halogen. No `--tensor-split` is copied.

## Why this is not the PROJFIX memory selector

Halogen v2 retains its contiguous device-weight allocation and bounded uploads.
The existing w4b profile has a different copy/host-registration arrangement.
GUFO's inspected `device_model.cpp` allocates weight tensors with `hipMalloc`
and uploads with `WeightUpload`. Changing those allocations would need a distinct
engine implementation and qualification; the CLI does not provide PROJFIX's
per-tensor host selector. This implementation leaves both allocators intact.

## Matched measurement method

All short comparisons use 262144 allocated context positions, exact 512/2048-token
inputs including template, 128 generated tokens, one request at a time, temperature
zero, thinking off and prefix cache Off. Each cell has one excluded warmup plus
three retained measurements. Actual counts, no-cache condition and repeated output
hashes are checked. Inputs are carried from control to candidate. Runs are sequential,
not randomized A-B-A. No full occupied-262K or general sampled-quality claim is made.

Halogen phase rates are calibrated against Windows/WSL clocks using the existing
harness; raw counters and Windows wall times are retained. GUFO uses its native
Windows phase timers. Rates must not be attributed to clock corrections as an
engine optimization. All measured/slow samples are retained.

## Halogen v2: one draft token versus previous depth two

| Input | Previous MTP tokens/s | Depth-one MTP tokens/s | Change | Previous request | New request |
|---:|---:|---:|---:|---:|---:|
|512|43.0726|45.7010|+6.10%|3.4971 s|3.3086 s|
|2048|45.2421|46.6154|+3.04%|4.3846 s|4.2639 s|

Whole-request reductions are 5.39% and 2.75%. Both prompts and output hashes
match the control. Serial and MTP output hashes also match within the candidate
run, including warmups. The minimum recorded Windows availability was 36.60 GiB.
The recorded manifest confirms `HALOGEN_MTP_DEPTH=1` and unchanged
`HALOGEN_HYBRID_PROFILE=vgm64-v2-device64-v1`.
These short greedy results do not establish the best depth for every coding,
sampled, multilingual or long-context workload. Existing defaults remain selectable.

## GUFO candidates

The registered control uses draft cap 3, full vocabulary and the default length
policy. Changing only the cap to 1 produced 33.42/33.60 tokens/s against
33.45/33.01 at 512/2048 inputs: -0.09%/+1.80%, within a small noisy range.
It is available as an explicit profile but not presented as a clear speed win.

Keeping cap 3 while selecting the existing Latin draft vocabulary produced
35.04/33.28 tokens/s. A repeat after additional probes produced 34.97/33.73.
The repeated control and final aggregate are retained in the JSON.
The verifier still uses the full vocabulary. No target weights or precision change.
The sampled `survival` policy is exposed by the profile generator but was not
live-qualified by this greedy comparison; it is not enabled in these candidates.

Both short benchmark outputs matched the control. Additional German, Cyrillic
and prompt-requested JSON outputs were byte-identical across the control, cap-one
and Latin-vocabulary profiles. This is three synthetic probes, not a general
multilingual, schema-constrained JSON or sampled-distribution certification.
The Cyrillic probe's single wall-time sample rose from 0.924 s to 1.420 s under
Latin drafting; that is a reason to keep this optimization opt-in, not a stable
language-specific performance estimate. All probe times and outputs are retained.

### GUFO repeat-controlled aggregate

The final aggregate pools six measured runs per input for the full-vocabulary
control (before and after the candidates) and six for the Latin candidate.
The intervening cap-one trial is retained separately, not merged into the control.

| Input | Full-vocab cap 3 | Latin-vocab cap 3 | Decode change | Control wall | Latin wall |
|---:|---:|---:|---:|---:|---:|
|512|33.4895 t/s|35.0038 t/s|+4.52%|5.0084 s|4.8254 s|
|2048|32.9208 t/s|33.5054 t/s|+1.78%|6.7526 s|6.6449 s|

Sample standard deviations are 0.1540/0.7664 t/s for control/Latin at 512,
and 0.6799/0.5765 at 2048. These are repeat variability, not confidence intervals.
The 2048 effect is small relative to variation and is not a strong general gain.
Prompt and output hashes match across all pooled measured requests. The original
full-vocabulary registered GUFO profile is retained; Latin is opt-in.

## Regression tests

The fresh-source export ran nine suites: 465 test cases, 396 passed, 68 skipped
for platform/installed-artifact requirements and one known legacy failure.
Server: 34 passed. GUFO adapter: 15 passed. Current Halogen: 89 passed, 22 skipped.
PROJFIX: 20 passed. All 27 PowerShell source files parsed.
The existing `test_sessions_probe_cleanup_terminates_real_descendant` failure in
old `backends/halogen-wsl2` again reported `DUMMY_DESCENDANT_SURVIVED`.
That unchanged legacy path was not repaired; the full suite is not entirely green.
The previously retained unmodified-HEAD reproduction is not rewritten.

## Available profiles and limits

The following files were generated with runtime validation, without overwriting
registered defaults:

- `server/.local/halogen-mtp-shallow-262k.json`: measured greedy depth 1.
- `server/.local/gufo-mtp-latin-262k.json`: cap 3, Latin vocabulary, length policy.
- `server/.local/gufo-mtp-shallow-262k.json`: cap 1, full vocabulary; no clear gain.

Start a candidate with the normal `server/controller.py run --config ... --port 8840`
only after the previous managed engine has stopped and completed cleanup.
The public model identifier and existing token remain the same for that backend.
The registered default `Start.ps1` configurations are not silently rewritten.

Full raw samples, excluded warmups, probe text, source hashes, before snapshots,
source-test logs and per-run state are in
`server/.local/halogen-gufo-mtp-20261001-1938/`.
The public result JSON carries raw benchmark samples and the exact comparisons.
No new occupied-long-context, sampled equivalence, NPU head transfer or allocator
qualification was completed. Local changes are not committed or pushed.

## Final restart verification

Halogen was restarted from the generated `halogen-mtp-shallow-262k.json` profile.
The repeated short benchmark measured 46.06 and 46.43 MTP tokens/s at 512/2048,
with request wall times 3.2887 and 4.2938 seconds. Prompt/output hashes still match
the first control and serial output. A slow PP512 prefill-only observation remains
in the repeat's raw samples; no prefill improvement is claimed.

The final run `4b540d0d0dfa4f108c8ff55ae458f9cc` is READY, context 262144,
`HALOGEN_MTP_DEPTH=1`, outer reserve 18 GiB and original v2 allocation profile.
Its minimum observed Windows availability was 37.01 GiB, current about 37.31 GiB.
Authenticated model discovery and an actual `OK` generation returned HTTP 200.
Missing and wrong bearer tokens returned 401. Ports 8826, 8836 and 52628 are closed;
no experimental PROJFIX, GUFO or NPU process is left serving there.
These checks originated locally, not from a separate external client.

Across this task there are 114 measured benchmark requests, plus excluded warmups,
calibration requests and additional synthetic probes. Final code bytes still match
the fresh-source test export. No commit or push was performed.
