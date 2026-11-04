"""Offline exact-method CSTAT fixtures; no engine, API server or network starts."""
import ast
import asyncio
import copy
import hashlib
import importlib.util
import json
import io
import os
import textwrap
from pathlib import Path
import sys
import tempfile
import types
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
AUTH=ROOT/'backends/halogen-wsl2-0.18.22/scripts/auth_api.py'
FIXTURE=ROOT/'server/tests/fixtures/halogen01822_cache_stats.py'
PROVENANCE=json.loads(FIXTURE.with_suffix('.provenance.json').read_text(encoding='utf-8'))
RETAINED=Path(os.environ.get('HALOGEN_RETAINED_API','C:/Projects/strix-alloy-clean/server/.local/halogen-update-20261101/primary01822/extracted/serve_api.py'))
COLLECTOR=Path(os.environ.get('HALOGEN_CACHE_COLLECTOR','C:/Projects/strix-alloy-clean/server/.local/voice-repair-20261102/voice-overlap-qualification-20261103/overlap-lifecycle-fix-20261104/collect_overlap.py'))
API_SHA='0fc902343a816feb7a933f67c773e98025d8d09b55711545d874d6cddc07ea08'
OFF='C 0 0 0 0 0 0 0 0 0 0.0 0.0 0.0 0.0 0 0 0.0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.0 0 0 0 %d %.1f %ld %ld %d %d %d %d %ld %ld %ld'
ENABLED='C %d %lld %lld %lld %ld %ld %ld %ld %lld %.1f %.1f %.1f %.1f %ld %ld %.1f %ld %d %lld %ld %ld %ld %lld %d %d %d %lld %lld %ld %ld %ld %ld %ld %ld %.1f %lld %ld %ld %d %.1f %ld %ld %d %d %d %d %ld %ld %ld %ld %ld %s %ld %ld %ld %ld'


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


auth=load('cache_wire_auth_under_test',AUTH)
collector=load('cache_wire_quiescence_under_test',COLLECTOR) if COLLECTOR.is_file() else None
SOURCE=FIXTURE.read_bytes()
FIXTURE_SHA=hashlib.sha256(SOURCE).hexdigest()
assert FIXTURE_SHA==PROVENANCE['fixture_sha256']


def off(positions=32768,busy=0,held=7):
    return OFF % (2,.7,13,17,19,positions,busy,held,23,29,31)


def enabled():
    values=['C']+[str(n+100) for n in range(1,57)]
    for index in [10,11,12,13,16,35,40]:values[index]='1.2'
    values[36]='1234567890123456789';values[44]='65536';values[45]='6';values[46]='7';values[52]='/cache-root'
    return ' '.join(values)


def actual_engine(line,slots=1,patched=True):
    tree=ast.parse(SOURCE)
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Engine')
    method=next(n for n in node.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='cache_stats')
    namespace=dict(__name__='__main__',asyncio=asyncio,time=time,HTTPException=RuntimeError)
    module=ast.Module(body=[ast.ClassDef(name='Engine',bases=[],keywords=[],body=[copy.deepcopy(method)],decorator_list=[])],type_ignores=[])
    exec(compile(ast.fix_missing_locations(module),auth.UPSTREAM,'exec'),namespace)
    if patched:
        install=getattr(auth,'install_cache_stats',None)
        if not callable(install):raise AssertionError('Version-bound cache_stats correction is missing')
        with patch.object(auth,'UPSTREAM_SHA256',FIXTURE_SHA):install(namespace,SOURCE)
    engine=namespace['Engine']();engine.n_slots=slots;engine.cstat=asyncio.Queue()
    engine.wlock=asyncio.Lock();engine.slots=asyncio.Semaphore(1);engine._cstat_last=None;engine._cstat_at=None
    engine.commands=[];engine.pool_notes=[]
    async def ensure():pass
    async def drain():pass
    async def readline():return (line+'\n').encode()
    def write(value):
        engine.commands.append(value)
        if slots>1:engine.cstat.put_nowait(line.split())
    engine._ensure=ensure;engine.w=SimpleNamespace(write=write,drain=drain);engine.r=SimpleNamespace(readline=readline)
    engine._note_pool=engine.pool_notes.append
    return engine,namespace


def quiescence(cache,queued=0):
    evidence=dict(exclusive_owned_pair=True,owner_seal_before='owned',owner_seal_after='owned',
        health=dict(route='/health',source='native',observed_ns=100,body=dict(status='ok',in_flight=0,queued=queued)),
        cache=dict(route='/cache',source='native',observed_ns=100,body=cache))
    return collector.validate_quiescence(dict(owner_seal='owned'),evidence,now_ns=100,after_ns=99)


