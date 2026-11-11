"""Fresh-binding, exact helper and passive-entry checks; no runtime calls."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import collect_epoch as collector
from test_validator import fixture
from validate_capture import BINDING,bound_pcs,MAGIC,HEADER,RECORD

ROOT=Path(r'C:\Projects\strix-alloy-clean')
PRIMARY=ROOT/'server/.local/halogen-update-20261111/primary0202'
REQUEST=ROOT/'server/.local/halogen-update-20261107/primary0191/natural8192-prep/request-natural8192.json'
REQUEST_SHA='2e26413988ce75fcf745a1a143aa3647297349c1516f9d18968e9d1b4da0632d'


class MigrationTests(unittest.TestCase):
    def test_seven_HTTP_QPC_helpers_have_exact_original_function_bodies(self):
        original=ROOT/'server/.local/halogen-update-20261110/primary0201/measure.py'
        helper=PRIMARY/'real-npu-v4-prep/measure_helpers.py'
        old={n.name:n for n in ast.parse(original.read_text(encoding='utf-8')).body
             if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        new={n.name:n for n in ast.parse(helper.read_text(encoding='utf-8')).body
             if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        expected={'utc','digest','require','save_new','load_runtime','check_reserve','fetch_http_response'}
        self.assertEqual(set(new),expected)
        for name in expected:
            self.assertEqual(ast.dump(old[name],include_attributes=False),ast.dump(new[name],include_attributes=False),name)

    def test_fresh_binding_is_exact_source_proof_and_wire_layout_remains_unchanged(self):
        proof=PRIMARY/'npu-consumer-seam-v1/raw-binding.json'
        self.assertEqual(BINDING.read_bytes(),proof.read_bytes())
        self.assertEqual(hashlib.sha256(proof.read_bytes()).hexdigest(),
            'b842c1f407a92e3b325b989ebd4692076cfa9e760a340a19f4110a956e1300b9')
        binding=json.loads(proof.read_bytes())
        self.assertEqual(binding['engine_sha256'],'bf84053705d1e89c214ff64c79ad1276c5fe353d80a9bb0f38ef3bac6645b97c')
        self.assertEqual(set(bound_pcs()),{1,2,3,4})
        self.assertEqual((MAGIC,HEADER.format,RECORD.format),(0x3357415231393048,'<8Q','<6Q4q4Q4Iq'))

    def test_original_frozen_8192_request_is_unchanged(self):
        raw=REQUEST.read_bytes();request=collector.request_value(raw,REQUEST_SHA,'mtp')
        self.assertEqual(hashlib.sha256(raw).hexdigest(),REQUEST_SHA)
        self.assertEqual((request['temperature'],request['seed'],request['max_tokens']),(0,1,128))
        self.assertEqual(request['prompt_cache_policy'],'no_store')
        self.assertFalse(request['cache_prompt'])

    def test_passive_entry_never_loads_runtime_sends_HTTP_or_writes_output(self):
        with tempfile.TemporaryDirectory()as tmp:
            output=Path(tmp)/'uncreated';raw_dir=Path(tmp)/'raw-uncreated'
            argv=['collect_epoch.py','--profile',str(PRIMARY/'serving0202-text32k-8192.json'),
                '--port','8840','--expected-ready',str(PRIMARY/'ready-left-online.json'),
                '--request-file',str(REQUEST),'--request-sha256',REQUEST_SHA,'--route','/v1/completions',
                '--raw-dir',str(raw_dir),'--epoch','0202000000000001','--output',str(output)]
            with (patch.object(sys,'argv',argv),
                  patch.object(collector.m,'load_runtime',side_effect=AssertionError('No runtime')),
                  patch.object(collector,'session_for_token',side_effect=AssertionError('No HTTP')),
                  patch('builtins.print')):
                collector.main()
            self.assertFalse(output.exists());self.assertFalse(raw_dir.exists())

    def test_scoped_head_counter_cannot_be_replaced_with_combined_acceptance(self):
        _,response=fixture(generated=128,prompt=8192,native_slot=0)
        response['choices']=[dict(text='bounded fixture',finish_reason='length')]
        response['timings'].update(prompt_per_second=8192/0.002,predicted_per_second=128/0.003,
            draft_n=17,draft_n_accepted=6,speculation=dict(drafter='mtp',rounds=10,
                head=dict(rounds=7,drafted=11,accepted=3),lookup=dict(rounds=2,drafted=4,accepted=2),
                grammar=dict(rounds=1,drafted=2,accepted=1)))
        request=json.loads(REQUEST.read_bytes())
        row=collector.account_response(json.dumps(response).encode(),request,
            expected_prompt_tokens=8192,expected_output_tokens=128)
        self.assertEqual(row['scoped']['head'],dict(rounds=7,drafted=11,accepted=3))
        response['timings']['draft_n_accepted']=7
        with self.assertRaisesRegex(ValueError,'scoped and combined'):
            collector.account_response(json.dumps(response).encode(),request,
                expected_prompt_tokens=8192,expected_output_tokens=128)


if __name__=='__main__':unittest.main()
