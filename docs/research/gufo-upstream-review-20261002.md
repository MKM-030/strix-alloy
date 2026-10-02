# GUFO pinned-source upstream review (2 October 2026)

The production profile remains `thomas9120/gufo` at
`7e924c2d787aabf640db3c0f818cb824dc18ec8e`, with the separately pinned
Windows/ROCm numerical patch and executable hashes. The upstream `gufo-org/gufo`
mainline observed at `d707143223c52b91da3f0fb231ba85ac3eab247c` diverges
from that fork at `d9a84f13f35d1f98da22886a12eb25dc7062e392`. A merge or
blind cherry-pick would discard fork-specific MTP, prompt lookup and snapshot
behavior. No engine binary, weights, driver or registered profile changed.

## Compatible experimental source change

Upstream [#292](https://github.com/gufo-org/gufo/commit/6a4c89784adb1c99830889b42fc3e243c3fcb7d8)
cuts sparse-attention tiles across mask-compaction windows. The one-file HIP
kernel patch applies with offsets to the pinned post-numerics source (`git apply
--check`), without changing the numerical compatibility patch or manifest.
It is staged as `backends/gufo-windows/patches/attention-window-optin.patch`.
`backends/gufo-windows/optin_attention.py` checks the post-numerics SHA-256 and
requires an explicit `--apply` in an unbuilt *separate* checkout. Removing that
checkout or reverse-applying the patch rolls it back. The registered runtime is
unaffected. Static applicability is not numerical equivalence or a speed claim.

Source-level exercise: detached worktree from the exact pinned commit at
`server/.local/gufo-attention-source`, numerical patch applied first, then this
attention patch. `cmake --preset gpu-test` configured with the pinned TheRock
10.2.0a20260930 compiler/SDK and vcpkg path, and Ninja compiled the one HIP
translation unit for gfx1151 with `-j 1`. It succeeded; only the existing
unhandled quant-enum warnings at kernel lines 52/72 were emitted. Object
SHA-256: `311efd926db4be62bd63b3f56d600c6d127018cd9a92a22f79321fcf8e171030`.
Patch SHA-256: `886375c5d6b943606ab00a2196c904729f427b341afb34c405b90769d7defdfc`.
The object and CMake cache are ignored local artifacts. No link, GPU operator
execution or full-model test was claimed.

One independent compatible CPU optimization from upstream #332 is also staged:
`backends/gufo-windows/patches/greedy-penalties-optin.patch` replaces per-vocabulary
binary searches in `SamplerState::SampleGreedy` with a linear walk over the
already sorted sparse penalty counts. It does not relax the existing CPU
verification fallback, change top-p acceptance, or adopt GPU penalty arithmetic.
The same staging script accepts `--patch greedy` and checks exact pinned
`src/core/sampling.cpp` SHA-256 `094c3dad5b9ea93768224ce94ffb558eaea2edd18b4e11ba9fc5d1f5cc9e21eb`.
The hunk applies to the pinned source and the experimental checkout's CPU
translation unit compiled with the pinned toolchain. Object SHA-256:
`2ff08ede6759be298384a140b9343f9ca7f01cb679af34506ebbc52d14aef920`;
patch SHA-256: `d56c81cb5078075528976195d3bbd824e8f2b18f20c769e884e40a2e51c816aa`.
On 2 October the isolated candidate linked the needed HIP core and six focused
test executables. `config`, `ngram`, `prompt_lookup`, CPU `mtp_sampling`, gfx1151
`attention_ops` and CPU `logit_sampler_test` all passed, including existing
greedy-penalty parity and sparse/long-context attention cases. This is operator
evidence only; a model-level logit/hash and latency comparison is still mandatory
before considering the source or binary qualified.

The patch's split assignment and carried partial tile still need more targeted
sparse-mask tests across 1024-block boundaries, occupied depths and multiple
split counts on this GPU, followed by full-model logits and the common quality suite.
Until then it must not be registered. In particular, do not call the matching
patch hunk a qualified ROCm speedup.

## Inspected, not blindly ported

- [#330](https://github.com/gufo-org/gufo/commit/a917b790df8d5fd98205abddd3b7c1afd0ca9458)
  changes seeded MTP replay and GPU cache projections across executor, batch,
  kernels, snapshot version and tests. The pinned fork already has host/device
  snapshot state (`kSnapshotPayloadVersion=15`), prompt lookup and a different
  verification path. Its snapshot-version hunk does not apply. This requires
  an isolated semantic port and deterministic cache-reuse tests, not a one-line
  version bump.
- [#332](https://github.com/gufo-org/gufo/commit/7e450e8c0bc5458d056b34675e6d7f844d0ef23f)
  also adds GPU greedy penalties and sampling-range fixes. The pinned fork has
  GPU greedy verification but deliberately excludes penalties; the engine
  hunk does not apply and the change spans sampling ABI, kernel workspace and
  verification. Keep the CPU-verifier fallback until a separately qualified
  port checks penalty configurations and full-model distributions.
- GUFO's pinned Qwen prefill is already chunked at 2048 tokens, based on its
  512/1024/2048/4096 sweep. Its MTP verification already has GPU greedy and
  sampled paths; prompt lookup already inspects committed token n-grams and
  proposes only on a sufficiently long match. Replacing this with a second
  per-request engine would violate single-engine memory occupancy, while a
  startup prompt router cannot know future request content. No fake router or
  HGN loader was added. HGN needs a separately qualified weight conversion.

The common suite must record control/candidate profiles, hashes, memory floor,
prompt/response bytes, acceptance and top-N logprobs where actually returned.
It must run engines serially with at least 18 GiB protected reserve. For this
source patch, add ROCm operator/numeric tests and a built candidate before any
live comparison; source applicability alone is not runtime qualification.
