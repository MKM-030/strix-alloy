# GUFO Halogen Ten-Prompt Offline Recipe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development under the established user-approved implementation workflow, or superpowers:executing-plans for inline implementation. Steps use checkbox (`- [ ]`) syntax for tracking. This report authorizes no runtime execution. The main agent must read the complete plan before implementation.

**Goal:** Add a pure, offline definition and evidence summary for GUFO's missing Halogen ten-prompt corpus experiment, retaining the historical protocol differences and every expected observation.

**Architecture:** One focused standard-library module consumes pinned corpus bytes, emits fixed requests and a deterministic 30-row projection for one externally selected AR or MTP mode, and summarizes already collected `benchmark_http.request_once` observations. Reuse `benchmark_recipes.canonical` and `benchmark_http.RequestLimits`; do not add transport, lifecycle, CLI, profile registration, retries, or evidence-file writing. A checked-in byte-pinned corpus and two small unittest files make this independently reviewable without a server.

**Tech Stack:** Existing Python standard library, `unittest`, `hashlib`, `statistics`, existing GUFO request/result contracts. PowerShell only for documented offline test commands.

## Global Constraints

- Planning provenance: private report `gufo-halogen-ten-recipe-plan-20260927.md`, SHA256 `127EB13335D08E95030E65599295B2615B685809930C439DABD3142A5E0F98CC`, fully read by the main agent, including the localized cache-policy correction. This saved plan does not authorize a live run.

- Governing specification: `C:/Projects/strix-alloy-research/integration/docs/superpowers/specs/2026-09-26-gufo-native-design.md`.
- Only this plan report is written now. Future implementation touches only the four new files enumerated below. Existing checkout files, especially ongoing finite-store/controller work, are outside this plan's editing scope.
- Approved memory floors remain 49/24/12 GiB; 12 GiB is the explicit commit reserve, not permission to lower the 24-GiB physical floor. Current controller envelope remains 68/4/20 GiB. This module performs no memory admission and cannot qualify a launch.
- Current finite controller's frozen 66/6 POST workload must not change. Its qualification argv is AR-only, context4096, max-tokens64, request-policy `ar4k-service-v1`; max256 requests are incompatible with that runtime boundary. No hook, registry addition, replacement request, new controller, launch profile, safety bypass, or generic framework is included.
- No models, GPU, WSL, helper/process launches, sockets/listeners, telemetry, recovery, `D:`, or actual evidence-root changes. Offline unit-test commands below are future implementation instructions, not commands executed in this planning task.
- No commit, fetch, browse, public push, or source snapshot mutation in this task. The usual writing-plans commit step is replaced with local diff review under the explicit no-commit instruction.
- No duplicate PP1, filler, calibration, warmed GUFO PP/TG, five-fixture correctness, cache-reuse, sampled, concurrency, or long-context recipes.
- Neither different-quantization outputs nor sampled AR/MTP outputs have a byte-identity pass criterion. This module makes no cross-run equality or speedup claim.

---

## Evidence already available and exact seams checked

Read in full: `C:/Projects/strix-alloy-research/reports/matched-upstream-benchmark-recipes-20260926.md`, `C:/Projects/strix-alloy-research/reports/gufo-benchmark-recipes-20260926.md`, and `C:/Projects/strix-alloy-research/integration/docs/benchmarks/gufo-native-20260927.md`. The latter already reports 4K runbook AR/MTP, AR16K PP2048/8192 and contextual community figures. It explicitly leaves the native ten-prompt decode cell unmeasured. Do not relabel those existing runs as ten-prompt results.

The only additional source inspection was the exact corpus, request/order loop, timing/parser contracts, existing recipe/test patterns, and the historical methodology/result statements. No runtime/controller dirty files were inspected.

| Identity | Exact pin |
|---|---|
| Halogen source | `c8270bb31cd824a0bf53fe9ecf80059c13e7a5bf` |
| `tools/eval-prompts.json` | SHA256 `23df9feb5ec2b343f675bb08dc6c0c2286e17dd6d73acf4e7d363d0c0c49922b`, 1,384 bytes, UTF-8/LF with final LF |
| `tools/bench-serving.py` | SHA256 `7edd38e6ce04854298cf7584ecac13d47afeb96c93e4c85fe113c14094944f83` |
| Historical Halogen 0.13.8 image | `ghcr.io/peonist-ai/halogen-flash-server@sha256:6e626c979d536ab1edb07898e278be6686afd353758ea268817457f801d687dd` |
| GUFO Windows source reference | `cff564964e8506c0abb3e530cecb55332187ac6c` |
| GUFO Linux reference, contextual only | `d9a84f13f35d1f98da22886a12eb25dc7062e392` |
| Existing local target revision, future manifest must identify actual files | Unsloth IQ4_XS `38bb39ee97821de2c9009abb7e93950eec396e66` |
| Inspected `benchmark_recipes.py` | SHA256 `d6c92b80314a31b3b1e5ed164dfe7f89edd4923fa054e7d95d46924f4790bf61` |
| Inspected `benchmark_http.py` | SHA256 `4b366c19e580a1cabb3759d9eb141273d389b5b50394e3973d20ae6a5f9cf752` |

