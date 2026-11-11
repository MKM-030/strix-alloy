"""CPU-only contracts: no DLL, hardware, child, API, WSL or compiler calls."""
import copy
import ctypes as c
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def subject(name):
    if not (HERE/(name+'.py')).is_file():
        raise AssertionError(name+' is not implemented')
    return importlib.import_module(name)


class Function:
    def __init__(self, body): self.body = body
    def __call__(self, *args): return self.body(*args)


class FakeDLL:
    def __init__(self):
        self.calls = []; self.count = 512; self.skips = 0; self.enabled = False
        self.restored = 1; self.ticks = 1
        self.sl1012_last_error = Function(lambda: b'injected head restoration failure')
        self.sl1012_create = Function(self.create)
        self.sl1012_close = Function(lambda handle: self.calls.append(('close',)) or 0)
        self.sl1012_context = Function(self.context)
        self.sl1012_set_append_head_skip = Function(self.select)
        self.sl1012_head_skip_status = Function(self.status)
        self.sl1012_append_only = Function(self.append)
        self.sl1012_forward = Function(lambda *args: 0)
        self.sl1012_seed = Function(lambda *args: 0)
        for name in ('state_read', 'state_write', 'state_free'):
            setattr(self, 'sl1012_'+name, Function(lambda *args: 0))

    def timing(self, out):
        self.ticks += 2
        out._obj.started_ticks = self.ticks; out._obj.finished_ticks = self.ticks+1
        out._obj.frequency = 10000000
    def create(self, model, bundle, timing): self.timing(timing); self.calls.append(('create',)); return 71
    def context(self, handle, out): out._obj.value = self.count; return 0
    def select(self, handle, enabled): self.calls.append(('select', enabled)); self.enabled = bool(enabled); return 0
    def status(self, handle, count, restored): count._obj.value = self.skips; restored._obj.value = self.restored; return 0
    def append(self, handle, token, timing):
        self.calls.append(('append', token)); self.count += 1; self.skips += int(self.enabled); self.timing(timing); return 0


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.m = subject('native_backend'); self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name); self.bridge = self.path/'bridge.dll'; self.bridge.write_bytes(b'fixture')
        self.qwen = self.path/'qwen3_5vl_npu.dll'; self.qwen.write_bytes(b'CPU identity fixture')
        self.dll = FakeDLL(); self.closed = []

    def backend(self):
        def directory(path): return type('Directory', (), {'close': lambda obj: self.closed.append(path)})()
        with patch.object(self.m.os, 'add_dll_directory', side_effect=directory), patch.object(self.m.c, 'CDLL', return_value=self.dll):
            backend = self.m.NativeBackend(self.bridge, self.path/'model', self.path/'bundle', self.path)
        self.addCleanup(lambda: backend.close() if backend.handle is not None else None)
        return backend

    def test_default_off_and_typed_selector_observation_ABI(self):
        b = self.backend(); self.assertFalse(b.append_head_skip_enabled)
        self.assertEqual(self.dll.calls, [('create',)])
        self.assertEqual(self.dll.sl1012_set_append_head_skip.argtypes, [c.c_void_p, c.c_int])
        self.assertEqual(self.dll.sl1012_head_skip_status.argtypes,
                         [c.c_void_p, c.POINTER(c.c_uint64), c.POINTER(c.c_int32)])
        self.assertEqual(b.head_skip_status(), {'count': 0, 'restored': True})

    def test_enable_verifies_actual_loaded_path_and_hash_before_native_selection(self):
        b = self.backend(); proof = {'path': str(self.qwen.resolve()), 'sha256': self.m.QWEN_SHA256}
        with patch.object(self.m, 'verify_loaded_qwen', return_value=proof) as verify:
            b.set_append_head_skip(True)
        verify.assert_called_once_with(self.qwen.resolve())
        self.assertTrue(b.append_head_skip_enabled); self.assertEqual(self.dll.calls[-1], ('select', 1))
        self.assertEqual(b.head_skip_identity, proof)
        with patch.object(self.m, 'verify_loaded_qwen', side_effect=AssertionError('disable must remain available')):
            b.set_append_head_skip(False)
        self.assertFalse(b.append_head_skip_enabled)

    def test_identity_refusal_and_wrong_thread_never_enable(self):
        b = self.backend()
        with patch.object(self.m, 'verify_loaded_qwen', side_effect=ValueError('Wrong loaded Qwen path')):
            with self.assertRaisesRegex(ValueError, 'Qwen path'): b.set_append_head_skip(True)
        b.owner = -1
        with self.assertRaisesRegex(RuntimeError, 'owner thread'): b.set_append_head_skip(True)
        b.owner = threading.get_ident()
        self.assertEqual(self.dll.calls, [('create',)])

    def test_getmodule_proof_checks_actual_file_not_just_requested_DLL(self):
        class Kernel:
            def __init__(self, path):
                self.path = str(path); self.slots = []
                self.GetModuleHandleW = Function(lambda name: self.slots.append(name) or 88)
                self.GetModuleFileNameW = Function(self.filename)
            def filename(self, handle, buffer, length): buffer.value = self.path; return len(self.path)
        kernel = Kernel(self.qwen)
        with patch.object(self.m.c, 'WinDLL', return_value=kernel), patch.object(self.m, 'QWEN_SHA256', hashlib.sha256(self.qwen.read_bytes()).hexdigest()):
            proof = self.m.verify_loaded_qwen(self.qwen)
        self.assertEqual(kernel.slots, ['qwen3_5vl_npu.dll']); self.assertEqual(proof['path'], str(self.qwen.resolve()))
        other = self.path/'other.dll'; other.write_bytes(self.qwen.read_bytes()); kernel.path = str(other)
        with patch.object(self.m.c, 'WinDLL', return_value=kernel):
            with self.assertRaisesRegex(ValueError, 'path'): self.m.verify_loaded_qwen(self.qwen)
        kernel.path = str(self.qwen)
        with patch.object(self.m.c, 'WinDLL', return_value=kernel):
            with self.assertRaisesRegex(ValueError, 'SHA256'): self.m.verify_loaded_qwen(self.qwen)

    def test_unrestored_scope_cannot_report_clean_close(self):
        b = self.backend(); self.dll.restored = 0
        with self.assertRaisesRegex(RuntimeError, 'restor'): b.close()
        self.assertIsNotNone(b.handle); self.assertNotIn(('close',), self.dll.calls)
        self.dll.restored = 1


