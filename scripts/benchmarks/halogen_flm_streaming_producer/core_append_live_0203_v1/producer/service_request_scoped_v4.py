"""Finite reverse-TCP producer with explicit default-off unused-head append.

Root starts this helper after GPU Ready and request-memory admission. Import,
connection and idle worker creation load no FLM DLL or native model. A valid
BEGIN seeds a lazy context; END/retirement releases its final opaque state.
"""
import argparse
import errno
import json
import os
import re
import stat
import hashlib
from pathlib import Path
import queue
import socket
import threading
import time

from actor import need
from service import ProducerWorker,read_frame,write_frame
from request_scoped_backend import RequestScopedBackend
from native_backend import QWEN_SHA256


def cleanup_failure(message,owner):
    error=RuntimeError(message);error.native_cleanup_complete=False;error.resource_owner=owner
    return error


class TrackedHeadBackend:
    """Delegate all native math/state; retain exact head status before close."""
    def __init__(self,backend,record):self.backend=backend;self.record=record

    def __getattr__(self,name):return getattr(self.backend,name)

    def close(self):
        if self.record['native_closed']:return
        try:
            status=self.backend.head_skip_status()
            need(type(status)is dict and type(status.get('count'))is int and status['count']>=0
                 and type(status.get('restored'))is bool,'Exact terminal native head status required')
            self.record['terminal_status']=dict(status)
            if not status['restored']:
                raise RuntimeError('Native head instructions are not restored; native owner retained')
            self.backend.close()
            need(self.backend.handle is None and not self.backend.states,'Native request context did not close completely')
            self.record['native_closed']=True
        except BaseException as error:
            self.record['close_error']=type(error).__name__+': '+str(error)
            raise cleanup_failure('Unused-head native cleanup failed: '+str(error),self)from error


class UnusedHeadFactory:
    """Lazy factory, called only by the serial actor's validated request seed.

    Selection happens before seed and never patches instructions itself. A
    failed selection closes its just-created engine or retains its true owner.
    """
    def __init__(self,dll,model,bundle,runtime_dir,*,enabled=False,native_factory=None):
        need(type(enabled)is bool,'Explicit boolean unused-head mode required')
        self.args=(dll,model,bundle,runtime_dir);self.enabled=enabled;self.native_factory=native_factory
        self.owner=None;self.contexts=[]

    def __call__(self):
        thread=threading.get_ident()
        if self.owner is None:self.owner=thread
        if self.owner!=thread:raise RuntimeError('Unused-head factory belongs to one native actor thread')
        need(all(record['native_closed']for record in self.contexts),'Previous unused-head request context must close before another')
        if self.native_factory is None:
            from native_backend import NativeBackend
            backend=NativeBackend(*self.args)
        else:backend=self.native_factory(*self.args)
        record=dict(context_ordinal=len(self.contexts)+1,owner_thread_id=thread,
            requested_enabled=self.enabled,enabled_at_seed=False,initial_status=None,
            terminal_status=None,native_closed=False,provider_identity=None,enable_error=None,close_error=None)
        self.contexts.append(record);tracked=TrackedHeadBackend(backend,record)
        try:
            need(backend.append_head_skip_enabled is False,'A new native engine must default to head-on')
            if self.enabled:backend.set_append_head_skip(True)
            status=backend.head_skip_status()
            need(type(status)is dict and type(status.get('count'))is int and status['count']==0
                 and status.get('restored')is True,'New native context must start restored with zero completed skips')
            need(backend.append_head_skip_enabled is self.enabled,'Native head mode differs from explicit request')
            record['enabled_at_seed']=backend.append_head_skip_enabled;record['initial_status']=dict(status)
            record['provider_identity']=backend.head_skip_identity
            return tracked
        except BaseException as original:
            record['enable_error']=type(original).__name__+': '+str(original)
            try:tracked.close()
            except BaseException as cleanup:
                raise cleanup_failure('Unused-head enable failed: '+str(original)+'; '+str(cleanup),tracked)from original
            raise

    def report(self):
        # Terminal observations are captured on the actor before native close.
        # Missing observations stay unknown instead of inventing a zero count.
        observed=all(type(record['terminal_status'])is dict for record in self.contexts)
        restored=observed and all(record['terminal_status']['restored']is True for record in self.contexts)
        return dict(unused_head_append_enabled=self.enabled,
            head_skip_count=sum(record['terminal_status']['count']for record in self.contexts)if observed else None,
            head_instructions_restored=restored,
            head_contexts_cleanup_complete=restored and all(record['native_closed']for record in self.contexts),
            head_contexts=[dict(record)for record in self.contexts])


