# Real native voice latency — 13 October 2026

Exact caching demonstrably reused real voice prompts. The repeated identical intent reached the same German name question in **33.201s**, compared with **46.541s** earlier (**28.66% shorter**). This is an observed trial comparison; persona/output changes and uncalibrated native clocks prevent attributing the entire difference to caching.

| Trial/turn | ASR → agent response | Time-correlated model calls | Cached prompt tokens |
|---|---:|---:|---:|
| Earlier intent | 46.541s | 3 | 0 |
| Repeated intent | 33.201s | 3 | 4,096 |
| Name → summary | 43.642s | 5 | 28,672 |
| Confirmation → goodbye | 44.029s | 6, including one finishing after goodbye | 28,672 |

The first input and final German question have matching SHA-256 values across the two trials. The repeated 7,608-token planner-sized prompt reused 4,096 tokens; later 13–14K agent-sized prompts reused 12,288. The original three different prompt types shared only 11/20/7 leading tokens, below the 4,096-token Exact boundary. Those cold misses did not predict the subsequent matching-template hits.

The repeated intent still contained an uncached 13,369-token call, despite an 11,995-token historical prefix match. Its cause is unproven. The name turn generated 873 tokens across five calls; caching does not remove their serial generation and orchestration.

**Capacity correction:** startup reports **six entries, approximately 111MiB each**, about **0.7GiB total**, with KV retained in place. Health `cap_mb=110` is a per-entry snapshot size, not the total budget. The container sets only `HALOGEN_PROMPT_CACHE=1`; sizing uses installed binary defaults. No runtime HTTP sizing setter exists.

During the confirmation window, fresh counters changed from 23→29 requests, 65,536→94,208 cached tokens, 125,869→144,754 processed prompt tokens, and 3,671→4,635 output tokens. These deltas match the six model lines. Final cache statistics were fresh (age 0.001s): 11 hits, 18 misses, six held entries and five total evictions. These are cumulative counters; they do not identify the cause of a particular miss.

Windows gateway interval unions were 39.533s for the earlier intent, 26.982s for the repeated intent, 34.865s for the name turn and 39.788s for all six confirmation calls. The last confirmation call finished at 18:01:31.869Z; terminal callback arrived 15.979s later. No shared model request ID connects these intervals to the Bot IDs, so attribution remains time-based. Native timestamps can jump and native phase clocks are uncalibrated; Windows wall times define latency.

ASR took 0.401/0.244/0.281s in the three-turn probe. Agent response→first PCM took 0.052/0.052/0.231s. German question, summary and goodbye were spoken, while English planner preludes remained. Numeric evidence establishes neither item identity nor order creation; the separate UI review determines that outcome.

After the call, all services were healthy and idle, cache matched Exact, physical headroom was 28.561GiB and commit headroom 119.71GiB. No inference, restart, cache mutation or private prompt disclosure occurred during this analysis. Keep Exact active; the remaining latency opportunity is reducing unnecessary serial planning through legitimate voice-specific routing and concise agent context.

Detailed bounded evidence: [real-voice-latency-20261013.json](real-voice-latency-20261013.json).