The two source-file hashes were recomputed from the read-only snapshot and match completed research. Existing contract hashes are review baselines, not locks that override the main agent's concurrent work.

`bench-serving.py` loops **repetition -> case -> drafter**, with serial then MTP for each case: 3 x 10 x 2 = 60. The stable case order is `code_a, code_b, proof_a, proof_b, proc_a, proc_b, chat_a, chat_b, prose_a, prose_b`. It does not run all serial cases followed by all MTP cases. Each GUFO mode below is a 30-row projection of this sequence; paired historical ordinal is `2 * mode_ordinal + (0 for AR else 1)`. Separate GUFO launches introduce a declared scheduling difference. Do not counterbalance or rotate cases inside this source-shaped recipe.

Historical request: non-streaming `/v1/chat/completions`, one user message, max256, `reasoning_effort:"low"`, `drafter:"serial"|"mtp"`; no explicit sampling fields in the default greedy branch. Thinking was **enabled**, with the answer budget closing it at token1 in the recorded run. The corpus comment mentions default xhigh, but the command explicitly overrides effort to low. GUFO below is explicit greedy **thinking off**, seed42, cache bypass and non-streaming JSON. It is a corpus-matched deployment experiment, never an exact historical-protocol reproduction. Unsupported Halogen `drafter`/`reasoning_effort` fields are not sent.

The original tool's serial `*` rates use actual completions / wall, while MTP uses ledger engine decode; its displayed per-case spread is half-range, not sample SD. The historical supplemental engine records permit a separately labelled equal-denominator comparison. New summaries below use mean plus **sample SD** and never divide differently defined rates. The historical 41.20 tok/s is context, not an expected result or threshold.

## File map

All future paths are under `C:/Projects/strix-alloy-research/integration/`:

1. `scripts/gufo_control/fixtures/halogen-eval-prompts.json`: exact pinned 1,384 corpus bytes.
2. `scripts/gufo_control/halogen_ten.py`: pure recipe and summary functions; no I/O at module import or function call.
3. `tests/gufo/test_halogen_ten_recipe.py`: corpus/order/request isolation and bad-input tests.
4. `tests/gufo/test_halogen_ten_summary.py`: all-observation retention, native metrics, incomplete/failure and summary tests. Synthetic dictionaries only; no socket-based fixture.

No existing file needs modification. In particular do not widen `benchmark_recipes._profile`, borrow `build_argv`, or call `benchmark_http.request_once` in offline tests.

## Task 1: Fixed corpus, per-mode schedule and GUFO requests

**Files:** Create files 1, 2 and 3 from the file map.

**Interfaces:**

- Consumes: raw corpus `bytes`; `benchmark_recipes.canonical(value) -> str`; `benchmark_http.RequestLimits(max_prompt_tokens, max_completion_tokens, cache_policy, request_bytes)`.
- Produces: `definition(corpus: bytes, engine_mode: str) -> dict`; `request_for(corpus: bytes, engine_mode: str, ordinal: int) -> dict`; `request_limits() -> RequestLimits`; `request_sha256(request: dict) -> str`.
- `engine_mode` is exactly `ar` or `mtp`; it is descriptive metadata, never a runtime control. Request bodies are identical across these modes. MTP depth/policy belongs to actual external run provenance.

- [ ] **Step 1: Add this complete corpus fixture using apply_patch.** Preserve LF and the final LF. Do not reserialize it, omit its comment, or normalize whitespace.

```json
{
  "_comment": "drafter-eval prompt set. Five request shapes taken from the serving ledger, two each. Keep this file STABLE, changing it makes runs across drafter releases incomparable; add new prompts under new names instead of editing existing ones. The endpoint's own defaults apply (thinking on, effort xhigh), which is the point: live output is mostly reasoning tokens, and that is the register corpus anchors miss entirely.",
  "code_a": "Write a Python function that merges two sorted lists into one sorted list. Include a docstring.",
  "code_b": "Write a Python function parse_duration(s) that turns strings like 1h30m into seconds. Include a docstring and type hints.",
  "proof_a": "Prove that the square root of 2 is irrational.",
  "proof_b": "Prove that there are infinitely many prime numbers.",
  "proc_a": "List the steps to set up SSH key authentication on a new Linux server.",
  "proc_b": "Give me a numbered procedure for safely replacing a failed drive in a RAID 5 array.",
  "chat_a": "hey, how is your day going? I am procrastinating on laundry",
  "chat_b": "what do you think about people who put pineapple on pizza?",
  "prose_a": "Explain in a couple of paragraphs why unified memory changes the performance tradeoffs for LLM inference on an APU.",
  "prose_b": "Describe, in prose, what makes speculative decoding effective and when it stops helping."
}
```

