"""Original credential is a one-use loopback bootstrap, never public context."""
import unittest
from native_bridge import Config, Dialog
from assistant_settings import CallSettings
from test_assistant_settings import authorized_settings, SERVICE, AGENT

TOKEN = 'Bearer original.voice.credential'


class CallerBootstrapTests(unittest.IsolatedAsyncioTestCase):
    def dialog(self, *, started=False, failure=False, backend='http://127.0.0.1:8850'):
        d = Dialog(Config(backend_url=backend), CallSettings.from_authorized_response(authorized_settings(), SERVICE, AGENT))
        self.addAsyncCleanup(d.shutdown)
        sent = []
        async def request(method, path, **kwargs):
            sent.append((method, path, kwargs))
            if path == '/api/session': return {'csrf':'csrf', 'started':started, 'serviceNowEnabled':True}
            if path == '/api/start':
                if failure: raise RuntimeError('fixed synthetic failure')
                return {'accepted':True}
            if path == '/api/events': return {'cursor':1, 'events':[], 'busy':False}
            raise AssertionError(path)
        d.request = request
        return d, sent

    async def test_original_bearer_only_in_single_bootstrap_and_replay_refused(self):
        d, sent = self.dialog()
        getattr(d, 'bind_caller_authorization', lambda _:None)(TOKEN)
        self.assertEqual(await d.open(), [])
        starts = [v for v in sent if v[1] == '/api/start']
        self.assertEqual(starts[0][2].get('caller_authorization'), TOKEN)
        self.assertEqual(sum(TOKEN in repr(x) for x in sent), 1)
        with self.assertRaises(RuntimeError): await d.open()
        self.assertNotIn(TOKEN, repr(d.__dict__))

    async def test_failed_bootstrap_retires_bearer_and_never_retries(self):
        d, sent = self.dialog(failure=True)
        getattr(d, 'bind_caller_authorization', lambda _:None)(TOKEN)
        with self.assertRaises(RuntimeError): await d.open()
        self.assertNotIn(TOKEN, repr(d.__dict__))
        with self.assertRaises(RuntimeError): await d.open()
        self.assertEqual(sum(path == '/api/start' for _,path,_ in sent), 1)

    async def test_preexisting_cookie_cannot_bind_a_new_caller(self):
        d, sent = self.dialog(started=True)
        getattr(d, 'bind_caller_authorization', lambda _:None)(TOKEN)
        with self.assertRaises(RuntimeError): await d.open()
        self.assertFalse(any(path == '/api/start' for _,path,_ in sent))
        self.assertNotIn(TOKEN, repr(d.__dict__))

    async def test_shutdown_without_offer_retires_credential(self):
        d, _ = self.dialog()
        getattr(d, 'bind_caller_authorization', lambda _:None)(TOKEN)
        await d.shutdown()
        with self.assertRaises(RuntimeError): await d.open()

    async def test_partial_create_binding_is_private_until_complete_then_immutable(self):
        d, _ = self.dialog()
        binding = {'source':'servicenow_create_conversation','conversationId':'a'*32,
                   'creationMessageId':'b'*32,'createRequestId':'c'*32}
        d.observe_state({'conversationBinding':binding})
        self.assertFalse(any(d.metadata.values()))
        complete = dict(binding,interactionId='d'*32)
        d.observe_state({'conversationBinding':complete})
        self.assertEqual(d.metadata,{'conversation_id':'a'*32,'creation_message_id':'b'*32,
                                   'create_request_id':'c'*32,'interaction_id':'d'*32})
        d.observe_state({'conversationBinding':binding})
        self.assertEqual(d.metadata['interaction_id'],'d'*32)
        with self.assertRaisesRegex(RuntimeError,'binding changed'):
            d.observe_state({'conversationBinding':dict(complete,interactionId='e'*32)})
        self.assertEqual(d.metadata['interaction_id'],'d'*32)

    async def test_credential_never_sent_to_nonloopback_backend(self):
        d, sent = self.dialog(backend='https://foreign.example.test')
        getattr(d, 'bind_caller_authorization', lambda _:None)(TOKEN)
        with self.assertRaises(RuntimeError): await d.open()
        self.assertEqual(sent, [])
        self.assertNotIn(TOKEN, repr(d.__dict__))

    async def test_request_header_guard_cannot_be_bypassed_by_direct_internal_request(self):
        d = Dialog(Config(backend_url='https://foreign.example.test'))
        class HTTP:
            def request(self,*args,**kwargs):raise AssertionError('credential escaped its boundary')
        d.http=HTTP()
        with self.assertRaises(RuntimeError):
            await d.request('POST','/api/start',caller_authorization=TOKEN,json={})


if __name__ == '__main__': unittest.main()
