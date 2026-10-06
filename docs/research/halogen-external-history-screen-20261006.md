# Earlier-response retrieval: one causal CPU screen

**Retire this fixed earlier-response corpus for the retained request family.**
One finite CPU pass produced no external-history candidate at any of the 15
committed prefixes, and none after the two observed pending native MTP IDs.
This supplies no extra accepted-prefix opportunity and no reason for an engine,
model or hardware run. It does not exclude a different independently owned
corpus. The existing CPU/Vulkan/NPU predictor screens remain unchanged.

## The independently owned data actually available

The workspace contains [September 25 public responses](../../backends/halogen-wsl2/docs/benchmarks/responses-20260925.json):
14 retained samples, 10 prompt-recipe hashes and 10 distinct assistant texts.
Their memory/compute, context-check and independent-session recipes differ from
the retained river-town story family. The response `created` fields span
2026-09-25 13:03:41–13:48:24 UTC, before the evaluated response's retained
2026-10-04 02:29:47 UTC field. These are checked source metadata dates, not a
claim about live request timing. The 33,638-byte collection has SHA256
`a2cbc6a9d07d098d619169eda74c0fa99349a503bf81d3d9cca4fff78c7c0dee`.

The texts contain no original emitted raw IDs. The already installed
`tokenizers 0.23.2`, under `server/.local/article0162-20261003/vendor`, and that
directory's exact target `tokenizer.json` made a bounded derivation possible.
The tokenizer is 12,809,320 bytes, SHA256
`0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3`.
Python 3.13.15 loaded the existing CPU tokenizer; no dependency was installed.
Its binary hash and each derived ID sequence's hash are in the receipt.

Exact UTF-8 assistant-text deduplication retained the first occurrence, then
ordered the documents by their source dates. Encoding the ten texts produced
**829 derived IDs**, all in `0..248069`. Encoding used the actual target
tokenizer with no template, added special tokens, padding or truncation. These
IDs are owned retrieval inputs derived from text; they are not reconstructed
original emitted-token truth. Missing original prompt ID and the evaluation
response text were not used to fill the corpus.

A scoped filename/source inventory of this workspace found the 32 raw-ID MTP
files from the evaluated family and the separate early64 embedding-row candidate
fixture. The latter is a predefined row-verification schedule, not a response
corpus. Article corpus files contain public source code. No other ready earlier
response raw-ID corpus or newly trained predictor was identified by this bounded
inventory; this is not a global filesystem claim.

## Causal mechanism and the one result

An external corpus can supply an exact suffix continuation absent from the
current request's own history. That differs from the rejected same-history
lookup mechanism. This screen indexed only earlier-response documents, keeping
the four most recent positions of each exact token trigram. It compared suffixes
backward for at most 64 IDs, required at least three matches, kept the newer
position on a tie, and copied at most three following IDs within the selected
document. Neither committed request IDs nor pending MTP IDs entered the index.

For each frozen case, normal retrieval received the owned shifted8192 seed plus
only outputs committed before that case. A separately labeled hybrid query
appended the two pinned scalar MTP IDs and requested one third-ID extension.
Only after both proposals were recorded did the evaluator use future labels
and opening references. The [workload](halogen-independent-proposer-workload-20261006.json)
hash remained `1f3a2fbfafe1a8fd90f99c23dac49f3f0028644d5f010fcd057edfcce26a4919`.

| One fixed screen | Result |
|---|---:|
| Normal external-corpus candidate cases | 0/15 |
| Hybrid after observed pending2 candidate cases | 0/15 |
| Exact leading label matches from normal proposals | 0 |
| Usable hybrid third-label matches | 0 |
| Cases with a complete third label | 14/15 |

Every queried trigram had zero indexed corpus positions. There is no candidate
denominator for an acceptance percentage. The final missing third label remains
unscored. Native hit/opening execution, acceptance, timely readiness, target
Prefill/Decode and serving gain remain unmeasured. No native hook or controller
audit was retried.

## Reproduction and receipt

The new [script](../../scripts/benchmarks/halogen_external_history_replay.py)
and [complete receipt](halogen-external-history-screen-20261006.json) are in the
`gpu-draft-snapshot` worktree. Ignored fixture reads use the original source
checkout. Exactly one replay was executed:

```powershell
& 'C:/Users/Marcel/AppData/Local/Programs/Python/Python313/python.exe' -I 'scripts/benchmarks/halogen_external_history_replay.py' --source-root 'C:/Projects/strix-alloy-clean' --output 'docs/research/halogen-external-history-screen-20261006.json'
```

Script SHA256: `5b6de7867d63768aef04e161e2ac8b797f02114821de14e7bb15b7bd05761eb3`.
Receipt SHA256: `ff4ce63813e650c301fef9c6f6685fd2e31b48d5d999af5398c0e7142e410a8b`.
No model weights were loaded, and no download, build, WSL, GPU/NPU, engine
request, server lifecycle, native hook or Git action occurred.
