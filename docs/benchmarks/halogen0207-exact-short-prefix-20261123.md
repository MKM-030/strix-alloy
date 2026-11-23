# Halogen 0.20.7 Exact reuse of a 2K system-prefix checkpoint

Exact caching cut mean time to receive the full response from **1.490 s**
and **1.494 s** in the two Cache Off controls to **0.385 s** with a
populated checkpoint, a **74.15–74.23%** reduction. Every measured Exact
follow-up reused **2,048 of 2,329 input tokens**. All six finished sooner
than both controls for their corresponding request.

| Arm | Input / processed / reused tokens | API Prefill (tok/s) | Native prompt duration (ms) | API Decode (tok/s) | MTP head acceptance | Full HTTP response (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Off before | 2,329 / 2,329 / 0 | 1,619.90 | 1,437.80 | 81.89 | 12/12 (100%) | 1.489851 |
| Exact | 2,329 / 281 / 2,048 | 859.29 | 327.03 | 81.41 | 12/12 (100%) | 0.385081 |
| Off after | 2,329 / 2,329 / 0 | 1,596.65 | 1,460.45 | 79.64 | 12/12 (100%) | 1.494082 |

Each time and rate is the mean of six measured requests per arm. The
native prefill rate uses only processed tokens. With reuse, the engine
processed 281 tokens at 859.29 tok/s and spent **77.25–77.61% less time**
in the native prompt phase. Windows QPC measured from dispatch through
receipt of the complete response body. Requests used `stream: false`,
so the comparison provides no time-to-first-token measurement.
The decode rates and MTP acceptance apply to three-output-token responses.
[Phase clock audit](../research/halogen0207-phase-clock-audit-20261123.md)

## Workload and controls

Frozen synthetic `/v1/responses` requests held `instructions` constant
and varied `input`. The renderer and tokenizer produced 2,291 identical
leading token IDs and 2,329 input tokens per request. Each arm sent one
seed, two excluded warmups, and three measured pairs of distinct questions
at temperature 0, with Thinking Off and a 32-token output cap. All 27
responses generated three tokens. For each fixture, the expected answer,
output bytes, finish reason and native speculation counters matched across
arms and repetitions.

Each private Halogen 0.20.7 v2/r2-HT4 engine used a single 32,768-position
BF16 KV slot, a 2,048-token `prefill_chunk`, an 8,192-token
`max_prefill_tokens` arena, and Vision Off. The only profile difference
between arms was the cache mode. All three seeds reused zero tokens and
took 1.715, 1.877 and 1.690 s, respectively. The lowest reserve sampled
during the requests was 27.84 GiB.

## Where the result applies

This test isolates the benefit of reusing a populated, aligned checkpoint
for short follow-up questions over a shared synthetic reference in a single
trust group. The earlier 8,192-token Exact checkpoint test used a different
geometry and workload.
[8,192-token Exact checkpoint test](halogen0207-exact-system-prefix-20261123.md)

Actual ServiceNow traffic uses a flat Chat Completions prompt and is
outside this live test's scope. The regular 32K Cache Off service was
restored on port 8840, and the post-run check recorded zero private
listeners and zero measurement helpers.
[ServiceNow prefix audit](../integrations/halogen-servicenow-prefix-cache-20261101.md)

## Evidence

Raw requests, responses, QPC intervals, native cache and speculation
counters, and the restoration receipts are retained locally under
`server/.local/halogen-update-20261122/primary0207/exact-short-prefix-prep-v1/exact-short-prefix-run-v1`.

The terminal auditor reconstructed all 27 observations from the retained
files. It accepts the campaign writer's inherited schema identifier and
verifies the short runner and fixture hashes, input count, cache
alignment, all three arms, and normal restoration.

| Artifact | SHA-256 |
| --- | --- |
| Short Exact runner | `7a8acadae819df2a3011fd8391d322b48c4c965ecedff99a7fd78675fd636d95` |
| Frozen tokenized fixture | `56bb4de14ca4891952fc8e6ccf5262796987e1f22631105410ceac17badae4e0` |
| Terminal campaign handle | `dd21e9a2ccf7c80b162ddb06873a722fb1f698b634e88a9415446c1325b36c42` |
| Terminal offline auditor | `b9419a522a043755075a1e46b89fe92671c807e24acc896fce8a7330631fa1c5` |
| Terminal offline replay result | `313219c1bb9938d2ead5710c4206a1a5c61425cc266d7db7c775eabd53d30015` |
| Restored profile readiness receipt | `eda11f56a2ecebd696aaedb457e6dcb74bd8dcf655582e63c7bb3c61b4c28039` |
| Post-restoration service check | `b68a1e44ef56380600fadc0e1a38346287ed85539d421ee9974a9e2e7b5f358b` |