- [ ] **Step 2: Add the complete recipe tests below.**

```python
import hashlib
import json
from pathlib import Path
import unittest

from gufo_control import halogen_ten as h

CORPUS_PATH = Path(__file__).resolve().parents[2] / "scripts/gufo_control/fixtures/halogen-eval-prompts.json"


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.corpus = CORPUS_PATH.read_bytes()

    def test_exact_fixture_and_projection(self):
        self.assertEqual(len(self.corpus), 1384)
        self.assertEqual(hashlib.sha256(self.corpus).hexdigest(), h.CORPUS_SHA256)
        for mode, offset in (("ar", 0), ("mtp", 1)):
            d = h.definition(self.corpus, mode)
            self.assertEqual(len(d["schedule"]), 30)
            expected = [(rep, case) for rep in range(3) for case in h.CASES]
            self.assertEqual([(r["repetition"], r["case"]) for r in d["schedule"]], expected)
            self.assertEqual([r["historical_ordinal"] for r in d["schedule"]], list(range(offset, 60, 2)))
            self.assertTrue(all(r["kind"] == "measurement" for r in d["schedule"]))
            self.assertEqual(d["extra_warmup_requests"], 0)
            self.assertFalse(d["exact_historical_protocol"])
        d["schedule"].clear()
        self.assertEqual(len(h.definition(self.corpus, "ar")["schedule"]), 30)

    def test_all_requests_exact_and_fresh(self):
        corpus = json.loads(self.corpus)
        sampler = dict(temperature=0, top_p=1, top_k=0, min_p=0, min_keep=1,
                       seed=42, repeat_penalty=1, repeat_last_n=0,
                       frequency_penalty=0, presence_penalty=0)
        for i in range(30):
            request = h.request_for(self.corpus, "ar", i)
            self.assertEqual(request, h.request_for(self.corpus, "mtp", i))
            self.assertEqual(request["messages"], [{"role": "user", "content": corpus[h.CASES[i % 10]]}])
            self.assertEqual(request["max_tokens"], 256)
            self.assertEqual({k: request[k] for k in sampler}, sampler)
            self.assertIs(request["cache_prompt"], False)
            self.assertIs(request["stream"], False)
            self.assertEqual(request["chat_template_kwargs"], {"enable_thinking": False})
            self.assertFalse(set(request) & {"drafter", "reasoning_effort", "stream_options", "tools"})
            wire = json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
            self.assertEqual(h.request_sha256(request), hashlib.sha256(wire).hexdigest())
        request["messages"][0]["content"] = "changed"
        self.assertNotEqual(h.request_for(self.corpus, "ar", 29), request)
        limits = h.request_limits()
        self.assertEqual((limits.max_prompt_tokens, limits.max_completion_tokens, limits.cache_policy), (3072, 256, "cold"))

    def test_reject_mutations_and_invalid_selection(self):
        for corpus in (self.corpus + b"\n", self.corpus.replace(b"laundry", b"washing"), b"{}", "not bytes"):
            with self.assertRaisesRegex(ValueError, "corpus_identity"):
                h.definition(corpus, "ar")
        for mode in ("serial", "sampled", "mtp-cap3", None):
            with self.assertRaisesRegex(ValueError, "engine_mode"):
                h.definition(self.corpus, mode)
        for ordinal in (-1, 30, True, 0.0):
            with self.assertRaisesRegex(ValueError, "ordinal"):
                h.request_for(self.corpus, "ar", ordinal)
```

- [ ] **Step 3: Run this one offline test file; expect ImportError for the absent module.** From the integration checkout:

```powershell
$env:PYTHONPATH = 'C:/Projects/strix-alloy-research/integration/scripts'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m unittest discover -s tests/gufo -p test_halogen_ten_recipe.py -v
```

- [ ] **Step 4: Create the complete recipe portion of `halogen_ten.py`.**

