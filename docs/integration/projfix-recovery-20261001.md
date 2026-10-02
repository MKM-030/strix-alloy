# PROJFIX recovery on the installed Windows driver

Tested on 1 October 2026 with display driver 32.0.32015.2008. The target is the
existing IQ4_NL-PROJFIX Flash-Next model, not a substituted GUFO/Halogen model.
The engine binary and model files were retained. SDK runtime files were copied
into an isolated directory from TheRock 10.2.0a20260930, with matching BLAS code packs.
This was a runtime/deployment change, not a recompilation with a newer compiler.

## Reproduced failures and retained policy

The old native profile failed in two distinguishable ways. It crossed the 12 GiB
physical reserve on long conversations and encountered a GPU launch error when
moving from short to larger prefill work. Windows also recorded watchdog 141.
A reported hipMemcpyAsync failure is the error-reporting point, not proof that the
copy call itself caused the earlier asynchronous GPU failure.

The pinned fork changes lazy-mode AUTO to OFF on integrated GPUs without its
mmap capability flag. Explicit `--lazy-mode on` keeps the PLE lookup table mapped
on the CPU. At 32K capacity, live controller readings improved from approximately
15.4 to 41.9 GiB minimum available physical memory. These are rounded live observations,
not a complete continuous memory trace. They do not represent total model memory.

Runtime-library replacement alone did not fix the crash. Microbatch 512 passed the
previously failing PP2048 transition. Restoring microbatch 2048 reproduced the GPU
failure even with more than 31 GiB available, separating it from the physical reserve.
The supported recovery profile therefore explicitly uses lazy-mode on, batch 2048,
microbatch 512 and f16 KV. The internal large-microbatch kernel failure remains
unresolved; this is a tested configuration mitigation, not a claimed kernel repair.

## Measured short-prompt results

All requests below use the authenticated Strix Alloy gateway, exact input lengths,
cache disabled and 128 generated tokens for decode. Prefill-only probes generate
one token and are not counted as decode benchmarks. Each point has one warmup and
three measured repetitions. These are native Windows engine timings, without WSL
clock correction. The workload is not a full model-quality evaluation.

| Configuration | Capacity | Input | Prefill t/s | Decode t/s |
|---|---:|---:|---:|---:|
| latest-ub512-32k | 32768 | 512 | 550.73 | 11.89 |
| latest-ub512-32k | 32768 | 2048 | 722.00 | 12.63 |
| mapped-lookup32k | 32768 | 512 | 549.11 | 11.90 |
| mapped-lookup32k | 32768 | 2048 | 737.24 | 12.67 |
| mapped-ub512-262k | 262144 | 512 | 528.89 | 11.75 |
| mapped-ub512-262k | 262144 | 2048 | 720.77 | 12.54 |
| serial-mapped512-262k | 262144 | 512 | 553.33 | 6.35 |
| serial-mapped512-262k | 262144 | 2048 | 739.69 | 6.23 |
| mtp-no-graphs262k | 262144 | 512 | 533.10 | 11.76 |
| mtp-no-graphs262k | 262144 | 2048 | 709.78 | 12.53 |

The configurations are separate sequential runs. Differences are not an isolated display-driver effect. Failed attempts remain in the JSON and are not zero-throughput results.

## Long-conversation validation

Executed 1 three-turn conversation at 262144 capacity. Initial input tokens: [131099]. Retrieval: 8/8; completed streams: 3; responses at the requested output cap: 2. The cap was 768 tokens.
The client scope sentence contains a fixed two-repetition description; the actual run used one repetition, shown by its request records. Coding outputs were not executed or graded. This is a continuity/memory test, not the earlier two-repetition article comparison.

## Validation boundaries and reproduction

The long-conversation client verifies incremental SSE completion and exact retrieval;
its success does not establish every client-disconnect/cancellation path. The separate
custom cancellation/authentication QA command was blocked by tool safety, so it is
not counted as passed. API authentication is retained; the published benchmark client
made authenticated local requests. Public-network checks are listed only if separately
recorded in the final-state evidence. No GPU watchdog or memory guard was relaxed.

