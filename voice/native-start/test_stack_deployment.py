"""Offline regression: status must agree with selected, pinned gateway profile."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

STATUS_PATH = Path(__file__).parents[1]/'native-speech-validation/stack_status.py'
spec = importlib.util.spec_from_file_location('aligned_stack_status', STATUS_PATH)
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


class Response:
    status = 200
    def __init__(self,value): self.value = value
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,size): return json.dumps(self.value).encode()


class StackDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.good = {'status':'ok','model':'halogen-qwen3.8-flash-next',
            'version':{'api':'0.18.8','engine':'0.18.8','match':True},
            'context':32768,'slot_ctx':32768,'kv_pool_positions':32768,'slots':1,
            'vision':{'enabled':True},
            'prompt_cache':{'mode':1,'enabled':True,'cap_mb':4096,'bitwise_identical_to_cold':True}}

    def health(self,value):
        opener = SimpleNamespace(open=lambda request,timeout:Response(value))
        with patch.object(status.urllib.request,'build_opener',return_value=opener):
            return status.health(8731)

    def test_selected0188_health_is_accepted(self):
        self.assertTrue(self.health(self.good)['version_matches'])
        self.assertTrue(self.health(self.good)['profile_matches'])

    def test_old0181_version_is_rejected(self):
        value = copy.deepcopy(self.good)
        value['version'] = {'api':'0.18.1','engine':'0.18.1','match':True}
        self.assertFalse(self.health(value)['version_matches'])

    def test_wrong_context_slots_vision_or_health_type_still_rejected(self):
        for changes in ({'context':8192},{'slot_ctx':8192},{'kv_pool_positions':8192},
                {'slots':2},{'vision':{'enabled':False}},{'context':32768.0},
                {'model':'other-model'}):
            with self.subTest(changes=changes):
                self.assertFalse(self.health({**self.good,**changes})['profile_matches'])

    def test_status_paths_come_from_same_selected_deployment(self):
        self.assertEqual(status.PROFILE.name,'serving0188-voice32k-prefill8192.json')
        self.assertEqual(status.MODEL,
            Path(r'C:\Projects\strix-alloy-clean\backends\halogen-wsl2-0.18.8\.local\api-token.txt'))


if __name__ == '__main__': unittest.main()