```python
"""Pinned ten-prompt GUFO adaptation; pure definitions and offline evidence only."""
from copy import deepcopy
import hashlib
import json
import math
import statistics

from .benchmark_recipes import canonical
from .benchmark_http import RequestLimits

CORPUS_SHA256 = "23df9feb5ec2b343f675bb08dc6c0c2286e17dd6d73acf4e7d363d0c0c49922b"
SCRIPT_SHA256 = "7edd38e6ce04854298cf7584ecac13d47afeb96c93e4c85fe113c14094944f83"
HALOGEN_COMMIT = "c8270bb31cd824a0bf53fe9ecf80059c13e7a5bf"
GUFO_REFERENCE_COMMIT = "cff564964e8506c0abb3e530cecb55332187ac6c"
RECIPE_ID = "halogen-ten-gufo-thinking-off-greedy-v1"
CASES = ("code_a", "code_b", "proof_a", "proof_b", "proc_a", "proc_b",
         "chat_a", "chat_b", "prose_a", "prose_b")


def _corpus(raw):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != CORPUS_SHA256:
        raise ValueError("corpus_identity")
    value = json.loads(raw)
    cases = {k: v for k, v in value.items() if not k.startswith("_")}
    if tuple(cases) != CASES or any(type(v) is not str for v in cases.values()):
        raise ValueError("corpus_schema")
    return cases


def definition(corpus: bytes, engine_mode: str) -> dict:
    prompts = _corpus(corpus)
    if engine_mode not in ("ar", "mtp"):
        raise ValueError("engine_mode")
    rows = []
    for rep in range(3):
        for case, prompt in prompts.items():
            ordinal = len(rows)
            rows.append(dict(ordinal=ordinal, historical_ordinal=2*ordinal + (engine_mode == "mtp"),
                             repetition=rep, case=case, kind="measurement", output_budget=256,
                             prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest()))
    value = dict(recipe_id=RECIPE_ID, engine_mode=engine_mode, sampling="explicit_greedy_seed42",
                 source_commit=HALOGEN_COMMIT, corpus_sha256=CORPUS_SHA256,
                 bench_serving_sha256=SCRIPT_SHA256, gufo_reference_commit=GUFO_REFERENCE_COMMIT,
                 exact_historical_protocol=False, thinking="off",
                 historical_thinking="on_low_effort_answer_room_closure_at_token_1",
                 order="rep_case_projection_separate_mode_launches", prefix="",
                 extra_warmup_requests=0, expected_requests=30, repetitions=3,
                 cache="prompt_cache_reuse_bypassed_not_cold_process_or_storage",
                 context_capacity=4096, max_prompt_tokens=3072, max_completion_tokens=256,
                 endpoint="/v1/chat/completions", stream=False, schedule=rows)
    value["definition_sha256"] = hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
    return value


def request_limits() -> RequestLimits:
    return RequestLimits(3072, 256, "cold", 262144)


def request_for(corpus: bytes, engine_mode: str, ordinal: int) -> dict:
    rows = definition(corpus, engine_mode)["schedule"]
    if type(ordinal) is not int or not 0 <= ordinal < len(rows):
        raise ValueError("ordinal")
    prompt = _corpus(corpus)[rows[ordinal]["case"]]
    return dict(model="gufo-flash-next", messages=[dict(role="user", content=prompt)],
                max_tokens=256, temperature=0, top_p=1, top_k=0, min_p=0, min_keep=1,
                seed=42, repeat_penalty=1, repeat_last_n=0, frequency_penalty=0,
                presence_penalty=0, cache_prompt=False,
                chat_template_kwargs={"enable_thinking": False}, stream=False)


def request_sha256(request: dict) -> str:
    # Exact serialization used by benchmark_http.request_once; NOT canonical().
    wire = json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(wire).hexdigest()
```

- [ ] **Step 5: Repeat the exact Step 3 command; expect 3 tests, OK.** If corpus hashing fails, preserve the source bytes (including LF) rather than changing the expected hash. Review the three new files; do not commit in this task.

## Task 2: Complete evidence ledger and conservative statistics

**Files:** Append only the following code to `scripts/gufo_control/halogen_ten.py`; create `tests/gufo/test_halogen_ten_summary.py`.

**Interfaces:**

- Consumes Task 1's three public recipe functions and `request_sha256`.
- Consumes `observations: list[dict]`, each exactly identifying one schedule row via integer `ordinal` and containing unmodified `benchmark_http.request_once` result under `result`. This is a transport result, not raw unvalidated JSON. No live call is made here.
- Consumes nonempty JSON-compatible `provenance: dict` captured by a later authorized harness. Preserve it completely. The summarizer does not assert this metadata qualifies a runtime.
- Produces `summarize(corpus: bytes, engine_mode: str, observations: list[dict], provenance: dict) -> dict`, with all 30 expected rows, original supplied observations, missing-row markers, per-case/per-repetition/whole-mode statistics, and explicit protocol/timing labels.
- Duplicate, unordered or out-of-range ordinals fail input validation, avoiding silent overwrite or invented order. Transport failures remain rows. Unattempted suffix rows after an abort become `not_observed`, never fabricated failures or measurements.

Metrics: actual native logical/new/cached/completion counts only; engine TG is actual completion count / native decode stage seconds, engine PP is actual newly prefetched count / native prefill stage seconds. The transport's fallback `timings.predicted_ms`/`prompt_ms` remains available when native usage stage fields are absent. HTTP output throughput is actual completions / complete request wall. This is not HTTP PP1; that field must stay unavailable for these max256 requests. Non-streaming client TTFT is unavailable; engine TTFT is separately retained. No SSE chunk counting, visible-text retokenization, output-budget numerator, or common-window throughput.

