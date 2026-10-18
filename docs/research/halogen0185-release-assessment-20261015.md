# Halogen 0.18.5 release assessment — 15 October 2026

Source and public-metadata review only. No container, WSL, model, hardware, serving request, selector, profile or lifecycle operation was performed. Root owns installation and actual performance qualification. Findings are verified against public main on this date; an image's label revision is not proof that public main and the image's shipped Python files are identical.

## Available image

The public GHCR manifest and configuration were read with an anonymous pull token, without downloading any image layer. The initial sandbox socket denial was followed by an approved read-only metadata request. At `2026-10-15 13:11:04 UTC` the registry returned HTTP 200:

| Identity | Value |
|---|---|
| Pinned image | `ghcr.io/peonist-ai/halogen-flash-server@sha256:94c9d76b6b938459e00805c61978808957703745fe573ca2d7f01e9157446b3d` |
| Tag / platform | `0.18.5` / `linux/amd64` |
| Manifest format / layer count | OCI image manifest / 23 |
| Config digest | `sha256:d82d32a56199dceb9a9c19c9b2309f499d4f67cb21c8f0a4a1348cbe58b58441` |
| OCI revision | `55e7ca209671` |
| Config creation time | `2026-10-15T06:35:11.691227857Z` |

Creation is build metadata, not an established publication timestamp. The direct registry endpoints were `/v2/peonist-ai/halogen-flash-server/manifests/0.18.5` and `/blobs/<config digest>` on `ghcr.io`. The image environment contains Cache2, chunk/arena32768, slots4, context262144, and `/opt/halogen/flash-tune.plan`; it contains no explicit MTP depth or gate. [Official quickstart](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/getting-started.md) now pins 0.18.5.

## Mechanisms that warrant a benchmark

**Confidence-gated MTP is the first candidate.** The documented default is `HALOGEN_MTP_GATE_P=0.90`: after each greedy draft, compare the top token's probability within the allowed token set; the first draft below threshold ends the chain but is still checked. The maximum is seven drafts. Explicit `HALOGEN_MTP_DEPTH` disables the default gate unless the gate is also set explicitly. Gate0 restores the prior fixed-depth path; unset depth then chooses two or three per conversation. Sampled requests ignore the gate. The documented output guarantee is unchanged greedy tokens at any gate value. Keep PLD3,3 and adaptation32,0.35,64 initially. The new shipped reservation allows PLD K up to seven, but the existing natural16K negative PLD evidence supplies no reason to reopen a wider-tail sweep. [Flags](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/FLAGS.md).

**The second candidate is strict-tool grammar drafting.** The release proposes schema-forced tool-call text and verifies up to eight rows together. Both greedy and sampled requests use it by default; `HALOGEN_GRAMMAR_DRAFT=0` disables it and `HALOGEN_GRAMMAR_DRAFT_SAMPLED=0` disables only sampled grammar drafting. Unconstrained prose cannot measure this mechanism. The new `timings.speculation.grammar` joins `head` and `lookup`; source drafted/accepted totals must sum to `draft_n`/`draft_n_accepted`. The release adds approximately18MiB of device reservation and keeps 0.18.4 disk-cache entries valid. The 0.18.4 prefill reorder can change replies versus 0.18.3 and invalidates older disk-cache entries once. Its token budget aliases now use precedence completion > output > max_tokens, and context-room clamping appears explicitly in timings. [Changelog](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/CHANGELOG.md).

For a positive grammar workload, declare a supported tool `strict:true` at the correct route location, use a closed object with required fields, and confirm schema enforcement. Calls inside reasoning are unconstrained. Unsupported strict schemas, images/logprobs, more than128 tools, or more than32 parameters can fall back to unenforced tools; inspect the request log and `halogen:strict_tools_unenforced_total`. A plain response JSON schema is distinct from the release's strict-tool speed claim. [Strict-tool contract](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/codex.md).

Upstream's 0.18.4/0.18.5 v2 ten-shape decode is60.2/64.2tok/s, about6.6% from the rounded table (the prose claim says6.4%). The ht43 row is61.5/64.7, about5.2%. The v2 strict-tool on/off range is17–20% greedy,24% at T1, and −1% at T0.7. Prefill moves less than0.3% in those comparisons. These are native reference-machine claims, not WSL measurements; v2 is around85W and ht43 around120W. [Measured conditions and results](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/performance.md#0185-against-0184).

## Exact finite local comparison recommended

Preserve root's qualified v2/tokenizer files, context/slot/pool capacity, one slot, Cache Off, paired chunk/arena, thinking controls, memory floors and recovery. Do not substitute upstream's larger native-memory defaults for the retained local profile. Use explicit `temperature:0`, `drafter:"mtp"`, identical requests and one budget field. These are recommendations for separate root-owned profiles, not edits made here:

