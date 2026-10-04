# Halogen 0.16.2: sampled MTP has one proposal per round

`HALOGEN_MTP_DEPTH=2` versus `3` does not change the sampled article workload's
proposal depth. The pinned engine's sampled dispatch uses one draft token and a
two-token verification input. A depth sweep must use a separate greedy workload
to exercise the multi-token chain. No speed improvement is established here.

The engine inspected was `backends/halogen-wsl2-0.16.2/.local/flash_serve`,
26,052,768 bytes, SHA256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
The identical retained WSL copy is
`/home/revn/halogen-re/flash_serve0162`. Inspection used GNU `objdump` and bounded
host instruction ranges; it did not execute the engine, create a provider
session, read checkpoint tensors, or launch an accelerator.

## Dispatch evidence

These are unrelocated ELF virtual addresses. The binary is stripped; helper
names below describe their role rather than an exported symbol.

| Address | Observed instructions and implication |
|---|---|
| `0x171b5c0`–`0x171b61b` | Initialize the depth field to 2, read the `HALOGEN_MTP_DEPTH` string at `0x22651` with `getenv`, parse it and store the selected value. |
| `0x172dad1`–`0x172dae5` | Load the request's sampling-state pointer at `request+0x150`, combine it with another request policy pointer, and branch to `0x172de79` when either is present. |
| `0x172daeb`–`0x172db61` | The path without those pointers reads the chain-length field at `request+0x108`, bounds the chain against verify capacity and remaining output, and calls the chain helper at `0x173b630`. The sampled branch skips this path. |
| `0x172de79`–`0x172dea1` | When the sampling-state pointer is present, dispatch to the sampled round at `0x172e303`, with a state-restore check before it. |
| `0x172e33c`–`0x172e363` | Load the sampling temperature and seed, set `ECX=1`, and call the draft helper at `0x17e9980`. Its error strings explicitly identify `draft_sample`; it rejects temperature at or below zero. |
| `0x17e9ad2`–`0x17e9afa` | The draft helper calls its sampler with `ECX=1` and copies back exactly 4 bytes, one token ID. |
| `0x172e368`–`0x172e397` | Construct two token IDs, the current base token and that one draft, then call the target sequence-input helper with `EDX=2`. |
| `0x172e3d5`–`0x172e3eb` | Set `ESI=1` and call the sampled verification helper at `0x17e9ea0`. The following code uses the acceptance probability and seeded coin, then commits the accepted draft or takes the rejection path. |

The [pinned upstream flags](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md)
also scope `HALOGEN_MTP_DEPTH` to greedy requests. Prompt lookup is greedy-only;
sampling uses the head alone. Adaptive speculation already defaults to
`32,0.35,64` and applies to both policies. Enabling that existing default is not
a new optimization. The
[pinned sampling description](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/CHANGELOG.md)
says sampled speculative and serial decoding agree in distribution, while a
seed reproduces a request on the same configuration.

## Retained counter corroboration

The sampled 65536-capacity / 32768-input article cell retained at
`server/.local/article0162-20261003/halogen-v2-c65536-p32768-fresh` generated
4623 tokens, accepted 2094 draft tokens, and proposed 2497. Proposed tokens
divided by output tokens minus accepted drafts is `2497 / 2529 = 0.9873`, close
to one proposal per base token. This is corroboration, not an independent
reconstruction of every internal round; startup, EOS and adaptive policy affect
the accounting. The greedy TG128 stock control's 69 accepted / 115 proposed
instead gives `115 / (128 - 69) = 1.9492`, consistent with depth 2.

The article client sends temperature 1.0, top_p 0.95, top_k 20, min_p 0, seeds
20260930/20260931, thinking enabled and low reasoning effort. It is sampled,
despite the engine's default depth being 2. In this retained cell retrieval
accepted 284/289 proposals (98.27%); implementation/review accepted 1810/2208
(81.98%). Acceptance varies with the output task. Dropping later proposals can
raise the fraction while reducing throughput; the fraction itself is not the
optimization objective.

## Effective matched follow-up

`scripts/benchmarks/article_bench_greedy.py` copies the article client with only
its module description, explicit temperature 0 / removal of sampling filters,
and final scope changed. It preserves corpus construction, prompts, geometry,
tasks, seeds, cache requests, thinking, output cap, timing and retrieval grading.
It executes directly; the coordinator performs no runtime source rewriting.

The ignored `run_depth3_article_20261004.py` prepares depth 2a → 3 → 2b on v2,
65536 capacity, 32768 input target, Exact cache, one slot, 18 GiB reserve, two
three-turn conversations and output limit 1536. Profile engine fields differ
only in `draft_tokens`; lookup placement and compute controls remain stock.
All six outputs must retain valid finish reasons, pass retrieval 14/14, show
cold initial prompts and warm follow-ups, and match request/output/reasoning
hashes, token counts and finish/cap counts against depth 2a before speed is
interpreted. Silent output-limit clamping fails the gate. Identically capped
outputs permit timing of equal limited work, with cap counts reported and full
completion unqualified. Implementation and review code remain ungraded until
a separate checker evaluates them. Deeper proposals
can lower the accepted fraction while improving tokens per verification round;
the measured decode and conversation time determine whether there is a benefit.

This greedy experiment is separate from the sampled article comparison. Its
result cannot be presented as a depth improvement to that sampled workload.
