# GUFO format-aware benchmark follow-up

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Execution and independent agents are already selected by the user; no new design-approval loop.

**Goal:** Complete useful AR and PP measurements while recording, rather than disguising, Markdown-format noncompliance separately from safe function behavior.

**Architecture:** Keep the exact prompts, samplers,36/13 schedules and all reviewed runtime controls. Retire the consumed4k-v1 launcher identity in favor of a new4k-v2 identity/root/qualification. Preserve all old files and latch checks. Change only CODE assessment to recognize a single entire Python fence and apply the existing AST interpreter to its body, never executing generated code.

**Tech Stack:** Existing Python standard-library recipes/store/controller and unittest.

## Global Constraints

- Workspace C:\Projects\strix-alloy-research\integration, branch codex/gufo-native-integration. Preserve existing Halogen/native/27B installations and all evidence. No public push/release, no D:, BIOS/carve/driver/services/security/pagefile/WSL changes.
- Keep49 GiB available before launch,24 GiB physical stop floor,12 GiB commit reserve,68/4/20 GiB GPU/host/shared allowances and84 GiB prelaunch commit headroom. One model/session, AR/noMTP. All ownership, query2s/finalage2s/runtimeage5s, startup480s/request60s/lifetime600s, cleanup/recovery gates unchanged.
- No attempt/latch/result/qualification reset or deletion. Old4k-v1 failed honestly at a formatting instruction. No automatic model/request retry. The parent may perform one newly qualified v2 experiment after code review, exact previous cleanup verification and fresh admission.
- Same source/binary/model/runtime pins. Same input/output caps, request order, fields and prompt bytes. No new GPU allocation, dependencies, source rebuild or memory-margin change.
- No model/GPU/qualification execution by implementer. Parent owns qualifications, actual runs and semantic adjudication. No16k approval until real completed4k-v2 artifacts and independent semantic review exist. Format violations remain reported even when functional behavior passes.

## Task 1: Version the experiment and distinguish code format from behavior

**Files:** modify scripts/gufo_control/benchmark_recipes.py, benchmark_guard.py, smoke_store.py; matching tests plus tests/gufo/test_benchmark_runtime.py, test_smoke_policy.py and test_smoke_guard.py only as required for renamed fixed identities. Do not modify the HTTP client, suite scheduling or Guardian lifecycle.

**Interfaces:** preserve all signatures. Keep `_check_code(text)` strict and unchanged. The CODE branch of `validate_answer` adds `format_compliant`, `functional_state`, `evaluation_source`, and optional `format_violation`. A single fenced function that passes existing behavior checks gets `state='needs_review'`, never an automatic passed formatting claim.

- [ ] RED tests reproduce the exact observed answer (below): raw `_check_code` fails; `validate_answer('CODE',...)` must report needs_review, functional_state passed, format_compliant false. Plain valid code stays passed/format true. Single fenced wrong code stays failed; imports/attributes/arbitrary calls stay rejected; extra prose, multiple/nested fences and incomplete fences must not be unwrapped. Show the tests fail before production edits.

```python
OBSERVED = '''```python
def clamp(x, lo, hi):
    if lo > hi:
        raise ValueError("lo must be less than or equal to hi")
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
```'''
result = validate_answer('CODE', {'visible_answer': OBSERVED, 'finish_reason':'stop'})
assert result['state'] == 'needs_review'
assert result['functional_state'] == 'passed'
assert result['format_compliant'] is False
assert result['format_violation'] == 'markdown_fence'
```

- [ ] Implement the small CODE helper/branch (the existing AST interpreter remains the only behavior evaluator):

```python
def _code_assessment(text):
    lines = text.strip().splitlines()
    fenced = (len(lines) >= 3 and lines[0] == '```python'
              and lines[-1] == '```'
              and all('```' not in line for line in lines[1:-1]))
    source = '\n'.join(lines[1:-1]) if fenced else text
    functional = _check_code(source)
    assessment = dict(
        state='needs_review' if fenced and functional == 'passed' else functional,
        format_compliant=not fenced and functional != 'failed',
        functional_state=functional,
        evaluation_source='single_python_fence' if fenced else 'raw_python')
    if fenced:
        assessment['format_violation'] = 'markdown_fence'
    return assessment

