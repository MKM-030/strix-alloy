# Implementation ledger (2 October 2026)

This ledger classifies source work, not measured speedups. No model, SDK, display
driver, BIOS setting, registered default, or pinned production executable was
replaced. Source patches are reversible candidates and are not live qualification.

| Proposal | Classification | Evidence and boundary |
|---|---|---|
| Exact matched PP512/2048/8192/16384 and TG128 on managed GUFO, PROJFIX and Halogen | **Implemented** | `scripts/benchmarks/prepare_gateway_prompts.py`, `gateway_cold.py` and `article_metrics.py` prepare hashed prose and calibrate from observed gateway usage. Each cold sample rejects native cache/disk hits, count mismatch and clamping, checks the selected profile's byte hash against the managed run, and retains phase rates, acceptance and host-memory samples. Needs later live run. |
| Filled context, three-turn coding task | **Implemented** | `scripts/benchmarks/article_bench.py` retains conversation, observed input, first-token latency, retrieval grade, hashes, acceptance and actual output. `reddit_bench.py` adds a coding/tool-turn and 8K/32K/64K/131K occupied-depth ladder with a generation prompt and an enforced 128-token output; its text-token PP labels are not exact chat-token PP measurements. |
| Functional, multilingual, JSON, code, long-needle, state and optional top-N quality gate | **Implemented** | `scripts/benchmarks/quality_gate.py`, `reddit_suite.py` and tests bury the needle, require same-backend functional/hash parity and fail closed when one side exposes valid top-N data but the other lacks comparable token/candidate evidence. A top-N logprob proxy is not full logits. Requires live per-engine controls/candidates to claim quality preservation. |
| GUFO prompt lookup and deterministic profile selection | **Implemented** | `server/draft_profiles.py --lookup-workload copy/prose` explicitly enables/disables the existing switch in a separate pinned profile and rejects contradictory flags; `server/gufo_serial_profile.py` provides a separate serial control. Neither swaps engines based on future prompt content. The registered default is unchanged. |
| GUFO prompt lookup engine and MTP sampling paths | **Already-present** | Pinned `thomas9120/gufo` source has `--prompt-lookup`, n-gram lookup and MTP/greedy paths. Do not reimplement them or mistake a cache hit for cold PP. |
| Halogen draft depth and explicit prefill chunks | **Implemented** | `server/controller.py`, Halogen launcher/service and opt-in profiles forward validated 1..3 draft tokens and 2048/4096/8192 chunk settings. Existing defaults remain unchanged. |
| PROJFIX shallow MTP with host-expert placement | **Implemented** | `backends/projfix-windows/profile.py --mode mtp-host` writes a nondefault candidate with 18 GiB reserve. The measured 512-output difference still blocks registration/general equivalence. |
| PR91 parallel PLE gather prefetch | **Already-present** | Pinned pwilkin `src/llama-context.cpp` invokes `qwen4exp_ple_prefetch`; `src/models/qwen4exp.cpp` defines it. No duplicate patch. Other PR91 kernels are not presumed present or numerically portable from a different fork. |
| CPU grammar candidate-first rejection | **Already-present** | Pinned `common/sampling.cpp` checks one sampled token against grammar, then grammar-first resamples on rejection. The backend-sampler path still disables grammar/reasoning by default. |
| Backend-sampler grammar fast path | **Requires rebuilt runtime** | `backends/projfix-windows/patches/backend-grammar-fast-optin.patch` is environment-opt-in only for eager, non-LLGuidance, trigger-free, no-reasoning grammar. A rejected GPU token resamples only with full raw logits, otherwise fails closed. It applies and reverses in a temporary source copy. On 2 October an isolated patched translation unit passed pinned clang/PCH syntax compilation (`server/.local/projfix-grammar-source-20261002010631`), with one unused `-c` warning. No link, grammar operator/model verification or binary promotion. |
| PROJFIX scheduler reservation reuse | **Unqualified source candidate** | `backends/projfix-windows/patches/scheduler-reserve-optin.patch` leaves default behavior unchanged and requires `LLAMA_SAMPLER_KEEP_RESERVE=1`. It applies/reverses and an isolated patched translation unit passed pinned clang/PCH syntax compilation (`server/.local/projfix-scheduler-source-20261002012111`, one unused `-c` warning). A same-name sampler chain is **not proof of identical graph shape or safe request-owned pointer lifetime**; require allocation/graph-identity and changing-sampler tests before even a candidate server run. No production binary/profile uses this flag. |
| GUFO upstream sparse-attention window and sparse CPU greedy penalties | **Requires rebuilt runtime** | `docs/research/gufo-upstream-review-20261002.md` bounds compatible one-file source candidates to `attention-window-optin.patch` and `greedy-penalties-optin.patch`. Exact source SHA guards, isolated core linking and six focused CPU/HIP tests passed; this is not a full-model numerical/quality/speed gate. |
| GUFO upstream seeded MTP replay/snapshot and GPU greedy penalties | **Incompatible** | Upstream #330 and the GPU portion of #332 cross the pinned fork's snapshot ABI and verification/kernel layout; direct hunks do not apply. Only a separately reviewed semantic port and full requalification can change this. |
| HGN format / NPU offload / speculative cross-engine router | **Incompatible** | Current GGUF weights, one-engine occupancy and Windows/ROCm profiles provide no qualified converter, NPU execution path or safe dynamic switch. No hidden routing or model change was made. |

Upstream `gufo-org/gufo` commits already reflected in the pinned fork are not
cherry-picked. The local review found stop-sequence handling, vocabulary-derived
stop tokens, tool-interruption framing, LLVM 23 W8A8 scheduling fence and bounded
disk staging in the pinned source; identical or semantically present code does
not warrant a second patch. The pinned Thomas source is a shallow fork snapshot,
so ancestry alone does not establish compatibility. Review file-level anchors and
the numerical patch before any new candidate.

**Promotion gates:** build against the pinned SDK in an isolated checkout;
run grammar/penalty and cross-window operator tests, full-model logit comparisons,
matched serial/speculative output hashes, memory-floor and cancellation checks,
the exact PP/TG and three-turn suite, and the functional quality gate. Preserve
the old executable/profile for rollback. `server/.local/NEXT_STEPS.json` has
later commands; nothing here starts or benchmarks a model.

The local `NEXT_STEPS.json` now lists ten exact 18 GiB-reserve profiles, ordered
control/candidate quality comparisons in both Halogen modes, matched cold PP/TG,
occupied TG and stop/READY checks. The matrix has not been run. Source-only
`compare_reddit.py` additionally refuses cross-run prompt, output and token-count
drift on matched case/repetition keys, including serial-versus-MTP controls.
No changed-output prefill candidate is promoted on speed alone. Source-only
regression on 2 October: server 47, benchmark 53, PROJFIX 25, GUFO 20 and
Halogen 115 (19 skipped) passed. A first CTest invocation against the *candidate*
GUFO build reported three "Not Run" targets because only the changed translation
units existed. After linking the isolated HIP core and test executables,
`config`, `ngram`, `prompt_lookup`, `mtp_sampling`, `attention_ops` and
`logit_sampler_test` passed (six of six). This is not a model-quality claim.
