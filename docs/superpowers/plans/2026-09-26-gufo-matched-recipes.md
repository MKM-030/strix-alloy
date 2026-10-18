# Frozen matched AR/MTP request corpus implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Complete the cohesive offline task below and independently review it before connecting it to a GPU profile.

**Goal:** Supply identical, prevalidated requests for fresh native AR and MTP comparisons using the already measured 36-request corpus.

**Architecture:** Reuse benchmark_recipes rather than copy its prompts, sampler logic or answer validators. Freeze its calibration and bind the complete request list to the hash of the previously measured requests. This module does not launch anything; the following integration task will connect it to the existing Guardian after expanded memory review.

**Tech Stack:** Python 3.12 standard library; unittest; existing pinned GUFO Windows source and GGUF identities.

## Global Constraints

- Preserve existing finite profiles, raw artifacts, consumed attempt markers and existing launchers.
- At least 49 GiB available Windows physical memory before launch; 24 GiB runtime physical floor; 12 GiB commit reserve. This offline task grants no GPU permission and changes no policy.
- No model/GPU/network action, qualification creation, system setting, reboot, D: change or publication.
- Imports and recipe construction must perform no file/process/network I/O.
- Exact matched requests, explicit samplers, actual prompt counts and unchanged existing answer validators; no inferred speedup or quality claim.

### Task 1: Immutable matched recipes and request proof

**Files:** Create `scripts/gufo_control/matched_recipes.py` and `tests/gufo/test_matched_recipes.py` only. Do not modify existing source modules.

**Interfaces:** Consume `benchmark_recipes.recipe_definition(PROFILE_4K)`, `request_for(row, calibration)`, `canonical(value)`, `validate_answer(case, observation)`. Produce the same recipe-provider interface `recipe_definition(profile_id)`, `recipe_json(profile_id)`, `request_for(row, calibration=None)`, `validate_answer(case, observation)`, plus `validate_request(row, request)` and `validate_fixture()`.

Binding constraints for this task: preserve existing finite profiles, raw artifacts, consumed attempt markers and existing launchers; no model/GPU/network action, qualification creation, system setting, reboot, D: change or publication; imports and recipe construction perform no file/process/network I/O. No shared module modification. All numeric values must reject bool/float substitutions where integers are required.

#### Step 1: RED tests for corpus identity and AR/MTP equality

Use these exact constants:

```python
PROFILE_AR = 'matched4k-iq4xs-ar-v1'
PROFILE_MTP = 'matched4k-iq4xs-mtp-length-d1-v1'
REFERENCE_PROFILE = 'ar4k-iq4xs-correctness-pp1-v2'
REFERENCE_RESULT_SHA256 = '692149EEB38F89E662D9428A725533F14793680F5C70E8477A3B53E2DE8B04F3'
REQUESTS_SHA256 = 'EF677B664873CC42C07E4A22DA69723D6743AB57BF7944A0163A8E4799F394AB'
CALIBRATION = (13, 373)
PROMPT_COUNTS = (26,61,61,115,115,55,55,326,326,71,71,115,115,55,55,326,326,71,
                 71,61,61,55,55,326,326,71,71,61,61,115,115,13,373,2047,2047,2047)
```

The parent reconstructed all 36 requests from the completed reference run
`reports/gufo-ar4k-benchmark-v2-runs/20260926T183712Z-b77b8ac01bb54275aa4786db89478a69`
and verified each is exactly equal to the existing request factory with fixed
calibration `(13,373)`. The hash is SHA256 of UTF-8 `benchmark_recipes.canonical`
over the complete ordered request list. These observed counts are a pinned
same-tokenizer/request reference, not a generic text token estimator.

```python
def test_matched_bodies_are_identical(self):
    ar = matched.recipe_definition(matched.PROFILE_AR)
    mtp = matched.recipe_definition(matched.PROFILE_MTP)
    self.assertEqual(len(ar['schedule']), 36)
    self.assertEqual(ar['schedule'], mtp['schedule'])
    bodies = [matched.request_for(row) for row in ar['schedule']]
    self.assertEqual(bodies, [matched.request_for(row) for row in mtp['schedule']])
    self.assertEqual(sha256(base.canonical(bodies).encode()).hexdigest().upper(),
                     matched.REQUESTS_SHA256)
    self.assertEqual([row['expected_prompt_tokens'] for row in ar['schedule']],
                     list(matched.PROMPT_COUNTS))
```

