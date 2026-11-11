"""Finite Windows reverse-TCP client using the unchanged qualified actor worker.

Root starts this helper after GPU Ready and request-memory admission. Import,
connection and idle worker creation load no FLM DLL or native model. A valid
BEGIN seeds a lazy context; END/retirement releases its final opaque state.
"""
import argparse
import json
from pathlib import Path
import queue
import socket
import threading
import time

from actor import need
from service import ProducerWorker,read_frame,write_frame
from request_scoped_backend import RequestScopedBackend


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
    args=parser.parse_args();need(1<=args.maximum_seconds<=3600,'Finite component window required')
    need(not args.report.exists(),'Fresh report required')
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
        while time.monotonic()<deadline and not worker.closed.is_set()and not stop.wait(0.05):pass
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
        value=dict(schema='halogen0201.stateful1012-request-scoped-producer-process.v1',
            started_qpc_ns=started,finished_qpc_ns=time.perf_counter_ns(),worker_thread_closed=thread_closed,
            native_cleanup_complete=worker.native_cleanup_complete,native_closed=native_closed,
            request_context_active_at_shutdown=context_active,error=error or worker.error,
            transport_errors=transport_errors,ready_packets=worker.ready_count,
            actual_committed_T_count=worker.authoritative_count,
            operations=worker.backend.operations if worker.backend is not None else [],
            native_acceptance=None,prefill_tok_s=None,decode_tok_s=None,target_readiness=None,
            engine_benefit=None)
        with args.report.open('x',encoding='utf-8')as stream:json.dump(value,stream,indent=2);stream.write('\n')
    return 0 if native_closed and error is None and worker.error is None and not transport_errors else 1


if __name__=='__main__':raise SystemExit(main())
