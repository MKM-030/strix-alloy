import asyncio
from contextlib import redirect_stdout
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import service as s
import auth_api
import lease_supervisor as lease

class ServiceTests(unittest.TestCase):
    @unittest.skipUnless((s.LOCAL/'entrypoint-wsl.sh').exists(),'Installed entrypoint required')
    def test_exact_installed_entrypoint_auth_wrapper(self):
        source=(s.LOCAL/'entrypoint-wsl.sh').read_bytes()
        result=s.service_entrypoint(source)
        self.assertEqual(result.count(b'python3 /candidate/auth_api.py'),4)
        self.assertNotIn(b'python3 /halogen/tools/serve_api.py',result)
        with self.assertRaises(ValueError): s.service_entrypoint(source+b'changed')

    def test_memory_admission_waits_for_safe_stable_window(self):
        clock=[0.0]; count=[0]
        class Host:
            def frame(self):
                count[0]+=1
                return {'available_bytes':(46 if count[0]<=5 else 48)*s.r.GIB,
                        'commit_headroom_bytes':200*s.r.GIB}
        def advance(seconds): clock[0]+=seconds
        with patch.object(s.r,'exclusive_host'), patch.object(s.time,'monotonic',side_effect=lambda:clock[0]), patch.object(s.time,'sleep',side_effect=advance):
            result=s.admission(Host(),129024,s.threading.Event(),Mock())
        self.assertGreaterEqual(clock[0],65)
        self.assertEqual(result['available_bytes'],48*s.r.GIB)

    def test_memory_admission_timeout_does_not_lower_floor(self):
        clock=[0.0]
        class Host:
            def frame(self): return {'available_bytes':46*s.r.GIB,'commit_headroom_bytes':200*s.r.GIB}
        def advance(seconds): clock[0]+=seconds
        with patch.object(s.r,'exclusive_host'), patch.object(s.time,'monotonic',side_effect=lambda:clock[0]), patch.object(s.time,'sleep',side_effect=advance):
            with self.assertRaisesRegex(ValueError,'did not stabilize'):
                s.admission(Host(),129024,s.threading.Event(),Mock())
        self.assertEqual(s.floors(129024),(47,121))

    def test_default_126k_and_continuous(self):
        o=s.options()
        self.assertEqual(o.context_size,129024)
        self.assertEqual(o.serve_seconds,0)
        self.assertEqual(o.startup_timeout,900)

    def test_context_parameter_changes_both_limits_not_slots(self):
        for context in [4096,126000,129024,262144]:
            o=s.options(['--context-size',str(context)])
            env=s.environment(o.context_size)
            self.assertEqual(env['HALOGEN_CTX'],str(context))
            self.assertEqual(env['HALOGEN_KV_POOL_POSITIONS'],str(context))
            self.assertEqual(env['HALOGEN_KV_SLOTS'],'1')
            self.assertEqual(env['HALOGEN_PROMPT_CACHE'],'0')

    def test_invalid_parameters_refuse(self):
        for flag,value in [('--context-size','4095'),('--context-size','262145'),
                           ('--serve-seconds','-1'),('--startup-timeout','119')]:
            with self.subTest(flag=flag,value=value), self.assertRaises(ValueError):
                s.options([flag,value])

    def test_finite_duration_is_explicit(self):
        self.assertEqual(s.options(['--serve-seconds','600']).serve_seconds,600)
        self.assertEqual(s.options(['--startup-timeout','1800']).serve_seconds,0)

    def test_memory_planning_scales_up_without_lowering_baseline(self):
        self.assertEqual(s.floors(4096),(45,117))
        self.assertEqual(s.floors(129024),(47,121))
        self.assertEqual(s.floors(262144),(51,125))
        phys,commit=s.floors(129024)
        s.check_admission({'available_bytes':phys*s.r.GIB,'commit_headroom_bytes':commit*s.r.GIB},129024)
        with self.assertRaises(ValueError):
            s.check_admission({'available_bytes':phys*s.r.GIB-1,'commit_headroom_bytes':commit*s.r.GIB},129024)

    def test_actual_health_context_must_match(self):
        good={'status':'ok','version':{'api':'0.14.2','engine':'0.14.2','match':True},
              'context':129024,'slot_ctx':129024,'kv_pool_positions':129024,'slots':1}
        s.validate_health(good,129024)
        for k in ['context','slot_ctx','kv_pool_positions','slots']:
            with self.subTest(key=k), self.assertRaises(ValueError):
                s.validate_health({**good,k:0},129024)
        with self.assertRaises(ValueError): s.validate_health({**good,'version':{}},129024)

    def test_container_uses_lease_not_hard_shutdown_and_only_loopback(self):
        m={'run_id':'a'*32,'mounts':{'/models':'/srv/models'},'environment':s.environment(129024)}
        cmd=s.command(m)
        self.assertNotIn('/usr/bin/timeout',cmd)
        self.assertIn('/candidate/lease_supervisor.py',cmd)
        self.assertIn('--restart=no',cmd)
        self.assertIn('127.0.0.1:8731:8731',cmd)
        self.assertIn('--log-opt=max-size=10m',cmd)
        self.assertIn('HALOGEN_CTX=129024',cmd)
        self.assertNotIn('300',cmd)
        self.assertNotIn('600',cmd)
        self.assertNotIn('0.0.0.0:8731:8731',cmd)
        self.assertFalse(any('TOKEN=' in x for x in cmd))

    def test_atomic_state_never_leaves_temp(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json'
            s.atomic(p,{'a':1}); s.atomic(p,{'a':2})
            self.assertEqual(s.read(p),{'a':2})
            self.assertEqual([v.name for v in Path(d).iterdir()],['state.json'])

    def test_unknown_container_never_stopped(self):
        info={'Id':'b'*64,'Config':{},'State':{'Running':True}}
        with patch.object(s.r,'inspect',return_value=info),patch.object(s.r,'docker') as docker:
            with self.assertRaises(ValueError): s.stop_owned('a'*64,{'run_id':'a'*32})
            docker.assert_not_called()

    def test_no_auth_token_in_manifest_sources(self):
        files=s.source_hashes()
        self.assertTrue(any(k.endswith('service.py') for k in files))
        self.assertFalse(any('.local' in k or 'api-token.txt' in k for k in files))

    def test_print_only_has_no_wsl_or_token_generation(self):
        with patch.object(s.r,'configure') as configure, patch.object(s,'token') as token, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(s.main(['--print-only']),0)
            self.assertEqual(json.loads(out.getvalue())['context'],129024)
            configure.assert_not_called(); token.assert_not_called()

class AuthTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self,headers,stream=False,path='/v1/chat/completions'):
        calls=[]; messages=[]
        async def app(scope,receive,send):
            calls.append(scope['type'])
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'first','more_body':stream})
            if stream: await send({'type':'http.response.body','body':b'second','more_body':False})
        async def receive(): return {'type':'http.request','body':b''}
        async def send(message): messages.append(message)
        wrapped=auth_api.BearerAuth(app,'a'*43)
        with redirect_stdout(io.StringIO()) as out:
            await wrapped({'type':'http','headers':headers,'path':path,
                           'method':'POST','query_string':b'secret=should-not-log'},receive,send)
        return calls,messages,out.getvalue()

    async def test_missing_wrong_duplicate_token_refused(self):
        for headers in [[],[(b'authorization',b'Bearer wrong')],
                        [(b'authorization',b'Bearer '+b'a'*43)]*2]:
            calls,messages,log=await self.invoke(headers)
            self.assertEqual(calls,[])
            self.assertEqual(messages[0]['status'],401)
            self.assertIn((b'www-authenticate',b'Bearer'),messages[0]['headers'])
            self.assertNotIn('should-not-log',log)

    async def test_valid_token_and_stream_pass_unbuffered(self):
        calls,messages,log=await self.invoke([(b'authorization',b'Bearer '+b'a'*43)],True)
        self.assertEqual(calls,['http'])
        self.assertEqual(messages[0]['status'],200)
        self.assertEqual([m['body'] for m in messages[1:]],[b'first',b'second'])
        self.assertNotIn('a'*43,log)
        self.assertNotIn('should-not-log',log)

    async def test_all_api_routes_and_health_are_protected(self):
        for path in ['/health','/v1/models','/v1/responses','/metrics']:
            _,messages,_=await self.invoke([],path=path)
            self.assertEqual(messages[0]['status'],401)

    async def test_lifespan_is_not_blocked(self):
        calls=[]
        async def app(*args): calls.append(args[0]['type'])
        wrapped=auth_api.BearerAuth(app,'a'*43)
        await wrapped({'type':'lifespan'},None,None)
        self.assertEqual(calls,['lifespan'])

    def test_bad_configured_token_refused(self):
        for value in ['', 'a'*42,'unsafe token']:
            with self.assertRaises(ValueError): auth_api.BearerAuth(None,value)

class LeaseTests(unittest.TestCase):
    def test_fresh_stale_missing_future_wrong_identity(self):
        self.assertTrue(lease.fresh({'run_id':'x','time':100},'x',120))
        for record in [{'run_id':'x','time':1},{'run_id':'y','time':100},
                       {'run_id':'x','time':float('nan')},{'run_id':'x','time':True},
                       {'run_id':'x','time':200},{}]:
            self.assertFalse(lease.fresh(record,'x',120))

if __name__=='__main__': unittest.main()