Cold requires cached native count zero, no true cache flags, and explicit request bypass. Cache flags absent in evidence are recorded as unknown flags; native cached-count zero still establishes zero reused tokens under the existing transport contract. `cache_prompt:false` bypasses prefix/prompt-cache reuse; it does not establish that speculative n-gram/prompt lookup is disabled. Lookup and MTP settings remain separately captured runtime provenance. It is not a guarantee of no cache population or zero retained snapshots.

- [ ] **Step 1: Create this complete summary test file.**

```python
from copy import deepcopy
from pathlib import Path
import unittest

from gufo_control import halogen_ten as h

CORPUS_PATH = Path(__file__).resolve().parents[2] / "scripts/gufo_control/fixtures/halogen-eval-prompts.json"


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.corpus = CORPUS_PATH.read_bytes()
        self.provenance = {"fixture_only": True, "not_measured": True}

    def row(self, ordinal, count=256, rate=32.0):
        result = dict(success=True, validation_errors=[], request=h.request_for(self.corpus, "ar", ordinal),
                      model_matches_request=True, finish_reason="length" if count == 256 else "stop",
                      visible_answer="candidate", reasoning_content="", tool_calls=[],
                      usage={"gufo": {"cache_hit": False, "cache_disk_hit": False}},
                      metrics=dict(logical_prompt_tokens=60, new_prefill_tokens=60, cached_prompt_tokens=0,
                                   completion_tokens=count, engine_decode_ms=count*1000/rate,
                                   engine_prefill_ms=100, http_duration_ms=10000,
                                   draft_tokens=None, draft_tokens_accepted=None),
                      raw_response_base64="c3ludGhldGlj", body_parts=[], unavailable_metrics=[])
        return {"ordinal": ordinal, "result": result}

    def test_native_metrics_early_stop_all_repetitions(self):
        rows = [self.row(i, count=226 if i % 10 == 6 else 256, rate=30+i//10) for i in range(30)]
        original = deepcopy(rows)
        result = h.summarize(self.corpus, "ar", rows, self.provenance)
        self.assertEqual(rows, original)
        self.assertEqual(result["whole_mode"]["engine_tg"]["mean"], 31)
        self.assertEqual(result["per_case"]["chat_a"]["engine_tg"]["sample_sd"], 1)
        chat = result["rows"][6]
        self.assertEqual(chat["completion_tokens"], 226)
        self.assertEqual(chat["http_output_tps"], 22.6)
        self.assertTrue(chat["early_stop"])
        self.assertIsNone(chat["client_ttft_ms"])
        self.assertEqual(chat["semantic_status"], "review_required")
        self.assertEqual(result["input_observations"], rows)
        self.assertEqual(len(result["per_repetition"]), 3)

    def test_failure_and_unobserved_never_success_only_mean(self):
        rows = [self.row(i) for i in range(12)]
        rows[0]["result"].update(success=False, error="completion_http_500", raw_response="retained failure")
        result = h.summarize(self.corpus, "ar", rows, self.provenance)
        self.assertEqual(len(result["rows"]), 30)
        self.assertEqual(result["rows"][0]["state"], "failed")
        self.assertEqual(result["rows"][12]["state"], "not_observed")
        self.assertIsNone(result["whole_mode"]["engine_tg"]["mean"])
        self.assertEqual(result["whole_mode"]["engine_tg"]["valid"], 11)
        self.assertEqual(result["input_observations"][0]["result"]["raw_response"], "retained failure")

    def test_missing_or_invalid_duration_no_fallback_to_wall(self):
        for duration in (None, 0, -1, float("nan"), float("inf")):
            with self.subTest(duration=duration):
                row = self.row(0)
                row["result"]["metrics"]["engine_decode_ms"] = duration
                result = h.summarize(self.corpus, "ar", [row], self.provenance)
                self.assertIsNone(result["rows"][0]["engine_tg"])
                self.assertEqual(result["rows"][0]["http_output_tps"], 25.6)
        row = self.row(0)
        row["result"]["metrics"].update(engine_decode_ms=None, engine_timing_predicted_ms=8000)
        result = h.summarize(self.corpus, "ar", [row], self.provenance)
        self.assertEqual(result["rows"][0]["engine_tg"], 32)
        self.assertEqual(result["rows"][0]["decode_clock_source"], "timings.predicted_ms")

    def test_reject_changed_request_counters_cache_and_wrong_finish(self):
        changes = [lambda r: r["request"].update(max_tokens=128),
                   lambda r: r["metrics"].update(cached_prompt_tokens=1),
                   lambda r: r["metrics"].update(completion_tokens=True),
                   lambda r: r["metrics"].update(new_prefill_tokens=59),
                   lambda r: r.update(finish_reason=None),
                   lambda r: r.update(tool_calls=[{}]),
                   lambda r: r.update(model_matches_request=False),
                   lambda r: r["usage"]["gufo"].update(cache_hit=True)]
        for change in changes:
            row = self.row(0)
            change(row["result"])
            result = h.summarize(self.corpus, "ar", [row], self.provenance)
            self.assertEqual(result["rows"][0]["state"], "failed")
            self.assertIsNone(result["rows"][0]["engine_tg"])

    def test_ledger_shape_and_modes_do_not_impose_identity(self):
        for rows in ([self.row(0), self.row(0)], [self.row(1), self.row(0)], [{"ordinal": 30, "result": {}}]):
            with self.assertRaises(ValueError):
                h.summarize(self.corpus, "ar", rows, self.provenance)
        row = self.row(0)
        row["result"]["visible_answer"] = "a different quantization may produce this"
        row["result"]["metrics"].update(draft_tokens=100, draft_tokens_accepted=75)
        result = h.summarize(self.corpus, "mtp", [row], self.provenance)
        self.assertEqual(result["rows"][0]["state"], "observed")
        self.assertEqual(result["rows"][0]["mtp_acceptance"], .75)
        self.assertEqual(result["output_identity"], "diagnostic_only_no_cross_run_gate")
```

