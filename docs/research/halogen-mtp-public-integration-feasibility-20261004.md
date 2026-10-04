# Public MTP integration feasibility — 4 October 2026

There is no runnable supported Halogen-to-NPU head replacement in the retained
work. The immediate inaccessible asset is an **upstream supported engine
interface** for head inputs, continuation publication and accepted-prefix
feedback, or an online token-ID block-verification interface with retained
target state. More weight preparation
does not create either interface. No head integration code was added or built;
this receipt used source, small metadata and public documentation only.

## Current upstream surface

On 4 October, `git ls-remote` of the official Halogen repository returned HEAD
`7f31bbd4021f217a1be9776bdb7304bcf8eca62d`, the same revision already inspected.
The current `main` AGENTS, FLAGS and NPU pages were also checked. The engine is
closed source and the public tree contains deployment code; deployment patches
cannot change engine execution. The documented public clients use port 8731.
[Upstream AGENTS](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/AGENTS.md).

| Public surface | What it permits | Remaining integration gap |
|---|---|---|
| Startup flags | Native MTP depth/policy, native prompt lookup, checkpoint selection | No documented external drafter/plugin, head callback or live ngram feed |
| `HALOGEN_MTP_HEAD` | Selects an HGN native head for a GGUF trunk | No provider selection or external execution; embedded HGN checkpoints ignore it |
| Chat/completions and continuation | Rendered-text generation and continuing the final assistant message | No target residual export, accepted-prefix transaction or draft-token block submission |
| Greedy scoring | First next-token logprobs with `max_tokens:1`; at most 20 top logprobs | No prompt-position/block scoring; `n>1` is refused |
| Checkpoint CLI | Validation/conversion and offline `ppl`/`niah`; `ppl` can consume token IDs and save per-position scores/argmax | Separate model-loading jobs, with no serving-request draft feed or retained verification transaction |
| Small NPU models | Five documented architectures, with compatible fine-tunes of the first four | No arbitrary Flash-Next MTP-head loader |

The supported flags are read at startup. Native prompt lookup copies earlier
request-context tokens and needs the native head to open a chain; the ngram
checkpoint is model input data, not an external proposal-update service.
[FLAGS](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md),
[API scoring](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/README.md),
[NPU models](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/NPU.md).
This is a conclusion about the documented supported surface, not an inference
from failed source-page downloads.

The prepared `halogen0162_mtp_quality_publish.c` cannot bridge this gap within
public APIs. Lines 243–250 read private model fields, line 258 still runs the
native MLP, and lines 402–412 write a live instruction jump. Public HIP copies
do not make those engine accesses supported. It is an unbuilt diagnostic and
cannot establish a replacement speed gain.

## External drafting: exactness and work

For greedy drafts `d1…dk` at token prefix `x`, independent target queries at
`x`, `x+d1`, …, `x+d1…d(k−1)` can be exact: accept consecutive `di` only when
it equals the target argmax at that prefix, then emit the first mismatching
target token. This requires identical token prefixes, chat-template state,
stop rules and tie handling. Text/token round-trip identity and a public raw
token-ID prompt interface have not been established for Halogen.

In the present workload, [service.py](../../backends/halogen-wsl2-0.16.2/scripts/service.py)
lines 212–213 fix one KV slot, and the retained stock comparison uses cache Off.
Those prefix queries queue serially and each performs target next-token work;
cache Off also re-prefills the growing prefixes. Draft computation, HTTP and
template work are additional. They do not remove native head work or reuse
its target verification transaction. Continuing once after the whole draft
chain checks only the next conditional, not the proposed tokens. Asking the
target to generate the block returns target output with ordinary target work.
The public `ppl --ids --ref-out` CLI can score a specified sequence offline,
including per-position argmax. It loads its own model and does not attach to
the serving request's state. Repeated offline invocations therefore supply
neither the required live transaction nor a justified millisecond replacement.
[Checkpoint CLI](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/AGENTS.md).

