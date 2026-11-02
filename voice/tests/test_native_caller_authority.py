"""Native server response is the only identity authority; no real HTTP occurs."""
import asyncio
import json
import unittest
from voice.caller_binding import (CallerBinding, resolve_native_caller, validated_binding,
                                   refresh_native_caller_session)

SERVICE='8aa131d793f787105c8132d47aba1095'
AGENT='a6337ddf93f787105c8132d47aba1058'
PROFILE='c623e20f93374354e7f2b9fa6aba1081'
TOKEN='Bearer original.voice.credential'


def response():
    return {'result':{'authorized_agents':[AGENT],
        'assistant_settings':{'version':1,'service_id':SERVICE,'context_profile':PROFILE},
        'caller_binding':{'version':1,'service_id':SERVICE,'context_profile':PROFILE,
            'user_id':'1'*32,'user_name':'actual.username','email':'actual.email@example.test',
            'email_mapping_unique':True}}}


class CallerProjectionTests(unittest.TestCase):
    def test_exact_server_identity_is_private_and_not_subject_as_email(self):
        result=validated_binding(response(),SERVICE,AGENT,PROFILE)
        self.assertEqual(result.email,'actual.email@example.test')
        self.assertEqual(result.user_id,'1'*32)
        self.assertNotIn('actual',repr(result));self.assertNotIn('1'*32,repr(result))

    def test_wrong_or_incomplete_authority_never_produces_binding(self):
        changes=[('binding','version',True),('binding','service_id','f'*32),
            ('binding','context_profile','f'*32),('binding','user_id','bad'),
            ('binding','user_name','guest'),('binding','email','x@example.test^ORactive=true'),
            ('binding','email','x@example.test\nAuthorization: fake'),
            ('binding','email_mapping_unique',False),('binding','email_mapping_unique',1),
            ('settings','service_id','f'*32),('settings','context_profile','f'*32),('settings','version',True)]
        for target,key,value in changes:
            with self.subTest(target=target,key=key,value=value):
                data=response();obj=data['result']['caller_binding' if target=='binding' else 'assistant_settings'];obj[key]=value
                with self.assertRaises(ValueError):validated_binding(data,SERVICE,AGENT,PROFILE)
        for agents in ([],['f'*32],[AGENT,AGENT],['not-an-agent']):
            with self.subTest(agents=agents):
                data=response();data['result']['authorized_agents']=agents
                with self.assertRaises(ValueError):validated_binding(data,SERVICE,AGENT,PROFILE)
        for field in response()['result']['caller_binding']:
            data=response();del data['result']['caller_binding'][field]
            with self.subTest(missing=field), self.assertRaises(ValueError):validated_binding(data,SERVICE,AGENT,PROFILE)


class Body:
    def __init__(self,raw):self.raw=raw
    async def iter_chunked(self,count):
        for n in range(0,len(self.raw),count):yield self.raw[n:n+count]


class Response:
    def __init__(self,raw,status=200,headers=None):
        self.status=status;self.headers=headers or {'Content-Type':'application/json'};self.content=Body(raw)
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass


class NativeAuthorityWireTests(unittest.IsolatedAsyncioTestCase):
    def factory(self,*,raw=None,status=200,headers=None,error=False):
        self.created=[];self.sent=[]
        owner=self
        class HTTP:
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            def post(self,url,**kwargs):
                owner.sent.append((url,kwargs))
                if error:raise RuntimeError('sensitive network detail '+TOKEN)
                return Response(raw if raw is not None else json.dumps(response()).encode(),status,headers)
        def factory(**kwargs):self.created.append(kwargs);return HTTP()
        return factory

    async def resolve(self,factory):
        return await resolve_native_caller('https://instance.example.test',SERVICE,AGENT,PROFILE,TOKEN,http_factory=factory)

    async def test_fixed_native_post_uses_original_bearer_without_cookie_env_or_redirect(self):
        result=await self.resolve(self.factory())
        self.assertEqual(result.email,'actual.email@example.test')
        self.assertEqual(len(self.sent),1)
        url,options=self.sent[0]
        self.assertEqual(url,'https://instance.example.test/api/sn_voice_aia/ai_voice_agent/agents_authorized')
        self.assertEqual(options['headers']['Authorization'],TOKEN)
        self.assertEqual(options['json'],{'serviceId':SERVICE,'assistantSettingsVersion':1,'callerBindingVersion':1})
        self.assertFalse(options['allow_redirects'])
        self.assertFalse(self.created[0]['trust_env']);self.assertFalse(self.created[0]['auto_decompress'])
        self.assertEqual(type(self.created[0]['cookie_jar']).__name__,'DummyCookieJar')

    async def test_denial_redirect_oversize_invalid_json_duplicate_or_encoding_never_retries(self):
        for options in ({'status':401},{'status':403},{'status':302},
                {'raw':b'not json'}, {'raw':b'{"result":1,"result":2}'},
                {'raw':b'x'*131073}, {'headers':{'Content-Type':'application/json','Content-Encoding':'gzip'}},
                {'headers':{'Content-Type':'text/html'}},{'error':True}):
            with self.subTest(options={k:len(v) if k=='raw' else v for k,v in options.items()}):
                factory=self.factory(**options)
                with self.assertRaisesRegex(ValueError,'^Native caller binding unavailable$'):
                    await self.resolve(factory)
                self.assertEqual(len(self.sent),1)