- [ ] **Step 2: Run this single test file, expecting missing `summarize`.** Use the same environment as Task 1:

```powershell
python -m unittest discover -s tests/gufo -p test_halogen_ten_summary.py -v
```

- [ ] **Step 3: Append the following complete implementation.**

```python
def _finite_positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _rate(count, milliseconds):
    if type(count) is not int or count < 0 or not _finite_positive(milliseconds):
        return None
    value = count * 1000 / milliseconds
    return value if math.isfinite(value) else None


def _stats(rows, field):
    values = [row.get(field) if row["state"] == "observed" else None for row in rows]
    valid = [v for v in values if type(v) in (int, float) and math.isfinite(v)]
    complete = len(valid) == len(rows) and bool(rows)
    return dict(expected=len(rows), valid=len(valid), values=values,
                mean=statistics.mean(valid) if complete else None,
                sample_sd=statistics.stdev(valid) if complete and len(valid) > 1 else None,
                status="complete" if complete else "incomplete_no_headline_mean")


def _group(rows):
    return {field: _stats(rows, field) for field in ("engine_tg", "engine_pp", "http_output_tps", "http_duration_ms")}


def summarize(corpus: bytes, engine_mode: str, observations: list[dict], provenance: dict) -> dict:
    recipe = definition(corpus, engine_mode)
    if type(observations) is not list or len(observations) > 30:
        raise ValueError("observation_list")
    if type(provenance) is not dict or not provenance:
        raise ValueError("provenance_required")
    canonical(provenance)  # Reject non-JSON and non-finite manifest values.
    supplied = {}
    previous = -1
    for observation in observations:
        if type(observation) is not dict or set(observation) != {"ordinal", "result"}:
            raise ValueError("observation_shape")
        ordinal = observation["ordinal"]
        if type(ordinal) is not int or not previous < ordinal < 30:
            raise ValueError("observation_order_or_ordinal")
        if type(observation["result"]) is not dict:
            raise ValueError("transport_result")
        supplied[ordinal] = observation["result"]
        previous = ordinal
    rows = []
    for schedule in recipe["schedule"]:
        ordinal = schedule["ordinal"]
        expected_request = request_for(corpus, engine_mode, ordinal)
        row = dict(schedule, state="not_observed", reasons=[],
                   request_sha256=request_sha256(expected_request),
                   engine_tg=None, engine_pp=None, http_output_tps=None,
                   http_duration_ms=None, client_ttft_ms=None,
                   http_pp_tokens_per_second=None, common_window_decode_tokens_per_second=None,
                   semantic_status="not_assessed")
        rows.append(row)
        if ordinal not in supplied:
            continue
        result = supplied[ordinal]
        metrics = result.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        reasons = row["reasons"]
        if result.get("success") is not True or result.get("validation_errors"):
            reasons.append("transport_or_native_validation_failed")
        if result.get("request") != expected_request:
            reasons.append("request_mismatch")
        if result.get("model_matches_request") is not True:
            reasons.append("response_model_unconfirmed")
        count_names = ("logical_prompt_tokens", "new_prefill_tokens", "cached_prompt_tokens", "completion_tokens")
        counts = [metrics.get(name) for name in count_names]
        valid_counts = all(type(v) is int and v >= 0 for v in counts)
        if not valid_counts:
            reasons.append("native_counts_missing_or_invalid")
        else:
            logical, new, cached, completion = counts
            if not (0 < logical <= 3072 and logical == new + cached and cached == 0
                    and 0 < completion <= 256 and logical + 256 <= 4096):
                reasons.append("native_count_bounds_or_cache")
        usage = result.get("usage")
        gufo = usage.get("gufo", {}) if isinstance(usage, dict) else {}
        gufo = gufo if isinstance(gufo, dict) else {}
        flags = {key: gufo.get(key) for key in ("cache_hit", "cache_disk_hit")}
        if any(value is not None and value is not False for value in flags.values()):
            reasons.append("cache_flag")
        finish = result.get("finish_reason")
        if finish not in ("stop", "length") or result.get("tool_calls"):
            reasons.append("unexpected_terminal_or_tools")
        content, reasoning = result.get("visible_answer"), result.get("reasoning_content")
        if not isinstance(content, str) or not isinstance(reasoning, str):
            reasons.append("missing_text_fields")
        elif not content.strip() or reasoning:
            reasons.append("empty_answer_or_unexpected_reasoning")
        proposed, accepted = metrics.get("draft_tokens"), metrics.get("draft_tokens_accepted")
        draft_known = type(proposed) is int and type(accepted) is int and 0 <= accepted <= proposed
        if ((proposed is not None or accepted is not None) and not draft_known):
            reasons.append("invalid_draft_counts")
        row.update(state="failed" if reasons else "observed", finish_reason=finish,
                   cache_flags=flags, semantic_status="review_required" if not reasons else "not_assessed",
                   budget_exhausted=finish == "length",
                   early_stop=finish == "stop" and valid_counts and counts[3] < 256,
                   full_256_tokens=valid_counts and counts[3] == 256,
                   native_metrics=deepcopy(metrics), completion_tokens=metrics.get("completion_tokens"),
                   output_sha256=hashlib.sha256((reasoning + content).encode("utf-8")).hexdigest()
                       if isinstance(content, str) and isinstance(reasoning, str) else None,
                   mtp_acceptance=accepted/proposed if not reasons and draft_known and proposed else None)
        for prefix, primary, fallback, primary_label, fallback_label in (
                ("decode", "engine_decode_ms", "engine_timing_predicted_ms", "usage.gufo.decode_ms", "timings.predicted_ms"),
                ("prefill", "engine_prefill_ms", "engine_timing_prompt_ms", "usage.gufo.prefill_ms", "timings.prompt_ms")):
            native = metrics.get(primary)
            duration = native if native is not None else metrics.get(fallback)
            row[prefix + "_ms"] = duration
            row[prefix + "_clock_source"] = primary_label if native is not None else fallback_label if duration is not None else None
        if not reasons:
            row.update(engine_tg=_rate(counts[3], row["decode_ms"]),
                       engine_pp=_rate(counts[1], row["prefill_ms"]),
                       http_output_tps=_rate(counts[3], metrics.get("http_duration_ms")),
                       http_duration_ms=metrics.get("http_duration_ms") if _finite_positive(metrics.get("http_duration_ms")) else None)
    return dict(recipe=recipe, provenance=deepcopy(provenance), rows=rows,
                input_observations=deepcopy(observations),
                whole_mode=_group(rows),
                per_case={case: _group([r for r in rows if r["case"] == case]) for case in CASES},
                per_repetition={str(rep): _group([r for r in rows if r["repetition"] == rep]) for rep in range(3)},
                output_identity="diagnostic_only_no_cross_run_gate",
                timing_labels=dict(engine_tg="native_completion_tokens / native_decode_seconds",
                                   engine_pp="native_new_prefill_tokens / native_prefill_seconds",
                                   http_output_tps="native_completion_tokens / full_http_wall_seconds",
                                   client_ttft="unavailable_non_streaming", engine_ttft="retained_native_metric_separate_clock",
                                   spread="sample_standard_deviation", common_window="unavailable"))
```

