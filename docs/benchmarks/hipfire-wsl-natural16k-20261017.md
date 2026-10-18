# Hipfire WSL Natural16K baseline and inline-Q8 observation — 2026-10-17

**One candidate completed; no isolated kernel gain or production promotion.** Hipfire commit
`ddee82c7464946c86f946d89af1b5634f212d466` ran through WSL/ROCDXG with ROCm
SDK 7.14. The model uses **MQ2-XTS4500 weights and q4 PLE**, a different
quantization from Halogen IQ4; this is not a matched Halogen comparison.

The natural, non-repeated prompt has exactly **16,384 rendered input tokens and
128 actual output tokens**. Each arm completed one excluded warmup and three
measurements, greedy sampling, thinking off, 32K allocated context, q8 state,
legacy KV storage, one slot, cold resets and zero reported cached tokens.
Prompt/session caches and PLE prewarm/load-fill/hot-store budgets were zero.

| Arm | Native prefill tok/s* | Native decode tok/s* | Native accepted / drafted | QPC request → done receipt, mean s |
|---|---:|---:|---:|---:|
| AR | 778.3 | 21.03 | N/A | 26.72971 |
| Native MTP2 | 800.7 | 20.8 | 124 / 215 (57.674%) | 26.74837 |
| Inline-Q8 MTP2 candidate | 822.6 | 23.7 | 159 / 269 (59.108%) | 25.34120 |

The candidate added only `developer.qwen4_gdn_q8_inline=1` to the baseline
configuration. Observed mean QPC request-to-done time fell **5.260775%**, from
26.74837 to 25.34120 s. Mean request-to-first-visible-fragment receipt fell
**1.848204%**, from 20.31122 to 19.93582 s. These are complete-window observations:
baseline MTP retired in one of three runs, while candidate MTP retired in none.
That route difference confounds attribution to the inline conversion kernel.

*Native phase clocks remain **independently unqualified**. In the third AR
measurement, native `prefill_ms=22128.4` exceeds the Windows QPC request-to-first
visible-fragment receipt of `21165.924 ms`. The source uses request-local timers
and does not explain this inversion. Native fields are preserved observations;
they are not corrected or presented as qualified GPU phase rates.

The QPC column measures request send to final native JSONL `done` receipt,
including generation, emission, terminal commit handshake and transport. It
excludes model load and the preceding reset. Text events are fragments, including
MTP bursts; no client decode rate or 127-token interval is inferred.

Acceptance is measured-only `sum(accepted)/sum(drafted)`, before later semantic
filtering. Measured output hashes are stable within each arm; candidate MTP
matches baseline MTP in all three measurements, while AR differs:

- AR: `0e995171d60ba60c8161c84d24ce1fbe14708b5e2e97697aa926ad53f71de570`
- MTP: `3f6a21fccdb79eee79fd5f7c9ca99a7f1c18bd174ccfc954d4f6031a1973d116`

The measured hash match is limited to this fixture. No exact AR/MTP equivalence,
qualified phase-clock speedup or joint 1,925+ prefill/fast-decode result is claimed.
The baseline's historical normal-ready receipt is dated 17:57:03 UTC. The
candidate completed and normal Halogen 0.18.7 serving was authenticated ready
again at 18:10:04 UTC on port 8840. The trial coordinator and its WSL helper
are terminal; the sole running container belongs to normal serving. The
candidate was not promoted. The broader acceleration goal remains unachieved.

The [JSON evidence](hipfire-wsl-natural16k-20261017.json) retains sample arrays,
clock limitations, configuration and SHA256 pins. Original raw evidence remains
unchanged under `E:\strix-alloy\hipfire-mq2-ddee82\results`, in
`native-windows-trial-qpc-v5` and `native-windows-trial-inline-q8-v1`.
