import importlib
import importlib.util
import json
import unittest


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('gufo_control.benchmark_recipes'))
        self.r = importlib.import_module('gufo_control.benchmark_recipes')

    def test_exact_schedules_and_fresh_canonical_definition(self):
        r = self.r
        four = r.recipe_definition(r.PROFILE_4K)
        self.assertEqual(len(four['schedule']), 36)
        tasks = four['schedule'][1:31]
        for rep in range(3):
            part = tasks[rep*10:(rep+1)*10]
            order = ['EN', 'DE', 'CODE', 'TOOL', 'LONG']
            order = order[rep:] + order[:rep]
            modes = ['greedy', 'sampled'] if rep % 2 == 0 else ['sampled', 'greedy']
            self.assertEqual([(p['case'], p['mode']) for p in part], [(c, m) for c in order for m in modes])
        sixteen = r.recipe_definition(r.PROFILE_16K)['schedule']
        self.assertEqual(len(sixteen), 13)
        self.assertEqual([x['target_prompt_tokens'] for x in sixteen[3:9]], [2048,8192,8192,2048,2048,8192])
        self.assertEqual([x['cache_prompt'] for x in sixteen[9:]], [False, True, True, True])
        self.assertEqual(four, json.loads(r.recipe_json(r.PROFILE_4K)))
        four['schedule'].clear()
        self.assertEqual(len(r.recipe_definition(r.PROFILE_4K)['schedule']), 36)

    def test_requests_sampler_tool_and_argv(self):
        r = self.r
        for profile, context in [(r.PROFILE_4K, '4096'), (r.PROFILE_16K, '16384')]:
            argv = r.build_argv(profile, 'SECRET')
            for flag, value in [('--context',context),('--max-tokens','256'),('--max-connections','16'),('--max-request-bytes','262144')]:
                self.assertEqual(argv[argv.index(flag)+1], value)
        definition = r.recipe_definition(r.PROFILE_4K)
        for row in definition['schedule'][1:31]:
            request = r.request_for(row)
            self.assertEqual(request['chat_template_kwargs'], {'enable_thinking':False})
            self.assertFalse(request['cache_prompt'])
            self.assertEqual(request['seed'], 42 if row['mode']=='greedy' else 1001+row['repetition'])
            if row['case']=='TOOL':
                self.assertEqual(request['tool_choice'], 'required')
                self.assertEqual(request['tools'][0]['function']['name'], 'lookup_ticket')

    def test_calibration_rounding_and_invalid_counters(self):
        r = self.r
        self.assertEqual(r.calibrated_prompt(60,10,410), 'x'+r.FILLER*2)
        for args in [(2048,10,10),(2048,True,20),(2048,1,2.0),(100000000,0,1)]:
            with self.assertRaises(ValueError): r.calibrated_prompt(*args)

    def test_semantics_remain_pending_and_json_strict(self):
        r = self.r
        answer = lambda text: dict(visible_answer=text,finish_reason='stop',metrics={'completion_tokens':100})
        for case in ['EN','LONG']:
            self.assertEqual(r.validate_answer(case, answer('A complete candidate.'))['state'], 'semantic_review_pending')
        valid = '{"sprache":"de","hoechste_prioritaet":"B","begruendung":"Alle Nutzer sind betroffen."}'
        self.assertEqual(r.validate_answer('DE',answer(valid))['state'],'semantic_review_pending')
        for bad in [valid+' text',valid.replace('"de"','"en"'),valid.replace('"sprache":"de"','"sprache":"de","sprache":"de"')]:
            self.assertEqual(r.validate_answer('DE',answer(bad))['state'],'failed')
        self.assertTrue(r.validate_answer('LONG',answer('Candidate.'))['early_eos'])

    def test_code_interpreter_and_malicious_syntax(self):
        r = self.r
        def check(code): return r.validate_answer('CODE',{'visible_answer':code,'finish_reason':'stop'})['state']
        self.assertEqual(check('def clamp(x, lo, hi):\n if lo > hi: raise ValueError("bad")\n return min(hi, max(lo, x))'),'passed')
        self.assertEqual(check('def clamp(x, lo, hi):\n if lo > hi: raise ValueError\n return lo if x < lo else hi if x > hi else x'),'passed')
        self.assertEqual(check('def clamp(x, lo, hi):\n return x'),'failed')
        for bad in ['import os\ndef clamp(x, lo, hi): return x','def clamp(x, lo, hi):\n return __import__("os").system("evil")','@evil\ndef clamp(x, lo, hi): return x']:
            self.assertEqual(check(bad),'failed')
        self.assertEqual(check('def clamp(x, lo, hi):\n y = x\n return y'),'needs_review')

    def test_tool_arguments_and_prose_no_execution(self):
        r = self.r
        value = dict(visible_answer='', finish_reason='tool_calls', tool_calls=[dict(id='call-1',type='function',function=dict(name='lookup_ticket',arguments='{"ticket_id":"INC-2047"}'))])
        self.assertEqual(r.validate_answer('TOOL',value)['state'],'passed')
        value['finish_reason']='stop'
        self.assertEqual(r.validate_answer('TOOL',value)['state'],'needs_review')
        value['visible_answer']='Ticket is closed.'
        self.assertEqual(r.validate_answer('TOOL',value)['state'],'failed')

    def test_unexpected_tool_calls_and_deep_json_fail_closed(self):
        r=self.r
        for case,text in [('DE','{"sprache":"de","hoechste_prioritaet":"B","begruendung":"Alle Nutzer sind betroffen."}'),
                          ('CODE','def clamp(x, lo, hi):\n if lo>hi: raise ValueError\n return min(hi,max(lo,x))')]:
            self.assertEqual(r.validate_answer(case,dict(visible_answer=text,finish_reason='tool_calls',tool_calls=[{}]))['state'],'failed')
        deep='['*2000+'0'+']'*2000
        self.assertEqual(r.validate_answer('DE',dict(visible_answer=deep,finish_reason='stop'))['state'],'failed')
