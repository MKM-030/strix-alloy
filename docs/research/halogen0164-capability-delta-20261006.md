# Halogen 0.16.3/0.16.4 capability delta for target acceleration

Focused read-only follow-up to the [completed evening check](halogen-updates-20261006-evening.md), dated 6 October 2026. Scope: immutable public source and retained Windows runtime receipts, not another release survey. No hardware/provider/engine/WSL call, install, binary/model download, service action, or new native audit was performed. Only this note was written.

**Decision:** neither version exposes an independent supported NPU/CPU route to faster Flash Prefill, Decode or native acceptance under the current one-active-request and continuous 18-GiB physical/commit reserve requirements. New server behavior can improve correctness or side-model latency. It does not qualify target acceleration or make the defeated proposer/component work usable.

## Exact public contract comparison

| Version | Immutable commit | `docs/FLAGS.md` Git blob |
| --- | --- | --- |
| Pinned 0.16.2 | `7f31bbd4021f217a1be9776bdb7304bcf8eca62d` | `92610f3dc8baace22cce35377f5ce2723d095ace` |
| 0.16.3 | `8cd70aeefb0e5c85de8d74724aed2ab3ab45f5e1` | Same |
| 0.16.4 | `6d4e791ea4ca596a1f90e38beefdf2e017ae4544` | Same |

