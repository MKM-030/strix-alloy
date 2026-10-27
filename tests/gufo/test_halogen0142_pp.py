"""Offline tests for the bounded Halogen cold HTTP prefill adapter."""
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2]/'experimental/halogen0142_pp/runner.py'


class ColdPPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('halogen0142_pp_runner',SOURCE)
        cls.r=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.r)

    def test_schedule_is_one_warmup_two_calibrations_and_counterbalanced_six(self):
        rows=self.r.schedule()
        self.assertEqual([(x['kind'],x.get('target')) for x in rows],
            [('warmup',None),('calibration',None),('calibration',None),
             ('measurement',2048),('measurement',8192),('measurement',8192),
             ('measurement',2048),('measurement',2048),('measurement',8192)])
        self.assertEqual(len(rows),9)

    def test_pp_import_does_not_load_historical_gufo_controllers(self):
        script=('import experimental.halogen0142_pp.runner,sys; '
                'print(any(name in sys.modules for name in '
                '("scripts.gufo_control.reddit_native_run",'
                '"scripts.gufo_control.smoke_guard")))')
        done=subprocess.run([sys.executable,'-c',script],cwd=SOURCE.parents[2],
                            capture_output=True,text=True,check=True)
        self.assertEqual(done.stdout.strip(),'False')

    def test_pp_local_transport_and_calibration_match_pinned_sources(self):
        from scripts.gufo_control import benchmark_recipes as old_recipes
        from scripts.gufo_control import reddit_halogen_client as old_client
        r=self.r
        self.assertEqual(r.recipes.FILLER,old_recipes.FILLER)
        for counts in ((2048,10,100),(8192,1,200),(2048,100,400)):
            self.assertEqual(r.recipes.calibrated_prompt(*counts),
                             old_recipes.calibrated_prompt(*counts))
        for value in ({'text':'ü','n':3},[1,2,3]):
            self.assertEqual(r.client.packed(value),old_client.packed(value))
        for raw in (b'{"a":1}',b'{"a":1,"a":2}'):
            try: expected=old_client.strict_json(raw)
            except ValueError:
                with self.assertRaises(ValueError): r.client.strict_json(raw)
            else: self.assertEqual(r.client.strict_json(raw),expected)
        with self.assertRaises(ValueError): r.client.packed({'x':math.nan})
        self.assertEqual(r.client.RESPONSE_LIMIT,old_client.RESPONSE_LIMIT)

    def test_pp_local_transport_binds_loopback_and_response_limit(self):
        transport=self.r.client
        seen=[]
        class Socket:
            def settimeout(self,seconds): seen.append(('timeout',seconds))
        class Response:
            fp=None
            status=200
            def isclosed(self): return False
            def read1(self,limit):
                seen.append(('read_limit',limit))
                return b'x'*(transport.RESPONSE_LIMIT+1)
            def getheaders(self): return []
        class Connection:
            def __init__(self,host,port,timeout):
                self.sock=Socket(); seen.append(('connect',host,port,timeout))
            def request(self,method,path,body,headers):
                seen.append(('request',method,path,body,headers))
            def getresponse(self): return Response()
            def close(self): seen.append(('closed',))
        with patch.object(transport.http.client,'HTTPConnection',Connection):
            with self.assertRaisesRegex(ValueError,'response_body_limit'):
                transport.exchange('POST','/v1/chat/completions',b'{}',timeout=3)
        self.assertIn(('connect','127.0.0.1',8731,3),seen)
        self.assertIn(('request','POST','/v1/chat/completions',b'{}',
                       {'Content-Type':'application/json'}),seen)
        self.assertIn(('read_limit',65536),seen)
        self.assertEqual(seen[-1],('closed',))

    def test_profile_is_16k_one_slot_cache_off_serial_and_bounded(self):
        r=self.r
        m={'stage':'smoke','timeout_seconds':600,'artifacts':{
            'bridge':{'container_path':'/candidate/bridge'},
            'private':{'container_path':'/candidate/private'}}}
        env=r.environment(m)
        self.assertEqual(env['HALOGEN_CTX'],'16384')
        self.assertEqual(env['HALOGEN_KV_POOL_POSITIONS'],'16384')
        self.assertEqual(env['HALOGEN_KV_SLOTS'],'1')
        self.assertEqual(env['HALOGEN_PREFILL_CHUNK'],'2048')
        self.assertEqual(env['HALOGEN_PROMPT_CACHE'],'0')
        self.assertEqual(env['HALOGEN_MAX_TOK'],'2048')
        self.assertEqual(r.request('qwen38-flash-next-w4b','x')['max_tokens'],1)
        for key,value in {'temperature':0,'enable_thinking':False,
                          'drafter':'serial','reasoning_effort':'none','stream':False}.items():
            self.assertEqual(r.request('qwen38-flash-next-w4b','x')[key],value)

    def test_real_manifest_emits_one_exact_16k_environment_and_600s_deadline(self):
        r=self.r
        research = Path(__file__).resolve().parents[2].parent / 'strix-alloy-research'
        if not (research/'artifacts/halogen0142/smoke-manifest.json').is_file():
            self.skipTest('Historical 0.14.2 sibling smoke manifest required')
        self.enterContext(patch.object(r.base, 'ARTIFACT_ROOT', research/'artifacts/halogen0142'))
        m=r.base.read_json(r.base.ARTIFACT_ROOT/'smoke-manifest.json')
        sealed=r.offline(m)
        argv=sealed['docker_argv']
        entries=[argv[index+1] for index,item in enumerate(argv[:-1]) if item=='-e']
        names=[entry.split('=',1)[0] for entry in entries]
        self.assertEqual(len(names),len(set(names)))
        self.assertIn('HALOGEN_CTX=16384',entries)
        self.assertIn('HALOGEN_PROMPT_CACHE=0',entries)
        self.assertEqual(argv[argv.index('--kill-after=5')+1],'600')
        self.assertEqual(len(sealed['seal_sha256']),64)
        self.assertEqual(sealed['transport_contract'],{
            'timeout_semantics':'per-io-socket-timeout',
            'request_timeout_seconds':60,
            'completed_wall_max_seconds':60,
            'response_max_bytes':1048576,
            'container_timeout_seconds':600,
            'container_kill_after_seconds':5})

    def test_created_container_effective_environment_requires_reviewed_16k(self):
        r=self.r
        research = Path(__file__).resolve().parents[2].parent / 'strix-alloy-research'
        if not (research/'artifacts/halogen0142/smoke-manifest.json').is_file():
            self.skipTest('Historical 0.14.2 sibling smoke manifest required')
        self.enterContext(patch.object(r.base, 'ARTIFACT_ROOT', research/'artifacts/halogen0142'))
        m=r.base.read_json(r.base.ARTIFACT_ROOT/'smoke-manifest.json')
        expected=[key+'='+value for key,value in r.environment(m).items()]
        r.check_effective_environment({'Config':{'Env':expected}},m)
        altered=[entry.replace('HALOGEN_CTX=16384','HALOGEN_CTX=4096') for entry in expected]
        with self.assertRaises(ValueError):
            r.check_effective_environment({'Config':{'Env':altered}},m)

    def test_cold_counts_and_timing_use_actual_counters(self):
        r=self.r
        parsed={'usage':{'prompt_tokens':2048,'completion_tokens':1,
                         'prompt_tokens_details':{'cached_tokens':0}},
                'timings':{'prompt_n':2048,'cache_n':0,'predicted_n':1,
                           'prompt_ms':2000,'predicted_ms':50}}
        measured=r.assess(parsed,2048,2.0)
        self.assertEqual(measured['http_pp_tps'],1024)
        self.assertEqual(measured['engine_pp_tps'],1024)
        self.assertEqual(measured['engine_over_http_ms'],50)
        self.assertTrue(measured['engine_time_exceeds_http'])
        with self.assertRaises(ValueError): r.assess(parsed,2048,60.001)
        for change in ({'timings':{'prompt_n':2081}},
                       {'timings':{'cache_n':1}},
                       {'usage':{'completion_tokens':2}}):
            bad=json.loads(json.dumps(parsed))
            bad.update({key:{**bad[key],**value} for key,value in change.items()})
            with self.assertRaises(ValueError): r.assess(bad,2048,2.0)

    def test_actual_cold_response_can_omit_optional_cache_details(self):
        parsed={'usage':{'prompt_tokens':2048,'completion_tokens':1},
                'timings':{'prompt_n':2048,'cache_n':0,'predicted_n':1,
                           'prompt_ms':2000,'predicted_ms':50}}
        self.assertEqual(self.r.assess(parsed,2048,2.0)['cached_prompt_tokens'],0)
        parsed['usage']['prompt_tokens_details']={'cached_tokens':1}
        with self.assertRaises(ValueError): self.r.assess(parsed,2048,2.0)

    def test_nonfinite_cold_timing_is_rejected(self):
        parsed={'usage':{'prompt_tokens':2048,'completion_tokens':1},
                'timings':{'prompt_n':2048,'cache_n':0,'predicted_n':1,
                           'prompt_ms':2000,'predicted_ms':50}}
        for field in ('prompt_ms','predicted_ms'):
            for bad in (math.nan,math.inf,-math.inf):
                changed=json.loads(json.dumps(parsed))
                changed['timings'][field]=bad
                with self.assertRaises(ValueError): self.r.assess(changed,2048,2.0)
        for bad in (math.nan,math.inf,-math.inf):
            with self.assertRaises(ValueError): self.r.assess(parsed,2048,bad)

    def test_admission_45_117_does_not_weaken_runtime_guard(self):
        r=self.r
        frame={'available_bytes':45*r.base.GIB,'commit_headroom_bytes':117*r.base.GIB}
        r.check_pp_frame(frame)
        for key in frame:
            with self.assertRaises(ValueError): r.check_pp_frame({**frame,key:frame[key]-1})
        with self.assertRaises(ValueError):
            r.check_pp_frame({**frame,'commit_headroom_bytes':116*r.base.GIB})
        r.base.check_frame({'available_bytes':12*r.base.GIB,
                            'commit_headroom_bytes':12*r.base.GIB})

    def test_run_requires_reviewed_base_smoke_success(self):
        r=self.r
        with tempfile.TemporaryDirectory() as directory:
            m={'stage':'smoke','artifacts':{}}
            with self.assertRaises(ValueError): r.require_base_smoke({},m)
            with self.assertRaises(ValueError): r.require_base_smoke(
                {'base_smoke_success_path':str(Path(directory)/'missing.json'),
                 'base_smoke_success_sha256':'a'*64},m)

    def test_warmup_wrong_answer_fails_with_raw_http_retained(self):
        r=self.r
        with tempfile.TemporaryDirectory() as directory:
            attempt=Path(directory)
            response={'choices':[{'message':{'content':'wrong'},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':10,'completion_tokens':1,
                         'prompt_tokens_details':{'cached_tokens':0}},
                'timings':{'prompt_n':10,'cache_n':0,'predicted_n':1,
                           'prompt_ms':10,'predicted_ms':2}}
            raw=json.dumps(response).encode()
            with patch.object(r.base,'guard_alive'), patch.object(r.client,'exchange',
                 return_value=(200,{},raw,1.0,1.1)):
                with self.assertRaises(ValueError):
                    r.execute_rows(attempt,'a'*64,object(),{'model':'qwen38-flash-next-w4b'},
                                   r.time.monotonic()+60)
            self.assertTrue((attempt/'http-00.json').exists())
            self.assertFalse((attempt/'http-01.json').exists(),
                             'wrong warmup must fail before calibration')

    def test_one_token_warmup_accepts_length_when_answer_is_four(self):
        r=self.r
        with tempfile.TemporaryDirectory() as directory:
            attempt=Path(directory)
            response={'choices':[{'message':{'content':'4'},'finish_reason':'length'}],
                'usage':{'prompt_tokens':10,'completion_tokens':1},
                'timings':{'prompt_n':10,'cache_n':0,'predicted_n':1,
                           'prompt_ms':10,'predicted_ms':2}}
            raw=json.dumps(response).encode()
            with patch.object(r.base,'guard_alive'), patch.object(r.client,'exchange',
                 return_value=(200,{},raw,1.0,1.1)):
                with self.assertRaisesRegex(ValueError,'invalid_calibration_counts'):
                    r.execute_rows(attempt,'a'*64,object(),{'model':'qwen38-flash-next-w4b'},
                                   r.time.monotonic()+60)
            self.assertTrue((attempt/'parsed-00.json').exists(),
                            'one-token length warmup must proceed to calibration')

    def test_nine_http_rows_keep_raw_counts_and_counterbalanced_cells(self):
        r=self.r
        with tempfile.TemporaryDirectory() as directory:
            attempt=Path(directory)
            counts=[10,1,101,2048,8192,8192,2048,2048,8192]
            seen=[]
            def exchange(method,path,wire,timeout):
                index=len(seen); seen.append((method,path,json.loads(wire),timeout))
                n=counts[index]
                response={'choices':[{'message':{'content':'4'},'finish_reason':'stop'}],
                    'usage':{'prompt_tokens':n,'completion_tokens':1,
                             'prompt_tokens_details':{'cached_tokens':0}},
                    'timings':{'prompt_n':n,'cache_n':0,'predicted_n':1,
                               'prompt_ms':1000,'predicted_ms':1}}
                return 200,{'content-type':'application/json'},json.dumps(response).encode(),1,2
            with patch.object(r.base,'guard_alive'), patch.object(r.client,'exchange',
                 side_effect=exchange):
                cells=r.execute_rows(attempt,'a'*64,object(),
                                    {'model':'qwen38-flash-next-w4b'},r.time.monotonic()+600)
            self.assertEqual([cell['target'] for cell in cells],
                             [2048,8192,8192,2048,2048,8192])
            self.assertEqual(len(seen),9)
            self.assertTrue(all(item[3]<=60 for item in seen))
            self.assertTrue(all(item[2]['max_tokens']==1 and item[2]['drafter']=='serial'
                                for item in seen))
            self.assertEqual(len(list(attempt.glob('http-*.json'))),9)
            self.assertEqual(cells[0]['metrics']['fresh_prompt_tokens'],2048)
            self.assertEqual(cells[0]['metrics']['cached_prompt_tokens'],0)


if __name__=='__main__': unittest.main()
