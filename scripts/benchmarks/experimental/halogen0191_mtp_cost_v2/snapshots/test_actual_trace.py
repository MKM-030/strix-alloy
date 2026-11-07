"""CPU replay of the failed campaign's real native counters."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
HERE = Path(__file__).resolve().parent

def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
fixed=load(HERE/'mtp_cost_trace.py','cost_fixed')
frozen=load(HERE.parent/'cost-gate-cohort-prep/mtp_cost_trace.py','cost_frozen')

class ActualCounterReplay(unittest.TestCase):
    def setUp(self):
        self.text=(HERE/'actual-engine-log.txt').read_text()
        self.samples=json.loads((HERE/'actual-samples.json').read_bytes())
    def test_frozen_helper_reproduces_real_failure(self):
        with self.assertRaisesRegex(ValueError,'Native request and saved speculation counters differ'):
            frozen.qualify_trace(self.text,self.samples,'gate')
    def test_minimal_fix_accepts_matching_real_head_and_scope_counters(self):
        result=fixed.qualify_trace(self.text,self.samples,'gate')
        self.assertEqual([row['id'] for row in result['samples']],[4,5,6,7])
        for row in result['samples']:
            self.assertEqual(row['legacy_accepted'],45)
            self.assertEqual(row['head_accepted'],69)
            self.assertEqual(row['head_drafted'],109)
            self.assertEqual(row['rounds'],57)
    def test_real_head_counter_drift_still_rejected(self):
        for scope in ('head','lookup','grammar'):
            for key in ('rounds','drafted','accepted'):
                with self.subTest(scope=scope,key=key):
                    samples=copy.deepcopy(self.samples)
                    samples[0]['speculation'][scope][key]+=1
                    with self.assertRaisesRegex(ValueError,'counters differ'):
                        fixed.qualify_trace(self.text,samples,'gate')
    def test_actual_request_id_and_banner_drift_still_rejected(self):
        samples=copy.deepcopy(self.samples);samples[0]['native_request_id']=3
        with self.assertRaises(ValueError):fixed.qualify_trace(self.text,samples,'gate')
        with self.assertRaises(ValueError):fixed.qualify_trace(self.text,self.samples,'cost')

if __name__=='__main__':unittest.main()
