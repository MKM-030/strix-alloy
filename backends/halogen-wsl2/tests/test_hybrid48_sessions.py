"""CPU-only contracts for bounded, shared-pool preflight sessions."""
import base64
import importlib.util
import io
import json
import math
import pathlib
import subprocess
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / 'tools/qualification/qualify-hybrid48-model.ps1'
PROBE = ROOT / 'tools/qualification/hybrid48-sessions-check.py'
PWSH = pathlib.Path(shutil.which('pwsh') or 'pwsh')


def load_probe():
    spec = importlib.util.spec_from_file_location('hybrid48_sessions_test', PROBE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeBench:
    FILLER = ' filler words'

    def __init__(self, *, health=None, fail_group=None, bad_timing=None, prompt_tokens=None,
                 duplicate_ids=False, incorrect_marker=False, fail_calibration=False,
                 duplicate_across_groups=False):
        self.health = health or dict(prompt_cache={'enabled': False},
                                     version={'match': True}, context=32768,
                                     slot_ctx=32768, kv_pool_positions=32768, slots=3)
        self.fail_group = fail_group
        self.bad_timing = bad_timing
        self.prompt_tokens = prompt_tokens
        self.duplicate_ids = duplicate_ids
        self.incorrect_marker = incorrect_marker
        self.fail_calibration = fail_calibration
        self.duplicate_across_groups = duplicate_across_groups
        self.lock = threading.Lock()
        self.calls = []
        self.active = 0
        self.max_active = 0
        self.barriers = {2: threading.Barrier(2), 3: threading.Barrier(3)}

    def request_json(self, url, body=None, timeout=None):
        if url.endswith('/health'):
            return self.health, .01
        with self.lock:
            self.calls.append((body, timeout))
            serial = len(self.calls)
        if serial <= 2:
            if serial == 2 and self.fail_calibration:
                raise TimeoutError('calibration request timed out')
            tokens = 10 if serial == 1 else 370
            return self.response(f'cal-{serial}', tokens, 1, 'calibration'), .01
        prompt = body['messages'][0]['content']
        group = 2 if 'GROUP-2-' in prompt else 3
        marker = prompt.split('Begin with the exact marker ')[1].split('.')[0]
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self.barriers[group].wait(timeout=2)
            time.sleep(.02)
            if self.fail_group == group and marker.endswith('01'):
                raise TimeoutError('synthetic request timeout')
            tokens = self.prompt_tokens or 8190
            identifier = ('duplicate' if self.duplicate_ids else
                          'GROUP-2-SESSION-01' if self.duplicate_across_groups and
                          marker == 'GROUP-3-SESSION-01' else marker)
            response = self.response(identifier,
                                     tokens, 40,
                                     'wrong answer' if self.incorrect_marker else marker + ' answer')
            if self.bad_timing == group:
                response['timings']['predicted_ms'] = math.nan
            return response, .05
        finally:
            with self.lock:
                self.active -= 1

    @staticmethod
    def response(identifier, prompt_tokens, completion_tokens, content):
        return dict(id=identifier,
                    usage=dict(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
                    timings=dict(prompt_ms=100., predicted_ms=200.,
                                 prompt_per_second=100., predicted_per_second=40., cache_n=0),
                    choices=[dict(message=dict(content=content))])

    def build_prompt(self, target, calibration, instruction):
        return instruction + '\n' + self.FILLER * 100

    def extract_measurement(self, response, wall, marker):
        return dict(request_id=response['id'], prompt_tokens=response['usage']['prompt_tokens'],
                    completion_tokens=response['usage']['completion_tokens'],
                    prompt_ms=response['timings']['prompt_ms'],
                    generation_ms=response['timings']['predicted_ms'],
                    prompt_tokens_per_second=response['timings']['prompt_per_second'],
                    generation_tokens_per_second=response['timings']['predicted_per_second'],
                    cache_tokens=response['timings']['cache_n'],
                    content=response['choices'][0]['message']['content'],
                    nonempty=True, marker_present=marker in response['choices'][0]['message']['content'])


class SessionsTests(unittest.TestCase):
    def run_ps(self, body):
        encoded = base64.b64encode((f". '{CONTROLLER}';\n" + body).encode('utf-16-le')).decode('ascii')
        return subprocess.run([str(PWSH), '-NoProfile', '-EncodedCommand', encoded],
                              capture_output=True, text=True)

    def test_controller_changes_only_slot_count_and_selects_bounded_probe(self):
        result = self.run_ps(r"""
$machine=[pscustomobject]@{models='/models';workspace='/workspace';dxg='/dxg'}
$reference=Get-PublicReference
$a=@{adapters=@(@{binary='bin/halogen-preflight-adadd8dd5cebcdf559fcc9df767a2bcb36e6946c1a123b90c670320bf7a873f5.so'},@{binary='bin/hip-register-private-rw-vgm64copy48-0546a8817fdec642ae3e9b597a9912b547ccd743d6da7eda923d647d0d421c9c.so'})}
$old=New-RunArguments $reference $a 'test' -Mode PreflightPinned32k
$new=New-RunArguments $reference $a 'test' -Mode PreflightSessions32k
$expected=@($old | ForEach-Object {if($_ -ceq 'HALOGEN_KV_SLOTS=1'){'HALOGEN_KV_SLOTS=3'}else{$_}})
if(($expected -join '|') -cne ($new -join '|')){throw 'NON_SLOT_CHANGE'}
Write-Output 'ARGUMENTS_OK'
$p=Get-QualificationProbeSpec -Mode PreflightSessions32k
if($p.Script -cne 'hybrid48-sessions-check.py' -or $p.DeadlineSeconds -ne 300){throw 'BAD_PROBE'}
Write-Output 'PROBE_OK'
if((Get-RemainingInferenceSeconds -InferenceElapsed 390 -OverallElapsed 790 -Mode PreflightSessions32k) -ne 10){throw 'BAD_CLIP'}
Write-Output 'CLIP_OK'
$reference.Config.Env=@($reference.Config.Env | ForEach-Object {if($_ -ceq 'HALOGEN_KV_SLOTS=1'){'HALOGEN_KV_SLOTS=3'}else{$_}})
try{New-RunArguments $reference $a 'test' -Mode PreflightSessions32k;throw 'CHANGED_REFERENCE_ACCEPTED'}catch{if($_ -match 'CHANGED_REFERENCE_ACCEPTED'){throw}}
Write-Output 'REFERENCE_OK'
""")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_controller_passes_clipped_probe_deadline(self):
        result = self.run_ps(r"""
$spec=Get-QualificationProbeSpec -Mode PreflightSessions32k
$window=[Math]::Min($spec.DeadlineSeconds,(Get-RemainingInferenceSeconds -InferenceElapsed 275 -OverallElapsed 800 -Mode PreflightSessions32k))
$args=Get-QualificationProbeArguments -Spec $spec -Mode PreflightSessions32k -Window $window -RunDir 'C:\temp\sessions-test'
if($window -ne 20 -or ($args[-2..-1] -join '|') -cne '--deadline-seconds|20'){throw 'DEADLINE_NOT_PASSED'}
$old=Get-QualificationProbeArguments -Spec (Get-QualificationProbeSpec -Mode PreflightPinned32k) -Mode PreflightPinned32k -Window 20 -RunDir 'C:\temp\sessions-test'
if($old -contains '--deadline-seconds'){throw 'OLD_PROBE_CHANGED'}
Write-Output 'PASS'
""")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_sessions_probe_cleanup_terminates_real_descendant(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent_script = pathlib.Path(tmp) / 'dummy_parent.py'
            pid_file = pathlib.Path(tmp) / 'dummy_child.pid'
            parent_script.write_text(
                "import pathlib, subprocess, sys, time\n"
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], "
                "creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))\n"
                "pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding='ascii')\n"
                "time.sleep(30)\n", encoding='utf-8')
            script = str(parent_script).replace("'", "''")
            pidpath = str(pid_file).replace("'", "''")
            python = str(pathlib.Path(sys.executable)).replace("'", "''")
            result = self.run_ps(f"""
$parent=Start-Process -FilePath '{python}' -WindowStyle Hidden -PassThru -ArgumentList @('-u','{script}','{pidpath}')
$childId=$null
try {{
  for($i=0;$i -lt 50 -and -not (Test-Path -LiteralPath '{pidpath}');$i++){{Start-Sleep -Milliseconds 100}}
  if(-not (Test-Path -LiteralPath '{pidpath}')){{throw 'DUMMY_CHILD_NOT_STARTED'}}
  $childId=[int](Get-Content -LiteralPath '{pidpath}' -Raw)
  Get-Process -Id $childId -ErrorAction Stop | Out-Null
  Stop-QualificationProcess -Process $parent -Probe $parent -Mode PreflightSessions32k
  for($i=0;$i -lt 20 -and (Get-Process -Id $childId -ErrorAction SilentlyContinue);$i++){{Start-Sleep -Milliseconds 100}}
  if(Get-Process -Id $childId -ErrorAction SilentlyContinue){{throw 'DUMMY_DESCENDANT_SURVIVED'}}
  Write-Output 'TREE_STOPPED'
}} finally {{
  $parent.Refresh()
  if(-not $parent.HasExited){{$parent.Kill($true);$parent.WaitForExit(5000) | Out-Null}}
  if($childId){{Get-Process -Id $childId -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue}}
  $parent.Dispose()
}}
""")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('TREE_STOPPED', result.stdout)

    def test_tree_cleanup_is_limited_to_sessions_probe(self):
        result = self.run_ps(r"""
function Stop-HelperChecked {param($Process,[switch]$Tree) $script:flags += [bool]$Tree}
$script:flags=@()
$probe=[pscustomobject]@{name='probe'}
$guard=[pscustomobject]@{name='guard'}
Stop-QualificationProcess -Process $probe -Probe $probe -Mode PreflightSessions32k
Stop-QualificationProcess -Process $guard -Probe $probe -Mode PreflightSessions32k
Stop-QualificationProcess -Process $probe -Probe $probe -Mode PreflightPinned32k
if(($script:flags -join '|') -cne 'True|False|False'){throw 'WRONG_TREE_SCOPE'}
Write-Output 'PASS'
""")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def run_probe(self, bench=None, deadline=300, tail_margin=None):
        probe = load_probe()
        bench = bench or FakeBench()
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp) / 'sessions.json'
            if tail_margin is None:
                code = probe.run_qualification(bench, output, deadline_seconds=deadline)
            else:
                with mock.patch.object(probe, 'REQUEST_TAIL_MARGIN_SECONDS', tail_margin, create=True):
                    code = probe.run_qualification(bench, output, deadline_seconds=deadline)
            summary = json.loads(output.read_text())
            artifacts = {p.name: json.loads(p.read_text()) for p in output.parent.glob('sessions-*.json')}
        return code, bench, summary, artifacts

    def test_real_threads_overlap_and_archive_unique_sessions(self):
        code, bench, summary, artifacts = self.run_probe()
        self.assertEqual(code, 0)
        self.assertTrue(summary['passed'])
        self.assertEqual([g['successful_sessions'] for g in summary['groups']], [2, 3])
        self.assertEqual(len(artifacts), 5)
        self.assertGreaterEqual(bench.max_active, 3)
        self.assertTrue(all(g['client_overlap_seconds'] > 0 for g in summary['groups']))
        for group in summary['groups']:
            self.assertEqual(group['successful_sessions'], group['requested_sessions'])
            self.assertAlmostEqual(group['end_to_end_output_tokens_per_second'],
                                   sum(r['actual_output_tokens'] for r in group['sessions']) /
                                   group['group_wall_seconds'], places=3)
            for row in group['sessions']:
                self.assertTrue(row['passed'])
                self.assertEqual(row['request']['drafter'], 'mtp')
                self.assertEqual(row['cache_tokens'], 0)
                self.assertIn(row['marker'], row['content'])
                self.assertLessEqual(row['actual_prompt_tokens'] + 128,
                                     32768 // group['requested_sessions'])
        self.assertTrue(all(timeout <= 90 for body, timeout in bench.calls[2:]))

    def test_wrong_health_refuses_before_calibration_and_saves_failure(self):
        bench = FakeBench(health=dict(prompt_cache={'enabled': False}, version={'match': True},
                                     context=32768, slot_ctx=32768, kv_pool_positions=32768,
                                     slots=1))
        code, bench, summary, artifacts = self.run_probe(bench)
        self.assertEqual(code, 2)
        self.assertEqual(bench.calls, [])
        self.assertFalse(summary['passed'])
        self.assertIn('slots', summary['error'])

    def test_partial_failure_archives_all_completed_and_skips_later_group(self):
        code, bench, summary, artifacts = self.run_probe(FakeBench(fail_group=2))
        self.assertEqual(code, 2)
        self.assertEqual(len(summary['groups']), 1)
        self.assertEqual(len(artifacts), 2)
        self.assertEqual(summary['groups'][0]['successful_sessions'], 1)
        self.assertTrue(any(row['error'] for row in summary['groups'][0]['sessions']))
        self.assertEqual(bench.active, 0)

    def test_invalid_measurement_and_fair_share_fail_closed(self):
        for bench in (FakeBench(bad_timing=2), FakeBench(prompt_tokens=16300),
                      FakeBench(duplicate_ids=True), FakeBench(incorrect_marker=True)):
            with self.subTest(bench=bench):
                code, _, summary, artifacts = self.run_probe(bench)
                self.assertEqual(code, 2)
                self.assertEqual(len(summary['groups']), 1)
                self.assertEqual(len(artifacts), 2)
                self.assertFalse(summary['groups'][0]['all_sessions_succeeded'])

    def test_broken_barrier_is_archived_for_each_client(self):
        probe = load_probe()
        bench = FakeBench()
        real_barrier = threading.Barrier
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp) / 'sessions.json'
            with mock.patch.object(probe.threading, 'Barrier', side_effect=lambda count: real_barrier(count, action=lambda: 1 / 0)):
                code = probe.run_qualification(bench, output)
            summary = json.loads(output.read_text())
            artifacts = list(output.parent.glob('sessions-group-*.json'))
        self.assertEqual(code, 2)
        self.assertEqual(len(summary['groups']), 1)
        self.assertEqual(len(artifacts), 2)
        self.assertTrue(all(row['error'] for row in summary['groups'][0]['sessions']))
        self.assertTrue(any('BrokenBarrierError' in row['error'] for row in summary['groups'][0]['sessions']))

    def test_deadline_override_may_only_shrink(self):
        probe = load_probe()
        with tempfile.TemporaryDirectory() as tmp:
            for deadline in (0, 301):
                with self.assertRaises(ValueError):
                    probe.run_qualification(FakeBench(), pathlib.Path(tmp) / 'sessions.json', deadline)

    def test_calibration_timeout_keeps_partial_evidence(self):
        code, bench, summary, artifacts = self.run_probe(FakeBench(fail_calibration=True))
        self.assertEqual(code, 2)
        self.assertEqual(len(bench.calls), 2)
        self.assertEqual(len(summary['calibration']['samples']), 1)
        self.assertEqual(summary['groups'], [])
        self.assertEqual(artifacts, {})

    def test_fast_client_artifact_is_saved_before_sibling_finishes(self):
        class SlowSibling(FakeBench):
            def __init__(self):
                super().__init__()
                self.release = threading.Event()

            def request_json(self, url, body=None, timeout=None):
                response = super().request_json(url, body, timeout)
                if body and 'GROUP-2-SESSION-02' in body['messages'][0]['content']:
                    self.release.wait(timeout=2)
                return response

        probe = load_probe()
        bench = SlowSibling()
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp) / 'sessions.json'
            worker = threading.Thread(target=probe.run_qualification, args=(bench, output))
            worker.start()
            artifact = output.with_name('sessions-group-2-session-01.json')
            try:
                until = time.monotonic() + 1
                while not artifact.exists() and time.monotonic() < until:
                    time.sleep(.01)
                self.assertTrue(artifact.exists(), 'completed first client was not archived promptly')
                self.assertFalse(output.exists(), 'probe should still be waiting for the sibling')
            finally:
                bench.release.set()
                worker.join(timeout=3)
            self.assertFalse(worker.is_alive())

    def test_response_ids_must_be_unique_across_groups(self):
        code, _, summary, artifacts = self.run_probe(FakeBench(duplicate_across_groups=True))
        self.assertEqual(code, 2)
        self.assertEqual(len(summary['groups']), 2)
        self.assertFalse(summary['groups'][1]['all_sessions_succeeded'])
        self.assertIn('duplicate', summary['groups'][1]['error'])
        self.assertEqual(len(artifacts), 5)

    def test_raw_message_content_must_be_a_nonempty_string(self):
        class ObjectContent(FakeBench):
            def response(self, identifier, prompt_tokens, completion_tokens, content):
                response = super().response(identifier, prompt_tokens, completion_tokens, content)
                if identifier.startswith('GROUP-'):
                    response['choices'][0]['message']['content'] = {'text': content}
                return response

            def extract_measurement(self, response, wall, marker):
                measurement = super().extract_measurement(response, wall, marker)
                if isinstance(measurement['content'], dict):
                    measurement['content'] = json.dumps(measurement['content'])
                return measurement

        code, _, summary, artifacts = self.run_probe(ObjectContent())
        self.assertEqual(code, 2)
        self.assertEqual(len(summary['groups']), 1)
        self.assertTrue(all(not row['passed'] for row in summary['groups'][0]['sessions']))
        self.assertEqual(len(artifacts), 2)

    def test_elapsed_request_exceeding_global_deadline_is_rejected(self):
        class SlowResponse(FakeBench):
            def request_json(self, url, body=None, timeout=None):
                response = super().request_json(url, body, timeout)
                if body and 'GROUP-2-' in body['messages'][0]['content']:
                    time.sleep(1.05)
                return response

        code, _, summary, artifacts = self.run_probe(SlowResponse(), deadline=1, tail_margin=0)
        self.assertEqual(code, 2)
        self.assertEqual(len(summary['groups']), 1)
        self.assertFalse(summary['groups'][0]['all_sessions_succeeded'])
        self.assertTrue(all(row['error'] for row in summary['groups'][0]['sessions']))
        self.assertEqual(len(artifacts), 2)

    def test_request_allowance_reserves_time_for_child_cleanup_and_summary(self):
        code, bench, summary, artifacts = self.run_probe(FakeBench(), deadline=1, tail_margin=.4)
        self.assertEqual(code, 0)
        self.assertTrue(summary['passed'])
        self.assertTrue(all(timeout <= .6 for _, timeout in bench.calls))
        self.assertEqual(len(artifacts), 5)

    def test_absolute_transport_timeout_kills_slow_drip_child(self):
        probe = load_probe()
        with tempfile.TemporaryDirectory() as tmp:
            child = pathlib.Path(tmp) / 'slow_child.py'
            child.write_text("import sys, time\nsys.stdin.read()\nsys.stdout.write('{\"response\":')\nsys.stdout.flush()\ntime.sleep(5)\n",
                             encoding='utf-8')
            spawned = []
            real_popen = subprocess.Popen

            def capture(*args, **kwargs):
                process = real_popen(*args, **kwargs)
                spawned.append(process)
                return process

            transport = probe.BoundedBenchmarkTransport(FakeBench(), child_script=child)
            started = time.perf_counter()
            with mock.patch.object(probe.subprocess, 'Popen', side_effect=capture):
                with self.assertRaises(TimeoutError):
                    transport.request_json('http://unused/v1/chat/completions', {'x': 1}, timeout=.2)
            self.assertLess(time.perf_counter() - started, 2)
            self.assertEqual(len(spawned), 1)
            self.assertIsNotNone(spawned[0].poll(), 'request child survived timeout')

    def test_request_child_protocol_is_ascii_safe_on_windows_pipe(self):
        probe = load_probe()

        class Loader:
            def create_module(self, spec):
                return None

            def exec_module(self, module):
                module.request_json = lambda url, body, timeout: ({'content': '你好'}, .1)

        spec = importlib.util.spec_from_loader('fake_benchmark', Loader())
        raw = io.BytesIO()
        stdout = io.TextIOWrapper(raw, encoding='cp1252')
        request = io.StringIO(json.dumps({'url': 'http://unused', 'body': None, 'timeout': 1}))
        with (mock.patch.object(probe.importlib.util, 'spec_from_file_location', return_value=spec),
              mock.patch.object(probe.sys, 'stdin', request),
              mock.patch.object(probe.sys, 'stdout', stdout)):
            self.assertEqual(probe.request_child(), 0)
            stdout.flush()
        self.assertEqual(json.loads(raw.getvalue())['response']['content'], '你好')


if __name__ == '__main__':
    unittest.main()
