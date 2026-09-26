# GUFO MTP4k one-request stage implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Execute the single cohesive task below, then independently review before any GPU launch.

**Goal:** Execute one bounded native MTP bilingual correctness request, preserving the already qualified AR backends and evidence.

**Architecture:** Add a separate immutable MTP stage using the existing BoundStore/BoundPolicy and Guardian. Keep the Guardian process, telemetry and recovery implementation unchanged. Add narrowly allowlisted profile-specific bounds and descriptor validation, plus one private fixed HTTP request worker.

**Tech Stack:** Python 3.12 standard library; pinned GUFO Windows executable and existing HIP runtime.

## Global Constraints

- At least 49 GiB available Windows physical memory before launch.
- A 24 GiB available Windows physical-memory stop floor during testing.
- At least 12 GiB system commit headroom.
- No concurrent inference model during initial qualification.
- Preserve existing AR 68/4/20 envelopes; only the exact new MTP stage uses reviewed 71/4/20 (75 GiB commit charge, hence 87 GiB fresh commit headroom).
- Fresh query duration/final sample age <=2 seconds, runtime sample age <=5 seconds, nonoverlapping queries, start spacing >=1 second. Preserve all existing exact-owned-process termination and five-frame per-run recovery gates.
- Exactly one process/session, context4096, complete input<=512/output<=64, one greedy bilingual generation, no warmup or POST retry; startup480/request60/lifetime600 seconds, max connections16, request262144 bytes, response1048576 bytes.
- No cache store, prompt lookup, projector/vision, trace, other model/guest, persistent server, system settings changes, reboot, D: changes or public publication. Do not clear consumed markers or edit historical run artifacts.
- Preserve existing source/binary/DLL/target identities; use full-vocabulary shared Q8 MTP sidecar. MTP is a separate engine mode, not a Halogen kernel.

## Task 1: Exact profile, sidecar provenance, one-shot client and CLI

### Files and interfaces

Create `scripts/gufo_control/mtp_stage.py` for immutable constants, `profile_pins()`, `request_fixture()`, `validate_request(request)`, `build_argv(secret)`, `make_guardian()`, and status/print-only/run CLI. Split only the HTTP worker and response validator into `scripts/gufo_control/mtp_stage_http.py`.

Modify narrowly `model_identity.py`, `smoke_store.py`, `smoke_policy.py`, and if necessary `benchmark_runtime.py`. Add `tests/gufo/test_mtp_stage.py`, `test_mtp_stage_http.py`, and targeted model/store/policy tests using existing fixtures. Preserve existing benchmark recipes, qualification JSON shapes and AR behavior. No changes to `smoke_guard.py`, `winjob.py`, telemetry or GUFO source/binary.

Read the accepted reviews fully before implementation:

- `C:\Projects\strix-alloy-research\reports\gufo-mtp4k-staged-envelope-review-20260926.md` (SHA256 `7EC8175FFFC356058A0CA8F07B02F3A20AE3E8B88F44F9357D2E13C39F2E8AF6`)
- `C:\Projects\strix-alloy-research\reports\gufo-mtp4k-request-review-20260926.md`

Use profile ID `mtp4k-iq4xs-draft1-bilingual-v1`, evidence root `reports/gufo-mtp4k-stage-v1-runs`, qualification `reports/gufo-mtp4k-stage-v1-qualification.json`. The parent alone writes qualification after independent approval; implementation must fail closed without it. Reuse the successful AR4k-v2 predecessor and semantic acceptance file already used by AR16k; its result SHA is `692149EEB38F89E662D9428A725533F14793680F5C70E8477A3B53E2DE8B04F3`. Incomplete latches of the MTP root must block other profiles too.

### Step 1: RED tests for exact allowlisting and identity

- [ ] Add tests proving default AR bounds remain68/4/20, MTP is exactly71/4/20, cross-profile bounds/tampering fail before launch, qualification binds recipe + sidecar + margin + predecessor, and unqualified status cannot launch. Use strict integer types (no bool/float equality loopholes).

