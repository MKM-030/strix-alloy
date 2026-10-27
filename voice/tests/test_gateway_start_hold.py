import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

def repository_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / "voice/native_qwen_asr.py").is_file() and (parent / "voice/native-start/start_current_voice.py").is_file():
            return parent
    raise RuntimeError("Cannot find the repository Voice sources")

path=repository_root()/'voice/native-start/start_current_voice.py'
spec=importlib.util.spec_from_file_location('task78_gateway_hold_starter',path)
starter=importlib.util.module_from_spec(spec);spec.loader.exec_module(starter)


class GatewayStartHold(unittest.TestCase):
    def check(self,aliases):
        config={'controller_consumer':True,'backend':{'upstream':'http://127.0.0.1:8840'},
            'controller_aliases':aliases,'controller_model_aliases':{'Gemma 4 26B-A4B':'gemma4-26b-a4b'}}
        probes=[]
        services=SimpleNamespace(owned_listener=lambda *args:probes.append(args) or None)
        with patch.object(starter,'services',services),patch.object(starter,'read_json',return_value=config), \
             patch.object(starter,'credential',return_value='same-private-binding'):
            try:result=starter.gateway_ready({'backend':{'identifier':'halogen-v2'}})
            finally:self.probes=probes
        return result

    def test_fixed_gemma_names_are_rejected_before_listener_or_start(self):
        for alias in ('gemma4-26b-a4b','Gemma 4 26B-A4B'):
            with self.subTest(alias=alias),self.assertRaises(RuntimeError):self.check([alias])
            self.assertEqual(self.probes,[])

    def test_neutral_active_alias_can_reach_existing_readiness_check(self):
        self.assertFalse(self.check(['scc-local-active']))
        self.assertEqual(len(self.probes),1)


if __name__=='__main__':unittest.main()