# In validate_answer's CODE branch:
outcome.update(_code_assessment(text))
```

This helper is not a general Markdown parser. It never changes the raw response, request, output hash or token count. Unsupported safe AST syntax retains needs_review; known bad behavior remains failed. Preserve existing finish/tool rejection before this branch.

- [ ] Bind the changed assessment via `validator_version=2` in recipe_definition. Change only the following production identity/path literals and preserve the16k recipe and its gates:

```python
# smoke_store.BENCHMARK_4K and benchmark_recipes.PROFILE_4K:
BENCHMARK_4K = 'ar4k-iq4xs-correctness-pp1-v2'
# PROFILE_ROOTS value for this profile:
'gufo-ar4k-benchmark-v2-runs'
# benchmark_guard.profile_pins: explicit4k paths,16k paths unchanged:
evidence_name = 'gufo-ar4k-benchmark-v2-runs' if four else 'gufo-ar16k-benchmark-runs'
qualification_name = 'gufo-ar4k-benchmark-v2-qualification.json' if four else 'gufo-ar16k-benchmark-qualification.json'
```

Keep the fixed acceptance filename `gufo-ar4k-benchmark-acceptance.json`; its exact schema now requires the v2 profile ID and v2 root. No real acceptance file exists yet. Keep legacy arithmetic smoke-v3 unchanged. Old4k-v1 is no longer a launchable profile; its files/qualification remain untouched. Add the literal old root `gufo-ar4k-benchmark-runs` to `_incomplete_latches` independently of the new PROFILE_ROOTS mapping. It must still block initial/recheck/begin when incomplete, while its confirmed clean permanent attempt alone must not block v2.

- [ ] Tests cover old-v1 refusal, exact new evidence/qualification names, v1 incomplete latch block versus clean attempt preservation, unchanged argv except profile identity metadata (same context/options), validator_version2 recipe binding, and16k acceptance requiring actualv2 rather thanv1. Update existing synthetic fixture paths/IDs without removing assertions. No real marker mutation in tests.
- [ ] Run focused tests `python -m unittest test_benchmark_recipes test_benchmark_suite test_benchmark_guard test_benchmark_runtime test_smoke_store test_smoke_policy test_smoke_guard` with PYTHONPATH including absolute integration/scripts and tests/gufo. Then one full `python -m unittest discover -s tests/gufo`. Self-review, diff-check, scoped local commit and report. Independent recorded-base review before live work.

## Parent live-execution checklist

- [ ] Revalidate exact v1 result `reports/gufo-ar4k-benchmark-runs/20260926T181309Z-2c72974f6e784a0487444ee3c7f81b8a/result.json`, SHA FDC0BB0FF78A25E543A6F282E16713A0A417D6C78F51401E7CF340205B98C6A8; all cleanup/worker/evidence flags true, five recovery frames, no live owned process or incomplete latch. This is a reviewed clean failed experiment, not a successful predecessor. Preserve it. The successful native-v3 predecessor remains the original exact pinned identity.
- [ ] New4k-v2 qualification binds the new recipe digest and independent review ID under unchanged accepted fit. Fresh static/admission, one bounded36-request run. If it fails, retain every observed row and stop; do not automatically replay.
- [ ] On completed run, inspect every output and independently adjudicate behavior and format separately. Report format violations and all repetitions/spread. A completed transport suite alone cannot approve semantics. If useful functional correctness and cleanup pass, record honest semantic acceptance (review report includes format limitations) before qualifying16k PP/cache.
- [ ] Run reviewed16k13-request profile after the above actual acceptance, verify cleanup and evidence, compare HTTP PP2048/8192 to matching preserved Halogen boundary. Continue full goal afterward: MTP, PP32768, concurrency instrumentation, production lifecycle/install/rollback and other optimization tracks remain required.

## Self-review

No prompt or benchmark workload is being weakened to obtain a faster number.
The exact observed wrapper is assessed separately; incorrect functions still
abort, and correct fenced code still fails formatting and requires independent
review. Existing failed evidence, safety limits, true token counts and original
scope remain intact. This is a one-variable measurement-classification follow-up.