```python
def test_profile_demand_is_distinct(self):
    pins = mtp_stage.profile_pins()
    self.assertEqual(pins.profile_id, 'mtp4k-iq4xs-draft1-bilingual-v1')
    self.assertEqual(pins.bounds, dict(gpu_gib=71, host_gib=4, shared_gib=20,
        prelaunch_gib=49, runtime_gib=24, commit_reserve_gib=12))
    self.assertEqual(smoke_store.BOUNDS['gpu_gib'], 68)
    with self.assertRaises(ValueError):
        smoke_store._binding(replace(pins, bounds=dict(pins.bounds, gpu_gib=72)))
```

- [ ] Add metadata-only sidecar tests for changed size/descriptor/name, symlink/path escape, and stamp changes during static recheck. Never hash or read full tensor payloads.
- [ ] Run focused unittest tests and record expected failure before implementation.

### Step 2: Implement immutable MTP identity and profile-specific policy

Sidecar is exactly `C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\MTP\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf`, size2786568256, descriptor_end10946608, tensor_count32, descriptor SHA `5e9f7cc77b478fdd57cbbd2d5678d7c3d55a43c6f1428f78bae1f219385ed5d3`, target revision38bb39ee97821de2c9009abb7e93950eec396e66. Use the existing bounded GGUF inspector/descriptor hashing, reject escape/symlinks, record its exact identity and stat in manifest and qualification, recheck its stamp in every static recheck. Exact descriptor hash authenticates geometry; do not invent new payload provenance.

Extend StorePins with optional sidecar identity only if needed, default None so all AR records remain byte-shape compatible. Add one exact stage branch to experiment binding (speculative=True, context4096, input512/output64, max_requests1, fixed draft1/full/length, recipe SHA); use the same AR4k predecessor/acceptance validation as16k. Reject MTP metadata/sidecar on AR profiles.

Replace hardcoded numeric policy checks with validated profile demand, not arbitrary caller configuration:

```python
# after _profile_valid has checked the allowlisted profile/bounds:
physical_charge = profile.host_peak_bytes + profile.shared_physical_allowance_bytes
commit_charge = profile.commit_peak_bytes
gpu_allowances = (profile.gpu_peak_bytes,
                  profile.shared_physical_allowance_bytes,
                  profile.gpu_peak_bytes)
```

`profile_from_manifest` and `_profile_valid` must construct exact profile-specific values from authenticated, allowlisted pins; AR remains68/4/20/72 and MTP71/4/20/75. Absolute floors unchanged. Qualification/status show the actual selected bounds. No live execution in imports, status, tests or print-only.

### Step 3: RED exact request and response tests

- [ ] Use the exact request below and test all altered/unknown fields reject before transport, including max_completion_tokens, alternate message, Unicode, extra messages/tools, cache changes and output65. Structural type changes also reject. No warmup and exactly one POST even on failure/cancellation; bounded GET readiness only.

```python
PROMPT = ('Answer in two lines, without Markdown. EN: Explain in one short sentence '
          'how a backup helps after accidental file deletion. DE: Explain the same '
          'in one short German sentence.')
rendered = '<|im_start|>user\n' + PROMPT + '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
assert rendered.isascii() and len(rendered.encode('utf-8')) == 243 <= 512
```

`request_fixture()` returns a fresh copy of the exact `smoke_http.REQUEST` with only prompt changed. Validate full canonical body and the243-byte complete rendering before Guardian can launch and again immediately before sole POST. Copy/freeze what was validated; never accept caller-supplied text. Pin immutable request + byte-bound proof + reviewed source revision in recipe/qualification. The source-reviewed ASCII BPE bound proves <=243 tokens before prefill; runtime counter must corroborate positive input<=243.

- [ ] Response fixtures must cover missing/zero/inconsistent/Boolean draft counters, lookup fields absent-pair/zero-pair vs malformed/nonzero/one-only, cache hit/counts, wrong/missing model, truncated/reasoning/tools, and malformed bilingual structure. Positive accepted counts are required; never count stream chunks.

