# GUFO recovery query ownership correction

> **For agentic workers:** Use superpowers:subagent-driven-development and test-driven-development. This narrowly corrects the approved runner before GPU execution.

**Goal:** Never report a blocked recovery telemetry collector as terminal.

**Architecture:** Separate polling an existing Query from creating one. Recovery retains its Query and reports the actual completion event even on exception. No deadline or admission change.

**Tech Stack:** Existing Python standard library, unittest, operator_probe.py.

## Global Constraints

- Workspace C:\Projects\strix-alloy-research\integration, existing codex/gufo-native-integration branch.
- Keep 49 GiB prelaunch, 24 GiB runtime physical headroom, 12 GiB commit reserve, query watchdog 2s and freshness 5s unchanged.
- No real GPU/model/WSL/server execution by implementer. Offline tests only; harmless existing Python process fixtures are allowed.
- Keep durable incomplete latch after any unconfirmed recovery. No automatic retry or reset.
- Own only scripts/gufo_control/operator_probe.py and tests/gufo/test_operator_probe.py. Commit only those files. No public push.

## Plan correction authority

The previous runner plan lost a recovery Query inside collect_one and retained
collector_terminal=true after timeout. Independent review reproduced this.
The user was asked about the plan/code correction and then instructed us to
continue and finish the reviewed safeguards before bounded GPU tests. This
amendment governs that recovery implementation in the earlier plan. All
approved design and safety limits remain unchanged.

### Task 1: Retain recovery query lifecycle state

**Modify:** scripts/gufo_control/operator_probe.py; tests/gufo/test_operator_probe.py.

**Interfaces:** Query.done is a threading.Event set only when collection work
finishes. Existing collect_one callers still receive a Frame or exception.
Add private finish_query(query, log_path, phase) for polling/logging an owned
query; it creates no thread. _run_owned owns the recovery Query reference.

- [ ] Add this method to RunnerTests first:

```python
    def test_blocked_recovery_reports_collector_nonterminal(self):
        release = threading.Event()
        finished = threading.Event()
        def blocked():
            try:
                release.wait(3)
                return snapshot()
            finally:
                finished.set()
        try:
            with tempfile.TemporaryDirectory() as folder:
                child = FakeChild(finished=True)
                result = self.invoke(folder, child, blocked, MAX_QUERY_SECONDS=0.05)
                self.assertTrue(child.closed)
                self.assertTrue(result['owned_exit_confirmed'])
                self.assertFalse(finished.is_set())
                self.assertFalse(result['collector_terminal'])
                self.assertFalse(result['cleanup_confirmed'])
                self.assertFalse(result['success'])
                self.assertIn('active_query_timeout', result['failure'])
                self.assertIn('collector_still_active', result['failure'])
        finally:
            release.set()
            self.assertTrue(finished.wait(1))
```

- [ ] Run focused suite before implementation. Set child-shell PYTHONPATH to
the absolute integration/scripts path. Run Python312 python.exe -m unittest
discover -s tests/gufo -p test_operator_probe.py -v. Expect the new assertion
on collector_terminal to fail; existing tests pass.

- [ ] Replace collect_one with these functions (same polling logic):

```python
def finish_query(query, log_path, phase):
    while True:
        value = query.poll()
        if value is not None:
            log_frame(log_path, value, phase)
            return value
        time.sleep(POLL_SECONDS)


def collect_one(collect, log_path, phase, previous_start=None):
    if previous_start is not None:
        time.sleep(max(0, previous_start+QUERY_INTERVAL-time.monotonic()))
    return finish_query(Query(collect), log_path, phase)
```

- [ ] In _run_owned's recovery loop, replace only its collect_one assignment:

```python
                time.sleep(max(0, last_query_start+QUERY_INTERVAL-time.monotonic()))
                query = Query(collect)
                try:
                    frame = finish_query(query, evidence, 'recovery')
                finally:
                    collector_terminal = query.done.is_set()
                    if not collector_terminal:
                        failure = (failure or '')+';collector_still_active'
```

Keep following last_query_start assignment and recovery checks unchanged.
Do not wait beyond the original query deadline or launch another collector
after this failure. Completed-but-invalid collection remains terminal but
recovery remains failed.

- [ ] Re-run the focused test_operator_probe.py suite. Expect 13 passing
tests and pristine output. Parent owns the full-suite run after review.
- [ ] Self-review, commit only the two owned files with message
`fix: retain recovery telemetry ownership on timeout`. Append RED/GREEN
commands and exact output to .superpowers/sdd/operator-runner-task-1-report.md.
Return commit and concerns. Do not invoke production operator_probe CLI.