The recovery runtime is copied into an isolated version-specific directory. The
[profile guide](../../backends/projfix-windows/README.md) records preparation and exact
registration commands. `profile.py` pins runtime files and refuses an existing profile;
it does not download models or silently replace GUFO/Halogen. Model size/header checks
are not cryptographic verification of all weight bytes or general quality certification.

The previous article benchmark and its PROJFIX failures remain historical evidence;
this report does not rewrite them as successes. A working 512-microbatch profile does
not establish that larger microbatches, different quants or other SDK builds are safe.
Raw timing counters and failed cases are retained in the JSON; the CSV labels each case.

Primary code reference for AUTO-to-OFF behavior:
[pinned llama-model.cpp](https://github.com/pwilkin/llama.cpp/blob/40a9f4d01b69314d0f75c9120abe8e199e49111d/src/llama-model.cpp).
The integrated-GPU capability flag is in the corresponding ggml-cuda.cu. Windows
direct lazy reads are a stub in this build; explicit mapped reads are not described
as DirectIO. [Microsoft watchdog 141 definition](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/bug-check-0x141---video-engine-timeout-detected).

## Retained operating mode

The registered profile retains MTP and normal graph replay. The no-draft serial control was slower, and disabling graph replay did not improve decode. The measured recovery configuration remains slower than historical PROJFIX results; performance is not represented as fully restored.

The normally registered launcher was checked separately: {"passed_execution": true, "requests": 3, "retrieval_correct": 8, "retrieval_total": 8, "capped_outputs": 2, "actual_initial_tokens": [2070]}

## Fresh-source verification

```json
{
  "fresh_source_export": true,
  "tests": {
    "projfix_profile": 9,
    "publication": 15,
    "controller_gateway": 23,
    "benchmark": 27
  },
  "powershell_source_parses": 27,
  "all_passed": true,
  "tested_source_sha256": {
    "app/launch-flash-next.ps1": "ba2e1766da5971339971d263ac6d28e4448d755d93d66af2dfd5274ef4a57168",
    "backends/projfix-windows/profile.py": "1df6e38b5996df384ece19af045eb854d3456af7f154c6ee72b12fcc1ebec3ec",
    "backends/projfix-windows/tests/test_decoding_mode.py": "e08739061047c601f8836aff48870cb6948a9d76d896d601569c13c11ea4e7f2",
    "backends/projfix-windows/tests/test_profile.py": "51ee973d8b2313ae646b949d67ea094ba335ec634b9962d5fa1f0091eb3b0776",
    "backends/projfix-windows/tests/test_runtime_identity.py": "f80143b0a6cf3a95c3ebdf1ddb3d8e24777de3c444c31aa70d055420ac7151d3",
    "tests/publication/test_projfix_loading.py": "d8e65eea271eceb300a4944dde1cb3ce0c7af0eaf1385b7e734c456d5f2e0e91"
  },
  "scope": "Offline source tests; live model validation recorded separately."
}
```

## Final service and connection check

```json
{
  "checked_at": "2026-10-01T04:21:49.603284+00:00",
  "phase": "ready",
  "backend": "projfix-flash-next",
  "context": 262144,
  "mode": "mtp",
  "run_id": "35dfc15a53654cd88dc1016bf9219197",
  "minimum_available_gib": 32.460289001464844,
  "available_gib": 32.73432159423828,
  "display_driver": "32.0.32015.2008",
  "sdk_runtime": "10.2.0a20260930",
  "engine_rebuilt": false,
  "local_api": "http://127.0.0.1:8840/v1",
  "public_api": "https://strix-alloy.tail7f425a.ts.net/v1",
  "local_authenticated_validation": {
    "completed_streams": 3,
    "retrieval": "8/8"
  },
  "public_ipv4_authentication_rejections": [
    401,
    401
  ],
  "public_authenticated_inference_tested": false,
  "public_automatic_address_selection": "Two TLS handshake failures before successful explicit IPv4 checks; no certificate-validation bypass used",
  "external_cloud_instance_tested": false,
  "api_key_changed": false,
  "funnel_restored": true,
  "custom_cancellation_test": "Not executed: tool safety blocked the QA command"
}
```

## Captured state observations

```json
[
  {
    "evidence": "serialized32k-terminal.json",
    "run_id": "8c2e83801a014f6192cbf76125a77ad3",
    "phase": "failed",
    "backend": "projfix-flash-next",
    "context": 32768,
    "minimum_available_gib": 13.511920928955078,
    "available_gib": null,
    "error": "owned-process exit not confirmed; retain handles for retry; cleanup: owned-process exit not confirmed; retain handles for retry",
    "mode": null,
    "checked_at": null
  },
  {
    "evidence": "mapped-ub2048-32k-terminal.json",
    "run_id": "04b4a778eb834da2a3b52a9f54fc7aee",
    "phase": "failed",
    "backend": "projfix-flash-next",
    "context": 32768,
    "minimum_available_gib": 31.029354095458984,
    "available_gib": 45.33317947387695,
    "error": "Engine process exited",
    "mode": null,
    "checked_at": null
  },
  {
    "evidence": "mapped32k-before-stop.json",
    "run_id": "833e96b8fb2c4e0c979f03bfd975f8ee",
    "phase": "ready",
    "backend": "projfix-flash-next",
    "context": 32768,
    "minimum_available_gib": 41.929893493652344,
    "available_gib": 42.06732940673828,
    "error": null,
    "mode": null,
    "checked_at": null
  },
  {
    "evidence": "mtp262k-final.json",
    "run_id": "f67e44b34b2b41d4bfb2b9307028ab63",
    "phase": "ready",
    "backend": "projfix-flash-next",
    "context": 262144,
    "minimum_available_gib": 29.074859619140625,
    "available_gib": 29.17232894897461,
    "error": null,
    "mode": null,
    "checked_at": null
  },
  {
    "evidence": "mtp262k-stop.json",
    "run_id": "f67e44b34b2b41d4bfb2b9307028ab63",
    "phase": "stopped",
    "backend": "projfix-flash-next",
    "context": 262144,
    "minimum_available_gib": 29.074859619140625,
    "available_gib": 29.17232894897461,
    "error": null,
    "mode": null,
    "checked_at": null
  },
  {
    "evidence": "serial262k-final.json",
    "run_id": "29394f807a274d31949a0d6fafbb104f",
    "phase": "ready",
    "backend": "projfix-flash-next",
    "context": 262144,
    "minimum_available_gib": 38.327980041503906,
    "available_gib": 38.4996223449707,
    "error": null,
    "mode": null,
    "checked_at": null
  },
  {
    "evidence": "serial262k-stop.json",
    "run_id": "29394f807a274d31949a0d6fafbb104f",
    "phase": "stopped",
    "backend": "projfix-flash-next",
    "context": 262144,
    "minimum_available_gib": 38.327980041503906,
    "available_gib": 38.4996223449707,
    "error": null,
    "mode": null,
    "checked_at": null
  },
  {
    "evidence": "graph-control-final.json",
    "run_id": "846b4b73107c40b9bd1969c18c001480",
    "phase": "ready",
    "backend": "projfix-flash-next",
    "context": 262144,
    "minimum_available_gib": 33.339378356933594,
    "available_gib": 33.382301330566406,
    "error": null,
    "mode": null,
    "checked_at": null
  },
  {
    "evidence": "graph-control-stop.json",
    "run_id": "846b4b73107c40b9bd1969c18c001480",
    "phase": "stopped",
    "backend": "projfix-flash-next",
    "context": 262144,
    "minimum_available_gib": 33.339378356933594,
    "available_gib": 33.382301330566406,
    "error": null,
    "mode": null,
    "checked_at": null
  },
  {
    "evidence": "final-state.json",
    "run_id": "35dfc15a53654cd88dc1016bf9219197",
    "phase": "ready",
    "backend": "projfix-flash-next",
    "context": 262144,
    "minimum_available_gib": 32.460289001464844,
    "available_gib": 32.73432159423828,
    "error": null,
    "mode": "mtp",
    "checked_at": "2026-10-01T04:21:49.603284+00:00"
  }
]
```