The [FLAGS file](https://github.com/peonist-ai/halogen-flash-server/blob/6d4e791ea4ca596a1f90e38beefdf2e017ae4544/docs/FLAGS.md) is byte-identical at all three pins. The new changelog is additional official contract evidence; identical FLAGS does not negate its new settings. Fresh recursive tree reads at each pin contain neither `serve_api.py` nor `npu_api.py`, so the new server's Python request/grouping implementation cannot be audited from this public tree. No image payload was fetched to fill that gap. The [immutable comparison](https://github.com/peonist-ai/halogen-flash-server/compare/7f31bbd4021f217a1be9776bdb7304bcf8eca62d...6d4e791ea4ca596a1f90e38beefdf2e017ae4544) exposes deployment, docs and benchmark changes, not the private engine implementation.

| New behavior | Native work changed | Frozen-profile result |
| --- | --- | --- |
| 0.16.3 NPU small-group batching | Chooses existing batched versus scalar complete side-model passes | No Flash layer/Prefill/verifier work is replaced. |
| 0.16.3 multi-stream PLE decode, `HALOGEN_PLE_PAR=0` rollback | Closed engine's multi-stream path | New GPU-only concurrent workload candidate; the one-active-request profile is outside the stated claim. No two-stream MTP verifier was shipped. |
| Longer disk-prefix selection | Reuses more cached history | Cache is off here; cold Prefill must still process the actual prompt. |
| Admission reserve/priority header | Queue admission with several streams | No competing queued client in the frozen profile; no preemption or arithmetic change. |
| System One choices/scores | `decider-0.8b` classification passes | Option probabilities are not Qwen vocabulary logits or target draft acceptance. |
| JSON/tool fix; streamed whitespace fix | Server interpretation of generated output | Can prevent agent retries or wrong tool content; does not establish faster target PP/TG or native acceptance. |
| Notice routing and tool-mode JSON fix | stdout/stderr handling | Operational correctness; no target compute gain established. |

These scopes come from the [pinned changelog](https://github.com/peonist-ai/halogen-flash-server/blob/6d4e791ea4ca596a1f90e38beefdf2e017ae4544/CHANGELOG.md). It explicitly says 0.16.4's engine/checkpoints are unchanged from **0.16.3**, not that its engine equals pinned **0.16.2**.

## The NPU batching change does not transfer to the loaded Windows runtime

The [new NPU guide](https://github.com/peonist-ai/halogen-flash-server/blob/6d4e791ea4ca596a1f90e38beefdf2e017ae4544/docs/NPU.md#L208-L224) defines up to eight texts of up to 512 tokens, padded to one model bucket. It chooses batching at six inputs up to 128 tokens or five up to 512; small remainders run individually. Those cutoffs depend on the side model's whole-pass costs. This is a frontend scheduling fix, not a new low-level batched tensor operation, concurrent NPU execution, or faster draft head. The guide still says one NPU pass at a time. Its cutoff values cannot be copied into a Windows projection/gather graph or FLM token loop as a performance rule.

The retained Windows paths are different interfaces:

- ONNX Runtime/Vitis AI and DynamicDispatch component graphs have their own placement, format, numerical and dispatch contracts. The [candidate inventory](halogen-npu-candidate-inventory-20261004.md) records failed placement, precision failures and slower complete projection calls. A side-model bucket does not repair those operators or shorten their host copies.
- The completed [FLM 1.0.7 raw-ID screen](halogen-npu-independent-proposer-screen-20261006.md) used native Windows XRT, separate Qwen3.5-0.8B Q4NX weights, committed logits and scalar forwards. It measured roughly 45 ms for three proposals before rebuilding/correction costs and remains disabled. Halogen's new text-embedding batch selector neither changes this DLL nor its tokenizer/state/rollback contract. Its 47.73% offline prefix statistic remains distinct from native MTP acceptance.
- The [batch-cut disposition](halogen-npu-batch-cut-source-disposition-20261005.md) already ruled out normalized rows arriving early enough to overlap the same trunk Prefill. New side-model batching adds no earlier token/hidden-state publication, no tensor consumer, no target verification feedback and no native injection seam. It therefore does not resurrect that route.

NPU `qwen3.5-2b` text generation existed in 0.16.2. In the new guide it is still an OpenAI text-chat model selection, not a raw-token-ID proposer API or Flash-head callback. `/v1/systemone` likewise provides application classifications, not access to target tensors. Reducing the number of Flash calls by routing some tasks to small models would change the task/model workload; it would not establish faster Flash tokens or acceptance.

## Compose, AGESA and the one-engine/reserve boundary

[docker-compose.npu.yml](https://github.com/peonist-ai/halogen-flash-server/blob/6d4e791ea4ca596a1f90e38beefdf2e017ae4544/docker-compose.npu.yml) packages the existing GPU/NPU topology in one container. It still mounts `/dev/kfd`, `/dev/dri`, `/dev/accel/accel0` and host XRT. The [entrypoint](https://github.com/peonist-ai/halogen-flash-server/blob/6d4e791ea4ca596a1f90e38beefdf2e017ae4544/deploy/entrypoint.sh#L1362-L1370) starts a separate `halogen-npu` process and `flash_serve`; one container is not one inference engine. The internal `_hg_npu_alone`/`start_npu_alone` path is present in both 0.16.2 and 0.16.4, not a newly added documented Windows mode. It is not a reason to use an internal underscore control.

Installed AGESA 1.0.0.2b now matches [AMD's tested firmware fix](https://github.com/ROCm/TheRock/issues/8709#issuecomment-6019477697), as the evening receipt's SMBIOS addendum records. This metadata does not create `/dev/accel` access in WSL, a Windows ABI for the Linux binary, or supported FP11 fabric hold/query/release semantics. Pinned 0.16.4 still requires the Linux hold and marks `HALOGEN_NPU_WITH_GPU=1` unsupported. No AGESA exception is documented. Do not bypass it or repeat old overlap cohorts on the strength of the revision match.

The NPU guide says the models occupy additional RAM and share the bus/power budget with Flash. Compose's default enables all five side models; it neither budgets Windows physical/commit headroom nor enforces the continuous 18-GiB guard. `HALOGEN_HOST_RESERVE_GIB` sizes the GPU KV pool at startup and is not that Windows runtime guard. Adding side models, a helper or several slots must preserve the existing reserve, current request counts and one target engine; available margin was not freshly queried in this source task. No memory-feasibility claim follows from this note.

## Concrete future staging boundary

A future **version-only GPU comparison** can remain independent of unsupported overlap: stage the complete immutable 0.16.4 release with NPU models unset, one slot, unchanged checkpoint/tokenizer/context/actual input-output counts, MTP/PLD/cache/sampling settings and existing ownership/reserve guards, replacing the old target only within an authorized exclusive window. Validate the new release identity and normal API behavior first. Keep private 0.16.2 hook/operand consumers disabled for a changed engine binary; old addresses and integration receipts do not establish new-image compatibility. Do not mix a 0.16.4 frontend with a 0.16.2 engine on the assumption that 0.16.4's server-only fix proves that cross-version protocol.

This is a concrete staging/compatibility candidate, **not a qualified single-stream speed mechanism**. The advertised decode benefit is multi-stream, and new acceptance improvement is not claimed. A distinct multi-client PLE comparison would change the workload and require an explicit scope change plus pool/reserve feasibility. Server correctness tests can justify a product upgrade independently of tok/s, but they cannot substitute for a matched full-engine PP/TG/accepted-attempted comparison. No fresh engine cohort is justified solely by the NPU batching fix, compose addition or already installed AGESA revision.