### Step 4: One-shot HTTP and guarded CLI implementation

Build argv from existing fixed smoke argv and change only stage-defined options; explicitly pass:

```text
--context 4096 --sessions 1 --max-tokens 64 --max-connections 16
--max-request-bytes 262144 --speculative mtp --mtp-model <exact-sidecar>
--draft-tokens 1 --min-draft-tokens 1 --mtp-policy length --mtp-draft-vocab full
```

Keep loopback8836, generated private API key, thinkingoff, no lookup/disk cache/projector. Check actual parser flag names against existing pinned source if needed (read its AGENTS first). The native max-tokens flag is only a default: safety depends on exact private one-shot request, not that flag. Guardian must retain sole private credential; do not export it or expose another generation interface. Existing threat model trusts this user's local process environment, not a malicious same-user process that can read process memory/commandlines. Use existing exact-owned Guardian, locking, local secret redaction, and authenticated private listener; don't create a bypassable proxy or claim OS-level isolation.

`make_guardian()` validates the immutable fixture prelaunch, injects exact BoundStore/BoundPolicy, `argv_builder=build_argv`, and one worker referencing actual guardian.run_dir. Worker uses existing `benchmark_suite._ready`, `benchmark_http.request_once`, `benchmark_suite._persist`, SmokeTask and cancel/deadline handling. Reuse lifecycle, transport, evidence sizing/redaction; don't duplicate them.

Single worker sends only fixture once, with RequestLimits(512,64,'cold'), then stores raw request-000.json and compact actual token/rate/counter evidence. No callbacks for arbitrary workload, no POST retry. Report generic transport success separately from MTP progression and semantic_review_pending. A failed check makes worker.success=False and triggers existing cleanup, retaining all evidence.

Stage response checks implement the request review exactly: all four strict native draft fields present/equal, 0<accepted<=drafted, ratio accepted/drafted; pinned-emitter pair omission means lookup0 with explicit provenance; otherwise both integer0. Explicit cache_hit/cache_disk_hit false, both cached token fields and timing.cache_n0, prefill/prompt counts equal positive<=243, output1..64, total/predicted consistent. Zero restore/disk-queued/shared-prefix counts/bytes; internal snapshot capture is allowed. All observed model IDs nonempty and exact alias. Finish stop, no reasoning/tool calls/replacement/control/fences/Markdown, exactly two nonempty trimmed lines with optional EN:/DE: prefixes. Manual actual bilingual semantics remain a parent review requirement, not a keyword proof. Drafted-accepted is unaccepted proposals, not exact rejection-event count. No common-window throughput claim.

CLI `python -m gufo_control.mtp_stage status|print-only|run` has no arbitrary profile/limits arguments. Only run invokes Guardian. Print-only verifies static qualification/environment/port like benchmark_guard, but no telemetry or creation. No qualification written by CLI.

### Step 5: GREEN, integration regression tests, commit and review

- [ ] Run new focused tests then the entire offline suite once:

```powershell
$env:PYTHONPATH='C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p 'test_*.py'
```

- [ ] Include tests showing policy starts only with87GiB commit headroom, runtime75GiB increment, original AR72 unchanged, missing/changed sidecar blocks, one-shot/client cancellation/evidence limits, and exact guardian injection with no native calls.
- [ ] Self-review, local commit only, full RED/GREEN report at `.superpowers/sdd/mtp-stage-report.md`. Parent creates BASE..HEAD review package and independently reviews. No GPU run until code review and qualification are complete. This task is not overall goal completion.

## Parent execution after task review

Bind exact independent review in qualification with apply_patch, run print-only, then one actual `mtp_stage run` under the existing guardian. Capture lifecycle, memory, startup and native counter evidence, review actual English/German output and cleanup. Do not retry consumed run or widen limits. Record failure honestly; report small-stage results as n=1, not benchmark improvement. The full goal's larger MTP, sampled, PP32768, concurrency and packaging remain later work.