class NativeRefreshWireTests(unittest.IsolatedAsyncioTestCase):
    factory=NativeAuthorityWireTests.factory
    owned={'conversation_id':'3'*32,'interaction_id':'4'*32,'create_message_id':'5'*32}

    def acknowledgement(self):
        data=response()
        data['result']['conversation_authentication']={'version':1,'refresh_requested':True,
            'service_id':SERVICE,'context_profile':PROFILE,**self.owned}
        return data

    async def refresh(self,data,**kwargs):
        return await refresh_native_caller_session('https://instance.example.test',SERVICE,AGENT,PROFILE,
            TOKEN,dict(self.owned),CallerBinding('1'*32,'actual.email@example.test'),
            http_factory=self.factory(raw=json.dumps(data).encode(),**kwargs))

    async def test_exact_owned_refresh_is_distinct_from_projection_and_does_not_claim_authentication(self):
        self.assertIsNone(await self.refresh(self.acknowledgement()))
        self.assertEqual(len(self.sent),1)
        payload=self.sent[0][1]['json']
        self.assertEqual(payload,{'serviceId':SERVICE,'assistantSettingsVersion':1,'callerBindingVersion':1,
            'conversationAuthenticationVersion':1,'conversationId':'3'*32,'interactionId':'4'*32,'createMessageId':'5'*32})
        self.assertEqual(self.sent[0][1]['headers']['Authorization'],TOKEN)
        self.assertNotIn('userId',payload);self.assertNotIn('email',payload);self.assertNotIn('clientApp',payload)

    async def test_missing_changed_ambiguous_or_false_refresh_ack_never_succeeds_or_retries(self):
        for key,value in [('version',True),('refresh_requested',False),('refresh_requested',1),
                ('service_id','f'*32),('context_profile','f'*32),('conversation_id','f'*32),
                ('interaction_id','f'*32),('create_message_id','f'*32),('authenticated',True)]:
            data=self.acknowledgement();data['result']['conversation_authentication'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):await self.refresh(data)
            self.assertEqual(len(self.sent),1)
        data=response()
        with self.assertRaises(ValueError):await self.refresh(data)
        for key in ('user_id','email'):
            data=self.acknowledgement();data['result']['caller_binding'][key]='2'*32 if key=='user_id' else 'changed@example.test'
            with self.subTest(changed=key),self.assertRaises(ValueError):await self.refresh(data)

    async def test_refresh_denial_is_not_replayed(self):
        with self.assertRaises(ValueError):await self.refresh(self.acknowledgement(),status=403)
        self.assertEqual(len(self.sent),1)

    async def test_metadata_response_cannot_outlive_remaining_bootstrap_budget(self):
        sent=[]
        class NeverBody:
            async def iter_chunked(self,count):
                await asyncio.Event().wait()
                yield b''
        class HTTP:
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            def post(self,url,**kwargs):
                sent.append(kwargs)
                reply=Response(b'')
                reply.content=NeverBody()
                return reply
        with self.assertRaisesRegex(ValueError,'^Native caller binding unavailable$'):
            await refresh_native_caller_session('https://instance.example.test',SERVICE,AGENT,PROFILE,
                TOKEN,dict(self.owned),CallerBinding('1'*32,'actual.email@example.test'),
                timeout_seconds=.01,http_factory=lambda **kwargs:HTTP())
        self.assertEqual(len(sent),1)

    async def test_caller_cancellation_propagates_without_retry(self):
        entered=asyncio.Event();sent=[]
        class NeverBody:
            async def iter_chunked(self,count):
                entered.set();await asyncio.Event().wait()
                yield b''
        class HTTP:
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            def post(self,url,**kwargs):
                sent.append(kwargs)
                reply=Response(b'');reply.content=NeverBody();return reply
        task=asyncio.create_task(refresh_native_caller_session('https://instance.example.test',
            SERVICE,AGENT,PROFILE,TOKEN,dict(self.owned),CallerBinding('1'*32,'actual.email@example.test'),
            http_factory=lambda **kwargs:HTTP()))
        await asyncio.wait_for(entered.wait(),1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(len(sent),1)


if __name__=='__main__':unittest.main()
