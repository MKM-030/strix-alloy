import importlib
import importlib.util
import json
from hashlib import sha256
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('gufo_control.benchmark_suite'))
        self.s = importlib.import_module('gufo_control.benchmark_suite')
        self.calls = []
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def exchange(self, method, path, *args, **kwargs):
        now = time.monotonic()
        payload = {'status':'ready','model':'gufo-flash-next'} if path=='/ready' else {'data':[{'id':'gufo-flash-next'}]}
        return 200, {}, json.dumps(payload).encode(), now, now, []

    def observation(self, **kwargs):
        self.calls.append(kwargs)
        req = kwargs['request']; prompt = req['messages'][0]['content']
        tokens = 10 + prompt.count(self.s.recipes.FILLER)*20
        case = next((k for k,v in self.s.recipes.FIXTURES.items() if v['prompt']==prompt), None)
        answer = {'DE':'{"sprache":"de","hoechste_prioritaet":"B","begruendung":"Alle Nutzer sind betroffen."}',
                  'CODE':'def clamp(x, lo, hi):\n if lo > hi: raise ValueError\n return min(hi, max(lo, x))',
                  'TOOL':'','EN':'Transport succeeded. Schema failed; inspect the response.','LONG':'1. Inspect timing.'}.get(case, '4')
        tool = [dict(id='a',type='function',function=dict(name='lookup_ticket',arguments='{"ticket_id":"INC-2047"}'))] if case=='TOOL' else []
        cached = tokens-1 if req['cache_prompt'] else 0
        return dict(success=True,error=None,post_attempted=True,request=req,visible_answer=answer,
                    tool_calls=tool,finish_reason='tool_calls' if tool else 'stop',
                    metrics=dict(logical_prompt_tokens=tokens,new_prefill_tokens=tokens-cached,cached_prompt_tokens=cached,
                                 completion_tokens=1,http_duration_ms=10.,engine_pp_tokens_per_second=100.,engine_tg_tokens_per_second=None,
                                 http_pp_tokens_per_second=tokens*100. if req['max_tokens']==1 else None),
                    usage={'gufo':{'cache_hit':bool(cached)}},raw_response_base64='U0VDUkVU',body_parts=[],validation_errors=[],unavailable_metrics=[])

    def run_suite(self, profile=None, observation=None, cancel=None):
        with patch.object(self.s.smoke_http,'_exchange',self.exchange), patch.object(self.s.benchmark_http,'request_once',observation or self.observation):
            task = self.s.start_suite(profile_id=profile or self.s.recipes.PROFILE_4K,evidence_dir=self.root,
                api_key='SECRET',startup_deadline=time.monotonic()+30,lifetime_deadline=time.monotonic()+60,cancel=cancel)
            self.assertTrue(task.done.wait(5))
            return task.result

    def test_full_4k_bounded_artifacts_and_summary(self):
        result = self.run_suite()
        self.assertTrue(result['success'],result)
        self.assertEqual(len(self.calls),36)
        self.assertEqual(result['counts'],dict(valid=36,failed=0,not_run=0))
        self.assertEqual(result['semantic_status'],'semantic_review_pending')
        self.assertEqual(sha256(self.s.recipes.canonical(result['recipe']).encode()).hexdigest().upper(),result['recipe_sha256'])
        self.assertLess(len(json.dumps(result)),2*1024*1024)
        for i,row in enumerate(result['rows']):
            artifact = row['artifact']; raw=(self.root/artifact['name']).read_bytes()
            self.assertEqual(artifact,dict(name=f'request-{i:03d}.json',size_bytes=len(raw),sha256=sha256(raw).hexdigest().upper()))
            self.assertNotIn('raw_response_base64',row)
            self.assertEqual(json.loads(raw)['raw_response_base64'],'U0VDUkVU')
        self.assertEqual(result['common_window_decode_reason'],'native_window_counters_unavailable')
        self.assertTrue(any(g['metrics']['engine_pp_tokens_per_second']['sample_sd']==0 for g in result['groups']))

    def test_16k_order_cache_actual_labels_nonstream_pp(self):
        result=self.run_suite(self.s.recipes.PROFILE_16K)
        self.assertTrue(result['success'],result)
        self.assertEqual(len(self.calls),13)
        self.assertTrue(all(not c['request']['stream'] for c in self.calls[1:9]))
        self.assertEqual([x['cache_observation'] for x in result['rows'][9:]], ['miss','hit','hit','hit'])
        self.assertEqual(len({c['request']['messages'][0]['content'] for c in self.calls[9:]}),1)

    def test_failure_aborts_and_keeps_all_ordinals(self):
        def fail(**kwargs):
            value=self.observation(**kwargs)
            if len(self.calls)==5: value.update(success=False,error='counter_disagrees')
            return value
        result=self.run_suite(observation=fail)
        self.assertFalse(result['success']); self.assertEqual(len(self.calls),5)
        self.assertEqual(result['counts'],dict(valid=4,failed=1,not_run=31))
        self.assertEqual(result['rows'][4]['status'],'failed')
        self.assertTrue(all('artifact' not in row for row in result['rows'][5:]))

    def test_calibration_miss_and_context_overflow_abort(self):
        for kind in ['calibration','context']:
            self.calls=[]
            for p in self.root.iterdir(): p.unlink()
            def bad(**kwargs):
                v=self.observation(**kwargs)
                if len(self.calls)==(34 if kind=='calibration' else 1):
                    v['metrics']['logical_prompt_tokens']=4000
                    v['metrics']['new_prefill_tokens']=4000
                return v
            result=self.run_suite(observation=bad)
            self.assertFalse(result['success']); self.assertEqual(len(self.calls),34 if kind=='calibration' else 1)

    def test_write_failure_keeps_observed_failure_without_fabricated_artifact(self):
        with patch.object(self.s.operator_store,'atomic_json',side_effect=OSError('disk')):
            result=self.run_suite()
        self.assertFalse(result['success']); self.assertEqual(len(self.calls),1)
        self.assertEqual(result['rows'][0]['status'],'failed')
        self.assertTrue(result['rows'][0]['attempted'])
        self.assertEqual(result['rows'][0]['evidence_write_error'],'OSError')
        self.assertEqual(result['counts'],dict(valid=0,failed=1,not_run=35))
        self.assertEqual(result['error'],'evidence_write_failed')
        self.assertNotIn('artifact',result['rows'][0])

    def test_cancel_and_expired_deadline_publish_result_without_post(self):
        cancel=threading.Event(); cancel.set()
        result=self.run_suite(cancel=cancel)
        self.assertEqual(result['error'],'cancelled'); self.assertEqual(self.calls,[])
        task=self.s.start_suite(profile_id=self.s.recipes.PROFILE_4K,evidence_dir=self.root,api_key='SECRET',startup_deadline=0,lifetime_deadline=0)
        self.assertTrue(task.done.wait(2)); self.assertFalse(task.result['success'])

    def test_readiness_overload_and_poll_limit(self):
        def exchange(*a,**k): return 503,{},b'{"error":{"code":"overloaded"}}',0,0,[]
        with patch.object(self.s.smoke_http,'_exchange',exchange):
            with self.assertRaisesRegex(self.s.smoke_http.SmokeError,'ready_http_503'):
                self.s._ready('SECRET',time.monotonic()+5,threading.Event(),{})
        class Cancel:
            def is_set(self): return False
            def wait(self,t): pass
        def refused(*a,**k): raise self.s.smoke_http.SmokeError('transport_ConnectionRefusedError')
        with patch.object(self.s.smoke_http,'_exchange',side_effect=refused) as get:
            with self.assertRaisesRegex(self.s.smoke_http.SmokeError,'ready_poll_limit'):
                self.s._ready('SECRET',time.monotonic()+5,Cancel(),{})
            self.assertEqual(get.call_count,240)

    def test_ready_retry_models_identity_and_no_post_retry(self):
        sequence=[(503,{},b'{"error":{"code":"not_ready"}}',0,0,[]),self.exchange('GET','/ready'),self.exchange('GET','/v1/models')]
        class Cancel:
            def is_set(self): return False
            def wait(self,t): pass
        metadata={}
        with patch.object(self.s.smoke_http,'_exchange',side_effect=sequence) as get:
            self.s._ready('SECRET',time.monotonic()+5,Cancel(),metadata)
        self.assertEqual(metadata['ready_polls'],2)
        self.assertEqual([c.args[1] for c in get.call_args_list],['/ready','/ready','/v1/models'])
        for response in [(302,{},b'{}',0,0,[]),(200,{},b'{"status":"ready","model":"other"}',0,0,[])]:
            with patch.object(self.s.smoke_http,'_exchange',return_value=response),self.assertRaises(self.s.smoke_http.SmokeError):
                self.s._ready('SECRET',time.monotonic()+5,Cancel(),{})

    def test_calibration_nonincrease_and_cancel_mid_schedule(self):
        for variant in ['calibration','cancel']:
            self.calls=[]
            for p in self.root.iterdir(): p.unlink()
            cancel=threading.Event()
            def observe(**kwargs):
                value=self.observation(**kwargs)
                if variant=='calibration' and len(self.calls)==33: value['metrics']['logical_prompt_tokens']=10
                if variant=='cancel' and len(self.calls)==2: cancel.set()
                return value
            result=self.run_suite(observation=observe,cancel=cancel)
            self.assertFalse(result['success'])
            self.assertEqual(len(self.calls),33 if variant=='calibration' else 2)
            self.assertEqual(result['error'],'invalid_calibration_counts' if variant=='calibration' else 'cancelled')

    def test_large_artifact_bound_and_unique_filename(self):
        artifact=self.s._persist(self.root,0,{'text':'x'*(2*1024*1024+1)})
        self.assertGreater(artifact['size_bytes'],2*1024*1024)
        with self.assertRaisesRegex(ValueError,'exists'):
            self.s._persist(self.root,0,{'text':'replacement'})
        with self.assertRaisesRegex(ValueError,'limit'):
            self.s._persist(self.root,1,{'text':'x'*(16*1024*1024)})
        self.assertFalse((self.root/'request-001.json').exists())

    def test_unknown_metrics_single_sample_sd_and_full_long_budget(self):
        result=self.run_suite()
        warmup=next(g for g in result['groups'] if g['case']=='WARMUP')
        self.assertIsNone(warmup['metrics']['engine_pp_tokens_per_second']['sample_sd'])
        self.assertEqual(warmup['metrics']['engine_tg_tokens_per_second'],dict(n=0,mean=None,sample_sd=None))
        full=self.s.recipes.validate_answer('LONG',dict(visible_answer='1. Observe timing.',finish_reason='length',metrics={'completion_tokens':256}))
        self.assertTrue(full['sustained_256_sample']); self.assertFalse(full['early_eos'])
        self.assertEqual(full['state'],'semantic_review_pending')

    def test_observer_exception_and_summary_failure_always_signal_done(self):
        def fail(**kwargs): raise RuntimeError('SECRET')
        result=self.run_suite(observation=fail)
        self.assertEqual(result['counts'],dict(valid=0,failed=0,not_run=36))
        self.assertNotIn('SECRET',json.dumps(result))
        with patch.object(self.s,'_summarize',side_effect=ValueError('bad summary')):
            result=self.run_suite(observation=fail)
        self.assertFalse(result['success'])

    def test_completed_suite_artifacts_accepted_by_predecessor_store(self):
        from dataclasses import replace
        from test_benchmark_runtime import BenchmarkFixture, SIXTEEN
        from gufo_control import smoke_store
        result=self.run_suite()
        with tempfile.TemporaryDirectory() as temp:
            f=BenchmarkFixture(temp); f.bind(SIXTEEN)
            for row in result['rows']:
                name=row['artifact']['name']
                (f.predecessor_run/name).write_bytes((self.root/name).read_bytes())
            saved=self.s.operator_store.read_json(f.predecessor_run/'result.json')
            saved['http']=result
            self.s.operator_store.atomic_json(f.predecessor_run/'result.json',saved)
            digest=self.s.operator_store.artifact_record(f.predecessor_run/'result.json')['sha256']
            f.pins=replace(f.pins,predecessors=(replace(f.pins.predecessors[0],result_sha256=digest),))
            self.assertEqual(len(smoke_store._predecessor_records(f.pins)[0]['artifacts']),36)
