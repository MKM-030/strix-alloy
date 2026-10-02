# PROJFIX native Windows: restored decode performance

This package supplies a measured loading policy for the existing IQ4_NL-PROJFIX
Flash-Next engine. It is not a new model, a kernel rewrite or a GUFO fallback.
The retained engine binaries are combined with application-local TheRock
10.2.0a20260930 runtime libraries. The display driver tested is 32.0.32015.2008.
The engine was not recompiled by this repair; compiler and runtime versions are
not interchangeable claims.

## Required loading policy

Use `--load-mode none --lazy-mode on`, with logical batch 2048 and microbatch 512.
Keep `-ctk f16 -ctv f16`. This fork disables automatic lazy loading on integrated
GPUs, so omitting the explicit lazy setting makes the large lookup table resident.
`on` means CPU-mapped lookup rows; `on-direct` is not implemented by this Windows
build and must not be described as a working asynchronous direct-I/O optimization.

The 2048-token microbatch reproduced a GPU launch failure even after memory pressure
was removed. The 512-token profile avoids that tested failing path; it does not prove
the underlying large-microbatch kernel defect repaired. No watchdog, driver, BIOS,
Windows memory policy or 12 GiB physical/commit reserve is disabled by this package.

## Fast serial placement on the 64 GiB carve-out

The default registration is now **serial decoding with split weight placement**.
At 262144 capacity, PP512/TG128 measured 33.12 tokens/s and PP2048/TG128 31.77 tokens/s,
versus about 6.3 serial and 12 MTP tokens/s in the preceding resident configuration.
These are native engine rates through Strix Alloy, not a WSL clock correction.

The target contains about 66.34 GiB of non-lookup weights before working buffers.
The selected 54 expert tensors (first 18 layers) occupy 23.73 GiB. This configuration
keeps those weights in GPU-accessible pinned host buffers using:

```text
-ot ^blk[.](?:[0-9]|1[0-7])[.]ffn_(?:gate|up|down)_exps[.]weight$=CPU
```

In this **pinned engine**, the CPU selector prefers the GPU host buffer and the
integrated HIP backend supports that buffer. This is not a universal instruction
to execute model layers on the CPU. Buffer selection must be rechecked for another
engine, model, carve-out or runtime. No weight values, precision or equations change.
The final outputs matched the retained slow serial reference on both short tests.

Keep mapped lookup loading, microbatch512 and f16 KV. The 12 GiB physical/commit
reserves and normal watchdog remain enabled. The current improvement is a placement
fix, not a claim that the large-microbatch kernel failure is repaired.

Earlier mixed-placement MTP failed before serving with `invalid vector subscript` in draft
loading. The explicit single-device split experiment below resolves that startup failure. Explicit draft placement and the already-installed full Q8_0 head did not
resolve it. Therefore `--mode mtp` deliberately retains the older, slower resident
configuration; it is not silently enabled on top of the fast placement.

## Prepare the runtime

Retain the original native Strix Alloy runtime from the existing native setup.
Use a separate directory, never overwrite an engine that is running. Copy its engine
files and the matching SDK runtime libraries/code packs according to the example
below. The manifest pins every resulting file, including BLAS kernel libraries.
Do not copy files into System32 or change global PATH.

```powershell
$Original = 'C:\AI\runtimes\strix-alloy-native' # Existing, matching native runtime.
$Sdk = 'C:\AI\sdk\therock1151-10.2.0a20260930'
$Runtime = 'C:\AI\runtimes\projfix-recovered'
if (Test-Path $Runtime) { throw 'Use a new runtime directory.' }
New-Item -ItemType Directory $Runtime | Out-Null
Copy-Item "$Original\*.exe", "$Original\*.dll" $Runtime
Get-ChildItem $Runtime -Filter '*.dll' | ForEach-Object {
    $Replacement = Join-Path "$Sdk\bin" $_.Name
    if (Test-Path $Replacement) { Copy-Item $Replacement $_.FullName }
}
Copy-Item "$Sdk\bin\rocblas", "$Sdk\bin\hipblaslt" $Runtime -Recurse
Copy-Item "$Sdk\.kpack" "$Runtime\.kpack" -Recurse
```

`compatibility.json` pins the retained engine and the exact SDK payload used here.
A different build or SDK needs its own tests and revised manifest; do not change a
hash merely to bypass validation. The original engine provenance is documented in
[the native build record](../../docs/benchmarks/engine-provenance-20260916.md).
No engine, model, SDK binary or access token is shipped in this source repository.

## Register explicitly, then start

Stop the current managed server and confirm `STOPPED` before replacing a profile.
The generator refuses to overwrite existing files. Archive an older PROJFIX profile
and its runtime explicitly for rollback; GUFO and Halogen profiles need no change.

```powershell
$Models = 'C:\AI\models\qwen38-flash\projfix'
$TokenFile = '.\backends\halogen-wsl2-0.15.1\.local\api-token.txt'
python .\backends\projfix-windows\profile.py `
  --runtime $Runtime --models $Models --token-file $TokenFile `
  --context 262144 --register
.\server\Start.ps1 -Backend Projfix -ContextSize 262144
```

The registered mode is stated in the command vector. Profile creation verifies every
runtime component, model-file sizes and GGUF headers. Size/header checks are not
complete model-file hashes or an independent model-quality certification.
Use `--output <new-path.json>` instead of `--register` to create an isolated test
profile; it does not start anything. Only use capacities actually validated for your
host. A capacity setting does not imply that a full conversation of that length passed.

