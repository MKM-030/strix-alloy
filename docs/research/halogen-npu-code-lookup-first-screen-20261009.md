# First CPU code-lookup quality screen — 9 October 2026

The first frozen MiniLM reranking screen did not justify NPU placement. Compared with CPU BM25, it reduced source-line retrieval quality and increased the observed lookup time. It remains disabled. No GPU/NPU computation, Halogen inference, server restart, or new native prefill/decode/acceptance measurement occurred in this screen.

## Scope and preserved first evaluation

An independent agent authored and froze 16 questions, the expected source locations, and the complete eligible source corpus before root evaluation. The questions comprise six clear-intent, four identifier/path, three ambiguous, and three out-of-scope questions. They are authored development probes, not real human requests or a representative coding benchmark. The prototype author did not inspect these questions or the ground truth before freezing the implementation.

The corpus contains 52 tracked Python files under `server/` and `backends/halogen-wsl2-0.17.3/scripts/`, divided into 248 bounded chunks. Private, hidden, untracked, cache, and `.local` files are excluded. The CPU prototype verifies source hashes, returns at most 12 lexical candidates and three exact, re-read source excerpts, and leaves `lookup_sufficient=null`. It makes no automatic large-model calls. Its four scoped filesystem correctness cases are separate from this quality screen.

Root preserved exactly one successful first evaluation. Early evaluator errors occurred before model evaluation and were fixed by using the frozen corpus's `sha256` key. No question, truth, threshold, model, ranking policy, or preprocessing was tuned against the completed result, and the screen was not repeated.

## Model and preprocessing

The model is `cross-encoder/ms-marco-MiniLM-L6-v2`, revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`. The original ONNX file SHA256 is `5d3e70fd0c9ff14b9b5169a51e957b7a9c74897afd0a35ce4bd318150c1d4d4a`. A derived graph fixes each input to one pair of 256 positions and the output to one logit. A single CPU preparation probe produced bit-identical original/fixed outputs; this does not establish all-input equivalence or NPU accuracy.

The pinned tokenizer uses a maximum query length of 64 tokens, truncates only the passage, and pads on the right to 256 positions. Passages include the source path, inclusive line range, and excerpt. Scores are raw logits used for ordering, with no answer-sufficiency threshold. Exact whole-query identifiers/paths can retain the CPU direct route; that policy is the same in both arms. All 16 frozen prompts were multiword queries and none exercised this bypass, including the four identifier/path-category prompts. All 16 therefore scored the same 12-candidate sets.

ONNX Runtime sessions explicitly used only `CPUExecutionProvider`, one intra-op thread, one inter-op thread, and sequential execution. The import emitted an `Init provider bridge failed` warning; the retained session provider list was CPU-only. There was no NPU discovery, registration, session, execution, or placement qualification. Tokenizers 0.23.2 was installed only in the isolated preparation directory; existing runtimes were not modified.

## Results

| Metric | CPU BM25 | CPU BM25 + MiniLM |
| --- | ---: | ---: |
| Known-answer questions | 13 | 13 |
| Correct source file in top three | 13/13 | 13/13 |
| At least one expected line span in top three | 12/13 | 10/13 |
| Expected spans found in top three | 13/17 | 10/17 |
| Correct abstention on out-of-scope questions | 0/3 | 0/3 |
| Raw median full lookup observation | 117.22 ms | 485.60 ms |

The line-span metric requires the same file and overlap with a frozen expected inclusive line interval. It does not judge full implementation recovery or the completeness or correctness of a generated answer. File-level success alone hides the line-location regression. Both arms returned lexical matches for all three out-of-scope questions, so neither supplies a qualified automatic answerability gate. All three ambiguity-category questions also returned `ok` in both arms; lexical tie detection is not a calibrated semantic ambiguity decision.

Root scored 192 query/passage pairs after one excluded model warmup. Model session load was 106.59 ms and is reported separately. Each task was observed once, with the baseline followed by the reranked lookup. The medians span different question types and include source freshness checks, retrieval, and, where used, tokenization/model work. They are neither a cold/warm repeated latency cohort nor a controlled CPU-versus-NPU comparison. No claim of a precise production slowdown or statistically established performance gain follows from these observations.

## Decision and relation to the Reddit proposal

The [Reddit harness](https://github.com/aic0d3r/qwen38-strix-halo-harness/tree/2da9e968cc4ffc57099d33bc95f0fd5dbbe5b373) uses separate embedding/reranking tools to reduce agent work. This CPU probe uses a different model and a small local corpus; its negative result does not refute that author's pipeline or all semantic retrieval. It does reject this unchanged MiniLM candidate for NPU placement. Improved placement would not repair worse retrieval quality.

The CPU index remains a development tool with unresolved sufficiency, ambiguity, and real-workflow benefit. No avoided large-model request count, shorter useful prompt, task-time saving, native token-rate increase, or MTP-acceptance improvement was measured. GPU serving remains Halogen 0.17.3 with the experimental selector and NPU reranking off. The broader acceleration goal remains active and unachieved.

## Retained evidence

The [evidence directory](halogen-npu-code-lookup-first-screen-20261009/) contains exact copies of the prototype, frozen question/truth/corpus documents, evaluator and preparation scripts, model identity receipt, first result and tokenized pair feeds, independent review, and root publication manifest. Model weights and third-party runtime packages remain local and are not published. SHA256 identities in the manifest bind the original bytes; local absolute paths in historical receipts describe the original run, not portable execution instructions.
