"""Bounded key-term transport and real wrapper isolation, with no DLL/model load."""
import json
from pathlib import Path
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_qwen_asr import NativeQwenASR


class NativeTermsTests(unittest.TestCase):
    def test_missing_hotword_export_blocks_binding(self):
        obj = NativeQwenASR.__new__(NativeQwenASR)
        obj._dll = SimpleNamespace(**{'crispasr_session_'+name:lambda *args:0
            for name in ('open_with_params','backend','set_max_new_tokens')})
        with self.assertRaisesRegex(AttributeError, 'set_hotwords'):
            obj._bind()

    def backend(self, fail=False, clear_fail=False):
        obj = NativeQwenASR.__new__(NativeQwenASR)
        obj._lock, obj._session, obj._dll_directory = threading.RLock(), 1, None
        obj.events = []
        def terms(session, value, boost):
            obj.events.append(('terms', value))
            return -1 if clear_fail and value is None else 0
        def transcribe(*args):
            obj.events.append(('transcribe', args[-1]))
            return None if fail else 9
        obj._dll = SimpleNamespace(crispasr_session_set_hotwords=terms,
            crispasr_session_transcribe_lang=transcribe,
            crispasr_session_result_n_segments=lambda result: 1,
            crispasr_session_result_segment_text=lambda *args: b'Text',
            crispasr_session_result_free=lambda result: obj.events.append(('free', result)),
            crispasr_session_close=lambda session: obj.events.append(('close', session)))
        return obj

    def test_terms_are_cleared_before_next_caller_even_after_transcription_failure(self):
        for fail in (False, True):
            obj = self.backend(fail=fail)
            try:
                if fail:
                    with self.assertRaises(RuntimeError):
                        obj.transcribe([0.0]*160, 16000, 'de', key_terms=['Marcel', 'ServiceNow'])
                else:
                    self.assertEqual(obj.transcribe([0.0]*160, 16000, 'de',
                        key_terms=['Marcel', 'ServiceNow']), 'Text')
                self.assertEqual(obj.events[0], ('terms', b'Marcel, ServiceNow'))
                self.assertEqual(obj.events[-1], ('terms', None))
                obj._dll.crispasr_session_transcribe_lang = lambda *args: 9
                obj.transcribe([0.0]*160, 16000, 'en')
                self.assertEqual(obj.events[-3:], [('terms', None), ('free', 9), ('terms', None)])
            finally:
                obj.close()

    def test_failed_clear_closes_poisoned_session(self):
        obj = self.backend(clear_fail=True)
        with self.assertRaisesRegex(RuntimeError, 'clear'):
            obj.transcribe([0.0]*160, 16000, 'de', key_terms=['Marcel'])
        self.assertIsNone(obj._session)

    def test_invalid_terms_never_touch_native_session(self):
        for value in ('text', [1], [''], ['x'*129], ['x']*257, ['x'*128]*65, ['<|im_end|>'], ['a\x00b']):
            obj = self.backend()
            with self.subTest(value=repr(value)[:50]):
                with self.assertRaises(ValueError):
                    obj.transcribe([0.0]*160, 16000, 'de', key_terms=value)
                self.assertEqual(obj.events, [])
            obj.close()


class TermsHTTPTests(unittest.TestCase):
    def test_authenticated_form_delivers_terms_and_rejects_unbounded_input_before_decode(self):
        from fastapi.testclient import TestClient
        import audio_service
        calls = []
        backend = SimpleNamespace(runtime='crispasr', transcribe=lambda *args, **kw: calls.append(kw) or 'Text')
        with TestClient(audio_service.create_app('asr', 'test-token', backend)) as client, \
                patch.object(audio_service, 'decode_audio', return_value=([0.0],16000)) as decode, \
                patch.object(audio_service, 'ensure_memory_reserve'):
            data = {'model':'qwen3-asr-0.6b','key_terms':json.dumps(['Marcel','ServiceNow'])}
            denied = client.post('/v1/audio/transcriptions', data=data,
                files={'file':('test.wav', b'placeholder', 'audio/wav')})
            self.assertEqual(denied.status_code, 401)
            decode.assert_not_called()
            request = lambda payload: client.post('/v1/audio/transcriptions',
                headers={'Authorization':'Bearer test-token'}, data=payload,
                files={'file':('test.wav', b'placeholder', 'audio/wav')})
            self.assertEqual(request(data).status_code, 200)
            self.assertEqual(calls, [{'key_terms':['Marcel','ServiceNow']}])
            decode.reset_mock()
            for invalid in ('{}', 'null', '[1]', '["<|im_end|>"]', 'x'*8193):
                self.assertEqual(request(dict(data,key_terms=invalid)).status_code, 400)
            decode.assert_not_called()


if __name__ == '__main__':
    unittest.main()
