import unittest
from native_bridge import Config, Speech


class Response:
    status = 200
    def __init__(self, data):
        self.data = data
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    async def json(self):
        return self.data


class HTTP:
    def __init__(self, data):
        self.data = data
        self.kwargs = None
    def post(self, url, **kwargs):
        self.kwargs = kwargs
        return Response(self.data)


class SpeechDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_diagnostics_request_preserves_text_and_decoding_flags(self):
        private_text = ' A private employee name. '
        http = HTTP({'text':private_text,'segments':[
            {'text':'sensitive segment','avg_logprob':-.2,'no_speech_prob':.1},
            {'avg_logprob':-.8,'no_speech_prob':.3}]})
        with self.assertLogs('native-voice',level='INFO') as logs:
            result = await Speech(http,Config()).transcribe(bytes(3200))
        fields = {part[0]['name']:part[2] for part in http.kwargs['data']._fields}
        self.assertEqual(fields['response_format'],'verbose_json')
        self.assertEqual(fields['token_timestamps'],'false')
        self.assertEqual(fields['no_language_probabilities'],'true')
        self.assertEqual(fields['language'],'de')
        self.assertEqual(fields['temperature'],'0')
        self.assertEqual(result,private_text.strip())
        self.assertFalse(http.kwargs['allow_redirects'])
        logged = ' '.join(logs.output)
        self.assertIn('avg_logprob_mean=-0.5000',logged)
        self.assertIn('no_speech_prob_max=0.3000',logged)
        self.assertNotIn('private employee',logged)
        self.assertNotIn('sensitive segment',logged)

    async def test_missing_malformed_nonfinite_segments_do_not_change_transcription(self):
        for segments in (None, 'wrong', {}, [None,[],{'avg_logprob':'secret','no_speech_prob':True},
                           {'avg_logprob':float('nan'),'no_speech_prob':float('inf')},
                           {'avg_logprob':-(10**1000),'no_speech_prob':10**1000}],
                         [{'avg_logprob':-.1,'no_speech_prob':.2}]*300):
            with self.subTest(kind=type(segments).__name__):
                http = HTTP({'text':' Recognized text. ','segments':segments})
                with self.assertLogs('native-voice',level='INFO') as logs:
                    result = await Speech(http,Config()).transcribe(bytes(3200))
                self.assertEqual(result,'Recognized text.')
                logged = ' '.join(logs.output)
                self.assertNotIn('secret',logged)
                self.assertNotIn('nan',logged)
                self.assertNotIn('inf',logged)
                if isinstance(segments,list) and len(segments)==300:
                    self.assertIn('segments=256',logged)
                    self.assertIn('truncated=True',logged)

    async def test_invalid_text_is_rejected_even_when_diagnostics_exist(self):
        for data in ({'text':4},{'text':'x'*4001},{},None,[]):
            with self.subTest(kind=type(data).__name__):
                with self.assertRaisesRegex(RuntimeError,'Invalid transcription'):
                    await Speech(HTTP(data),Config()).transcribe(bytes(3200))


if __name__ == '__main__':
    unittest.main()
