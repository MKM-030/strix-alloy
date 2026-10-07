# Halogen PLE: exact native controls, 8 October 2026

Two owned component controls completed with the same natural raw-CRLF input of 8,192 actual tokens and 128 generated tokens. Request settings were temperature 0, seed 1, Thinking Off, Cache Off, MTP2 and PLD3,3. The second request followed the normal fresh-request reset and substituted retained, exact original-GPU layer-1 key/value projection outputs. It did not use an NPU producer.

The full output SHA256 was identical. Both requests reported 67 accepted native draft tokens out of 120, or 55.8333%. Actual runtime table pointer/generation and immutable-file mappings were independently bound before arming and rechecked after the export. The bounded 22-file export passed hash checks. Offline CPU history, segment starts, row IDs, FP8 gather and BF16 input preparation matched exactly for all 8,192 tokens. That CPU replay does not compute the key/value projections.

## Component timing

| Instrumented interval | RAW wall milliseconds |
|---|---:|
| Original key projection | 43.614605 |
| Original value projection | 11.138067 |
| Publication of retained key/value results | 38.640195 |
| Complete instrumented stock consumer | 554.564514 |
| Complete instrumented ready consumer | 115.161066 |

The input is 40 MiB BF16; the key/value outputs total 200 MiB. Publication is already a substantial cost. The complete consumer intervals include common native key RMS, checks and readbacks. The first request additionally performs fixture capture and poison/oracle work, and the first and second requests have different cache history. These intervals therefore do not establish a controlled production speedup. Nested phase and observer durations must not be added or subtracted to manufacture an uninstrumented cost.

The two request walls were 16.823599 and 10.116678 seconds. Their raw engine rates are retained in the JSON evidence with `rates_qualified=false`. This is neither a warmup-plus-three serving cohort nor an NPU throughput measurement. No new Prefill, Decode or acceptance improvement is qualified.

## Result and next boundary

Exact GPU-result substitution and CPU input preparation are now demonstrated for this fixture. Live early input publication, independently qualified complete projection weights, an NPU producer, a measured preparation lead and a whole-engine gain remain open. The captured 120-byte descriptors contain metadata and pointers; they are not exported projection matrices. The default production path remains unchanged.

The normal visible ServiceNow server is restored on port 8840 after the controls. Both managed starts used the authorized 35 GiB physical / 131 GiB commit admission with 60 stable seconds. Runtime reserve remains 18/18 GiB. These successful starts occurred above the threshold and do not prove sufficiency at exactly 35 GiB.

Raw evidence: `server/.local/optimization9h-20261004/next-mechanism-20261007/ple-controls-2c6e928c1d1f46499b8038f36f4c729f`. The companion JSON pins native, CPU and final restoration artifacts. Tool session 81988 must be observed terminal before that JSON and continuation receipt are finalized. No unchanged repeat of this capture pair is needed.