- [ ] **Step 4: Run only the two new offline files together; expect 8 tests, OK.**

```powershell
python -m unittest discover -s tests/gufo -p 'test_halogen_ten_*.py' -v
```

These tests exercise returned transport-contract dictionaries without invoking transport. Do not broaden to the existing full GUFO suite in this task: some existing tests start loopback listeners or exercise process ownership. The inspected transport already owns parsing/reconciliation, errors, sanitized raw bodies, headers and receive boundaries; do not duplicate its parser in this module.

- [ ] **Step 5: Review the exact four-file change.** Confirm the corpus SHA256 remains the pin, only new files changed, tests contain no requests or listener setup, the recipe does not import runtime orchestration or access the filesystem itself, and no profile/controller allowlist changed. Do not commit or run a benchmark as part of this plan.

## Minimal future harness integration — interface only, not a change in this plan

A later reviewed experiment would need one narrow adapter in the existing guarded harness that reads the fixture, obtains `definition(corpus, engine_mode)`, iterates its exact 30 rows, calls existing `benchmark_http.request_once` with the generated request and `request_limits()`, and preserves `{ordinal, result}` records. A call would use `/v1/chat/completions`, an already-owned loopback endpoint, the existing guardian cancellation event and a bounded deadline supplied by that authorized harness. The pure module never supplies a port, key, deadline, process command, launch policy or safety decision.