class Clock:
    def __init__(self): self.tick = 0
    def __call__(self): self.tick += 1000; return self.tick


class Engine:
    def __init__(self):
        self.history = (); self.states = {}; self.serial = 0; self.operations = []; self.handle = 71
        self.enabled = False; self.skips = 0; self.calls = []; self.fail_append = False; self.restored = True
    @staticmethod
    def row(ids):
        from actor import OwnedRow
        return OwnedRow((ids[-1]+1)%248070, hashlib.sha256(struct.pack('<%di'%len(ids), *ids)).digest())
    def set_append_head_skip(self, enabled): self.calls.append(('select', enabled)); self.enabled = enabled
    def head_skip_status(self): return dict(count=self.skips, restored=self.restored)
    def seed(self, ids): self.history = tuple(ids); self.calls.append(('seed',)); return self.row(self.history)
    def append_only(self, token):
        if self.fail_append: raise RuntimeError('append failure')
        self.history += (token,); self.skips += int(self.enabled); self.calls.append(('append', self.enabled))
    def forward(self, token): self.history += (token,); self.calls.append(('forward',)); return self.row(self.history)
    def context_length(self): return len(self.history)
    def save(self): self.serial += 1; self.states[self.serial] = self.history; return self.serial
    def restore(self, state): self.history = self.states[state]; return len(self.history)
    def free(self, state): del self.states[state]
    def close(self): self.handle = None; self.states.clear(); self.calls.append(('close',))