Standard sampled speculation instead requires position-wise
`min(1, p_i(d_i)/q_i(d_i))` acceptance and rejection draws from
`[p_i-q_i]_+`. The scoring surface supplies no batched verifier and does not
generally expose all required distributions. Independently sampling the
target and matching drafts remains exact but gives no target compute reduction.
The algorithm's speedup depends on evaluating draft-conditioned target rows
together. [Leviathan et al., ICML 2023](https://proceedings.mlr.press/v202/leviathan23a.html).

Multiple target slots or a different cache policy define a different workload;
these observations do not prove every possible external configuration slower.
There is no evidence that such a configuration fits the measured head budget,
and no justified external draft implementation follows for the current control.

## Speed and asset receipt

| Retained scope | Mean | Consequence |
|---|---:|---|
| Native count1 complete head, 73 calls | 3.323560 ms | Instrumented bracket; excludes 42 multirow calls |
| Native MLP only | 0.404612 ms | Narrower replacement budget |
| Qualified fixed-top10 NPU expert graph | 1.504985 ms | Already 1.100373 ms over the MLP budget before router/shared/transport; leaves 1.818575 ms of the full-head bracket |

Sources: [head timing](halogen-mtp-full-head-event-timing-20261004.md),
[fixed-top10 scope](halogen-npu-top10-20261004.md). The ONNX timing does not bound
the newer direct-DD path. The retained expert0 outputs fail one FC1 element
per case against the corrected BF16 affine reference; all four calls pass the
same tolerance against the independently defined BFP operator reference.
Exact transaction arithmetic remains unproven. Neither comparison qualifies
full-head execution or acceptance. [BF16 contract](halogen-dd-reference-contract-20261004.md),
[BFP operator comparison](halogen-dd-bfp-reference-20261004.md).

The 31-tensor extraction filters only `mtp.*`
([metadata reader](../../scripts/benchmarks/halogen_npu_mtp_metadata.py), lines
48–62); it excludes shared embedding and vocabulary matrices. Complete qualified
current-v2 attention/HC/shared-embedding/output assets and a full NPU graph are
unprepared. These weights exist in the checkpoint in principle; unlike the
supported engine interface, they are not inherently inaccessible. Scalar raw
residual input plus output is 40,960 bytes; an 8192-row bootstrap is 160 MiB
each direction. No supported import/publication path or zero-copy contract is
established. [Full-head asset and state receipt](halogen-mtp-npu-full-head-plan-20261004.md).

## Accessible sibling-engine seam

PROJFIX has the smallest concrete source seam for the framework goal while
retaining its existing IQ4_NL-PROJFIX target and tokenizer. At its pinned base
`40a9f4d01b69314d0f75c9120abe8e199e49111d`, a drafter implements
`begin/process/draft/accept`; `draft` fills the token-ID vector supplied as
`dparams.result`. The server sends that vector through target block evaluation,
native acceptance and recurrent/checkpoint rollback, then reports the accepted
count. This can accommodate a new NPU drafter through ordinary source changes
and a separately built candidate, without modifying engine instructions.
[Drafter interface](https://github.com/pwilkin/llama.cpp/blob/40a9f4d01b69314d0f75c9120abe8e199e49111d/common/speculative.cpp#L138),
[token-vector contract](https://github.com/pwilkin/llama.cpp/blob/40a9f4d01b69314d0f75c9120abe8e199e49111d/common/speculative.h#L53),
[server verification](https://github.com/pwilkin/llama.cpp/blob/40a9f4d01b69314d0f75c9120abe8e199e49111d/tools/server/server-context.cpp#L3912).

The existing target shards and shared-Q8 MTP GGUF are retained in
`C:\AI\models\qwen38-flash\projfix`; the registered runtime remains pinned.
For a feature-dependent MTP drafter, this source also exposes staging
`llama_get_embeddings_nextn[_ith]` and the MTP implementation's accepted-row
replay. A standalone token-only drafter needs no hidden export, but a qualified
NPU executable with the original token IDs and architecture is not prepared.
The existing expert-only Halogen graphs cannot generate draft tokens.
[Existing asset/runtime receipt](../../backends/projfix-windows/compatibility.json),
[MTP result and remaining NPU gates](mtp-host-implementation-20261001.md).

GUFO's pinned `7e924c2d787aabf640db3c0f818cb824dc18ec8e` also defines
`IDraftBackend::Propose`, target-hidden input, accepted/correction feedback and
snapshots. Its live Flash-Next implementation uses its specialized
`Session::PrepareDecode/FinishDecode` path; attaching a generic provider does
not automatically replace that drafter. `TeacherForce` is a diagnostic whose
head state requires restore/resync, not a production external-verifier API.
[Provider interface](https://github.com/thomas9120/gufo/blob/7e924c2d787aabf640db3c0f818cb824dc18ec8e/src/core/speculative/draft_backend.hpp),
[Flash-Next session](https://github.com/thomas9120/gufo/blob/7e924c2d787aabf640db3c0f818cb824dc18ec8e/src/models/qwen38_flash_next/engine.hpp#L153).

Thus the sibling route removes the inaccessible-engine-interface obstacle but
still needs the actual NPU draft executable, its complete weights/state and
measured acceptance/latency. A callback-only patch would not supply a runnable
NPU path, so none was added. Its checkpoint and timing would be that sibling's,
not the Halogen v2 control. No end-to-end NPU improvement is established.
