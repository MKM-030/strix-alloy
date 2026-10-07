# Halogen 0.17.1 Current8K comparison — 7 October 2026

**All three measurement windows passed; no version-to-version gain is qualified.**
The 0.17.1 candidate's MTP decode mean is below both 0.16.2 controls, and its
PP8192 mean is also below both controls. The exact original 0.16.2 profile is
restored, authenticated ready, idle and open. Exact values, run identities and raw evidence hashes are retained in the
[matching JSON](halogen0171-current8k-20261007.json).

The sequential comparison uses `scripts/benchmarks/gateway_cold.py` unchanged:
v2 checkpoint, capacity 262144, one slot, prefill chunk/arena 8192/8192, MTP2,
PLD `3,3`, Cache Off, Thinking Off, temperature 0 and seed 1. Natural prose is
calibrated to 8192 actual input tokens through the same gateway chat route.
PP uses one output token; TG uses 128 actual output tokens. Each cohort has one
warmup and three measured repetitions. TG serial/MTP order alternates by repetition.
Console tracing is disabled in the measurement profiles.

| Window | Status | PP8192, tokens/s | TG128 MTP+PLD, tokens/s | TG128 serial, tokens/s | Combined acceptance |
| --- | --- | ---: | ---: | ---: | ---: |
| 0.16.2 before | Passed, n=3 per cohort | 1269.33 ± 35.15 | 40.71 ± 0.81 | 33.06 ± 0.27 | 207/345 = 60% |
| 0.17.1 | Passed, n=3 per cohort | 1218.31 ± 8.95 | 40.64 ± 0.38 | 32.69 ± 0.15 | 207/345 = 60% |
| 0.16.2 after | Passed, n=3 per cohort | 1249.41 ± 14.38 | 41.22 ± 0.50 | 32.27 ± 0.13 | 207/345 = 60% |

Candidate MTP decode is 0.18% below the before control and 1.40% below the after
control; PP8192 is 4.02% and 2.49% below them. These observations do not establish
a version improvement or isolate the cause of the timing differences. The
comparison uses one prompt, three repetitions per cohort and a fixed sequential
version order; the displayed standard deviations are not confidence intervals.

Values are arithmetic means ± sample standard deviations of the measured
clock-adjusted phase rates. The guest monotonic/raw-clock ratio corrects backend
phase rates and is checked against Windows QPC; request wall time is separate.
This whole-request calibration is an approximation and does not establish a
constant clock rate during each individual phase.
Acceptance is the API-reconstructed accepted-token total divided by the
drafted-token total across measured MTP requests. It combines MTP and PLD and
does not identify individual MTP heads. Serial acceptance is unknown/inapplicable.

Each completed window contains 12 raw rows and 9 measured rows, retaining reps
1–3 and excluding rep 0. All 36 raw rows have exact 8192 input and 1/128 output
usage, zero cache/disk restoration and no reasoning output. Repeated greedy
output hashes agree within and across all three windows and both TG128 modes.
The before and after profiles match; the candidate profile differs only in
release versions, backend directory and separate candidate credential paths.
The prompt hash is `0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1`;
the frozen client hash is `fcbb75c8f02018ecd68b13d2160173c415a4a809f3b759012f001f36ff73403d`.
The saved Windows prompt file uses CRLF; this prompt hash binds the LF request
text, not the file's raw bytes. All corresponding request hashes and the frozen
client hash match across all three windows. Each window's mean, sample deviation
and weighted acceptance reconstruct from its raw measured rows.

The backend log retains raw phase rates. For example, candidate MTP rep 3 logs
37.178 tokens/s; multiplying by its observed mono/raw ratio 1.0999998853 yields
40.8957957358 tokens/s. The same calculation applies to both versions.

| Window | Measured mono/raw range | Maximum RAW–QPC difference | Raw MTP mean, tokens/s | MTP request wall mean, seconds |
| --- | ---: | ---: | ---: | ---: |
| 0.16.2 before | 0.9999996285–1.0000000334 | 0.0911 ms | 40.7133 | 10.0508 |
| 0.17.1 | 1.0832615899–1.1000000342 | 0.0736 ms | 37.3263 | 10.1912 |
| 0.16.2 after | 1.0832614802–1.0999998910 | 0.0793 ms | 37.9903 | 9.9483 |

RAW/QPC disagreement stays below handshake uncertainty in every measured row.
Clock ratios change between windows and repetitions. Corrected summed phase
durations remain 22–71 ms below independent request walls, consistent with
request overhead, while uncertainty about clock changes within a phase remains.

The effective v2 admission is **35/131 GiB startup and 18/18 GiB runtime**, from
the [human authorization binding](../../server/.local/optimization9h-20261004/halogen0171-backend-preparation-20261007/authorized35-source-binding.json).
That receipt supersedes the frozen contract's historical 40 GiB physical floor.
All three windows' sampled host RAM/commit minima remain above 18 GiB; these
0.2-second observations do not measure VRAM peaks or prove sufficiency starting
at exactly 35 GiB. The historical 48.42 tokens/s result used different arena
settings and is outside this matched comparison.

The first candidate startup ended during a checksum scan and contributes no
throughput result. The fresh attempt reuses the completed checksum only for the
same source and typed file identity; the unchanged normal verifier accepted it
([receipt](../../server/.local/optimization9h-20261004/halogen0171-backend-preparation-20261007/exact-ngram-receipt-reuse.json)).
An unused candidate token was separately repaired to the backend's required
43-character format; the receipt records zero prior candidate serving requests
and unchanged original credentials
([receipt](../../server/.local/optimization9h-20261004/halogen0171-backend-preparation-20261007/candidate-token-length-repair.json)).

Raw evidence resides under
`server/.local/optimization9h-20261004/halogen0171-backend-preparation-20261007/`:
`comparison35-0162-before`, `comparison35-0171-qualified` and
`comparison35-0162-after`.

Root's [final live receipt](../../server/.local/optimization9h-20261004/halogen0171-backend-preparation-20261007/live35-080f490e2cae47eca52ded6b6256e9aa.json)
confirms authenticated readiness, idle serving and the visible open console for
the exact original 0.16.2 profile, SHA-256
`50e09bc549f1238a42ff1f68e3a6304ada380ef5eb418adf28f60315f55bf9c1`.
The restored controller is PID 32908/run `8472be0502e24b149af5f06f8f6d0cf9`;
backend PID 26664/run `a4a5752affe440569cdf0dc1e868dcd7`;
visible Windows PowerShell 5.1 console PID 35972. Context remains 262144 and
console tracing is restored to true. Reported physical/commit headroom is
26.4529/116.1385 GiB, with startup 35/131 and runtime 18/18 GiB floors.
The reviewed warmed-WSL keeper was promoted only after all measurements
([promotion receipt](../../server/.local/optimization9h-20261004/halogen0171-backend-preparation-20261007/warmed-lifecycle-promotion.json));
no serving token-rate gain is attributed to that lifecycle change.