class QualifierTests(unittest.TestCase):
    def execute(self, engine=None):
        m = subject('qualify_core_append'); engine = engine or Engine(); clock = Clock(); creations = []
        value = json.loads(m.DEFAULT_INPUT.read_bytes())
        def factory(): creations.append(1); return engine
        with patch.object(m.StatefulActor, 'prepare_one', side_effect=AssertionError('No future feed')):
            report, rows = m.run_modes(factory, value, clock=clock, frequency=1000000,
                deadline_seconds=10, row_bytes=32, module_probe=lambda: ['CPU fixture'])
        return m, report, rows, engine, value, creations

    def test_both_arms_queued16_alternate_one_warmup_three_measured_one_engine(self):
        m, r, rows, e, v, created = self.execute()
        self.assertTrue(r['complete'], r['error']); self.assertEqual(created, [1]); self.assertEqual(len(rows), 81)
        self.assertEqual(r['schema'], 'halogen0201.stateful1012-core-append-qualification.v1')
        self.assertEqual([x['mode'] for x in r['runs']], ['head_on', 'head_skip']*4)
        self.assertEqual([x['excluded_warmup'] for x in r['runs']], [True, True]+[False]*6)
        self.assertTrue(all(x['committed_event_batches'] == 8 and len(x['states']) == 9 and x['commit_loop_ms'] == 8 for x in r['runs']))
        self.assertEqual([x['head_skip_count_delta'] for x in r['runs']], [0, 120]*4)
        self.assertEqual(sum(x[0] == 'append' for x in e.calls), 1048)
        self.assertEqual(sum(x[0] == 'forward' for x in e.calls), 104)
        mixed = r['correctness_mixed_batches']
        self.assertEqual(mixed['mode'], 'correctness_mixed_batches'); self.assertFalse(mixed['timed'])
        self.assertEqual(mixed['batch_sizes_per_span'], [1,2,3,4,6]); self.assertEqual(mixed['committed_event_batches'], 40)
        self.assertEqual(mixed['head_skip_count_delta'], 88); self.assertEqual(len(mixed['states']), 9)
        self.assertNotIn('commit_loop_ms', mixed)
        self.assertTrue(r['head_instructions_restored']); self.assertFalse(e.enabled)
        self.assertIsNone(r['decode_tok_s']); self.assertIsNone(r['prefill_tok_s'])

    def test_failure_is_partial_with_restoration_and_same_engine_closed(self):
        m, r, rows, e, v, created = self.execute(EngineFailure())
        self.assertFalse(r['complete']); self.assertIn('append failure', r['error'])
        self.assertTrue(r['native_closed']); self.assertFalse(e.enabled); self.assertEqual(created, [1])

    def test_restoration_failure_cannot_become_clean_cleanup(self):
        class Broken(Engine):
            def append_only(obj, token):
                if obj.enabled:
                    obj.restored = False
                    raise RuntimeError('head restoration failed')
                return super().append_only(token)
            def close(obj):
                if not obj.restored: raise RuntimeError('head restoration failed; retain owner')
                return super().close()
        m, r, rows, e, v, created = self.execute(Broken())
        self.assertFalse(r['complete']); self.assertFalse(r['native_cleanup_complete'])
        self.assertFalse(r['native_closed']); self.assertFalse(r['head_instructions_restored'])
        self.assertEqual(r['terminal_head_skip_status']['restored'], False)
        self.assertEqual(created, [1])

    def test_full_rows_compare_to_unchanged_stock_and_one_bit_fails(self):
        m, r, rows, e, v, created = self.execute()
        reference = {g: dict(data=e.row(tuple(v['prompt_ids'][-512:]+v['input']['cases'][0]['teacher_ids'][:g])).data,
                             greedy_id=e.row(tuple(v['prompt_ids'][-512:]+v['input']['cases'][0]['teacher_ids'][:g])).greedy_id,
                             pin={'path':'CPU reference'}) for g in m.ENDPOINTS}
        rows[(3, 48)] = bytes([rows[(3, 48)][0]^1])+rows[(3, 48)][1:]
        with tempfile.TemporaryDirectory() as tmp: result = m.persist_and_compare(r, rows, reference, Path(tmp), row_bytes=32)
        self.assertFalse(result['exact_endpoint_row_parity']); self.assertFalse(result['tolerance_relaxed'])
        self.assertEqual(result['schema'], 'halogen0201.stateful1012-core-append-comparison.v1')

    def test_default_validation_is_native_off_and_no_output(self):
        m = subject('qualify_core_append')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'absent.json'
            with patch('native_backend.NativeBackend', side_effect=AssertionError('No native construction')):
                self.assertEqual(m.main(['--output', str(output)]), 0)
            self.assertFalse(output.exists())


class EngineFailure(Engine):
    def append_only(self, token):
        if self.enabled: raise RuntimeError('append failure')
        return super().append_only(token)


