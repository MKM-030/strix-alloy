# Prospective DNZ comparison with private8K capacity

This is a distinct allocation experiment following the terminal
[32K attempt with zero requests](halogen0203-dnz-prefill-20261111.md).
It does not relax an admission threshold or repeat the same profile.

Keep the exact2048-input/128-output natural request, weights,0.20.3ELF,
Prefill chunk and maximum8192, temperature0/seed1, MTPgate0.90, PLD3,3,
Cache/Thinking/VisionOff and prefetch0. Change only the unused private capacity
from32768 to8192 equally in all three arms. Every arm fits the entire request;
the normal32K server is restored after the experiment.

Within this new cohort, profiles differ only in DNZ **0 / 1 / 0**. Each arm has
one excluded warmup and three measured requests. This protocol qualifies only
2048 input tokens at8192 capacity; it cannot qualify an8192+128 request or be
pooled with the failed32K attempt.

The supported ordinary one-slot path omits both explicit engine capacity keys;
the native pool defaults to its8192 context. Source accounting estimates
0.609375GiB of KVrow-equivalent reduction or0.675201GiB of pooled budget
reduction. These are allocation estimates, not measured physical RAM release.

The private memory-policy copy clamps v2commit admission to **at least131GiB**
before its unchanged Vision charge. This prevents the implicit8K path from
falling to its lower existing estimate. Startup stays30/131GiB, every request
22/22GiB and runtime18/18GiB. No active normal policy or global WSL setting is
changed. If actual admission fails, retain the failure and restore normal;
neither the threshold nor the private capacity is automatically reduced again.

A private copy of the existing RAWcollector uses default slot1 at its two
configuration reads when the optional slot key is absent. All native health,
actual count, accounting, concurrency and timing checks remain. Its original
file and the previous evidence stay byte-identical.

The original counter, phase-clock and interpretation rules remain: exact
process/ELF/PIE mapping, two out-of-timing uint64reads per request, stockdelta0
and candidatedelta>0, unchanged RAW bounds plus independent wholeHTTPQPC,
exactUTF8/finish/count/scoped-counter comparison and no claim of independently
reconstructed native output-ID or full neural acceptance. No EXTERNAL_STREAM,
HDO2consumer or NPU helper is enabled.

Only a fresh Root-reviewed source/dependency seal permits execution. One large
engine, actual game/GPU checks, captured lifecycle handles, no timeout-based
restart and exact normal32K restoration remain mandatory. No performance result
or successful memory release is claimed by this prospective plan.
