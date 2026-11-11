"""One retained Windows helper; only Root's executed cohort creates a process."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid

from evidence import need, pin, read, save_new


class OwnedProducer:
    def __init__(self, runtime, folder, binding, module_probe):
        self.runtime=runtime; self.folder=Path(folder); self.binding=binding; self.probe=module_probe
        self.child=None; self.log=None; self.thread=None; self.stop=threading.Event(); self.lock=threading.Lock()
        self.nonce=uuid.uuid4().hex; self.stop_file=self.folder/'stop.json'
        self.report=self.folder/'terminal.json'; self.record=dict(terminal=False, memory=[], modules=[], module_errors=[])

    def save(self):
        with self.lock:self.runtime.ops.atomic(self.folder/'handle.json',self.record)

    def start(self):
        frame=self.runtime.ops.host.frame()
        need(min(frame['available_bytes'],frame['commit_headroom_bytes'])>=22*2**30,'22-GiB NPU entry reserve required')
        self.folder.mkdir(); self.log=(self.folder/'service.log').open('xb')
        b=self.binding
        command=[b['host'],'-B',b['service'],'--enable-native-component','--dll',b['dll'],
            '--model',b['model'],'--bundle',b['bundle'],'--runtime-dir',b['runtime_dir'],
            '--connect-host','127.0.0.1','--connect-port','8843','--maximum-seconds','900',
            '--report',str(self.report),'--stop-file',str(self.stop_file),'--stop-nonce',self.nonce]
        self.record.update(command=command,entry_memory=frame,deadline_seconds=900,automatic_retries=0)
        env=dict(os.environ); env['PATH']=b['runtime_dir']+';C:\\Windows\\System32;C:\\Windows'
        try:
            self.child=subprocess.Popen(command,cwd=b['runtime_dir'],env=env,stdin=subprocess.DEVNULL,
                stdout=self.log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.record['identity']=self.runtime.ops.ident.process_identity(self.child.pid)
            self.started=time.monotonic(); self.save()
            self.thread=threading.Thread(target=self.watch,daemon=True); self.thread.start()
        except BaseException:
            if self.child is not None and self.child.poll() is None:
                self.child.terminate(); self.record['exit_code']=self.child.wait(timeout=20)
            self.log.close(); self.record['terminal']=True; self.save(); raise
        return self

    def watch(self):
        previous=None
        try:
            while not self.stop.is_set() and self.child.poll() is None:
                frame=self.runtime.ops.host.frame(); self.record['memory'].append(frame)
                need(min(frame['available_bytes'],frame['commit_headroom_bytes'])>=18*2**30,'18-GiB NPU runtime reserve crossed')
                need(time.monotonic()-self.started<=900,'Finite900-second helper deadline exceeded')
                try:
                    paths=self.probe(self.child)
                    if paths!=previous:
                        self.record['modules'].append(dict(elapsed_seconds=time.monotonic()-self.started,paths=paths)); previous=paths
                except OSError as error:self.record['module_errors'].append(str(error))
                self.save(); self.stop.wait(.1)
        except BaseException as error:
            self.record['guard_error']=dict(type=type(error).__name__,message=str(error))
            # An emergency guard acts on the retained own HANDLE only.
            if self.child.poll() is None:self.child.terminate()
            self.save()

    def check(self):
        need(not self.record.get('guard_error'),'NPU helper guard failed')
        need(self.child is not None and self.child.poll() is None,'NPU helper exited during candidate')

    def wait_connected(self):
        deadline=time.monotonic()+10
        while True:
            self.check()
            data=(self.folder/'service.log').read_bytes()
            need(len(data)<=1024*1024,'Owned helper startup log exceeded its finite bound')
            for line in data.splitlines():
                try:value=json.loads(line)
                except (ValueError,UnicodeDecodeError):continue
                if value.get('event')=='request_scoped_producer_connected':
                    need(value.get('endpoint')==['127.0.0.1',8843]
                         and value.get('model_load')=='lazy_on_valid_BEGIN','Owned helper connection identity differs')
                    self.record['connected']=True; self.save(); return
            need(time.monotonic()<deadline,'Owned helper connection observation timed out; never restart it')
            time.sleep(.05)

    def close(self):
        if self.record['terminal']:
            need(self.record.get('native_closed') is True,'Previously closed helper has no qualified native cleanup')
            return self.record
        try:
            if self.child is not None and self.child.poll() is None:
                save_new(self.stop_file,dict(nonce=self.nonce))
                try:self.record['exit_code']=self.child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.child.terminate(); self.record['exit_code']=self.child.wait(timeout=20)
                    self.record['forced_own_child_termination']=True
            elif self.child is not None:self.record['exit_code']=self.child.wait()
        finally:
            self.stop.set()
            if self.thread is not None:self.thread.join(2)
            if self.log is not None:self.log.close()
            self.record['terminal']=self.child is None or self.child.poll() is not None; self.save()
        need(self.record['terminal'] and self.record.get('exit_code')==0
             and not self.record.get('guard_error') and not self.record.get('forced_own_child_termination'),
             'Own NPU helper did not exit normally')
        report=read(self.report)
        need(report.get('schema')=='halogen0202.stateful1012-request-scoped-producer-process.v2'
             and report.get('native_closed') is True and report.get('worker_thread_closed') is True
             and report.get('native_cleanup_complete') is True
             and report.get('request_context_active_at_shutdown') is False
             and report.get('stop_request_observed') is True
             and type(report.get('stop_file_identity')) is dict and bool(report['stop_file_identity'])
             and report.get('error') is None and report.get('transport_errors')==[],
             'NPU actor/native context cleanup failed')
        operations=report['operations']; need(operations and all(op.get('request_context_closed') is True
             and op['request_close_started_qpc_ns']<=op['request_close_finished_qpc_ns'] for op in operations),
             'Each actual request context must close')
        actual={path.casefold() for row in self.record['modules'] for path in row['paths']}
        for name,expected in self.binding['required_modules'].items():
            need(expected['path'].casefold() in actual and pin(expected['path'])==expected,
                 'Actual selected producer module was not observed: '+name)
        self.record.update(report=pin(self.report),request_contexts=len({op['request_context'] for op in operations}),
            native_closed=True,qualified_loaded_modules=self.binding['required_modules'])
        self.save(); return self.record