```text
Managed API: http://127.0.0.1:8840/v1
Model ID:    projfix-flash-next
Native API:  http://127.0.0.1:8826/v1
```

The same existing bearer token protects both endpoints. Existing Tailscale forwarding
to port8840 needs no backend-specific change. Only the tested Chat Completions route
is advertised by this profile. Streaming/cancellation and long-context results, along
with remaining limitations, are recorded in the [repair report](../../docs/integration/projfix-recovery-20261001.md).

## Operation and regression checks

```powershell
.\server\Start.ps1 -Status
.\server\Start.ps1 -Logs
.\server\Start.ps1 -Stop
```

Registration defaults to `--mode serial`, with the measured pinned-host expert placement.
`--mode mtp` explicitly selects the older resident configuration, not an automatic fallback. Changing mode or capacity requires a separate
profile and controlled stop/start. Never infer that MTP helps from its name alone;
measure actual output lengths, accepted draft tokens and whole-request timing.

The legacy standalone launcher now also specifies mapped lookup loading and a
512 microbatch by default. Without `-DraftPath`, it also applies the fast placement.
Its separate `-BatchSize` default is 2048. An explicit draft keeps the older resident path. Prefer the
managed controller for monitored operation; a printed standalone command is not a
substitute for the independent process and memory protections.

[Decode-restoration measurements](../../docs/integration/projfix-decode-restored-20261001.md)
record the placement comparison, output checks and limits. The historical
[Measured recovery results](../../docs/integration/projfix-recovery-20261001.md)
separate short-prompt performance, long-history continuity and failed experiments.
Do not present successful startup as recovery of the earlier speed figures.
The old article benchmark used different operating conditions and remains unchanged.

```powershell
python -B -m unittest discover -s backends/projfix-windows/tests -v
python -B -m unittest discover -s tests/publication -p test_projfix_loading.py -v
```

## Opt-in mixed-placement MTP

`--mode mtp-host` adds an explicit `--tensor-split 1` to the fast host-expert
placement and retains the real MTP head. On this single-GPU machine the positive
split avoids the loader's zero-free-memory normalization. It is not NPU offload.
No runtime, driver, weight precision or existing default is replaced.

The mode requires `--output`; `--register` is refused while general equivalence
qualification remains incomplete. Read the [measured implementation report](../../docs/research/mtp-host-implementation-20261001.md)
for the exact tested contexts, output comparisons and performance trade-offs.

```powershell
$Candidate = '.\server\.local\projfix-mtp-host.json'
python .\backends\projfix-windows\profile.py `
  --runtime $Runtime --models $Models --token-file $TokenFile `
  --context 262144 --mode mtp-host --output $Candidate
# Stop the current engine normally and confirm STOPPED before this command:
.\server\.local\venv\Scripts\python.exe -B .\server\controller.py `
  run --config $Candidate --port 8840
```

This candidate requests an 18 GiB physical/commit reserve from the controller,
leaving margin above a 16 GiB availability target. Polling cannot guarantee that
unrelated instantaneous allocations never cross that target. Existing profiles
retain their previous reserve unless an explicitly stricter value is configured.
Use the ordinary `Start.ps1 -Stop` control to stop the candidate before returning
to the normal Halogen, GUFO or serial PROJFIX profile.

For a separately reversible scheduler checkpoint experiment, generate a
**serial** profile with the same runtime, model, token and 262144 context as
the control:

```powershell
$Candidate = '.\server\.local\projfix-checkpoints64-serial-262k.json'
python .\backends\projfix-windows\profile.py `
  --runtime $Runtime --models $Models --token-file $TokenFile `
  --context 262144 --mode serial --ctx-checkpoints 64 --output $Candidate
```

The existing
`--cache-ram 8192` MiB cap remains; the generated profile requests 18 GiB
headroom and cannot be registered as the default. Compare against a fresh
18 GiB serial control with the ordered matrix in `server/.local/NEXT_STEPS.json`.

## Rebuild-only grammar experiment

`patches/backend-grammar-fast-optin.patch` stages a reversible change against
the pinned pwilkin source. The existing CPU sampler already checks a sampled
token against the grammar before a full resample; PLE prefetch is also present
in the pinned source. The patch does not duplicate either optimization.

The patch keeps backend grammar sampling disabled by default. In a **separate
rebuilt candidate only**, `LLAMA_BACKEND_GRAMMAR_FAST=1` permits eager,
trigger-free, non-LLGuidance grammar without reasoning-budget sampling. It
checks the GPU-selected token against grammar and resamples from full raw logits
on rejection; when full logits are unavailable it fails closed rather than
emitting an invalid token. Source applicability/reversibility tests are in
`tests/test_grammar_patch.py`. This is not a qualified binary or a deployment
instruction: compile, exercise both valid/rejected paths, compare grammar
outputs/logits and run the broad gate before considering promotion. The pinned
production executable, DLLs, runtime hashes and default profiles remain intact.
An isolated patched `common/sampling.cpp` passed the pinned clang/PCH syntax
check on 2 October 2026; no linked binary or grammar operator result is claimed.

`patches/scheduler-reserve-optin.patch` is a separate, default-off source
candidate using `LLAMA_SAMPLER_KEEP_RESERVE=1`. It applied and reversed cleanly
and passed an isolated `llama-context.cpp` clang/PCH syntax check. Matching
sampler names alone does not prove identical graph allocation, sampler lifetime
or output equivalence. Do not enable it on the registered binary; test graph
growth, changed sampling chains, cancellation and multi-turn memory/quality
in a separately pinned candidate before any speed claim.
