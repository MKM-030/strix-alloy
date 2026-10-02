# Strix Alloy: article-format performance and driver comparison

Measurements began on 30 September 2026 on the BOSGAME Ryzen AI Max+ 395 / Radeon
8060S, 128 GB machine. Requests use the authenticated local Strix Alloy gateway,
port 8840. Public ingress is paused during measured groups. Driver 32.0.32015.2008
(Adrenalin 26.9.2) is held constant; no BIOS, power plan or driver was changed here.

## Reading these tables

The reference is [deepu105's comparison](https://www.reddit.com/r/LocalLLM/comments/1wu0m53/benchmarks_best_engine_for_qwen_38flashnext_on/).
We reproduce its columns and occupied-context dimensions, not the author's exact prompt
bytes. Its host was an Arch Linux Flow Z13 at 70 W; ours is Windows/WSL2, with different
weights and engine revisions. Direct percentages against that author's scores would
not isolate an engine or OS effect. The separate ten-exercise Aider suite was not run.

Here, two three-turn conversations use twelve pinned public LlamaStash source files
plus deterministic exact-value fixtures. Every first request is approximately the
stated fill, including template tokens (tolerance: max(128, 1%)). Follow-ups extend
that history. Thinking is requested with low effort, temperature 1, top-p .95, top-k
20, min-p 0 and a 1536-token output ceiling. Actual output/reasoning token counts,
truncations and missing telemetry are retained. Engines may differ in supported
reasoning-budget behavior. Generated source is never executed.

3-turn time is the average across two conversations of the sum, over three requests,
of **TTFT + 1000/decode_tokens_per_second**. It is a normalized time, not measured job
elapsed time. Prefill averages the two initial requests; decode is token-weighted
across all six. Draft acceptance is accepted/proposed tokens, not acceptance per round.
Retrieval grades exact JSON string values, including punctuation and Unicode. Our
fixtures are explicitly marked in the replacement corpus, so identical scores do
not establish equal retrieval difficulty to the article. This does not grade coding ability. Seven values are checked at 64K capacity, eight above it.

Halogen's raw phase timers and per-request WSL/raw-clock calibration are both retained.
Calibrated rates are estimates: within-request clock-rate changes add uncertainty.
Windows TTFT is not rescaled. Native GUFO/PROJFIX timings need no WSL correction.

## Article-format results

### 65,536 capacity; 32,768 initial input (50% filled)

| Engine | Weights | 3-turn time | Prefill t/s | Decode t/s | MTP accept | Retrieval |
|---|---|---:|---:|---:|---:|---:|
| GUFO latest-SDK | UD-IQ4_XS + Q8_0 MTP | 2.00 min | 707.9 | 40.52 | 79.8% | 14/14 |
| Halogen 0.15.1 | v2 HGN | 2.08 min | 1041.9 | 30.32 | 83.9% | 14/14 |
| Halogen 0.15.1 | w4b HGN + overlay | 1.93 min | 1070.9 | 33.85 | 84.5% | 14/14 |
| PROJFIX native HIP | IQ4_NL-PROJFIX + Q8_0 MTP | Not completed | — | — | — | — |

### 131,072 capacity; 65,536 initial input (50% filled)

| Engine | Weights | 3-turn time | Prefill t/s | Decode t/s | MTP accept | Retrieval |
|---|---|---:|---:|---:|---:|---:|
| GUFO latest-SDK | UD-IQ4_XS + Q8_0 MTP | 2.93 min | 666.1 | 38.43 | 76.7% | 16/16 |
| Halogen 0.15.1 | v2 HGN | 2.38 min | 1114.1 | 34.05 | 85.7% | 16/16 |
| Halogen 0.15.1 | w4b HGN + overlay | 2.64 min | 1076.5 | 29.24 | 82.5% | 16/16 |
| PROJFIX native HIP | IQ4_NL-PROJFIX + Q8_0 MTP | Not completed | — | — | — | — |

### 131,072 capacity; 98,304 initial input (75% filled)

| Engine | Weights | 3-turn time | Prefill t/s | Decode t/s | MTP accept | Retrieval |
|---|---|---:|---:|---:|---:|---:|
| GUFO latest-SDK | UD-IQ4_XS + Q8_0 MTP | 4.02 min | 623.3 | 35.66 | 73.1% | 16/16 |
| Halogen 0.15.1 | v2 HGN | 2.69 min | 1147.9 | 39.58 | 85.5% | 16/16 |
| Halogen 0.15.1 | w4b HGN + overlay | 2.72 min | 1142.9 | 38.81 | 82.8% | 16/16 |
| PROJFIX native HIP | IQ4_NL-PROJFIX + Q8_0 MTP | Not completed | — | — | — | — |

### 262,144 capacity; 131,072 initial input (50% filled)

| Engine | Weights | 3-turn time | Prefill t/s | Decode t/s | MTP accept | Retrieval |
|---|---|---:|---:|---:|---:|---:|
| GUFO latest-SDK | UD-IQ4_XS + Q8_0 MTP | 4.96 min | 623.5 | 34.13 | 73.1% | 16/16 |
| Halogen 0.15.1 | v2 HGN | 3.48 min | 1117.3 | 32.39 | 84.4% | 16/16 |
| Halogen 0.15.1 | w4b HGN + overlay | 3.53 min | 1098.4 | 31.69 | 82.7% | 16/16 |
| PROJFIX native HIP | IQ4_NL-PROJFIX + Q8_0 MTP | Not completed | — | — | — | — |

### Output ceilings and failed cells

- gufo at 65536/32768: 6 requests; 0 hit the output ceiling. Initial input counts: [32791, 32792].
- gufo at 131072/65536: 6 requests; 1 hit the output ceiling. Initial input counts: [65562, 65559].
- gufo at 131072/98304: 6 requests; 0 hit the output ceiling. Initial input counts: [98331, 98326].
- gufo at 262144/131072: 6 requests; 1 hit the output ceiling. Initial input counts: [131099, 131099].
- halogen-v2 at 65536/32768: 6 requests; 0 hit the output ceiling. Initial input counts: [32791, 32792].
- halogen-v2 at 131072/65536: 6 requests; 0 hit the output ceiling. Initial input counts: [65562, 65559].
- halogen-v2 at 131072/98304: 6 requests; 0 hit the output ceiling. Initial input counts: [98331, 98326].
- halogen-v2 at 262144/131072: 6 requests; 0 hit the output ceiling. Initial input counts: [131099, 131099].
- halogen-w4b at 65536/32768: 6 requests; 0 hit the output ceiling. Initial input counts: [32791, 32792].
- halogen-w4b at 131072/65536: 6 requests; 0 hit the output ceiling. Initial input counts: [65562, 65559].
- halogen-w4b at 131072/98304: 6 requests; 0 hit the output ceiling. Initial input counts: [98331, 98326].
- halogen-w4b at 262144/131072: 6 requests; 0 hit the output ceiling. Initial input counts: [131099, 131099].
- projfix at 65536/32768: Windows physical/commit reserve crossed 12 GiB
- projfix at 131072/65536: RuntimeError('Windows physical/commit reserve crossed 12 GiB')
- projfix at 131072/98304: RuntimeError('Windows physical/commit reserve crossed 12 GiB')
- projfix at 262144/131072: RuntimeError('Windows physical/commit reserve crossed 12 GiB')

The PROJFIX 64K retry completed two turns, then its controller stopped the engine
when available Windows RAM reached 11.94 GiB, below the unchanged 12 GiB reserve.
The incomplete-SSE error was the client-visible consequence; both records are retained.
A failed cell is not scored as zero throughput, and two successful turns are not
presented as a completed three-turn conversation. The original early-ready Halogen
64K screening run remains archived locally; the final table uses its explicitly
named ready-confirmed repeat when available. The readiness barrier waits for the
backend's own startup checks, not merely the gateway listener.

## Before/after display-driver controls

Old display driver: 32.0.31041.1004. Current: 32.0.32015.2008. The retained Halogen
baseline used 0.15.1, the same checkpoint family, 262144 capacity, exact stored short
prompts, greedy generation and cache Off. New controls use port 8840 and match those
inputs/output limits; prefill uses a one-token probe and decode uses 128 tokens.
No driver downgrade was performed. Differences include elapsed time, system/cache
state, gateway routing and wrapper revisions. Treat these as before/after stack
observations, not an isolated causal measurement of the display-driver change.

| Checkpoint | Test | Mode | Before t/s | After t/s | Change |
|---|---|---|---:|---:|---:|
| v2 | PP512 | serial | 1025.14 | 1043.03 | +1.74% |
| v2 | PP512 → TG128 | serial | 36.96 | 36.33 | -1.70% |
| v2 | PP512 → TG128 | mtp | 43.17 | 42.78 | -0.91% |
| v2 | PP2048 | serial | 1358.56 | 1375.71 | +1.26% |
| v2 | PP2048 → TG128 | serial | 36.17 | 35.77 | -1.11% |
| v2 | PP2048 → TG128 | mtp | 45.27 | 44.62 | -1.44% |
| w4b | PP512 | serial | 967.74 | 986.87 | +1.98% |
| w4b | PP512 → TG128 | serial | 34.50 | 35.16 | +1.93% |
| w4b | PP512 → TG128 | mtp | 42.41 | 42.72 | +0.73% |
| w4b | PP2048 | serial | 1323.38 | 1357.57 | +2.58% |
| w4b | PP2048 → TG128 | serial | 34.08 | 34.32 | +0.71% |
| w4b | PP2048 → TG128 | mtp | 42.39 | 42.90 | +1.19% |

There is **no qualified pre-driver GUFO performance baseline**. Its 10.0-toolchain
and latest-SDK measurements both occurred after the new display driver was installed.
Comparing those would test toolchain/configuration differences, not the driver.

PROJFIX's historical native `llama-bench` record is PP512 **761.30 +/- 38.24** and
serial TG128 **31.49 +/- 0.17**, on the old 96 GB carve. The current fixed test host
uses a 64 GiB carve and gateway conversation workload. Those values are historical
context only; they cannot justify a driver percentage. See
[canonical baseline](canonical-llama-bench-20260916.md) and
[recorded binary provenance](engine-provenance-20260916.md). The restored isolated
PROJFIX dependency bundle retained its original engine/kernel hashes; it was not
silently rebuilt under another SDK.

## Evidence and reproduction

The [JSON](strix-alloy-article-driver-comparison-20260930.json) includes request-level
timing data, exact retrieval answers, source hashes, rejected/partial results and
control comparisons. Code-answer text is kept privately with the raw run; exported
rows retain its hash. No API-token values, model binaries or SDK DLLs are published.
[Commands](../../scripts/benchmarks/README.md) describe the supplied clients.
The first incomplete control attempt was rejected before any timed inference because
Halogen's own validation was still running. That is a harness-readiness failure, not
a driver or model-performance result.

## Native short-prompt controls through the gateway

These are additional PP512/PP2048 and TG128 checks, not the article's filled-history workload. Native draft settings remain configured per profile.

| Engine | Capacity | Input | Prefill t/s | Decode t/s |
|---|---:|---:|---:|---:|
| gufo | 262144 | 512 | 495.50 | 33.76 |
| gufo | 262144 | 2048 | 742.61 | 32.98 |
| projfix (partial, then failed) | 32768 | 512 | 543.59 | 12.14 |

Three retained repeats after warmup; no WSL rate correction for these native phase timers. These rows do not create a missing pre-driver baseline.

PROJFIX completed the PP512/TG128 points but failed before a PP2048 measurement: the native log reports an unspecified ROCm launch failure during a device-to-host hipMemcpyAsync read. The client saw HTTP503. These partial timings are diagnostic results, not a successful stability qualification; no PP2048 value is inferred.

## Source verification

```json
{
  "fresh_source_export": true,
  "tested_source_hashes": {
    "scripts/benchmarks/article_bench.py": "eb0b7a6618fd788077f7852cfe02df67a4db250322a84fec43864015e08c8c23",
    "scripts/benchmarks/article_metrics.py": "7bb210ea3e66339eb78fab457f0eb86f3d87f8484311f20d9e4f89908e0adc97",
    "scripts/benchmarks/prepare_article_inputs.py": "e7408730456aa49475eabb3c8e37c22938aa33c2a4c6035e2a1cd76d9080b3db",
    "scripts/benchmarks/gateway_cold.py": "0aba32e6997c3c53480bc003e1eeabe7c50ba615824cbecc2eff82930579faf4",
    "scripts/benchmarks/prepare_native_profile.py": "8b91523bba68ad08fdc1f0588255f5f30191055d5288b299f9e04301226c2534",
    "scripts/benchmarks/tests/test_article_geometry.py": "f1b7ef01a40646ec8d0fc94716fffd44dfeb51d9702202ef09c8870cad7aabf5",
    "scripts/benchmarks/tests/test_article_identity.py": "7bbc21a9e90c1255ca1d653d273004da03b1a361bf765c26583b5cbabd5e7adf",
    "scripts/benchmarks/tests/test_article_inputs.py": "dcb6252d52e999d157bb4c14aec21eb62794d24e4aba9e20ce27046c577e39ea",
    "scripts/benchmarks/tests/test_article_metrics.py": "15f5814db8995ca032f2e8f0d53d67f8075352f90474053357c6005d03208b88",
    "scripts/benchmarks/tests/test_article_readiness.py": "c072bc395cb2bfb757affed8c0671db3b5111952fdeffc49544b203c10093cd1",
    "scripts/benchmarks/tests/test_article_run_name.py": "ad8a3729a7b63131530828283aed94db5cd1bb69bd427a53e940b80b9759363d",
    "scripts/benchmarks/tests/test_native_profile.py": "5786d05583ccdedfa1d5a895a863abb36d46abf4b84b7e8fa5408be38e05df7d"
  },
  "test_suites": {
    "benchmark": 27,
    "server": 23,
    "publication": 14,
    "toolchain": 15
  },
  "runtime_code_changed": false,
  "all_passed": true,
  "powershell_files": 27,
  "note": "Source tests are separate from model benchmarks. Injected disconnect/failure fixtures may emit diagnostics while assertions pass."
}
```

## Final verified service

```json
{
  "phase": "ready",
  "backend": "GUFO",
  "context": 262144,
  "run_id": "2c48cad0f7064541a2e8be8595c3721d",
  "model": "gufo-flash-next",
  "public_api": "https://strix-alloy.tail7f425a.ts.net/v1",
  "api_key_changed": false,
  "original_profile_restored": true,
  "checks": {
    "http://127.0.0.1:8840": {
      "status": 200,
      "answer": "OK",
      "missing_and_wrong_token": 401
    },
    "https://strix-alloy.tail7f425a.ts.net": {
      "status": 200,
      "answer": "OK",
      "missing_and_wrong_token": 401
    }
  },
  "transient_network_errors": [],
  "origin": "Windows PC through public HTTPS hostname; external cloud instance not tested",
  "checked_at": "2026-09-30T22:48:28.438936+00:00"
}
```

The original checkpoints, qualified runtime profiles and old failed evidence remain available. No main-branch merge is part of this benchmark.
