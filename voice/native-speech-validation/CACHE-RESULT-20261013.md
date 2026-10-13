# Exact prompt cache: controlled local result

Root accepted keeping Exact active after a controlled Halogen 0.18.1 comparison. The separately reviewed desktop/source handoff then reused the same engine and restored the public gateway healthy and idle (commit `d6d8eaf2ee25801ca076ac1b19b52ad821e3438c`). The measured workload is one synthetic system document with 8,227 prompt tokens and 64 output tokens. It does not establish ServiceNow voice-call latency.

| Windows latency, repeated requests | Off | Exact | Reduction |
|---|---:|---:|---:|
| Full response, mean of two repeats | 7.950 s | 1.588 s | 80.0% |
| First content, mean of two repeats | 6.607 s | 0.304 s | 95.4% |

Each Exact repeat reused 8,192 tokens and processed 35. All six outputs had the same SHA256 and 64 tokens with zero reasoning tokens. The first requests are retained in the JSON: Off 12.134 s and Exact 11.838 s, each with zero cached tokens.

The accepted engine reports Exact mode 1, positive 110 MiB capacity, 4,096-token snapshot alignment and its bitwise-identical-to-cold contract. Context remains 262144, one slot, v2, draft depth 2 and prefill chunk/max 4096. The experiment changed only prompt_cache Off to Exact. Physical and commit guards remain 18 GiB.

During Exact requests, 91 samples recorded minimum 30.172 GiB available physical memory and 121.527 GiB commit headroom. Post-checks found the engine healthy and idle, native sessions zero, and the public gateway intentionally stopped during the measurement; its later restoration is recorded separately. These observations do not measure incremental cache memory or guarantee a cache memory bound.

The service's unchanged v2 cold admission is 35 GiB physical / 131 GiB commit for ten consecutive safe seconds. Early launch receipts incorrectly described a sixty-frame gate; that belongs to a different disposable runner path. The JSON records this correction. No guard or runtime source was altered.

The original managed stop completed container cleanup but missed its 180-frame recovery window (44.639 GiB observed, 45.277 GiB required). Its failed records were preserved. After late recovery and an independently reviewed verifier, the exact dead runner lock was archived once. Two pre-engine starts then encountered a Windows atomic state-file replacement error. Under the controller lease, the exact dead outer metadata was preserved by a same-directory, non-overwriting rename; the subsequent managed Exact start succeeded. No unknown process, WSL distro, ASR or TTS worker was stopped to resolve it.

The installed `/cache` endpoint fails parsing an extended counter field. Reuse is therefore supported by each response's cache_n/usage and `/metrics`: completed requests rose 2 to 5 and cached tokens 0 to 16384. Hit/miss/store/eviction counters remain unavailable. Raw engine phase timing is retained but uncalibrated; Windows request timing supports the latency comparison.

See [machine-readable evidence](cache-result-20261013.json) for hashes, each retained request, lifecycle receipts and scope limits. Large raw SSE, memory frames, logs and protected historical records remain on the inspected host under the recorded evidence paths.
