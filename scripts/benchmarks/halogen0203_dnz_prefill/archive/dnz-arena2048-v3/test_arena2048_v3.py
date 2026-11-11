"""Focused private CPU fakes. No hardware or lifecycle implementation is called."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE=Path(__file__).resolve().parent


def load(test,name):
    path=HERE/(name+'.py')
    test.assertTrue(path.exists(),name+' source is not implemented')
    spec=importlib.util.spec_from_file_location('arena2048_test_'+name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module


def frame(physical=31,commit=150,**extra):
    return dict(available_bytes=int(physical*2**30),commit_headroom_bytes=int(commit*2**30),
                committed_bytes=123,commit_limit_bytes=456,**extra)


class Clock:
    def __init__(self):self.value=0
    def __call__(self):return self.value
    def sleep(self,delay):self.value+=delay


class ProfileTests(unittest.TestCase):
    def setUp(self):self.p=load(self,'prepare_source')

    def test_only_DNZ_differs_and_both_arena_controls2048_keep_context8192(self):
        normal=self.p.read(self.p.NORMAL);untouched=copy.deepcopy(normal)
        profiles=self.p.profiles(normal);reference=None
        for arm,mode in (('before',0),('candidate',1),('after',0)):
            p=copy.deepcopy(profiles[arm]);engine=p['engine']
            self.assertEqual((engine['context'],engine['prefill_chunk'],engine['max_prefill_tokens']),
                             (8192,2048,2048))
            self.assertEqual(p['backend']['context'],8192)
            self.assertEqual(p['backend']['expected']['context'],8192)
            self.assertEqual(p['backend']['expected']['kv_pool_positions'],8192)
            self.assertNotIn('slots',engine);self.assertNotIn('kv_pool_positions',engine)
            self.assertEqual(engine['kernel_controls'].pop('HALOGEN_DN_Z_STREAM'),mode)
            if reference is None:reference=p
            self.assertEqual(p,reference)
        self.assertEqual(normal,untouched)
        self.assertEqual(normal['engine']['max_prefill_tokens'],8192)

    def test_case_is_unchanged2048_plus128_and_cannot_chain8k(self):
        case=self.p.request_case(2048)
        self.assertEqual(case['request']['sha256'],
                         'd7ae756957ef499de88880aba9c6c89da076cad6bcad70d120c54431c7bc071b')
        self.assertEqual((case['actual_input_tokens'],case['actual_output_tokens'],case['capacity_context']),
                         (2048,128,8192))
        with self.assertRaises(ValueError):self.p.request_case(8192)

    def test_closure_includes_new_sources_local_design_and_both_prospective_plans(self):
        paths={str(p.resolve()) for p in self.p.dependencies()}
        for p in [HERE/name for name in ('prepare_source.py','campaign.py','counter_reader.py',
                                         'measure_helpers.py','restore_margin.py','DESIGN-PLAN.md')]:
            self.assertIn(str(p.resolve()),paths)
        for ext in ('md','json'):
            self.assertIn(str((self.p.ROOT/'docs/benchmarks'/
                ('halogen0203-dnz-prefill-plan-20261111-v3.'+ext)).resolve()),paths)

    def test_collector_bytes_are_reviewed_v2_and_only_helper_is_new(self):
        sources=self.p.collector_sources()
        self.assertEqual(sources['measure_helpers.py'],(HERE/'measure_helpers.py').read_bytes())
        for name,data in sources.items():
            if name!='measure_helpers.py':self.assertEqual(data,(self.p.V2/name).read_bytes())


class FailureCaptureTests(unittest.TestCase):
    def setUp(self):self.m=load(self,'measure_helpers')

    def test_passing22_and_runtime18_do_not_write_or_requery_a_frame(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            self.m.configure_failure_capture(Path(temporary))
            actual=frame(22,22,sequence=7);calls=[]
            runtime=types.SimpleNamespace(ops=types.SimpleNamespace(host=types.SimpleNamespace(
                frame=lambda:calls.append('frame') or actual)))
            self.assertIs(self.m.check_reserve(runtime,22),actual)
            self.assertEqual(calls,['frame']);self.assertEqual(list(Path(temporary).iterdir()),[])
            actual['available_bytes']=17*2**30
            with self.assertRaises(ValueError):self.m.check_reserve(runtime,18)
            self.assertEqual(list(Path(temporary).iterdir()),[])

    def test_failed_admission_saves_exact_first_frame_and_never_overwrites(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            self.m.configure_failure_capture(Path(temporary))
            actual=frame(21.5,145,sequence=8,opaque_detail='retained');calls=[]
            runtime=types.SimpleNamespace(ops=types.SimpleNamespace(host=types.SimpleNamespace(
                frame=lambda:calls.append('frame') or actual)))
            for _ in range(2):
                with self.assertRaisesRegex(ValueError,'22-GiB memory reserve unavailable'):
                    self.m.check_reserve(runtime,22)
            paths=sorted(Path(temporary).glob('memory-admission-failure-*.json'))
            self.assertEqual(len(paths),2);self.assertEqual(len(calls),2)
            for path in paths:
                saved=json.loads(path.read_bytes())
                self.assertEqual(saved['frame'],actual)
                self.assertEqual((saved['physical_floor_gib'],saved['commit_floor_gib']),(22,22))
                self.assertTrue(saved['outside_timed_HTTP_RAW'])

    def test_initial22_failure_can_create_only_failure_evidence_before_output_mkdir(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            output=Path(temporary)/'fresh-run';self.m.configure_failure_capture(output)
            actual=frame(21.99,145,sequence=9);calls=[]
            runtime=types.SimpleNamespace(ops=types.SimpleNamespace(host=types.SimpleNamespace(
                frame=lambda:calls.append('one frame only') or actual)))
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError,'22-GiB'):
                self.m.check_reserve(runtime,22)
            self.assertEqual(calls,['one frame only'])
            self.assertEqual([p.name for p in output.iterdir()],['memory-admission-failure-0000.json'])
            self.assertEqual(json.loads(next(output.iterdir()).read_bytes())['frame'],actual)

    def test_collector_uses_its_exact_private_helper_despite_foreign_cached_module(self):
        prep=load(self,'prepare_source')
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            target=Path(temporary)
            for name,data in prep.collector_sources().items():
                path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            foreign=types.SimpleNamespace(require=lambda *args:(_ for _ in ()).throw(AssertionError('foreign helper')))
            previous=sys.modules.get('measure_helpers');sys.modules['measure_helpers']=foreign
            try:
                spec=importlib.util.spec_from_file_location('dnz_v3_fake_isolated_collector',
                                                          target/'raw/collector/collect_epoch.py')
                collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
                self.assertEqual(Path(collector.m.__file__).resolve(),(target/'measure_helpers.py').resolve())
                self.assertIsNot(collector.m,foreign)
                self.assertTrue(callable(collector.m.configure_failure_capture))
            finally:
                if previous is None:sys.modules.pop('measure_helpers',None)
                else:sys.modules['measure_helpers']=previous


class RestoreMarginTests(unittest.TestCase):
    def setUp(self):self.m=load(self,'restore_margin')

    def wait(self,get_frame,clock=None):
        clock=clock or Clock();failures=[]
        runtime=types.SimpleNamespace(ops=types.SimpleNamespace(host=types.SimpleNamespace(frame=get_frame)))
        result=self.m.wait_for_normal(runtime,record_failure=lambda *a,**kw:failures.append((a,kw)),
                                      clock=clock,sleep=clock.sleep)
        return result,failures,clock

    def test_real_frames30_25_and131_stable10_with_no_passing_file_write(self):
        calls=[];actual=frame(30.25,131)
        result,failures,clock=self.wait(lambda:calls.append('sample') or actual)
        self.assertGreaterEqual(clock.value,10);self.assertGreaterEqual(len(calls),41)
        self.assertEqual(failures,[])
        self.assertEqual(result['required_physical_gib'],30.25)
        self.assertEqual(result['required_commit_gib'],131)
        self.assertEqual(result['runtime_physical_commit_gib'],18)
        self.assertGreaterEqual(result['stable_seconds_observed'],10)

    def test_margin_dip_resets_stability_and_commit_floor_is_not_lowered(self):
        clock=Clock()
        def get():return frame(30.3,130 if clock.value==4 else 140)
        result,failures,clock=self.wait(get,clock)
        self.assertGreaterEqual(clock.value,14.25);self.assertEqual(failures,[])
        self.assertGreaterEqual(result['stable_started_monotonic'],4.25)

    def test_timeout300_records_exact_last_frame_without_launching(self):
        clock=Clock();actual=frame(30.24,150,marker='exact');failures=[]
        runtime=types.SimpleNamespace(ops=types.SimpleNamespace(host=types.SimpleNamespace(frame=lambda:actual)))
        with self.assertRaisesRegex(ValueError,'300-second'):
            self.m.wait_for_normal(runtime,record_failure=lambda *a,**kw:failures.append((a,kw)),
                                   clock=clock,sleep=clock.sleep)
        self.assertEqual(clock.value,300);self.assertEqual(len(failures),1)
        self.assertEqual(failures[0][0][0],actual)
        self.assertEqual(failures[0][1]['physical_floor_gib'],30.25)

    def test_qualifying_frame_after300_fails_instead_of_extending_deadline(self):
        clock=Clock();failures=[];steps=iter((290,301))
        def sleep(delay):clock.value=next(steps)
        actual=frame(31,150,marker='late qualifying frame')
        def get():return frame(30,150) if clock.value==0 else actual
        runtime=types.SimpleNamespace(ops=types.SimpleNamespace(host=types.SimpleNamespace(frame=get)))
        with self.assertRaisesRegex(ValueError,'300-second'):
            self.m.wait_for_normal(runtime,record_failure=lambda *a,**kw:failures.append((a,kw)),
                                   clock=clock,sleep=sleep)
        self.assertEqual(len(failures),1)
        self.assertEqual(failures[0][0][0],actual)
        self.assertEqual(failures[0][1]['observed_monotonic'],301)

    def test_valid_stable_window_can_finish_exactly_at300(self):
        clock=Clock();steps=iter((290,300));failures=[]
        def sleep(delay):clock.value=next(steps)
        def get():return frame(30 if clock.value==0 else 31,150)
        runtime=types.SimpleNamespace(ops=types.SimpleNamespace(host=types.SimpleNamespace(frame=get)))
        result=self.m.wait_for_normal(runtime,record_failure=lambda *a,**kw:failures.append((a,kw)),
                                      clock=clock,sleep=sleep)
        self.assertEqual(failures,[])
        self.assertEqual(result['finished_monotonic'],300)
        self.assertEqual(result['stable_seconds_observed'],10)

    def test_frame_read_time_counts_toward300_deadline(self):
        clock=Clock();steps=iter((290,299));calls=[];failures=[]
        def sleep(delay):
            try:clock.value=next(steps)
            except StopIteration:clock.value+=delay
        actual=frame(31,150,marker='host read crossed deadline')
        def get():
            calls.append(clock.value)
            if clock.value==0:return frame(30,150)
            if clock.value==299:clock.value=301
            return actual
        runtime=types.SimpleNamespace(ops=types.SimpleNamespace(host=types.SimpleNamespace(frame=get)))
        with self.assertRaisesRegex(ValueError,'300-second'):
            self.m.wait_for_normal(runtime,record_failure=lambda *a,**kw:failures.append((a,kw)),
                                   clock=clock,sleep=sleep)
        self.assertEqual(calls,[0,290,299])
        self.assertEqual(len(failures),1)
        self.assertEqual(failures[0][0][0],actual)
        self.assertEqual(failures[0][1]['observed_monotonic'],301)

    def test_runtime_reserve18_failure_stops_margin_without_waiting(self):
        clock=Clock();actual=frame(17.9,150);failures=[]
        runtime=types.SimpleNamespace(ops=types.SimpleNamespace(host=types.SimpleNamespace(frame=lambda:actual)))
        with self.assertRaisesRegex(ValueError,'18-GiB'):
            self.m.wait_for_normal(runtime,record_failure=lambda *a,**kw:failures.append((a,kw)),
                                   clock=clock,sleep=clock.sleep)
        self.assertEqual(clock.value,0);self.assertEqual(len(failures),1)


class CampaignTests(unittest.TestCase):
    def setUp(self):self.m=load(self,'campaign')

    def manifest(self):
        return dict(environment=dict(HALOGEN_DN_Z_STREAM='1',HGN0203_RAW_ENABLE='1',HGN0203_API_NATIVE_ID='1',
            HALOGEN_CTX='8192',HALOGEN_KV_POOL_POSITIONS='8192',HALOGEN_MAX_TOK='2048',
            HALOGEN_PREFILL_CHUNK='2048',HALOGEN_PROMPT_CACHE='0'),mounts=[])

    def test_native_capacity_and_working_arena_are_checked_separately(self):
        self.m.check_native_manifest(self.manifest(),1)
        for key in ('HALOGEN_CTX','HALOGEN_KV_POOL_POSITIONS','HALOGEN_MAX_TOK','HALOGEN_PREFILL_CHUNK'):
            bad=self.manifest();bad['environment'][key]='2048' if 'CTX' in key or 'KV_POOL' in key else '8192'
            with self.assertRaises(ValueError):self.m.check_native_manifest(bad,1)

    def test_normal_launch_waits_once_and_does_not_retry_observation_timeout(self):
        calls=[];runtime=object()
        def wait(rt,**kwargs):calls.append('margin');return dict(passed=True)
        def launch():calls.append('launch');raise TimeoutError('live launch observation')
        with self.assertRaises(TimeoutError):
            self.m.launch_normal_after_margin(runtime,launch,lambda x:calls.append('publish margin'),
                                               lambda *a,**kw:None,wait=wait)
        self.assertEqual(calls,['margin','publish margin','launch'])

    def test_failed_margin_never_starts_normal(self):
        calls=[]
        def fail(*args,**kwargs):raise ValueError('margin failed')
        with self.assertRaises(ValueError):
            self.m.launch_normal_after_margin(object(),lambda:calls.append('launch'),lambda x:None,
                                               lambda *a,**kw:None,wait=fail)
        self.assertEqual(calls,[])

    def test_partial_startup_failure_rolls_back_then_waits_before_one_normal_launch(self):
        calls=[]
        def wait(*args,**kwargs):calls.append('real-frame margin');return dict(passed=True)
        result=self.m.restore_online(active=None,baseline={},overlay_attempted=True,
            current=dict(phase='failed',run_id='captured-failed-owner'),
            stop=lambda *args:calls.append('unexpected stop'),rollback=lambda:calls.append('rollback'),
            launch=lambda:self.m.launch_normal_after_margin(object(),
                lambda:calls.append('one normal launch') or dict(ready=True),
                lambda value:calls.append('retain margin'),lambda *args,**kwargs:None,wait=wait),
            verify=lambda:None)
        self.assertEqual(result,dict(ready=True))
        self.assertEqual(calls,['rollback','real-frame margin','retain margin','one normal launch'])


if __name__=='__main__':unittest.main()
