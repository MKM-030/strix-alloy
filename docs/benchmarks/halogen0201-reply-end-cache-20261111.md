# Halogen 0.20.1 complete-history cache comparison

The Off / Flexible / Off V3 campaign completed all 24 requests on 11 November 2026 and restored the normal server. Each arm has one excluded warmup conversation and three measured two-turn conversations. All three follow-ups use the exact prior assistant answer and 8192 actual input tokens from a non-repeated War and Peace document.

| Follow-up observation | Off before | Flexible | Off after |
| --- | ---: | ---: | ---: |
| First nonempty content, mean seconds | 6.135995 | 0.243087 | 6.234544 |
| DONE event, mean seconds | 6.705916 | 0.830447 | 6.801810 |
| Clean HTTP EOF, mean seconds | 6.707109 | 0.831481 | 6.802710 |
| Cached / newly processed input tokens, every measured follow-up | 0 / 8192 | 8160 / 32 | 0 / 8192 |
| Actual output tokens, three measured follow-ups | 29 / 29 / 24 | 29 / 29 / 29 | 29 / 29 / 24 |
| API neural-head accepted / drafted | 39 / 55 | 42 / 60 | 39 / 55 |
| API neural-head acceptance | 70.91% | 70.00% | 70.91% |

Flexible reused 8160 tokens in all three measured follow-ups. Its observed first-content latency was about 96% lower than each cold control. The third follow-up changes output text and length; both answers contain facts present in the document. All samples remain in the means. The full-cohort output-matched comparison therefore remains unqualified. This does not establish a causal decode gain, general accuracy equivalence, faster prefill kernels, or the incremental contribution of reply-end caching alone. Dividing the full 8192 input tokens by cached latency would misrepresent newly executed prefill work.

Caching also costs time on the cold first turn: mean first-content latency is 6.292798 seconds with Flexible versus 5.887651 and 5.972982 seconds for the controls, a 5.35–6.88% increase. The normal serving profile retains Cache Off. This study identifies a useful follow-up-latency option for suitable conversation workloads rather than a universal speed improvement.

Fixed controls are v2, context/pool 32768, one slot/concurrency one, paired `prefill_chunk=2048` and `max_prefill_tokens=2048`, gate 0.90, Q4 draft vocabulary, PLD `3,3`, temperature 0/seed 1, 128-token output cap, Thinking/Vision Off and prefetch zero. First turns contain 8126 actual input tokens and produce 34 tokens. API phase rates are observations only; no RAW observer was used. API neural-head acceptance retains its source-derived counter mapping and is not independently reconstructed. Lookup counters remain separate; Flexible follow-ups record 6/21, with no grammar proposals.

[Numeric results](halogen0201-reply-end-cache-20261111.json) retain per-request evidence and separate first-content, DONE and EOF clocks. The [V3 preregistration](halogen0201-reply-end-cache-plan-20261111-v3.json) has SHA256 `714c590afb051372d6b6592ef6317f0dbd35e7f9cb0f30e34ab2b4472aea284a`. Seventeen focused CPU tests pass; independent audit verifies all arms, exact histories, 35 source roles, resource observations and authenticated normal restoration.

Earlier attempts are preserved: V1 failed at startup inspection before any benchmark request; V2 completed its before arm but its Flexible launcher rejected explicit experimental capacity settings before controller publication. Both restored normal serving. V3 omits the explicit capacity fields in every private arm and verifies the unchanged actual one-slot/pool32768 defaults. No capacity policy was relaxed.

Fresh post-campaign checks at 03:24 UTC confirm matching API/engine 0.20.1, authenticated model discovery and a `READY` chat response on port 8840. The server remains online with the existing ServiceNow credential and visible request/response console. The normal controller run is `02e38955abb44f40be18b878c6768a63`, backend run `642221c86f6e4196b1f0ece635d80b59`. The broader acceleration and NPU objectives remain open.
