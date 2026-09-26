# GUFO 16k native-counter attempt implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development and test-driven-development.

**Goal:** Identify one new16k benchmark attempt after the reviewed native-gauge collector correction, without resetting a consumed attempt.

**Architecture:** Update only the current16k fixed profile identity and paths. The recipe, model, memory margins, guardian, accepted4k predecessor and all historical records stay unchanged. Historical16k-v2 incomplete state continues to block every launch until independently disposed.

**Tech Stack:** Python standard library and existing unittest fixtures.

## Global Constraints

- Workspace C:\Projects\strix-alloy-research\integration, branch codex/gufo-native-integration.
- Keep49GiB prelaunch,24GiB physical runtime,12GiB commit reserve; AR68/4/20GiB margin; query/final age2s, runtime age5s; cadence>=1s, nonoverlap;480startup/60request/600lifetime/10cleanup/60recovery unchanged.
- No model, GPU, WSL, telemetry probes, qualification creation, attempt reset, latch mutation, persistent setting, reboot, public push or unrelated edit by implementer.
- New run requires independently reviewed counter implementation and actual late-recovery evidence before launch. A successful build/test is not a model result.

### Task 1: Version only the next16k identity

**Own:** scripts/gufo_control/benchmark_recipes.py, benchmark_guard.py, smoke_store.py and tests/gufo/test_benchmark_recipes.py, test_benchmark_guard.py, test_smoke_store.py.

Fixture dependency correction discovered by the focused run: also own
tests/gufo/test_benchmark_runtime.py and test_benchmark_suite.py solely to
update their current16k fixture identity fromv2 tov3. Preserve historical
and rejection cases. No additional production or recipe change.

- [ ] RED: change exact expected current profile to`ar16k-iq4xs-pp1-cache-v3`, evidence root`gufo-ar16k-benchmark-v3-runs`, qualification`gufo-ar16k-benchmark-v3-qualification.json`. Assert old16k-v2 andv1 are not launchable,4k-v2 unchanged. Extend sibling incomplete-latch refusal tests to all three16k roots; snapshot oldv2 attempt/latch bytes and assert refusal/recheck leave them untouched. Run these three modules and retain expected assertion failures before implementation.
- [ ] Implement the exact identity replacements:

```python
PROFILE_16K = 'ar16k-iq4xs-pp1-cache-v3'
# benchmark_guard.profile_pins: four-case stays unchanged
evidence_name = 'gufo-ar4k-benchmark-v2-runs' if four else 'gufo-ar16k-benchmark-v3-runs'
qualification_name = 'gufo-ar4k-benchmark-v2-qualification.json' if four else 'gufo-ar16k-benchmark-v3-qualification.json'
```

Update smoke_store.PROFILE_ROOTS current16k mapping to the new exact profile/root. Keep both obsolete16k-v1 andv2 roots explicitly in `_incomplete_latches`, alongside existing older4k roots. Never move or change their actual markers. Recipe content aside from profile identifier must remain identical (13sequential requests,16384capacity, same calibrated PP2048/8192 and cache sequence).

- [ ] GREEN: focused tests above pass, existing benchmark_suite and smoke_guard tests pass. Run full offline suite once before commit; absolute PYTHONPATH includes integration/scripts and integration/tests/gufo. Use Python312 at C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe.
- [ ] Commit only six owned files. Write RED/GREEN evidence, exact commands, preserved-byte assertions and self-review to .superpowers/sdd/ar16k-v3-report.md. Independent task review precedes parent qualification and single actual run.
