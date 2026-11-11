"""Root-only unused-head live binding around frozen admission-v2 and c.run.

The workload, RAW observer, transition, profiles, deadlines and lifecycle stay
in the frozen campaign. Only explicit producer binding, the opt-in launch flag
and genuine v4 close validation
are selected here. Default invocation validates files and performs no hardware.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
PRIMARY = HERE.parent
FROZEN = PRIMARY/'stateful1012-live-prep/cohort'
LIVE = HERE/'live-producer'
DLL = HERE/'build/native_backend.dll'
CAMPAIGN_SHA = 'b2a6cbf5a7c492d2bb9d73befed2b0f7dc3575d07b729b23bd8e4c7a56aa03ad'
ADMISSION_SHA = '43d691a0fbd46ec5d322d357ba5cc36341f0a9cc6be8b2b77a1566a5907be57b'
OWNER_SHA = 'ddcc2a9766ef394bfe6715dd02083a070e3af81e6c66f701d09848a43942de66'
TRANSITION_SHA = '815f2cd06e272b0cc8a600ec051dad1db034f61892620aafe44b9c975d7baa55'
DLL_SHA = '063bb3f183bfb2d02304942f628950b80e815aa5f9cf4d15db7801304ae625dc'
QWEN = Path('C:/AI/runtimes/flm-1.0.12-npu-probe/portable/qwen3_5vl_npu.dll').resolve()
QWEN_SHA = '81b9349b5eb6cc7af277a41fad3a5dd7aa71321a82f8a484e7a980d80c334fad'
TERMINAL_SCHEMA = 'halogen0201.stateful1012-request-scoped-producer-process.v4'
PRODUCER_HASHES = {
    'actor.py': '60e78c82312b66f87b4f5490b91ba1882ad32c566b6e922061538d9d7d64bde0',
    'service.py': 'd03e74b17bc706ee2aff232e017e1bedfb92b416a7ce5dd97cb29e0edc3d05f6',
    'native_backend.py': 'f9327bbc4e005e8adf6089be1f7a6e8123e7bd9807186cb0ff6a9ca2d9a406bf',
    'request_scoped_backend.py': '6ecf73a2fcddc24270bf84b769d9d7da74ceca9eee442b5b75cce4b704de06a0',
    'service_request_scoped_v4.py': '4722929f33ceeeacb88a9b5a58483853ca2c589bcc72556b4e6f28de53aa5126',
    'append_head_scope.hpp': '109340b3357e808d02a71d1a1fa447cc7e6a22f902993a117f40fe9d1f36ad39',
    'native_backend.cpp': '5fecfd2d199aab27d217ed6be78598ca7807c97c2a642fe0da4d9e9dd392f8be',
}


def need(ok, message):
    if not ok: raise ValueError(message)


def pin(path):
    path = Path(path).resolve(); h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=h.hexdigest())


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module


def validate_producer_binding(value):
    producer = value['producer']
    need(Path(producer['service']).resolve() == LIVE/'service_request_scoped_v4.py'
         and Path(producer['dll']).resolve() == DLL
         and producer['connect'] == dict(host='127.0.0.1', port=8843)
         and producer.get('enable_unused_head_append') is True
         and producer.get('terminal_schema') == TERMINAL_SCHEMA,
         'Explicit unused-head producer, real service-v4 flag/schema and qualified new DLL required')
    indexed = {str(Path(row['path']).resolve()): row for row in value['pins']}
    for name, sha in PRODUCER_HASHES.items():
        actual = pin(LIVE/name)
        need(actual['sha256'] == sha and indexed.get(actual['path']) == actual,
             'Exact Root-pinned unused-head source required: '+name)
    actual = pin(DLL)
    need(actual['sha256'] == DLL_SHA and indexed.get(actual['path']) == actual
         and producer['required_modules']['native_backend.dll'] == actual,
         'Exact Root-pinned qualified unused-head DLL required')


def validate_terminal(report):
    need(report.get('schema') == TERMINAL_SCHEMA
         and report.get('native_closed') is True and report.get('worker_thread_closed') is True
         and report.get('transport_threads_closed') is True
         and report.get('native_cleanup_complete') is True
         and report.get('request_context_active_at_shutdown') is False
         and report.get('stop_request_observed') is True
         and type(report.get('stop_file_identity')) is dict and bool(report['stop_file_identity'])
         and report.get('error') is None and report.get('transport_errors') == []
         and report.get('unused_head_append_enabled') is True
         and type(report.get('head_skip_count')) is int and report['head_skip_count'] >= 0
         and report.get('head_instructions_restored') is True
         and report.get('head_contexts_cleanup_complete') is True,
         'Real service-v4 actor/native/transport/head cleanup failed')
    contexts=report.get('head_contexts')
    need(type(contexts)is list and bool(contexts),'Actual v4 head contexts required')
    total=0;owners=set()
    for ordinal,context in enumerate(contexts,1):
        before=context.get('initial_status',{});after=context.get('terminal_status',{})
        identity=context.get('provider_identity',{})
        need(context.get('context_ordinal') == ordinal
             and type(context.get('owner_thread_id')) is int and context['owner_thread_id']>0
             and context.get('requested_enabled') is True and context.get('enabled_at_seed') is True
             and context.get('native_closed') is True
             and context.get('enable_error') is None and context.get('close_error') is None
             and type(before.get('count'))is int and before['count']==0 and before.get('restored') is True
             and type(after.get('count'))is int and after['count']>=0 and after.get('restored') is True
             and Path(identity.get('path','')).resolve() == QWEN and identity.get('sha256') == QWEN_SHA,
             'Each v4 native context must enable after identity proof and restore before close')
        total+=after['count']-before['count'];owners.add(context['owner_thread_id'])
    need(len(owners)==1 and total==report['head_skip_count'],'Truthful v4 owner/count aggregation required')
    operations = report['operations']
    need(operations and all(op.get('request_context_closed') is True
         and op['request_close_started_qpc_ns'] <= op['request_close_finished_qpc_ns']
         for op in operations), 'Each actual request context must close')
    need(len(contexts)==len({op['request_context']for op in operations}),
         'Actual v4 head context count differs from request context ownership')
    return operations


def producer_command(binding,report,stop_file,nonce):
    need(binding.get('enable_unused_head_append')is True,'Explicit unused-head launch authorization required')
    return [binding['host'],'-B',binding['service'],'--enable-native-component','--enable-unused-head-append',
        '--dll',binding['dll'],'--model',binding['model'],'--bundle',binding['bundle'],
        '--runtime-dir',binding['runtime_dir'],'--connect-host','127.0.0.1','--connect-port','8843',
        '--maximum-seconds','900','--report',str(report),'--stop-file',str(stop_file),'--stop-nonce',nonce]


def install(c):
    old_validate, old_producer = c.validate_bindings, c.OwnedProducer
    def validate_bindings(path, expected_sha, *, running=False):
        # Frozen validator's exact gates, with the genuine new producer check
        # substituted for its service-v2 filename check. No translated binding.
        need(c.pin(path)['sha256'] == expected_sha, 'Exact Root binding changed')
        value = c.read(path)
        need(value.get('schema') == 'halogen0201.real-NPU-cohort-bindings.v1'
             and value.get('oracle_future_IDs') is False, 'Real-NPU bindings required')
        need(c.pin(c.REQUEST)['sha256'] == c.REQUEST_SHA
             and {k:v for k,v in c.read(c.REQUEST).items() if k != 'prompt'} ==
             dict(cache_prompt=False,drafter='mtp',max_tokens=128,model='halogen-v2',
                  prompt_cache_policy='no_store',seed=1,stream=False,temperature=0),
             'Frozen greedy128 request changed')
        c.profiles(); validate_producer_binding(value)
        if value.get('root_sealed') is not True:
            need(not running, 'Root must seal final bindings before run'); return value, None
        need(value.get('source_freeze_complete') is True, 'Final source freeze must precede Root execution seal')
        for expected in value['pins']:
            need(c.pin(expected['path']) == expected, 'Executed input changed: '+expected['path'])
        transition = c.read(value['transition'])
        need(c.pin(value['transition'])['sha256'] == TRANSITION_SHA
             and transition['schema'] == 'halogen0201.b73-RAW-reverse-HDO2-private-source-overlay.v1'
             and transition['normal_source_manifest']['sha256'] == c.BASE_SOURCE_SHA
             and transition['common_RAW_observer_all_arms'] is True
             and transition['watchdog_timers_and_uptime_body_byte_identical'] is True
             and len(transition['baseline']) == 48, 'Exact frozen common RAW/reverse source47 baseline required')
        need(len(value['artifacts']) == 2 and {row['target'] for row in value['artifacts']} ==
             {'.local/libhgn0201-stream.so','.local/libhgn0201_raw_side.so'},
             'Exactly two owned native artifacts required')
        for arm, profile in c.profiles().items():
            need(c.read(Path(value['transition']).parent/(arm+'.profile.json')) == profile,
                 'Frozen overlay arm profile differs')
            env = value['native_environment'][arm]
            need(env['HGN0201_RAW_ENABLE'] == '1' and env['HGN0201_API_NATIVE_ID'] == '1'
                 and env['HALOGEN_PREFILL_CHUNK'] == env['HALOGEN_MAX_TOK'] == '8192'
                 and env['HGN0201_STREAM_CAPTURE'] == '1'
                 and env.get('HGN0201_EXTERNAL_STREAM') == ('1' if arm == 'candidate' else None),
                 'Common RAW/capture and0/1/0 native environment differ')
        return value, transition

    class CoreAppendProducer(old_producer):
        # watch/check/wait_connected stay frozen. Start differs only by the
        # truthful v4 entrypoint binding and explicit unused-head CLI switch.
        def start(self):
            frame=self.runtime.ops.host.frame()
            need(min(frame['available_bytes'],frame['commit_headroom_bytes'])>=22*2**30,'22-GiB NPU entry reserve required')
            self.folder.mkdir();self.log=(self.folder/'service.log').open('xb')
            b=self.binding;command=producer_command(b,self.report,self.stop_file,self.nonce)
            self.record.update(command=command,entry_memory=frame,deadline_seconds=900,automatic_retries=0)
            env=dict(os.environ);env['PATH']=b['runtime_dir']+';C:\\Windows\\System32;C:\\Windows'
            try:
                self.child=subprocess.Popen(command,cwd=b['runtime_dir'],env=env,stdin=subprocess.DEVNULL,
                    stdout=self.log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                self.record['identity']=self.runtime.ops.ident.process_identity(self.child.pid)
                self.started=time.monotonic();self.save()
                self.thread=threading.Thread(target=self.watch,daemon=True);self.thread.start()
            except BaseException:
                if self.child is not None and self.child.poll()is None:
                    self.child.terminate();self.record['exit_code']=self.child.wait(timeout=20)
                self.log.close();self.record['terminal']=True;self.save();raise
            return self

        def close(self):
            if self.record['terminal']:
                need(self.record.get('native_closed') is True,
                     'Previously closed helper has no qualified native cleanup'); return self.record
            try:
                if self.child is not None and self.child.poll() is None:
                    c.save_new(self.stop_file, dict(nonce=self.nonce))
                    try: self.record['exit_code'] = self.child.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        self.child.terminate(); self.record['exit_code'] = self.child.wait(timeout=20)
                        self.record['forced_own_child_termination'] = True
                elif self.child is not None: self.record['exit_code'] = self.child.wait()
            finally:
                self.stop.set()
                if self.thread is not None: self.thread.join(2)
                if self.log is not None: self.log.close()
                self.record['terminal'] = self.child is None or self.child.poll() is not None; self.save()
            need(self.record['terminal'] and self.record.get('exit_code') == 0
                 and not self.record.get('guard_error') and not self.record.get('forced_own_child_termination'),
                 'Own NPU helper did not exit normally')
            report = c.read(self.report); operations = validate_terminal(report)
            actual = {path.casefold() for row in self.record['modules'] for path in row['paths']}
            for name, expected in self.binding['required_modules'].items():
                need(expected['path'].casefold() in actual and c.pin(expected['path']) == expected,
                     'Actual selected producer module was not observed: '+name)
            self.record.update(report=c.pin(self.report),
                request_contexts=len({op['request_context'] for op in operations}), native_closed=True,
                qualified_loaded_modules=self.binding['required_modules'],
                unused_head_append_enabled=report['unused_head_append_enabled'],
                head_skip_count=report['head_skip_count'],
                head_instructions_restored=report['head_instructions_restored'],
                head_contexts_cleanup_complete=report['head_contexts_cleanup_complete'])
            self.save(); return self.record
    c.validate_bindings, c.OwnedProducer = validate_bindings, CoreAppendProducer
    def restore(): c.validate_bindings, c.OwnedProducer = old_validate, old_producer
    return restore


def main():
    for name, sha in [('cohort_campaign.py',CAMPAIGN_SHA),
                      ('cohort_campaign_admission_v2.py',ADMISSION_SHA),('owned_producer.py',OWNER_SHA)]:
        need(pin(FROZEN/name)['sha256'] == sha, 'Frozen campaign/admission/owner source changed')
    campaign = load('real_npu_core_append_frozen_campaign', FROZEN/'cohort_campaign.py')
    admission = load('real_npu_core_append_frozen_admission', FROZEN/'cohort_campaign_admission_v2.py')
    restore_binding = install(campaign)
    # Admission must wrap the selected new owner so its two-frame wait is kept.
    restore_admission = admission.install(campaign)
    try: return campaign.main()
    finally: restore_admission(); restore_binding()


if __name__ == '__main__': raise SystemExit(main())
