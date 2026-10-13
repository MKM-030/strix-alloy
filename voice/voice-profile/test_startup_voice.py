import hashlib, importlib.util, json, tempfile, unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

p=Path(__file__).resolve().parents[1]/'native-start'/'start_services.py'
s=importlib.util.spec_from_file_location('startup_voice',p); startup=importlib.util.module_from_spec(s); s.loader.exec_module(startup)

class StartupVoiceTests(unittest.TestCase):
    def test_startup_restores_selected_own_voice_instead_of_synthetic_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); (folder/'reference.wav').write_bytes(b'synthetic')
            synthetic={'kind':'designed_synthetic_voice','reference_text':'Synthetic default','reference_sha256':hashlib.sha256(b'synthetic').hexdigest()}
            (folder/'voice.json').write_text(json.dumps(synthetic))
            own={'profile_id':'own-revision','name':'Own voice','kind':'authorized_own_voice','reference_text':'Own recording','reference_sha256':'own-hash'}
            registered=[]
            speech=SimpleNamespace(SERVICES={'tts':{}},start=lambda:None,PROFILE=folder,owners=lambda:{'tts':{'pid':11,'created':123}},request=lambda *args:None)
            manager=SimpleNamespace(PROFILE_ROOT=folder,activation_lock=lambda p:nullcontext(),selected_profile=lambda:own,native_register=lambda p:registered.append(p),atomic_json=lambda p,v:p.write_text(json.dumps(v)))
            with patch.object(startup,'module',side_effect=lambda name,p: manager if 'manage_voice' in str(p) else speech), patch.object(startup,'RUNTIME',folder):
                startup.speech_start(['tts'])
            self.assertEqual(registered,[own], 'TTS startup must restore the selected own voice')
            self.assertEqual(json.loads((folder/'registered-voice.json').read_text())['reference_sha256'],'own-hash')

    def test_matching_receipt_reuses_existing_selected_voice_without_gpu_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); own={'profile_id':'own-revision','name':'Own voice','reference_sha256':'own-hash'}
            (folder/'reference.wav').write_bytes(b'synthetic')
            (folder/'voice.json').write_text(json.dumps({'kind':'designed_synthetic_voice','reference_text':'Synthetic default','reference_sha256':hashlib.sha256(b'synthetic').hexdigest()}))
            (folder/'registered-voice.json').write_text(json.dumps({'pid':11,'created':123,'reference_sha256':'own-hash'}))
            registered=[]
            speech=SimpleNamespace(SERVICES={'tts':{}},start=lambda:None,PROFILE=folder,owners=lambda:{'tts':{'pid':11,'created':123}},request=lambda *args:registered.append('synthetic'))
            manager=SimpleNamespace(PROFILE_ROOT=folder,activation_lock=lambda p:nullcontext(),selected_profile=lambda:own,native_register=lambda p:registered.append(p))
            with patch.object(startup,'module',side_effect=lambda name,p: manager if 'manage_voice' in str(p) else speech), patch.object(startup,'RUNTIME',folder):
                startup.speech_start(['tts'])
            self.assertEqual(registered,[])

if __name__=='__main__': unittest.main()
