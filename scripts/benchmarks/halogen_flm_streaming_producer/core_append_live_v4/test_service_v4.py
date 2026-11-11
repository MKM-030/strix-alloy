"""CPU-only v4 factory/ownership tests; no DLL, socket or accelerator is used."""
import hashlib
import ast
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import service_request_scoped_v4 as m
from actor import OwnedRow,prefix_hash
from request_scoped_backend import RequestScopedBackend
from service import ProducerWorker,ENGINE,TOKENIZER


class FakeNative:
    def __init__(self,*args):
        self.handle=71;self.states={};self.operations=[];self.history=();self.state_id=0
        self.owner=threading.get_ident();self.append_head_skip_enabled=False;self.head_skip_identity=None
        self.count=0;self.restored=True;self.enable_fail=False;self.close_fail=False;self.close_calls=0;self.set_calls=[]
    def head_skip_status(self):return dict(count=self.count,restored=self.restored)
    def set_append_head_skip(self,value):
        self.set_calls.append(value)
        if self.enable_fail:raise RuntimeError('injected enable failure')
        self.append_head_skip_enabled=value
        if value:self.head_skip_identity=dict(path='CPU fake',sha256=m.QWEN_SHA256)
    def row(self):
        return OwnedRow((self.history[-1]+1)%248070,hashlib.sha256(struct.pack('<%di'%len(self.history),*self.history)).digest())
    def seed(self,ids):self.history=tuple(ids);self.operations.append(dict(operation='seed'));return self.row()
    def forward(self,token):self.history+=(token,);self.operations.append(dict(operation='forward'));return self.row()
    def append_only(self,token):
        self.history+=(token,);self.operations.append(dict(operation='append_only'))
        if self.append_head_skip_enabled:self.count+=1
    def context_length(self):return len(self.history)
    def save(self):self.state_id+=1;self.states[self.state_id]=self.history;return self.state_id
    def restore(self,state):self.history=self.states[state];return len(self.history)
    def free(self,state):del self.states[state]
    def close(self):
        self.close_calls+=1
        if self.close_fail:raise RuntimeError('injected native close failure')
        self.handle=None;self.states.clear();self.append_head_skip_enabled=False


