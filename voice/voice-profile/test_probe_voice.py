import importlib.util, json, tempfile, unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

p=Path(__file__).resolve().parents[1]/'native-speech-validation'/'speech_probe.py'
s=importlib.util.spec_from_file_location('probe_voice',p); probe=importlib.util.module_from_spec(s); s.loader.exec_module(probe)

class ProbeVoiceTests(unittest.TestCase):
    def test_changed_ownership_fails_before_creating_http_connection(self):
        with patch.object(probe, 'assert_owned_listener', side_effect=RuntimeError('owner changed')), patch.object(probe.http.client, 'HTTPConnection') as connection:
            with self.assertRaises(probe.ProbePreflightError):
                probe.request(8862, '/v1/audio/voices', 'POST', b'{}')
            connection.assert_not_called()

    def test_loading_listener_retains_oserror_for_existing_startup_retry(self):
        with patch.object(probe, 'assert_owned_listener', side_effect=OSError('not yet listening')), patch.object(probe.http.client, 'HTTPConnection') as connection:
            with self.assertRaises(probe.ProbeListenerNotReady) as error:
                probe.request(8862, '/v1/models')
            self.assertIsInstance(error.exception, OSError)
            connection.assert_not_called()

    def test_validation_registers_selected_own_reference(self):
        self.assertTrue(hasattr(probe,'voice_profiles'),'Validation must resolve the selected voice profile')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); runtime=root/'runtime'; runtime.mkdir()
            own={'profile_id':'own-revision','name':'Own voice','kind':'authorized_own_voice','reference_text':'Own recording','reference_sha256':'own-hash'}
            registered=[]
            manager=SimpleNamespace(PROFILE_ROOT=root,activation_lock=lambda p:nullcontext(),selected_profile=lambda:own,native_register=lambda p:registered.append(p) or {'status':200})
            owner={k:{'pid':11} for k in probe.SERVICES}
            memory=SimpleNamespace(available=50*1024**3)
            with patch.object(probe,'voice_profiles',return_value=manager), patch.object(probe,'ROOT',root), patch.object(probe,'RUNTIME',runtime), patch.object(probe,'owners',return_value=owner), patch.object(probe,'same_process',return_value=True), patch.object(probe,'health',return_value={}), patch.object(probe,'transcribe',return_value={'transcript':'Guten Tag.'}), patch.object(probe,'request',return_value=(bytes(48000),{'status':200})), patch.object(probe.psutil,'virtual_memory',return_value=memory), patch.object(probe,'dump'):
                probe.validate()
            self.assertEqual(registered,[own])
            report=json.loads((root/'validation-result.json').read_text())
            self.assertEqual(report['voice_registration']['reference_sha256'],'own-hash')
            self.assertEqual(report['voice_registration']['voice'],'Own voice')

if __name__=='__main__': unittest.main()
