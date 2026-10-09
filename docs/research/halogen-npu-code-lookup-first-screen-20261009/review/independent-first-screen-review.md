# Independent review: first CPU MiniLM quality screen

The retained arithmetic and identities are consistent. This specific reranker fails the CPU quality screen; NPU placement is not justified by the result. Faster placement would not establish recovery of lost source spans or supply the absent no-answer/ambiguity gate. Retain the first result unchanged.

Review used saved JSON/text, SHA256, source ASTs and stored NPY arrays only. No evaluator/prototype/tokenizer/runtime import or execution, inference, additional questions, tuning, hardware/server/WSL/lifecycle action or Git mutation occurred. Frozen artifacts were not edited. Only this separate review was written.

| Recomputed metric | CPU lexical/BM25 | CPU MiniLM rerank |
| --- | ---: | ---: |
| Known questions with a correct file among top3 | 13/13 | 13/13 |
| Known questions with an expected-span overlap among top3 | 12/13 | 10/13 |
| Expected spans overlapped | 13/17 | 10/17 |
| Correct explicit no-answer refusals | 0/3 | 0/3 |
| Explicit ambiguous status on ambiguous truth | 0/3 | 0/3 |
| Raw median lookup interval, all16 calls | 117.219250ms | 485.600800ms |

All16 saved questions, prompts/categories and per-row metrics match the frozen dataset and independent recomputation. All17 ground-truth spans match current source hashes, normalized-LF excerpt hashes, inclusive bounds and qualified function/class scopes. The index and frozen eligible corpus have the same52 source-file identities, all currently unchanged. Every baseline/reranked question has the same12 candidate identities; saved scores match the original CPU candidate order and reranked top3 follows descending logits. All96 returned excerpts match re-read source bytes/spans/hashes and index generation.

Required publication limits:

- A span hit means any line overlap, not complete implementation recovery or successful task completion. The17-span denominator includes alternative locations for ambiguous questions. File hits use13 known questions, excluding3 unsupported cases; this is not100% answer accuracy on16 tasks.
- Both arms return status ok and three excerpts for every unsupported question and all three ambiguous questions. No-answer truth applies to the bounded Python corpus, not universal absence from the repository. lookup_sufficient remains null. Main-model-request avoidance and autonomous task completion are unmeasured.
- All16 exact_cpu_direct flags are false. The four identifier/path examples are multiword prompts and do not exercise the whole-query exact bypass. All16 queries were reranked:16×12=192 pairs, plus one explicitly excluded model warmup.
- Saved feeds contain576 INT64 arrays for192 sequential pair keys, each shape[1,256]. Masks, right padding, segment layout and <=64 query-token bound are consistent; actual pair lengths are248–256. Explicit only_second passage truncation means the model may not see all text in the returned32-line chunk. No tokenization reconstruction was executed here.
- One serial pass measured baseline before rerank for each query. No repeats, randomized arm order or clock qualification exist. Session load106.5877ms, warmup, construction/acquisition, index build and feed publication are excluded. Lookup includes Git/source freshness, lexical ranking and excerpt reads; rerank adds tokenization and12 sequential CPU calls. Raw session-call median29.620150ms excludes surrounding preparation. These are limited observations, not a NPU/task-time/native-performance benchmark; do not convert them into token rates.

All eight staged model assets match cpu-preparation.json sizes/hashes; report graph/tokenizer/preprocessing pins match. CPU preparation records original/fixed equality on one reference pair and CPUExecutionProvider only. That single probe does not qualify all-pair equivalence, NPU compatibility or future placement. Source guards preserve the first output directory and contain no tuning loop; this is consistent with root's first retained run, not an independent attestation of every historical process.

The reranker preserves file hits but loses two question-level span hits and three expected-span overlaps, correcting neither refusal nor ambiguity. This screen provides no quality-based admission for NPU work. Later changes require separately versioned evaluation, not tuning against or rewriting this result. Public notes should preserve these denominators, authored-not-human-benchmark scope, same candidates, truncation and timing limits. Use an explicit receipt/source whitelist; runtime packages and roughly91MB graph files need not be included. Retain revision, publisher/license and original absolute-reference scope if assets are redistributed.

Reviewed SHA256:

| Artifact | SHA256 |
| --- | --- |
| first-quality-screen/report.json | 4239530cedc8dac30da5ef8aa2bc594c1dbc609a822f4f57d579e33de432e85e |
| first-quality-screen/feeds.npz | 4de8b4a5b730f38e6789e2c232a89a638438c72c1b21fa3c2a9fc87546e3eb94 |
| evaluate_cpu_lookup.py | 8e3c4adc625fcffc97d4cc130efeb52d34c18a1865dff49f67b1e63754ee17e2 |
| cpu-preparation.json | 35174300d661d76964142be0905abee884a8c6d7899c96df6def69fe69988a5c |
| Prototype source | 1cab17e904d4c45bb8b071333f82d9de8f18ffc35726cbf2cd39fd093e61c767 |
| Frozen questions | b6ec91c58ad0926f7a51af17a87d65e9f8611d884ec85b75c3522e0d21f0709a |
| Frozen truth | 47bfa360574b4801a123ffb8ce1e9b1da0f17704bdfd84950b4afc676c8b5156 |

Verified index generation: c39df1e9b6e78c9369ad553ea52f4ce932b19acb634e17859eee444aa2a9fca8.