class Tests(unittest.TestCase):
    def factory(self,enabled=True,native=None):
        self.assertTrue(hasattr(m,'UnusedHeadFactory'),'Genuine opt-in v4 factory is not implemented')
        created=[]
        def construct(*args):
            backend=native or FakeNative(*args);created.append(backend);return backend
        return m.UnusedHeadFactory('fake.dll','model','bundle','runtime',enabled=enabled,native_factory=construct),created

    def test_default_off_never_selects_head_skip_and_reports_zero_restored(self):
        factory,created=self.factory(enabled=False);backend=factory()
        self.assertEqual(created[0].set_calls,[]);self.assertFalse(backend.append_head_skip_enabled)
        backend.close();result=factory.report()
        self.assertFalse(result['unused_head_append_enabled']);self.assertEqual(result['head_skip_count'],0)
        self.assertTrue(result['head_instructions_restored']);self.assertTrue(result['head_contexts_cleanup_complete'])

    def test_explicit_enable_occurs_before_seed_and_terminal_counter_survives_close(self):
        factory,created=self.factory();backend=factory();self.assertEqual(created[0].set_calls,[True])
        backend.seed([1]*512);backend.append_only(2);backend.append_only(3);backend.forward(4);backend.close()
        result=factory.report();self.assertEqual(result['head_skip_count'],2)
        context=result['head_contexts'][0]
        self.assertTrue(context['enabled_at_seed']);self.assertEqual(context['initial_status'],dict(count=0,restored=True))
        self.assertEqual(context['terminal_status'],dict(count=2,restored=True));self.assertTrue(context['native_closed'])
        self.assertEqual(context['owner_thread_id'],threading.get_ident());self.assertEqual(context['provider_identity']['sha256'],m.QWEN_SHA256)

    def test_enable_failure_closes_created_backend_and_rethrows_original(self):
        native=FakeNative();native.enable_fail=True;factory,created=self.factory(native=native)
        with self.assertRaisesRegex(RuntimeError,'enable failure'):factory()
        self.assertIsNone(native.handle);self.assertEqual(native.close_calls,1)
        result=factory.report();self.assertTrue(result['head_contexts_cleanup_complete'])
        self.assertIn('enable failure',result['head_contexts'][0]['enable_error'])

    def test_enable_failure_with_failed_cleanup_retains_actual_resource_owner(self):
        native=FakeNative();native.enable_fail=True;native.close_fail=True;factory,_=self.factory(native=native)
        with self.assertRaises(RuntimeError)as failure:factory()
        self.assertFalse(failure.exception.native_cleanup_complete)
        self.assertIs(failure.exception.resource_owner.backend,native);self.assertEqual(native.handle,71)
        self.assertFalse(factory.report()['head_contexts_cleanup_complete'])

    def test_terminal_restoration_failure_is_not_disabled_or_reported_clean(self):
        factory,created=self.factory();backend=factory();created[0].restored=False
        with self.assertRaises(RuntimeError)as failure:backend.close()
        self.assertFalse(failure.exception.native_cleanup_complete);self.assertIs(failure.exception.resource_owner,backend)
        self.assertEqual(created[0].set_calls,[True]);self.assertEqual(created[0].close_calls,0)
        result=factory.report();self.assertFalse(result['head_instructions_restored'])
        self.assertFalse(result['head_contexts_cleanup_complete']);self.assertEqual(created[0].handle,71)

    def test_unknown_terminal_status_is_null_not_invented_zero(self):
        factory,created=self.factory();backend=factory()
        def failed_status():raise RuntimeError('injected status observation failure')
        created[0].head_skip_status=failed_status
        with self.assertRaises(RuntimeError):backend.close()
        result=factory.report();self.assertIsNone(result['head_skip_count']);self.assertFalse(result['head_instructions_restored'])

    def test_foreign_thread_cannot_create_second_context(self):
        factory,created=self.factory();backend=factory();backend.close();errors=[]
        def other():
            try:factory()
            except RuntimeError as failure:errors.append(str(failure))
        thread=threading.Thread(target=other);thread.start();thread.join(1)
        self.assertEqual(len(created),1);self.assertEqual(len(errors),1)

    def test_partial_native_construction_error_preserves_failure_owner(self):
        self.assertTrue(hasattr(m,'UnusedHeadFactory'),'Genuine opt-in v4 factory is not implemented')
        retained=object()
        def fail(*args):
            error=RuntimeError('partial native construction');error.native_cleanup_complete=False;error.resource_owner=retained;raise error
        factory=m.UnusedHeadFactory(None,None,None,None,enabled=True,native_factory=fail)
        with self.assertRaises(RuntimeError)as failure:factory()
        self.assertIs(failure.exception.resource_owner,retained);self.assertFalse(failure.exception.native_cleanup_complete)

    def test_active_context_prevents_a_second_native_construction(self):
        factory,created=self.factory();backend=factory()
        with self.assertRaises(ValueError):factory()
        self.assertEqual(len(created),1);backend.close()

    def test_transport_stop_and_error_classifier_remain_genuine_v3_definitions(self):
        old=HERE.parents[1]/'stateful1012-catchup-v2/live-producer/service_request_scoped_v3.py'
        trees=[ast.parse(path.read_text())for path in(old,HERE/'service_request_scoped_v4.py')]
        for name in('OwnedStop','connect_once','transport_observation','partition_transport_errors'):
            definitions=[next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))and n.name==name)for tree in trees]
            self.assertEqual(ast.dump(definitions[0],include_attributes=False),ast.dump(definitions[1],include_attributes=False))

    def test_CLI_defaults_off_and_requires_explicit_flag_for_configured_mode(self):
        for enabled in(False,True):
            with tempfile.TemporaryDirectory()as tmp:
                directory=Path(tmp);report=directory/'report.json'
                argv=['service','--enable-native-component','--dll','missing.dll','--model','missing',
                    '--bundle','missing','--runtime-dir','missing','--report',str(report),'--connect-port','8843',
                    '--stop-file',str(directory/'stop.json'),'--stop-nonce','a'*32]
                if enabled:argv.append('--enable-unused-head-append')
                with (patch.object(sys,'argv',argv),patch.object(m,'connect_once',side_effect=RuntimeError('CPU fixture: no network')),
                        patch('native_backend.NativeBackend',side_effect=AssertionError('No native model in CLI test'))):
                    self.assertEqual(m.main(),1)
                result=json.loads(report.read_bytes())
                self.assertEqual(result['schema'],'halogen0201.stateful1012-request-scoped-producer-process.v4')
                self.assertIs(result['unused_head_append_enabled'],enabled);self.assertEqual(result['head_contexts'],[])
                self.assertEqual(result['head_skip_count'],0);self.assertIn('no network',result['error'])

    def test_real_worker_and_unchanged_request_proxy_keep_factory_on_one_actor(self):
        factory,created=self.factory();prompt=list(range(8192));closed=threading.Event();done=[]
        def event(actual=(),kind='begin',epoch='a'*32,sequence=None):
            return dict(schema='halogen0201.authoritative-token-feedback.v1',kind=kind,source='native_T',
                engine_sha256=ENGINE,tokenizer_sha256=TOKENIZER,request_id=4,n_prompt=8192,request_epoch=epoch,nonce=7,
                generated_count=len(actual),prefix_count=8192+len(actual),prefix_sha256=prefix_hash(prompt+list(actual)),
                current_token=actual[-1]if actual else -1,sequence=sequence or len(actual)+1,
                token_ids=list(actual[-1:])if kind=='commit'else [],prompt_ids=prompt)
        class Worker(ProducerWorker):
            def _event(inner,data):
                result=super()._event(data)
                if data['kind']=='done':
                    done.append(data['request_epoch'])
                    if len(done)==2:inner.stop.set()
                return result
        worker=Worker(lambda:RequestScopedBackend(None,None,None,None,backend_factory=factory),lambda packet:None)
        worker.submit_event(event());actual=[40,41,42,43]
        for i in range(1,5):worker.submit_event(event(actual[:i],kind='commit'))
        worker.submit_event(event(actual,kind='done',sequence=6));worker.submit_event(event(epoch='b'*32))
        worker.submit_event(event(kind='done',epoch='b'*32,sequence=2));worker.start()
        self.assertTrue(worker.closed.wait(2));worker.close(2);self.assertIsNone(worker.error)
        self.assertEqual(len(created),2);self.assertNotEqual(created[0].owner,threading.get_ident())
        self.assertEqual({native.owner for native in created},{created[0].owner})
        result=factory.report();self.assertEqual(result['head_skip_count'],3)
        self.assertEqual([c['terminal_status']['count']for c in result['head_contexts']],[3,0])
        self.assertTrue(result['head_contexts_cleanup_complete']);self.assertTrue(worker.native_cleanup_complete)


if __name__=='__main__':unittest.main()
