from copy import deepcopy
import unittest

from gufo_control import matched_recipes, matched_validation


def observation(row, *, mtp=False, proposed=0, accepted=0):
    prompt=row['expected_prompt_tokens']; output=1 if row['output_budget']==1 else 16
    return dict(success=True, error=None, visible_answer='4' if row['case']=='WARMUP' else '1. Observe timing.',
        finish_reason='stop', reasoning_content='', tool_calls=[], observed_models=['gufo-flash-next'],
        validation_errors=[], metrics=dict(logical_prompt_tokens=prompt,new_prefill_tokens=prompt,
            cached_prompt_tokens=0,completion_tokens=output,mtp_acceptance=accepted/proposed if proposed else None),
        usage=dict(prompt_tokens=prompt,completion_tokens=output,total_tokens=prompt+output,cached_tokens=0,
            prompt_tokens_details=dict(cached_tokens=0),draft_tokens=proposed,draft_tokens_accepted=accepted,
            gufo=dict(prefill_tokens=prompt,cache_hit=False,cache_disk_hit=False,cache_restore_bytes=0,
                cache_disk_queued_bytes=0,physical_execution_width=1,requested_logical_concurrency=1,
                resident_requests_at_admission=1)),timings=dict(prompt_n=prompt,predicted_n=output,
                cache_n=0,draft_n=proposed,draft_n_accepted=accepted))


class MatchedValidationTests(unittest.TestCase):
    def setUp(self):
        self.definition=matched_recipes.recipe_definition(matched_recipes.PROFILE_MTP)
        self.row=self.definition['schedule'][0]

    def assess(self, value, row=None):
        return matched_validation.assess(row or self.row,value,self.definition)

    def test_zero_draft_and_zero_acceptance_valid(self):
        zero=observation(self.row,mtp=True)
        correctness,errors=self.assess(zero)
        self.assertFalse(errors)
        self.assertIsNone(zero['matched_evidence']['acceptance_ratio'])
        self.assertEqual(zero['matched_evidence']['acceptance_reason'],'no_proposals')
        positive=observation(self.row,mtp=True,proposed=5,accepted=0)
        self.assertFalse(self.assess(positive)[1])
        self.assertEqual(positive['matched_evidence']['acceptance_ratio'],0)

    def test_invalid_native_counters_and_cache(self):
        mutations=(lambda v:v['usage'].pop('draft_tokens'),lambda v:v['usage'].update(draft_tokens=True),
                   lambda v:v['timings'].update(draft_n=.0),lambda v:v['timings'].update(draft_n=1),
                   lambda v:v['usage']['gufo'].update(cache_hit=True),lambda v:v['usage'].update(prompt_tokens=27),
                   lambda v:v['timings'].update(lookup_n=0),lambda v:v['usage']['gufo'].update(physical_execution_width=2))
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                value=observation(self.row); mutate(value)
                self.assertTrue(self.assess(value)[1])

    def test_ar_nonzero_draft_and_quality_failure(self):
        ar=matched_recipes.recipe_definition(matched_recipes.PROFILE_AR)
        value=observation(ar['schedule'][0],proposed=1)
        self.assertTrue(matched_validation.assess(ar['schedule'][0],value,ar)[1])
        value=observation(ar['schedule'][0]); value['visible_answer']='wrong'
        correctness,errors=matched_validation.assess(ar['schedule'][0],value,ar)
        self.assertEqual(errors,[])
        self.assertEqual(correctness['state'],'failed')
        self.assertTrue(value['matched_evidence']['quality_failed'])

    def test_long_early_eos_is_valid_but_not_sustained(self):
        row=next(r for r in self.definition['schedule'] if r['case']=='LONG')
        value=observation(row,mtp=True,proposed=2,accepted=0)
        correctness,errors=self.assess(value,row)
        self.assertEqual(errors,[])
        self.assertFalse(value['matched_evidence']['sustained_256_eligible'])
        self.assertTrue(correctness['early_eos'])
        value['usage']['completion_tokens']=256
        value['usage']['total_tokens']=row['expected_prompt_tokens']+256
        value['timings']['predicted_n']=256
        value['metrics']['completion_tokens']=256
        value['finish_reason']='length'
        self.assertEqual(self.assess(value,row)[1],[])
        self.assertTrue(value['matched_evidence']['sustained_256_eligible'])

    def test_explicit_lookup_and_snapshot_are_not_cache_hits(self):
        value=observation(self.row,mtp=True)
        value['timings'].update(lookup_n=0,lookup_n_accepted=0)
        value['usage']['gufo'].update(cache_snapshot_bytes=1024,cache_shared_bytes=128,
            cache_shared_prefix_snapshots=1,cache_shared_prefix_bytes=64)
        self.assertEqual(self.assess(value)[1],[])
        self.assertEqual(value['matched_evidence']['lookup_provenance'],'explicit_zero')
        self.assertEqual(value['matched_evidence']['snapshot_fields']['cache_snapshot_bytes'],1024)

    def test_quality_failure_does_not_hide_fatal_native_error(self):
        value=observation(self.row,mtp=True)
        value['visible_answer']='wrong'
        value['usage']['draft_tokens']=True
        correctness,errors=self.assess(value)
        self.assertEqual(correctness['state'],'failed')
        self.assertTrue(value['matched_evidence']['quality_failed'])
        self.assertIn('invalid_draft_tokens',errors)

    def test_malformed_snapshot_field_is_fatal(self):
        value=observation(self.row,mtp=True)
        value['usage']['gufo']['cache_snapshot_bytes']=True
        self.assertIn('invalid_cache_snapshot_bytes',self.assess(value)[1])