class CacheWire(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):asyncio.get_running_loop().slow_callback_duration=10
    async def test_fixture_provenance_and_default_runtime_pins_remain_exact(self):
        self.assertEqual(PROVENANCE['full_api_sha256'],API_SHA)
        self.assertEqual(auth.UPSTREAM_SHA256,API_SHA)
        release=json.loads((ROOT/'backends/halogen-wsl2-0.18.22/profiles/release.json').read_text(encoding='utf-8'))
        self.assertEqual(auth.ENGINE_SHA256,release['engine_sha256'])
        self.assertEqual(PROVENANCE['engine_sha256'],release['engine_sha256'])
        self.assertEqual(hashlib.sha256(OFF.encode()).hexdigest(),PROVENANCE['producer_layouts']['cacheDisabledLiteral']['formatSha256'])
        self.assertEqual(hashlib.sha256(ENABLED.encode()).hexdigest(),PROVENANCE['producer_layouts']['enabled']['formatSha256'])

    @unittest.skipUnless(RETAINED.is_file(),'Optional retained full API source is unavailable')
    async def test_local_full_pinned_api_proves_portable_method_fixture_is_exact(self):
        source=RETAINED.read_bytes();self.assertEqual(hashlib.sha256(source).hexdigest(),API_SHA)
        tree=ast.parse(source);engine=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Engine')
        method=next(n for n in engine.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='cache_stats')
        text=textwrap.dedent(''.join(source.decode().splitlines(keepends=True)[method.lineno-1:method.end_lineno]))
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),PROVENANCE['method_source_sha256'])
        fixture_tree=ast.parse(SOURCE);self.assertEqual(ast.dump(method),ast.dump(fixture_tree.body[0].body[0]))

    @unittest.skipUnless(RETAINED.is_file(),'Optional retained full API source is unavailable')
    async def test_full_pinned_module_compilation_context_installs_and_parses_without_executing_module(self):
        source=RETAINED.read_bytes();code=compile(source,auth.UPSTREAM,'exec',dont_inherit=True)
        class_code=next(value for value in code.co_consts if isinstance(value,types.CodeType) and value.co_name=='Engine')
        method_code=next(value for value in class_code.co_consts if isinstance(value,types.CodeType) and value.co_name=='cache_stats')
        for slots in [1,2]:
            engine,_=actual_engine(off(),slots,patched=False)
            namespace=dict(__name__='__main__',asyncio=asyncio,time=time,HTTPException=RuntimeError)
            original=types.FunctionType(method_code,namespace,'cache_stats')
            cls=type('Engine',(),{'cache_stats':original});namespace['Engine']=cls
            full_engine=cls();full_engine.__dict__.update(engine.__dict__)
            auth.install_cache_stats(namespace,source)
            self.assertEqual((await full_engine.cache_stats())['pool']['positions'],32768)

    async def test_original_pinned_method_reproduces_saved_0_point_0_failure(self):
        engine,_=actual_engine(off(),patched=False)
        with self.assertRaisesRegex(ValueError,'0.0'):await engine.cache_stats()

    async def test_exact_off_producer_preserves_all_differentiated_live_fields_both_slots_and_pools(self):
        for slots in [1,2]:
            for positions in [32768,65536]:
                for busy in [0,6]:
                    with self.subTest(slots=slots,positions=positions,busy=busy):
                        engine,_=actual_engine(off(positions,busy),slots)
                        result=await engine.cache_stats()
                        self.assertEqual(result['pool'],dict(waiting_for_room=2,waiting_s=.7,relocated=13,cold_resorts=17,
                            used=19,positions=positions,busy_regions=busy,held_regions=7,room_clamped=23,moved=29,packed=31))
                        self.assertEqual(result['disk']['restored_bytes'],0)
                        self.assertEqual(engine.commands,[b'CSTAT\n'])
                        self.assertEqual(engine.pool_notes,[dict(pool_used='19',pool_positions=str(positions))])
                        self.assertEqual(engine._cstat_last,result)
                        self.assertNotIn('dropped',result);self.assertNotIn('cache_root',result)
                        self.assertNotIn('taken_over',result['pool']);self.assertNotIn('grown',result['pool'])

    async def test_enabled57_behavior_and_large_integer_are_unchanged(self):
        for slots in [1,2]:
            old,_=actual_engine(enabled(),slots,patched=False);new,_=actual_engine(enabled(),slots)
            self.assertEqual(await old.cache_stats(),await new.cache_stats())
            self.assertEqual(new._cstat_last['disk']['restored_bytes'],1234567890123456789)
            self.assertEqual(new._cstat_last['pool']['busy_regions'],6)

    @unittest.skipUnless(collector is not None,'Optional saved collector source is unavailable')
    async def test_real_corrected_idle_reply_enters_existing_quiescence_guard(self):
        engine,_=actual_engine(off())
        self.assertEqual(quiescence(await engine.cache_stats())['proof_scope'],'exclusive_owned_pair_quiescence')

    @unittest.skipUnless(collector is not None,'Optional saved collector source is unavailable')
    async def test_real_corrected_busy6_held7_reply_still_refuses_existing_guard(self):
        engine,_=actual_engine(off(busy=6))
        with self.assertRaisesRegex(ValueError,'CSTAT quiescence'):quiescence(await engine.cache_stats())

    @unittest.skipUnless(collector is not None,'Optional saved collector source is unavailable')
    async def test_nonzero_native_queue_and_stale_cache_still_refuse_existing_guard(self):
        engine,_=actual_engine(off());cache=await engine.cache_stats()
        with self.assertRaisesRegex(ValueError,'health quiescence'):quiescence(cache,queued=1)
        with self.assertRaisesRegex(ValueError,'CSTAT quiescence'):quiescence(dict(cache,stale_s=.1))

    async def test_unknown_or_truncated_wire_never_becomes_idle_reply(self):
        base=off().split()
        cases=[base[:-1],base+['0'],['X']+base[1:],base[:35]+['1']+base[36:],base[:1]+['1']+base[2:]]
        for tokens in cases:
            engine,_=actual_engine(' '.join(tokens))
            with self.assertRaises(ValueError):await engine.cache_stats()
            self.assertIsNone(engine._cstat_last)

    async def test_off_live_suffix_never_coerces_nonintegers_negative_or_nonfinite_values(self):
        for index,value in [(40,'0.0'),(41,'nan'),(41,'inf'),(41,'-0.7'),(42,'13.0'),(45,'32768.0'),(46,'6.0'),(47,'7.0'),(50,'31.0')]:
            tokens=off().split();tokens[index]=value;engine,_=actual_engine(' '.join(tokens))
            with self.assertRaises(ValueError):await engine.cache_stats()

    async def test_version_drift_or_second_install_refuses(self):
        engine,namespace=actual_engine(off())
        with patch.object(auth,'UPSTREAM_SHA256',FIXTURE_SHA):
            with self.assertRaises(ValueError):auth.install_cache_stats(namespace,SOURCE)
            _,namespace=actual_engine(off(),patched=False)
            with self.assertRaises(ValueError):auth.install_cache_stats(namespace,SOURCE+b'\n')

    async def test_real_multislot_timeout_preserves_stale_cache_and_unavailable_failure(self):
        engine,namespace=actual_engine(off(),slots=2)
        cache=await engine.cache_stats();engine.w.write=engine.commands.append
        engine._cstat_at=time.monotonic()-1
        async def timeout(coroutine,**kwargs):coroutine.close();raise asyncio.TimeoutError()
        with patch.object(namespace['asyncio'],'wait_for',side_effect=timeout):
            stale=await engine.cache_stats()
            self.assertGreaterEqual(stale['stale_s'],1)
            self.assertEqual(stale['pool'],cache['pool'])
            self.assertNotIn('stale_s',engine._cstat_last)
            engine._cstat_last=None
            with self.assertRaises(RuntimeError) as caught:await engine.cache_stats()
            self.assertEqual(caught.exception.args[0],503)

    async def test_enabled_tokens_are_not_copied_or_rewritten(self):
        tokens=enabled().split();normalize=getattr(auth,'normalize_cache_tokens',None)
        self.assertTrue(callable(normalize),'Strict normalizer is missing')
        self.assertIs(normalize(tokens),tokens)


class WrapperIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):asyncio.get_running_loop().slow_callback_duration=10

    def setup_wrapper(self, binary):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        token=Path(directory.name)/'token.txt';token.write_text('a'*43,encoding='ascii')
        server=types.ModuleType('uvicorn');calls=[]
        def run(app,*args,**kwargs):calls.append((app,args,kwargs))
        server.run=run
        namespace_holder={}
        def upstream(path,run_name):
            self.assertEqual(path,str(FIXTURE));self.assertEqual(run_name,'__main__')
            engine,namespace=actual_engine(off(),patched=False)
            namespace_holder.update(engine=engine,namespace=namespace)
            module=types.ModuleType('__main__');module.__dict__.update(namespace)
            # Functions must share runpy's actual temporary module namespace.
            actual=engine.cache_stats
            replacement=types.FunctionType(actual.__code__,module.__dict__,actual.__name__)
            module.Engine.cache_stats=replacement
            with patch.dict(sys.modules,{'__main__':module}):
                server.run(object(),host='127.0.0.1',port=8731,access_log=True)
            return module.__dict__
        stack=self.enterContext(__import__('contextlib').ExitStack())
        stack.enter_context(patch.object(auth,'UPSTREAM',str(FIXTURE)))
        stack.enter_context(patch.object(auth,'UPSTREAM_SHA256',FIXTURE_SHA))
        stack.enter_context(patch.object(auth,'ENGINE_SHA256',hashlib.sha256(b'portable test engine pin').hexdigest()))
        stack.enter_context(patch.object(auth,'TOKEN_FILE',token))
        stack.enter_context(patch.object(auth,'ENGINE',binary,create=True))
        stack.enter_context(patch.dict(sys.modules,{'uvicorn':server}))
        stack.enter_context(patch.object(auth.runpy,'run_path',side_effect=upstream))
        return calls,namespace_holder

    async def test_existing_uvicorn_interception_installs_fix_before_authenticated_serving(self):
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/'flash_serve';binary.write_bytes(b'portable test engine pin')
            calls,holder=self.setup_wrapper(binary)
            auth.main()
        self.assertEqual(len(calls),1);self.assertIsInstance(calls[0][0],auth.BearerAuth)
        self.assertFalse(calls[0][2]['access_log']);self.assertEqual(calls[0][2]['port'],8731)
        self.assertEqual((await holder['engine'].cache_stats())['pool']['positions'],32768)

    async def test_real_runpy_temporary_main_installs_before_uvicorn(self):
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory)/'serve_api.py'
            script.write_bytes(b'import asyncio, time\n'+SOURCE+b'\nimport uvicorn\nuvicorn.run(object(), port=8731)\n')
            binary=Path(directory)/'flash_serve';binary.write_bytes(b'portable test engine pin')
            token=Path(directory)/'token';token.write_text('a'*43)
            server=types.ModuleType('uvicorn');calls=[]
            def run(app,**kwargs):
                calls.append(app)
                namespace=vars(sys.modules['__main__'])
                self.assertIn(auth._CACHE_WIRE_HELPER,namespace)
                self.assertIs(namespace['Engine'].cache_stats.__globals__,namespace)
            server.run=run
            with patch.object(auth,'UPSTREAM',str(script)),patch.object(auth,'UPSTREAM_SHA256',hashlib.sha256(script.read_bytes()).hexdigest()), \
                    patch.object(auth,'ENGINE',binary),patch.object(auth,'ENGINE_SHA256',hashlib.sha256(binary.read_bytes()).hexdigest()), \
                    patch.object(auth,'TOKEN_FILE',token),patch.dict(sys.modules,{'uvicorn':server}):
                auth.main()
            self.assertEqual(len(calls),1)
            self.assertIsInstance(calls[0],auth.BearerAuth)

    async def test_real_runpy_changed_method_refuses_before_authenticated_serving(self):
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory)/'serve_api.py'
            script.write_bytes(b'import asyncio, time\n'+SOURCE+b'\nasync def changed(self): return {}\nEngine.cache_stats=changed\nimport uvicorn\nuvicorn.run(object())\n')
            binary=Path(directory)/'flash_serve';binary.write_bytes(b'portable test engine pin')
            token=Path(directory)/'token';token.write_text('a'*43)
            server=types.ModuleType('uvicorn');calls=[];server.run=lambda *a,**k:calls.append(a)
            with patch.object(auth,'UPSTREAM',str(script)),patch.object(auth,'UPSTREAM_SHA256',hashlib.sha256(script.read_bytes()).hexdigest()), \
                    patch.object(auth,'ENGINE',binary),patch.object(auth,'ENGINE_SHA256',hashlib.sha256(binary.read_bytes()).hexdigest()), \
                    patch.object(auth,'TOKEN_FILE',token),patch.dict(sys.modules,{'uvicorn':server}):
                with self.assertRaisesRegex(ValueError,'method changed'):auth.main()
            self.assertEqual(calls,[])

    async def test_engine_identity_change_refuses_before_upstream_or_server(self):
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/'flash_serve';binary.write_bytes(b'different engine')
            calls,_=self.setup_wrapper(binary)
            with self.assertRaisesRegex(ValueError,'engine identity'):auth.main()
            self.assertEqual(calls,[]);auth.runpy.run_path.assert_not_called()

    async def test_bearer_auth_still_blocks_missing_duplicate_and_wrong_headers(self):
        reached=[];messages=[]
        async def app(scope,receive,send):
            reached.append(scope['path'])
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'{}'})
        async def receive():return {'type':'http.request','body':b''}
        async def send(value):messages.append(value)
        wrapped=auth.BearerAuth(app,'a'*43)
        for headers in [[],[(b'authorization',b'Bearer wrong')],[(b'authorization',b'Bearer '+b'a'*43)]*2]:
            messages.clear()
            await wrapped(dict(type='http',method='GET',path='/cache',headers=headers),receive,send)
            self.assertEqual(messages[0]['status'],401);self.assertEqual(reached,[])
        await wrapped(dict(type='http',method='GET',path='/cache',headers=[(b'authorization',b'Bearer '+b'a'*43)]),receive,send)
        self.assertEqual(reached,['/cache'])


if __name__=='__main__':unittest.main()
