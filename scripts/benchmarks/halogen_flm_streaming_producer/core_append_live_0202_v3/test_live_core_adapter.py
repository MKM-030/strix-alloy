"""CPU-only selection, launch-vector and genuine v4 cleanup regression tests."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent


def subject():
    path=HERE/'cohort_campaign_core_append_v1.py'
    if not path.is_file():raise AssertionError('Unused-head live adapter is not implemented')
    spec=importlib.util.spec_from_file_location('live_core_append_adapter_tests',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def terminal(m):
    context=dict(context_ordinal=1,owner_thread_id=7,requested_enabled=True,enabled_at_seed=True,
        initial_status=dict(count=0,restored=True),terminal_status=dict(count=12,restored=True),
        native_closed=True,provider_identity=dict(path=str(m.QWEN),sha256=m.QWEN_SHA),
        enable_error=None,close_error=None)
    return dict(schema='halogen0202.stateful1012-request-scoped-producer-process.v4',
        native_closed=True,worker_thread_closed=True,transport_threads_closed=True,native_cleanup_complete=True,
        request_context_active_at_shutdown=False,stop_request_observed=True,stop_file_identity={'inode':1},
        error=None,transport_errors=[],expected_shutdown_transport_errors=[{'winerror':10038}],
        unused_head_append_enabled=True,head_skip_count=12,head_instructions_restored=True,
        head_contexts_cleanup_complete=True,head_contexts=[context],
        operations=[dict(request_context='own',request_context_closed=True,
            request_close_started_qpc_ns=10,request_close_finished_qpc_ns=11)])


class Tests(unittest.TestCase):
    def setUp(self):self.m=subject()

    def binding(self):
        m=self.m;pins=[dict(path=str(m.LIVE/name),bytes=1,sha256=sha)for name,sha in m.PRODUCER_HASHES.items()]
        dll=dict(path=str(m.DLL),bytes=177152,sha256=m.DLL_SHA);pins.append(dll)
        value=dict(pins=pins,producer=dict(service=str(m.LIVE/'service_request_scoped_v4.py'),
            dll=str(m.DLL),connect=dict(host='127.0.0.1',port=8843),enable_unused_head_append=True,
            terminal_schema='halogen0202.stateful1012-request-scoped-producer-process.v4',
            required_modules={'native_backend.dll':dll}))
        def fake_pin(path):return next(row for row in pins if row['path']==str(Path(path).resolve()))
        return value,fake_pin

    def test_explicit_v4_flag_new_DLL_and_source_closure_are_required(self):
        value,pin=self.binding()
        with patch.object(self.m,'pin',side_effect=pin):self.m.validate_producer_binding(value)
        for key,bad in [('enable_unused_head_append',False),('service',str(self.m.LIVE/'service_request_scoped_v3.py')),
                        ('terminal_schema','halogen0202.stateful1012-request-scoped-producer-process.v3'),
                        ('dll',str(self.m.PRIMARY/'stateful1012-catchup-v2/build/native_backend.dll'))]:
            item=copy.deepcopy(value);item['producer'][key]=bad
            with patch.object(self.m,'pin',side_effect=pin),self.assertRaises(ValueError):self.m.validate_producer_binding(item)
        item=copy.deepcopy(value);item['pins']=item['pins'][1:]
        with patch.object(self.m,'pin',side_effect=pin),self.assertRaisesRegex(ValueError,'source'):self.m.validate_producer_binding(item)

    def test_genuine_v4_status_and_each_context_restoration_are_qualified(self):
        report=terminal(self.m);self.assertEqual(len(self.m.validate_terminal(report)),1)
        for key,bad in [('schema','halogen0202.stateful1012-request-scoped-producer-process.v3'),
                        ('unused_head_append_enabled',False),('head_skip_count',None),
                        ('head_instructions_restored',False),('head_contexts_cleanup_complete',False),
                        ('native_cleanup_complete',False),('transport_errors',['reset'])]:
            item=copy.deepcopy(report);item[key]=bad
            with self.assertRaises(ValueError):self.m.validate_terminal(item)
        for key,bad in [('enabled_at_seed',False),('native_closed',False),('enable_error','failed'),('close_error','failed')]:
            item=copy.deepcopy(report);item['head_contexts'][0][key]=bad
            with self.assertRaises(ValueError):self.m.validate_terminal(item)
        item=copy.deepcopy(report);item['head_skip_count']=13
        with self.assertRaises(ValueError):self.m.validate_terminal(item)
        item=copy.deepcopy(report);item['head_contexts'][0]['terminal_status']['restored']=False
        with self.assertRaises(ValueError):self.m.validate_terminal(item)

    def test_launch_vector_has_real_unused_head_flag_without_rewriting_service_or_schema(self):
        m=self.m;b=dict(host='python313.exe',service=str(m.LIVE/'service_request_scoped_v4.py'),dll=str(m.DLL),
            model='model',bundle='bundle',runtime_dir='runtime',enable_unused_head_append=True)
        args=m.producer_command(b,Path('terminal.json'),Path('stop.json'),'a'*32)
        self.assertEqual(args[:3],['python313.exe','-B',b['service']])
        self.assertEqual(args.count('--enable-unused-head-append'),1)
        self.assertIn('--enable-native-component',args);self.assertIn(str(m.DLL),args)
        self.assertEqual(args[args.index('--maximum-seconds')+1],'900')
        self.assertEqual(args[args.index('--connect-port')+1],'8843')

    def test_owner_launch_uses_retained_child_and_inherits_watch_check_connection(self):
        m=self.m
        class Owner:
            def watch(self):pass
            def check(self):pass
            def wait_connected(self):pass
        original=lambda *a:None;c=NS(validate_bindings=original,OwnedProducer=Owner)
        restore=m.install(c);selected=c.OwnedProducer
        for name in('watch','check','wait_connected'):self.assertIs(getattr(selected,name),getattr(Owner,name))
        frame=dict(available_bytes=22*2**30,commit_headroom_bytes=22*2**30)
        saved=[];child=NS(pid=71,poll=lambda:None)
        class Thread:
            def __init__(self,**kwargs):pass
            def start(self):pass
        with tempfile.TemporaryDirectory()as tmp:
            obj=selected();obj.runtime=NS(ops=NS(host=NS(frame=lambda:frame),ident=NS(process_identity=lambda pid:dict(pid=pid))))
            obj.folder=Path(tmp)/'helper';obj.report=obj.folder/'terminal.json';obj.stop_file=obj.folder/'stop.json'
            obj.nonce='a'*32;obj.record={};obj.child=None;obj.save=lambda:saved.append(1);obj.thread=None
            obj.binding=dict(host='python313.exe',service=str(m.LIVE/'service_request_scoped_v4.py'),dll=str(m.DLL),
                model='model',bundle='bundle',runtime_dir=tmp,enable_unused_head_append=True)
            with patch.object(m.subprocess,'Popen',return_value=child)as spawn,patch.object(m.threading,'Thread',Thread):
                self.assertIs(obj.start(),obj)
            self.assertIs(obj.child,child);self.assertTrue(saved)
            self.assertIn('--enable-unused-head-append',spawn.call_args.args[0]);obj.log.close()
        restore();self.assertIs(c.OwnedProducer,Owner);self.assertIs(c.validate_bindings,original)

    def test_admission_still_wraps_selected_owner_and_restores_in_reverse(self):
        m=self.m;admission=m.load('core_append_live_adapter_admission_test',m.FROZEN/'cohort_campaign_admission_v2.py')
        class Owner:
            def start(self):pass
        original=lambda *a:None;c=NS(validate_bindings=original,OwnedProducer=Owner,support=original,load=original)
        restore_binding=m.install(c);selected=c.OwnedProducer;restore_admission=admission.install(c)
        self.assertTrue(issubclass(c.OwnedProducer,selected))
        restore_admission();self.assertIs(c.OwnedProducer,selected)
        restore_binding();self.assertIs(c.OwnedProducer,Owner)


if __name__=='__main__':unittest.main()
