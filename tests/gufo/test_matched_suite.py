import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from gufo_control import benchmark_guard, benchmark_suite, matched_recipes, matched_validation
from test_matched_validation import observation


class MatchedSuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def run_suite(self, profile, *, mutate=None, validator=None, cancel=None):
        definition=matched_recipes.recipe_definition(profile)
        calls=[]
        def ready(*args, **kwargs): pass
        def send(**kwargs):
            index=len(calls); calls.append(kwargs)
            row=definition['schedule'][index]
            value=observation(row,mtp=profile in matched_recipes.MTP_DRAFT_LIMITS)
            if row['case']=='DE':
                value['visible_answer']='{"sprache":"de","hoechste_prioritaet":"B","begruendung":"Alle Nutzer sind betroffen."}'
            elif row['case']=='CODE':
                value['visible_answer']='def clamp(x, lo, hi):\n if lo > hi: raise ValueError\n return min(hi, max(lo, x))'
            elif row['case']=='TOOL':
                value.update(visible_answer='',finish_reason='tool_calls',tool_calls=[dict(
                    id='a',type='function',function=dict(name='lookup_ticket',arguments='{"ticket_id":"INC-2047"}'))])
            value['request']=kwargs['request']; value['post_attempted']=True
            if mutate: mutate(index,value)
            return value
        with patch.object(benchmark_suite,'_ready',ready), patch.object(benchmark_suite.benchmark_http,'request_once',send):
            now=time.monotonic()
            task=benchmark_suite.start_suite(profile_id=profile,evidence_dir=self.root,api_key='private',
                startup_deadline=now+480,lifetime_deadline=now+600,cancel=cancel,
                recipe_provider=matched_recipes,request_validator=validator or matched_recipes.validate_request,
                response_assessor=matched_validation.assess)
            self.assertTrue(task.done.wait(10))
            return task.result,calls

    def test_both_modes_complete_all_36(self):
        for profile in matched_recipes.PROFILES:
            with self.subTest(profile=profile):
                for item in self.root.iterdir(): item.unlink()
                result,calls=self.run_suite(profile)
                self.assertTrue(result['success'],result.get('error'))
                self.assertEqual(len(calls),36)
                self.assertEqual(result['counts']['quality_failed'],0)
                self.assertEqual(result['counts']['invalid_metric'],0)
                self.assertEqual(result['rows'][-1]['matched_evidence']['actual_prompt_tokens'],2047)
                pp=next(r for r in result['rows'] if r['case']=='PP1')
                self.assertEqual(pp['matched_evidence']['acceptance_reason'],
                    'no_proposals' if profile in matched_recipes.MTP_DRAFT_LIMITS else 'not_applicable')

    def test_draft3_positive_native_counters_across_full_corpus(self):
        def active(index, value):
            if index == 0:
                value['usage'].update(draft_tokens=4, draft_tokens_accepted=3)
                value['timings'].update(draft_n=4, draft_n_accepted=3)
                value['metrics']['mtp_acceptance'] = .75
        result, calls = self.run_suite(matched_recipes.PROFILE_MTP_D3, mutate=active)
        self.assertTrue(result['success'], result.get('error'))
        self.assertEqual(len(calls), 36)
        self.assertEqual(result['rows'][0]['matched_evidence']['accepted'], 3)

    def test_altered_final_request_rejected_before_post(self):
        def altered(row,request):
            request['temperature']=0.1
            return matched_recipes.validate_request(row,request)
        result,calls=self.run_suite(matched_recipes.PROFILE_AR,validator=altered)
        self.assertEqual(calls,[])
        self.assertEqual(result['counts']['not_run'],36)

    def test_quality_failure_continues_and_fatal_counter_stops(self):
        def quality(index,value):
            if index==0: value['visible_answer']='wrong'
        result,calls=self.run_suite(matched_recipes.PROFILE_MTP,mutate=quality)
        self.assertTrue(result['success'])
        self.assertEqual(len(calls),36)
        self.assertEqual(result['counts']['quality_failed'],1)
        self.assertEqual(result['rows'][0]['correctness']['state'],'failed')
        for item in self.root.iterdir(): item.unlink()
        def fatal(index,value):
            if index==2: value['usage'].pop('draft_tokens')
        result,calls=self.run_suite(matched_recipes.PROFILE_MTP,mutate=fatal)
        self.assertFalse(result['success'])
        self.assertEqual(len(calls),3)
        self.assertEqual(result['counts']['invalid_metric'],1)
        self.assertEqual(result['counts']['transport_failed'],0)
        self.assertEqual(result['counts']['not_run'],33)
        self.assertEqual(result['rows'][2]['status'],'failed')

    def test_cancel_and_write_failure(self):
        cancel=threading.Event(); cancel.set()
        result,calls=self.run_suite(matched_recipes.PROFILE_AR,cancel=cancel)
        self.assertEqual(calls,[])
        self.assertEqual(result['error'],'cancelled')
        with patch.object(benchmark_suite.operator_store,'atomic_json',side_effect=OSError('disk')):
            result,calls=self.run_suite(matched_recipes.PROFILE_AR)
        self.assertEqual(len(calls),1)
        self.assertEqual(result['error'],'evidence_write_failed')

    def test_early_eos_and_zero_acceptance_are_retained(self):
        long_index=next(r['ordinal'] for r in matched_recipes.recipe_definition(matched_recipes.PROFILE_MTP)['schedule'] if r['case']=='LONG')
        def change(index,value):
            if index==long_index: value['visible_answer']='1. Short answer.'
            if index==1:
                value['usage'].update(draft_tokens=3,draft_tokens_accepted=0)
                value['timings'].update(draft_n=3,draft_n_accepted=0)
                value['metrics']['mtp_acceptance']=0
        result,calls=self.run_suite(matched_recipes.PROFILE_MTP,mutate=change)
        self.assertEqual(len(calls),36)
        self.assertTrue(result['success'])
        self.assertEqual(result['rows'][1]['matched_evidence']['acceptance_ratio'],0)
        self.assertEqual(result['rows'][long_index]['status'],'completed')
        self.assertFalse(result['rows'][long_index]['matched_evidence']['sustained_256_eligible'])
        self.assertFalse(result['claims']['mtp_draft_path_exercised'])

    def test_mtp_claims_require_valid_long_proposals_and_acceptance(self):
        long_index=next(r['ordinal'] for r in matched_recipes.recipe_definition(matched_recipes.PROFILE_MTP)['schedule'] if r['case']=='LONG')
        def active(index,value):
            if index==long_index:
                value['usage'].update(draft_tokens=4,draft_tokens_accepted=1)
                value['timings'].update(draft_n=4,draft_n_accepted=1)
                value['metrics']['mtp_acceptance']=.25
        result,_=self.run_suite(matched_recipes.PROFILE_MTP,mutate=active)
        self.assertTrue(result['claims']['mtp_draft_path_exercised'])
        self.assertTrue(result['claims']['useful_accepted_speculation_observed'])

    def test_native_long_coverage_survives_quality_failure(self):
        long_index=next(r['ordinal'] for r in matched_recipes.recipe_definition(matched_recipes.PROFILE_MTP)['schedule'] if r['case']=='LONG')
        def active(index,value):
            if index==long_index:
                prompt=value['usage']['prompt_tokens']
                value['visible_answer']=''
                value['finish_reason']='length'
                value['usage'].update(completion_tokens=256,total_tokens=prompt+256,draft_tokens=4,draft_tokens_accepted=1)
                value['timings'].update(predicted_n=256,draft_n=4,draft_n_accepted=1)
                value['metrics'].update(completion_tokens=256,mtp_acceptance=.25)
        result,_=self.run_suite(matched_recipes.PROFILE_MTP,mutate=active)
        self.assertTrue(result['success'])
        self.assertEqual(result['counts']['quality_failed'],1)
        self.assertTrue(result['claims']['mtp_draft_path_exercised'])
        self.assertIn(long_index,result['claims']['sustained_256_rows'])
        self.assertNotIn(long_index,result['claims']['correct_sustained_256_rows'])

    def test_malformed_gufo_is_persisted_then_stops(self):
        for bad in (['malformed'], 'malformed'):
            with self.subTest(bad=bad):
                for item in self.root.iterdir(): item.unlink()
                def malformed(index,value):
                    if index==0:
                        value['usage']['gufo']=bad
                        value.update(success=False,error='validation_failed',raw_response_base64='UkFX')
                result,calls=self.run_suite(matched_recipes.PROFILE_MTP,mutate=malformed)
                self.assertEqual(len(calls),1)
                self.assertFalse(result['success'])
                self.assertEqual(result['rows'][0]['status'],'failed')
                self.assertEqual(result['counts']['not_run'],35)
                artifact=result['rows'][0]['artifact']['name']
                raw=json.loads((self.root/artifact).read_text())
                self.assertEqual(raw['usage']['gufo'],bad)
                self.assertEqual(raw['raw_response_base64'],'UkFX')