class MonitorTests(unittest.TestCase):
    def test_missing_guard_header_is_rejected_by_preparation_source_closure(self):
        m = subject('run_owned_core_append')
        names = ('actor.py','service.py','request_scoped_backend.py','native_backend.py',
                 'native_backend.cpp','qualify_core_append.py','run_owned_core_append.py')
        prep = dict(schema='halogen0201.stateful1012-core-append-runtime-preparation.v1',
            native_execution_performed=False, policy=m.POLICY, output_directory=str(m.OUT),
            source_pins=[m.pin(HERE/name) for name in names], references=[], runtime_pins=[])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'missing-header.json'; path.write_text(json.dumps(prep), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'source closure'):
                m.validate_preparation(path,m.pin(path)['sha256'],normal_profile=Path(tmp)/'unused.json',
                    wrapper_sha='063bb3f183bfb2d02304942f628950b80e815aa5f9cf4d15db7801304ae625dc')

    def fakes(self, m):
        spec = importlib.util.spec_from_file_location('core_append_owned_CPU_fakes',
            m.PRIMARY/'stateful1012-live-prep/producer/test_owned_qualification.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

    def execute(self, runtime, child, **extra):
        m = subject('run_owned_core_append'); fakes = self.fakes(m)
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.item = {}; self.phases = []; self.spawns = []
        def spawn(command, **kwargs): self.spawns.append((command, kwargs)); return child
        return m.execute_child(runtime, self.item, ['fake.exe','fake.py'], cwd=Path(temp.name), env={},
            log_path=Path(temp.name)/'fake.log', baseline=fakes.BASELINE, save=self.phases.append,
            module_probe=lambda child: ['C:/fixture/native_backend.dll'], spawn=spawn,
            pause=lambda seconds: None, **extra)

    def test_retained_child_closes_when_identity_capture_fails(self):
        m = subject('run_owned_core_append'); fakes = self.fakes(m); child = fakes.Process([None])
        with self.assertRaisesRegex(RuntimeError, 'identity failure'):
            self.execute(fakes.Runtime(identity_failure=True), child)
        self.assertTrue(child.terminated); self.assertEqual(len(self.spawns), 1)
        self.assertEqual(self.phases[-1], 'child_closed')

    def test_runtime_floor_and_deadline_close_only_the_retained_child(self):
        m = subject('run_owned_core_append'); fakes = self.fakes(m)
        for reserve, clock, message in [(17, lambda:0, '18-GiB'),(22, iter([0,121,122]).__next__, '120-second')]:
            child = fakes.Process([None,None])
            with self.assertRaisesRegex(RuntimeError, message): self.execute(fakes.Runtime(reserve=reserve), child, clock=clock)
            self.assertTrue(child.terminated); self.assertEqual(len(self.spawns), 1)

    def test_success_and_double_failure_keep_retained_handle_evidence(self):
        m = subject('run_owned_core_append'); fakes = self.fakes(m); closed = []
        child = fakes.Process([None,0]); child._handle = SimpleNamespace(Close=lambda:closed.append(1))
        self.execute(fakes.Runtime(), child)
        self.assertEqual(closed,[1]); self.assertTrue(self.item['retained_handle_closed'])
        child = fakes.Process([None,None])
        def bad_wait(timeout=None): raise TimeoutError('cleanup wait failure')
        child.wait = bad_wait
        with self.assertRaisesRegex(RuntimeError, '18-GiB'): self.execute(fakes.Runtime(reserve=17), child)
        self.assertIn('18-GiB', self.item['execution_error']['message'])
        self.assertIn('cleanup wait failure', self.item['own_child_cleanup_error']['message'])

    def test_new_schema_modes_counts_and_restoration_are_required(self):
        m = subject('run_owned_core_append')
        report = dict(schema='halogen0201.stateful1012-core-append-qualification.v1', complete=True, error=None,
            native_closed=True, native_cleanup_complete=True, terminal_cancel_completed=True, head_instructions_restored=True,
            native_engine_constructions=1, native_acceptance=None, prefill_tok_s=None, decode_tok_s=None, engine_benefit=None,
            runs=[dict(run_index=i, mode=('head_on','head_skip')[i%2], excluded_warmup=i<2,
                measured_run=None if i<2 else i//2, complete=True, actual_committed_T_count=128,
                committed_event_batches=8, states=[{}]*9, commit_segments=[{}]*8,
                head_skip_count_delta=120 if i%2 else 0, head_instructions_restored=True) for i in range(8)])
        report['correctness_mixed_batches'] = dict(run_index=8, mode='correctness_mixed_batches', timed=False,
            measured_run=None, complete=True, actual_committed_T_count=128, committed_event_batches=40,
            batch_sizes_per_span=[1,2,3,4,6], states=[{}]*9, head_skip_count_delta=88, head_instructions_restored=True)
        comparison = dict(schema='halogen0201.stateful1012-core-append-comparison.v1', exact_endpoint_row_parity=True,
            compared_endpoint_states=81, timed_compared_endpoint_states=72, timed_compared_BF16_values=17861040,
            endpoint_indices=list(range(0,129,16)), tolerance_relaxed=False,
            criterion='original exact BF16 byte equality', compared_BF16_values=20093670,
            runs=[dict(comparisons=[dict(passed=True,exact_BF16_bytes_equal=True,compared_BF16_values=248070)]*9) for i in range(8)])
        comparison['correctness_mixed_batches'] = dict(comparisons=[dict(passed=True,exact_BF16_bytes_equal=True,compared_BF16_values=248070)]*9)
        m.validate_outputs(report, comparison)
        for key, value in [('head_instructions_restored',False),('decode_tok_s',50)]:
            bad = copy.deepcopy(report); bad[key] = value
            with self.assertRaises(RuntimeError): m.validate_outputs(bad, comparison)
        bad = copy.deepcopy(report); bad['runs'][1]['head_skip_count_delta'] = 119
        with self.assertRaises(RuntimeError): m.validate_outputs(bad, comparison)
        self.assertEqual(m.POLICY['entry_reserve_gib'],22); self.assertEqual(m.POLICY['runtime_reserve_gib'],18)
        self.assertEqual(m.POLICY['automatic_retries'],0)


if __name__ == '__main__': unittest.main()