That future adapter must explicitly qualify **30 additional measured POSTs per mode**, separate from every readiness/smoke POST. This cannot fit by silently replacing requests in the frozen66/6 run. The current runtime is AR-only with max-tokens64 and request-policy `ar4k-service-v1`; neither GUFO mode's max256 recipe is attachable as-is, and MTP is additionally outside that current selection. A separately reviewed compatible runtime/profile selection is required later; this plan neither designs one nor broadens caps. Existing measured AR/MTP256-output profiles are historical consumed attempts, not automatically reusable profiles. AR and each MTP policy need their own approved process identity and run group. There are no added recipe warmups, retries, calibrations, prefix requests or cache-clearing actions. Record pre-existing readiness/smoke activity and its timestamps outside the 30 measurements so “no extra warmup” does not imply a cold-loaded engine. Preserve first repetition and abort gaps. No deadline value or enlarged lifetime is authorized here.

Required future provenance entries, captured before measurement and retained with results:

- Unique run/group identity, UTC times, actual AR/MTP mode and process/run order; recipe hash, fixture/tool pins; all 30 planned ordinals and actual attempted ordinals.
- Actual executable/build/patch identity and hashes, app-local DLL hashes, source commit; target shard/model revision and each file hash with local-versus-publisher hash status; tokenizer/template identity and hash; quantization. Retain the source reference separately if actual executed source differs.
- Actual MTP sidecar identity/hash; draft cap, length/survival policy, full/pruned vocabulary and prompt lookup settings; AR records MTP absent. The existing cap3 length/full-vocabulary measurement is context, not permission to assume these settings in a new launch.
- Exact request bodies and wire-serialization hashes; raw sanitized response evidence and its omission/redaction flags, HTTP status/headers, native usage/timings, finish reason, output hash, monotonic timing and error/abort result. Never remove failed/partial evidence because no rate can be computed.
- Existing host/run manifest with driver, power, 64-GiB carve, Windows/hardware identity, context capacity4096, actual input occupancy, one active session, start activity and independent memory policy/qualification identity. This module collects none of those counters.

Native `benchmark_http` results already reconcile prompt = new + cached, native/timings completion and prefill counts, and reject conflicting durations. Its sanitized request dict preserves insertion order used for serialization; request SHA256 here deliberately mirrors its non-ASCII, compact JSON serialization instead of `canonical` (which sorts and escapes). The latter is only for recipe-definition identity. Preserve existing evidence redaction/partial-wire omission flags; do not claim secret-bearing raw wire was retained or reintroduce secrets to get an unredacted hash.

For the future report, show per-case all three actual counts/rates, mean and sample SD; per-repetition ten-case mean; whole-mode 30-rate mean and sample SD only when all30 valid rates exist. Failed/incomplete groups have no headline mean, while valid individual observations remain inspectable. Early EOS/stop is retained with its actual count and may still supply a decode observation; max256 is a budget, not an assertion of256 produced tokens. Length termination is budget exhaustion and semantic review remains pending. A transport-complete proof or code answer is not automatically a correct answer.

Comparing local greedy AR/MTP text under the same weights/template can later be a diagnostic alongside pinned settings, but the summary does not gate on another run's hashes. HGN w4b versus IQ4_XS versus PROJFIX or Q4_K_XL is a labelled deployment comparison, not a quantization-controlled identity or causal engine/OS experiment. No claimed improvement over41.20 follows merely from adding the module.

## Self-review and handoff

Coverage: pinned exact corpus/text/order, three repetitions, max256, explicit identical AR/MTP greedy sampler, historical low-effort thinking distinction, non-streaming boundary, native counts/durations, no TTFT fabrication, cache bypass semantics, first-repetition retention, all-row/failure/abort retention, per-case/per-repetition/overall statistics, provenance contract and future minimal harness seam are specified. No PP work or runtime/store work is included.

Starting snippets are complete for the four files; the fixture is hashed, module functions referenced by tests are defined, no live measurement is present, and test totals are3 + 5 = 8. Runtime provenance enforcement belongs to the later reviewed harness; the supplied metadata is preserved and never treated as an admission decision. Fixture-only test provenance is deliberately labelled synthetic and must never populate a measured report.

Plan complete. Hand back this report for the main agent's full read. Implementation may proceed under the established user-approved `superpowers:subagent-driven-development` workflow, or inline under `superpowers:executing-plans`; neither choice changes the bounded scope or grants runtime authority. No runtime action or new permission request is implied by this plan.
