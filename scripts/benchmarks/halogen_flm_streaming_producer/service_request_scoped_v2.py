"""Finite Windows reverse-TCP client using the unchanged qualified actor worker.

Root starts this helper after GPU Ready and request-memory admission. Import,
connection and idle worker creation load no FLM DLL or native model. A valid
BEGIN seeds a lazy context; END/retirement releases its final opaque state.
"""
import argparse
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable-native-component',action='store_true',required=True)
    for name in('dll','model','bundle','runtime-dir','report'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--connect-host',default='127.0.0.1');parser.add_argument('--connect-port',type=int,required=True)
    parser.add_argument('--maximum-seconds',type=int,default=900)
    parser.add_argument('--stop-file',type=Path,required=True);parser.add_argument('--stop-nonce',required=True)
    args=parser.parse_args();need(1<=args.maximum_seconds<=3600,'Finite component window required')
    need(not args.report.exists(),'Fresh report required')
    owned_stop=OwnedStop(args.stop_file,args.stop_nonce);stop_observed=False
    outgoing=queue.Queue(256);stop=threading.Event();transport_errors=[];connection=None;threads=[];error=None
    worker=ProducerWorker(lambda:RequestScopedBackend(args.dll,args.model,args.bundle,args.runtime_dir),outgoing.put_nowait)
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
            except BaseException as failure:transport_errors.append(type(failure).__name__+': '+str(failure))
            finally:stop.set()
        def writer():
            try:
                while not stop.is_set():
                    try:value=outgoing.get(timeout=0.05)
                    except queue.Empty:continue
                    write_frame(connection,value)
            except BaseException as failure:transport_errors.append(type(failure).__name__+': '+str(failure));stop.set()
        threads=[threading.Thread(target=reader,daemon=True),threading.Thread(target=writer,daemon=True)]
        for thread in threads:thread.start()
        while time.monotonic()<deadline and not worker.closed.is_set()and not stop.wait(0.05):
            if owned_stop.requested():stop_observed=True;break
    except BaseException as failure:error=type(failure).__name__+': '+str(failure)
    finally:
        stop.set()
        if connection is not None:
            try:connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            connection.close()
        thread_closed=worker.close(timeout=10)
        for thread in threads:thread.join(1)
        context_active=worker.backend.context_active if worker.backend is not None else False
        native_closed=thread_closed and worker.native_cleanup_complete and not context_active
        value=dict(schema='halogen0201.stateful1012-request-scoped-producer-process.v2',
            started_qpc_ns=started,finished_qpc_ns=time.perf_counter_ns(),worker_thread_closed=thread_closed,
            native_cleanup_complete=worker.native_cleanup_complete,native_closed=native_closed,
            request_context_active_at_shutdown=context_active,error=error or worker.error,
            stop_request_observed=stop_observed,stop_file=str(args.stop_file),stop_file_identity=owned_stop.identity,
            transport_errors=transport_errors,ready_packets=worker.ready_count,
            actual_committed_T_count=worker.authoritative_count,
            operations=worker.backend.operations if worker.backend is not None else [],
            native_acceptance=None,prefill_tok_s=None,decode_tok_s=None,target_readiness=None,
            engine_benefit=None)
        with args.report.open('x',encoding='utf-8')as stream:json.dump(value,stream,indent=2);stream.write('\n')
    return 0 if native_closed and error is None and worker.error is None and not transport_errors else 1


if __name__=='__main__':raise SystemExit(main())
