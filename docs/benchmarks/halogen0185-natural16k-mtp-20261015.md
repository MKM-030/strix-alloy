# Halogen 0.18.5 natural 16K MTP policy comparison — 15 October 2026

Keep or restore fixed depth2 with gate0: this bracket does not establish a stable whole-request gain from confidence0.90.

The fixed2/gate0 → omitted-depth/gate0.90 → fixed2/gate0 bracket uses one natural War and Peace prefix, 16,384 actual input tokens and 128 ordinary output tokens. Each window excludes one warmup and retains all three measured requests. Temperature 0, seed 1, Thinking Off, Cache Off, PLD 3,3, context 32,768 and prefill/arena 4,096 are held fixed. All greedy outputs match.

| Window | Whole HTTP wall mean ± SD (s) | Generated tokens / whole HTTP second | API pooled prefill (tok/s)* | API pooled decode (tok/s)* |
|---|---:|---:|---:|---:|
| A-before fixed2 gate0 | 11.843273 ± 0.049046 | 10.80782 | 1841.278 | 44.878 |
| B confidence0.90 omitted-depth | 12.213424 ± 0.947627 | 10.48027 | 1825.068 | 40.553 |
| A-after fixed2 gate0 | 11.806082 ± 0.043978 | 10.84187 | 1846.646 | 45.046 |

*API phase rates are native engine observations and are not independently clock-qualified phase measurements. Pooled rates divide summed token counts by summed API phase seconds. Whole HTTP timing uses an independent client clock; no phase scaling or overhead subtraction is applied.

The gated mean HTTP time changes by +3.125% versus fixed-before, +3.450% versus fixed-after and +3.288% versus the equal-weight fixed bookend mean. Positive values mean slower. Fixed-after changes by -0.314% versus fixed-before.

| Window | Measured HTTP walls (s), all retained | API prefill arithmetic mean (tok/s)* | API decode arithmetic mean (tok/s)* |
|---|---|---:|---:|
| A-before fixed2 gate0 | 11.8978492, 11.8290844, 11.8028866 | 1841.310 | 44.879 |
| B confidence0.90 omitted-depth | 11.6879321, 11.6449702, 13.3073683 | 1825.223 | 42.427 |
| A-after fixed2 gate0 | 11.8405942, 11.7565651, 11.8210865 | 1846.651 | 45.050 |

The slow third gated request is retained in every pooled and arithmetic statistic. No measured request is dropped.

| Window | Head accepted / drafted | Head acceptance | Head rounds | Rejected head drafts | Accepted / head round |
|---|---:|---:|---:|---:|---:|
| A-before fixed2 gate0 | 177/408 | 43.382% | 204 | 231 | 0.867647 |
| B confidence0.90 omitted-depth | 177/330 | 53.636% | 204 | 153 | 0.867647 |
| A-after fixed2 gate0 | 177/408 | 43.382% | 204 | 231 | 0.867647 |

Confidence gating proposes fewer head drafts while accepted head tokens and head rounds remain unchanged. The higher acceptance percentage therefore reflects fewer rejected proposals; it does not show more accepted tokens per round or establish a whole-request speed gain.

Head, lookup and grammar ledgers are retained separately in JSON, with combined totals also preserved. Every request is linked to its raw response and independent client receipt. Nonstream first-body arrival is complete-JSON delivery and is not TTFT.

This is a bounded descriptive screen on one prompt. It supports no statistical-significance claim and no 0.18.1-to-0.18.5 version-speed or NPU-on/off claim. Historical 8K synthetic calibration and the historical 48 tok/s result are separate workloads.

Useful follow-ups are independent native phase-clock qualification, a small representative prompt set with longer outputs, a separate SSE delivery cohort if first-text latency matters, and exact offline preparation of a genuine natural 8K prompt. None is required to finish this bounded comparison.

## Final serving state

After all three windows and clean normal recovery, Halogen 0.18.5 was started with 262,144 context positions on the unchanged public port 8840. Both gateway and native health were verified ready with matching API/engine versions. The visible Windows PowerShell 5.1 console remains open. The serving profile retains Exact cache, vision enabled, Thinking On with medium effort and a 2,048-token thinking budget, prefill/arena 4,096, fixed MTP2 and PLD 3,3. Benchmark request settings and context capacity above remain separate from this serving configuration.

Final evidence: `server/.local/halogen0185-update-20261015/serving-full262-ready.json` and `checkpoint-final-ready-open.json`. All owned measurement clients and their three idle consoles are closed. No driver, firmware, voltage, model or global WSL setting was changed.

Manual restart through the updated starter, after normal stopping of the existing instance:

```powershell
.\scripts\Start-Halogen-ServiceNow.ps1 -HalogenVersion 0.18.5 -Profile Current4K -MtpPolicy Fixed2 -PromptCache Exact -ConsoleTrace
```

The public model remains `halogen-v2`; public credential path and endpoint are unchanged. `-MtpPolicy Confidence90` explicitly opts into the candidate. The starter defaults to the stable Fixed2 policy.