Also test unknown profile, invalid ordinals (negative, 36, bool, float), altered
case/mode/repetition/target/cache/output budget, added or altered request fields,
True substituted for numeric sampling values, mutated base prompt, fixture
mutability, and unknown/changed calibration. Record an expected failing run
before implementing the module.

#### Step 2: Implement provider without copying the existing recipe

`validate_fixture()` builds the reference definition, constructs all requests
using the fixed calibration, checks 36 rows and their strict contiguous integer
ordinals, and verifies the exact ordered-list digest. It returns fresh request
copies; a changed upstream fixture raises `ValueError('matched_fixture_changed')`.
The routine reads no historical file; the result hash and prompt-count vector
are recorded provenance, later tied to static profile qualification.

`recipe_definition(profile_id)` rejects unknown IDs and starts from a fresh
reference definition. It replaces `profile_id`, sets `max_prompt_tokens=2304`,
retains context4096/max_requests36/output caps at most256, and adds:

```python
definition.update(
    reference_profile=REFERENCE_PROFILE,
    reference_result_sha256=REFERENCE_RESULT_SHA256,
    matched_requests_sha256=REQUESTS_SHA256,
    fixed_calibration=list(CALIBRATION),
    input_count_provenance='same_pinned_tokenizer_template_and_request',
    speculative=profile_id == PROFILE_MTP,
    draft_tokens=1 if profile_id == PROFILE_MTP else 0,
    mtp_policy='length' if profile_id == PROFILE_MTP else None,
    mtp_draft_vocab='full' if profile_id == PROFILE_MTP else None,
)
for row, count in zip(definition['schedule'], PROMPT_COUNTS):
    row['expected_prompt_tokens'] = count
```

Call `validate_fixture()` before returning a definition. Keep sampled T1/p.95/
k20/seeds1001..1003 and greedy controls unchanged. The three PP2048 rows remain
actual reference2047/output1. Preserve warmup/calibration classifications and
counterbalanced sampler order. Do not relabel configured capacity as occupancy.

`request_for(row, calibration=None)` validates all original schedule identity
fields against the reference row selected by a strict integer ordinal. It may
accept additional runtime status/result fields; those cannot override identity.
If supplied, `expected_prompt_tokens` must be the exact strict integer reference
count. The runtime calibration argument may be absent, an empty list (before
probes), one exact integer13, or the exact pair13/373; reject any different
value/type/count. It never recalculates a PP body from returned runtime counts.
Return a fresh request from the checked fixture list. This keeps compatibility
with the existing sequential suite while preventing adaptive workload changes.

`validate_request(row, request)` obtains that exact expected request and compares
canonical JSON (including structural type distinctions), rejects differences,
and returns the expected complete prompt count. Assert count<=2304 and count+
output_budget<=4096. Do not accept an unrecognized field or a different prompt.
`validate_answer` delegates to the existing unchanged validator. `recipe_json`
uses the existing canonical formatter. No argv/CLI/server/profile store belongs
in this task.

#### Step 3: GREEN, regression and commit

Run the focused tests, then the full offline suite once:

```powershell
$env:PYTHONPATH='C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p 'test_matched_recipes.py' -v
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p 'test_*.py'
```

Baseline was327passing in40.797s at f5ceab0. Self-review; stage only the two
task files; commit locally. Full report `.superpowers/sdd/matched-recipes-report.md`
must record RED command/output, GREEN command/output, changed files and concerns.
Parent independently reviews the exact diff. No new launch is possible yet.

## Following integration (not completed by this task)

Use the expanded signed memory review and native response contract to connect
this corpus to two new qualified profiles and the existing finite Guardian.
Run AR and MTP sequentially with verified recovery, then compare same-case
repetitions, rates, TTFT, correctness and memory. General-purpose optional
setup/start/status/stop remains a separate deliverable recorded in the delivery
gap audit; it is not satisfied by finite benchmark scripts.