| Arm | MTP depth | Gate | Grammar draft | Purpose |
|---|---|---|---|---|
| Previous-version control | retained fixed2 | unavailable | unavailable | Whole update comparison with the same local settings |
| 0.18.5 fixed control | `2` | `0` | `0` | New engine with prior draft policies |
| 0.18.5 gated candidate | **unset** | `0.90` | `0` | Isolate confidence-gated depth |
| 0.18.5 tool candidate | **unset** | `0.90` | `1` | Isolate grammar drafting on strict-tool requests |

If grammar controls are not exposed by the managed validator, prepare explicit bounded pass-through before launch; do not bypass validation. A simpler first normal-serving comparison may leave grammar on in both fixed/gated arms, since a request with no tool call cannot exercise its new path. Benchmark a frozen natural16K prompt plus a small fixed mix of coding, prose and repetitive cases, with one excluded warmup and three measured calls per arm. Use bookends when drift is material. The strict-tool cohort should contain actual path/key/punctuation-heavy calls with free argument values and validate the parsed arguments. Use one short T1 grammar on/off pair only after greedy qualification if sampled production traffic matters; sampled output hash equality is not a correctness criterion.

Within 0.18.5 require identical greedy reasoning/content/tool-call payloads and finish behavior across fixed/gated/grammar controls, and compare to a serial request. Across the prefill reorder upgrade, preserve hashes as observations rather than demanding old-version equality. Report complete HTTP wall, generated tokens, first-token delay, engine timing fields, exact profile/request/output identities and all source counters. Select generated tokens per complete elapsed second and useful task completion, not the accepted fraction alone.

## Measurement and integration cautions

The official ten-shape `bench serial,mtp 256 low 3` uses request wall plus parsed engine log rates; its log-based decode and wall rates have different denominators. The official `sweep -p 8192,32768 -n 128` is synthetic and counts full HTTP wall. Run repeated prefill sweeps with Cache0: cache hits otherwise invalidate the printed cold-prefill mean. [Bench source](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/tools/bench-serving.py), [sweep source](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/tools/halogen-bench.py).

Local inspection found that `backends/halogen-wsl2-0.18.1/scripts/service.py` writes the old fixed-depth variable whenever `draft_tokens` is supplied. Its speculation validator allows only PLD0/3,3 and adaptation0/32,0.35,64. `scripts/benchmarks/halogen_agent_bench.py:draft_metrics` currently preserves combined counts only. `scripts/benchmarks/halogen_bench.py` still asserts version0.15.1 and must not be executed unchanged against0.18.5.

Preserve the entire raw `timings.speculation` object. Root subsequently supplied the extracted0.18.5 API, SHA256`3cfe542339d96e7995a23c0e45f1f04e459f30df6fd7088199147fbfdd9bb4b4`, at `server/.local/halogen0185-update-20261015/extracted/serve_api.py`. Its `timings()` at line3914 emits `speculation:{drafter,rounds,head:{rounds,drafted,accepted},lookup:{rounds,drafted,accepted},grammar:{rounds,drafted,accepted}}` when native rounds are supplied and either lookup rounds are zero or lookup drafted count is present. Missing speculation is not evidence of zero proposals. Source rounds sum to total rounds. Lookup/grammar counts come from native fields. Head rounds equal total minus lookup minus grammar; accepted head count is derived as `max(0,commit-rounds-shared-lookup_accepted-grammar_accepted)`. Head drafted uses the native field when present, otherwise a head-round fallback. Combined drafted and accepted are sums of these source fields. These are transparent API accounting rules, not three wholly independent accepted counters.

`prompt_n` is **processed** tokens, `max(0,n_prompt-n_cached)`, while usage prompt count includes cached tokens. The frozen natural16K request is raw `/v1/completions`, max128, temperature0, seed1, no tools, with a preclosed think block embedded in its prompt. `CompletionReq` has no `cache_prompt` field, so its historical `cache_prompt:false` does not switch caching off; the server profile must do so. Raw completions call `serve(chat=False)` without a thinking budget, so chat/server thinking defaults do not govern that prompt. It cannot exercise strict-tool grammar. The preupdate live receipt separately recorded CacheExact; an intentional cold benchmark profile must not be confused with that serving profile.

For the user's ServiceNow use, prioritize the natural cohort to qualify the new gate, then a short representative code/JSON cohort under the actual chat and thinking settings. Add grammar speed measurement only if actual clients send supported strict tools; otherwise label it a feature smoke, not a ServiceNow speed result. The main API reference retains pre0.18.4 alias wording, so use the changelog and actual `/health` when they disagree. The engine is closed source and these Python accounting rules do not prove native timing boundaries. [API reference](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/api.md), [upstream repository scope](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/AGENTS.md).

Confidence is high for publication identity and documented policy behavior; medium for transferring the measured decode opportunity to the local retained profile; unestablished for an actual local speed gain until root runs the matched cohort. Cache2 may separately accelerate growing real sessions, but it changes the repeat-answer equivalence contract and is not part of the matched CacheOff update comparison. Existing NPU, private-kernel and PLD-negative screens remain closed by this review.