class OwnedStop:
    """One fresh parent-owned JSON nonce file; never calls a native backend."""
    def __init__(self,path,nonce):
        path=Path(path)
        need(path.is_absolute()and path.parent.is_dir(),'Absolute stop path with existing parent required')
        need(type(nonce)is str and re.fullmatch('[0-9a-f]{32}',nonce),'Exact32hex stop nonce required')
        need(not path.exists()and not path.is_symlink(),'Fresh stop file required')
        need(not any(item.is_symlink()or getattr(item,'is_junction',lambda:False)()
             for item in path.parents),'Stop parent must not be linked')
        self.path=path;self.nonce=nonce;self.identity=None
        parent=path.parent.stat();self.parent_identity=(parent.st_dev,parent.st_ino)

    def requested(self):
        parent=self.path.parent.stat()
        need((parent.st_dev,parent.st_ino)==self.parent_identity,'Stop parent identity changed')
        try:before=self.path.lstat()
        except FileNotFoundError:return False
        need(stat.S_ISREG(before.st_mode)and before.st_nlink==1 and 0<before.st_size<=128
             and not self.path.is_symlink()and not getattr(self.path,'is_junction',lambda:False)(),
             'Bounded single-link regular stop JSON required')
        flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOINHERIT',0)|getattr(os,'O_NOFOLLOW',0)
        fd=os.open(self.path,flags)
        try:
            opened=os.fstat(fd);data=os.read(fd,129);after=os.fstat(fd)
        finally:os.close(fd)
        path_after=self.path.lstat()
        # Windows path-stat and fd-stat can expose different ctime semantics.
        # Compare identity/size/mtime across APIs, and ctime within each API.
        same=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_nlink)
        need(same(before)==same(opened)==same(after)==same(path_after)
             and before.st_ctime_ns==path_after.st_ctime_ns and opened.st_ctime_ns==after.st_ctime_ns
             and len(data)==before.st_size,'Stop file identity/content changed while reading')
        value=json.loads(data)
        need(type(value)is dict and set(value)=={'nonce'}and type(value['nonce'])is str,
             'Stop JSON must contain exactly one nonce')
        if value['nonce']!=self.nonce:return False
        self.identity=dict(path=str(self.path),device=before.st_dev,inode=before.st_ino,
                           bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        return True


def connect_once(host,port):
    need(host=='127.0.0.1'and type(port)is int and 1<=port<=65535,'Explicit loopback reverse endpoint required')
    connection=socket.create_connection((host,port),timeout=5)
    try:connection.settimeout(None);connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
    except BaseException:connection.close();raise
    return connection


def transport_observation(failure, intentional_local_shutdown):
    return dict(type=type(failure).__name__, message=str(failure),
        os_error=isinstance(failure, OSError), errno=getattr(failure, 'errno', None),
        winerror=getattr(failure, 'winerror', None),
        intentional_local_shutdown=intentional_local_shutdown)


def partition_transport_errors(observations, cleanup_complete):
    # Only closed-descriptor/socket errors from this explicit owner's shutdown
    # can be expected. Connection resets, queue/protocol faults and incomplete
    # native cleanup remain fatal, even if they coincide with a stop request.
    closed_codes = {10038, errno.EBADF, errno.ENOTSOCK}
    fatal, expected = [], []
    for item in observations:
        message = item['type'] + ': ' + item['message']
        if (cleanup_complete and item['intentional_local_shutdown'] is True
                and item['os_error'] is True
                and (item['winerror'] in closed_codes or item['errno'] in closed_codes)):
            expected.append(item)
        else:
            fatal.append(message)
    return fatal, expected


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable-native-component',action='store_true',required=True)
    parser.add_argument('--enable-unused-head-append',action='store_true',
                        help='Explicitly enable qualified unused-head intermediate appends; default off')
    for name in('dll','model','bundle','runtime-dir','report'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--connect-host',default='127.0.0.1');parser.add_argument('--connect-port',type=int,required=True)
    parser.add_argument('--maximum-seconds',type=int,default=900)
    parser.add_argument('--stop-file',type=Path,required=True);parser.add_argument('--stop-nonce',required=True)
    args=parser.parse_args();need(1<=args.maximum_seconds<=3600,'Finite component window required')
    need(not args.report.exists(),'Fresh report required')
    owned_stop=OwnedStop(args.stop_file,args.stop_nonce);stop_observed=False
    outgoing=queue.Queue(256);stop=threading.Event();transport_errors=[];connection=None;threads=[];error=None
    transport_observations=[];local_shutdown_started=threading.Event()
    def note_transport_failure(failure):
        transport_observations.append(transport_observation(failure,
            stop_observed and local_shutdown_started.is_set()))
    factory=UnusedHeadFactory(args.dll,args.model,args.bundle,args.runtime_dir,enabled=args.enable_unused_head_append)
    worker=ProducerWorker(lambda:RequestScopedBackend(args.dll,args.model,args.bundle,args.runtime_dir,
        backend_factory=factory),outgoing.put_nowait)
    started=time.perf_counter_ns();deadline=time.monotonic()+args.maximum_seconds
    try:
        connection=connect_once(args.connect_host,args.connect_port)
        worker.start()
        print(json.dumps(dict(event='request_scoped_producer_connected',endpoint=[args.connect_host,args.connect_port],
                             model_load='lazy_on_valid_BEGIN')),flush=True)
        def reader():
            try:
                while not stop.is_set():
                    if not worker.submit_event(read_frame(connection)):raise RuntimeError('Native actor event queue retired')
            except EOFError:pass
            except BaseException as failure:note_transport_failure(failure)
            finally:stop.set()
        def writer():
            try:
                while not stop.is_set():
                    try:value=outgoing.get(timeout=0.05)
                    except queue.Empty:continue
                    write_frame(connection,value)
            except BaseException as failure:note_transport_failure(failure);stop.set()
        threads=[threading.Thread(target=reader,daemon=True),threading.Thread(target=writer,daemon=True)]
        for thread in threads:thread.start()
        while time.monotonic()<deadline and not worker.closed.is_set()and not stop.wait(0.05):
            if owned_stop.requested():stop_observed=True;break
    except BaseException as failure:error=type(failure).__name__+': '+str(failure)
    finally:
        stop.set()
        if connection is not None:
            if stop_observed:local_shutdown_started.set()
            try:connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            connection.close()
        thread_closed=worker.close(timeout=10)
        for thread in threads:thread.join(1)
        transport_threads_closed=all(not thread.is_alive() for thread in threads)
        context_active=worker.backend.context_active if worker.backend is not None else False
        head_report=factory.report()
        native_closed=thread_closed and worker.native_cleanup_complete and not context_active and head_report['head_contexts_cleanup_complete']
        transport_errors,expected_shutdown_transport_errors=partition_transport_errors(
            transport_observations,native_closed and transport_threads_closed and error is None and worker.error is None)
        value=dict(schema='halogen0203.stateful1012-request-scoped-producer-process.v4',
            started_qpc_ns=started,finished_qpc_ns=time.perf_counter_ns(),worker_thread_closed=thread_closed,
            transport_threads_closed=transport_threads_closed,
            native_cleanup_complete=worker.native_cleanup_complete and head_report['head_contexts_cleanup_complete'],native_closed=native_closed,
            request_context_active_at_shutdown=context_active,error=error or worker.error or
                (None if head_report['head_contexts_cleanup_complete']else 'unused_head_context_cleanup_incomplete'),
            stop_request_observed=stop_observed,stop_file=str(args.stop_file),stop_file_identity=owned_stop.identity,
            transport_errors=transport_errors,
            expected_shutdown_transport_errors=expected_shutdown_transport_errors,
            transport_error_observations=transport_observations,ready_packets=worker.ready_count,
            actual_committed_T_count=worker.authoritative_count,
            operations=worker.backend.operations if worker.backend is not None else [],
            native_acceptance=None,prefill_tok_s=None,decode_tok_s=None,target_readiness=None,
            engine_benefit=None,**head_report)
        with args.report.open('x',encoding='utf-8')as stream:json.dump(value,stream,indent=2);stream.write('\n')
    return 0 if native_closed and transport_threads_closed and error is None and worker.error is None and not transport_errors else 1


if __name__=='__main__':raise SystemExit(main())
