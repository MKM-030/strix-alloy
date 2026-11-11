"""Default-off bounded framed endpoint; exactly one worker owns the native engine."""
import argparse
import copy
import json
from pathlib import Path
import queue
import socket
import struct
import threading
import time

from actor import CATCHUP_EVENTS,PrefixKey,StatefulActor,need

MAX_FRAME=4*1024*1024
ENGINE='bf84053705d1e89c214ff64c79ad1276c5fe353d80a9bb0f38ef3bac6645b97c'
TOKENIZER='0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3'


def read_exact(connection,size):
    data=bytearray()
    while len(data)<size:
        part=connection.recv(size-len(data))
        if not part:raise EOFError('Producer peer disconnected')
        data.extend(part)
    return bytes(data)


def read_frame(connection):
    length,=struct.unpack('<I',read_exact(connection,4))
    need(0<length<=MAX_FRAME,'Bounded framed JSON length required')
    value=json.loads(read_exact(connection,length))
    need(type(value)is dict,'Object frame required');return value


def write_frame(connection,value):
    data=json.dumps(value,separators=(',',':'),allow_nan=False).encode('utf-8')
    need(0<len(data)<=MAX_FRAME,'Bounded framed JSON required')
    connection.sendall(struct.pack('<I',len(data))+data)


def event_key(event):
    return PrefixKey(event['request_id'],event['n_prompt'],event['request_epoch'],event['nonce'],
        event['generated_count'],event['prefix_sha256'],event['current_token'])


def ready_packet(ready):
    key=ready.key
    return dict(schema='halogen0202.stateful1012-ready.v1',request_id=key.request_id,n_prompt=key.prompt_count,
        request_epoch=key.epoch,nonce=key.nonce,generated_count=key.global_t_count,
        prefix_sha256=key.prefix_sha256,current_token=key.current_token,token_ids=list(ready.token_ids),
        ready_sequence=ready.ready_sequence,producer_ready_qpc_ns=ready.ready_qpc_ns,
        owned_row_sha256=ready.owned_row_sha256,oracle_future_IDs=False,
        native_acceptance=None,prefill_tok_s=None,decode_tok_s=None,target_readiness=None)


class ProducerWorker:
    def __init__(self,backend_factory,on_ready,queue_capacity=64):
        need(type(queue_capacity)is int and 1<=queue_capacity<=256,'Bounded event queue required')
        self.factory=backend_factory;self.on_ready=on_ready;self.events=queue.Queue(queue_capacity)
        self.stop=threading.Event();self.loaded=threading.Event();self.closed=threading.Event()
        self.thread=None;self.actor=None;self.backend=None;self.error=None
        self.native_cleanup_complete=True;self.failed_backend=None
        self.sequence=0;self.ready_count=0;self.authoritative_count=0;self.last_ready_sequence=0
        self.catchup_batches=0;self.catchup_events=0;self.maximum_catchup_events=0

    def start(self):
        need(self.thread is None and not self.stop.is_set(),'Worker can start only once')
        self.thread=threading.Thread(target=self._run,name='flm1012-native-actor',daemon=True);self.thread.start()

    def submit_event(self,event):
        if self.stop.is_set():return False
        try:self.events.put_nowait(copy.deepcopy(event));return True
        except queue.Full:
            self.error='producer_event_queue_full';self.stop.set();return False

    def _emit(self):
        for ready in self.actor.mailbox.snapshot():
            if ready.ready_sequence<=self.last_ready_sequence:continue
            self.last_ready_sequence=ready.ready_sequence
            # The successful positive control only qualifies G>=1 consumption.
            if ready.key.global_t_count==0:continue
            self.on_ready(ready_packet(ready));self.ready_count+=1

    def _validated_event(self,event):
        need(type(event)is dict and event.get('schema')=='halogen0202.authoritative-token-feedback.v1'
             and event.get('source')=='native_T' and event.get('engine_sha256')==ENGINE
             and event.get('tokenizer_sha256')==TOKENIZER,'Frozen native target identity required')
        key=event_key(event);kind=event.get('kind');sequence=event.get('sequence')
        need(type(sequence)is int,'Monotonic authority event sequence required')
        need(event.get('prefix_count')==key.prompt_count+key.global_t_count,'Global authoritative prefix count differs')
        return key,kind,sequence

    def _commit_events(self,events):
        # Envelope, sequence, and every intermediate actor key/hash must be
        # valid before any queued true token reaches the native backend.
        need(type(events)in(list,tuple)and 1<=len(events)<=CATCHUP_EVENTS,
             'One to sixteen already-queued commit events required')
        need(self.actor.key is not None,'Commit requires an active authority prefix')
        sequence=self.sequence;transactions=[]
        for event in events:
            key,kind,next_sequence=self._validated_event(event)
            need(kind=='commit'and next_sequence==sequence+1,'Authority event sequence gap')
            transactions.append((key,event['token_ids']));sequence=next_sequence
        self.actor.commit_batch(self.actor.key,transactions)
        self.sequence=sequence;self.authoritative_count=key.global_t_count
        self.catchup_batches+=1;self.catchup_events+=len(events)
        self.maximum_catchup_events=max(self.maximum_catchup_events,len(events))

    def _event(self,event):
        key,kind,sequence=self._validated_event(event)
        if kind=='begin':
            need(self.actor.key is None and sequence==1,'One fresh serial request required')
            self.actor.begin(key,event['prompt_ids']);self.sequence=sequence;self.authoritative_count=0
        elif kind=='commit':
            self._commit_events([event])
        elif kind in('done','error','cancelled','invalid'):
            previous=self.actor.key
            need(previous is not None and sequence==self.sequence+1 and all(getattr(key,k)==getattr(previous,k)
                for k in('request_id','prompt_count','epoch','nonce')),'Terminal request binding differs')
            need(key==previous,'Terminal authoritative history differs')
            self.actor.cancel();self.sequence=sequence
        else:raise ValueError('Unsupported authority event kind')

    def _run(self):
        try:
            self.backend=self.factory();self.actor=StatefulActor(self.backend);self.loaded.set()
            empty=object();pending=empty
            while not self.stop.is_set():
                if pending is not empty:event,pending=pending,empty
                else:
                    try:event=self.events.get_nowait()
                    except queue.Empty:
                        if self.actor.prepare_one():self._emit();continue
                        try:event=self.events.get(timeout=0.05)
                        except queue.Empty:continue
                if type(event)is dict and event.get('kind')=='commit':
                    batch=[event]
                    # Never wait to fill a batch. A following END/BEGIN (or
                    # invalid event) stays in one local FIFO slot, not put back
                    # behind later queue events.
                    while len(batch)<CATCHUP_EVENTS:
                        try:following=self.events.get_nowait()
                        except queue.Empty:break
                        if type(following)is dict and following.get('kind')=='commit':batch.append(following)
                        else:pending=following;break
                    self._commit_events(batch)
                else:self._event(event)
                self._emit()
        except BaseException as error:
            self.error=type(error).__name__+': '+str(error);self.stop.set()
            self.native_cleanup_complete=getattr(error,'native_cleanup_complete',True)is True
            self.failed_backend=getattr(error,'resource_owner',None)
        finally:
            try:
                if self.actor is not None:self.actor.cancel()
            except BaseException as error:
                self.error=self.error or type(error).__name__+': '+str(error)
                self.native_cleanup_complete=False
            try:
                if self.backend is not None:self.backend.close()
            except BaseException as error:
                self.error=self.error or type(error).__name__+': '+str(error)
                self.native_cleanup_complete=False
            self.closed.set()

    def close(self,timeout=10):
        self.stop.set()
        if self.thread is not None:self.thread.join(timeout)
        else:self.closed.set()
        return self.closed.is_set()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable-native-component',action='store_true',required=True)
    parser.add_argument('--dll',type=Path,required=True);parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--listen-port',type=int,required=True)
    parser.add_argument('--runtime-dir',type=Path,required=True)
    parser.add_argument('--bind-address',default='127.0.0.1');parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--maximum-seconds',type=int,default=900)
    args=parser.parse_args();need(1<=args.listen_port<=65535 and 1<=args.maximum_seconds<=3600,'Finite endpoint bounds required')
    need(not args.report.exists(),'Fresh report required')
    from native_backend import NativeBackend
    outgoing=queue.Queue(256);transport_stop=threading.Event();transport_error=[]
    worker=ProducerWorker(lambda:NativeBackend(args.dll,args.model,args.bundle,args.runtime_dir),outgoing.put_nowait)
    started=time.perf_counter_ns();connection=None;listener=None;threads=[]
    try:
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        listener.bind((args.bind_address,args.listen_port));listener.listen(1);listener.settimeout(0.2)
        worker.start();deadline=time.monotonic()+args.maximum_seconds
        print(json.dumps(dict(event='producer_listening',address=listener.getsockname())),flush=True)
        while connection is None and time.monotonic()<deadline and not worker.closed.is_set():
            try:connection,_=listener.accept()
            except socket.timeout:pass
        need(connection is not None,'No producer client arrived in finite window')
        connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        def reader():
            try:
                while not transport_stop.is_set():
                    if not worker.submit_event(read_frame(connection)):raise RuntimeError('Native actor event queue retired')
            except EOFError:pass
            except BaseException as error:transport_error.append(type(error).__name__+': '+str(error))
            finally:transport_stop.set()
        def writer():
            try:
                while not transport_stop.is_set():
                    try:value=outgoing.get(timeout=0.05)
                    except queue.Empty:continue
                    write_frame(connection,value)
            except BaseException as error:transport_error.append(type(error).__name__+': '+str(error));transport_stop.set()
        threads=[threading.Thread(target=reader,daemon=True),threading.Thread(target=writer,daemon=True)]
        for thread in threads:thread.start()
        while time.monotonic()<deadline and not worker.closed.is_set() and not transport_stop.wait(0.05):pass
    finally:
        transport_stop.set()
        if connection is not None:
            try:connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            connection.close()
        if listener is not None:listener.close()
        worker_thread_closed=worker.close(timeout=10)
        native_closed=worker_thread_closed and worker.native_cleanup_complete
        for thread in threads:thread.join(1)
        value=dict(schema='halogen0202.stateful1012-producer-process.v1',started_qpc_ns=started,
            finished_qpc_ns=time.perf_counter_ns(),native_closed=native_closed,error=worker.error,
            worker_thread_closed=worker_thread_closed,native_cleanup_complete=worker.native_cleanup_complete,
            transport_errors=transport_error,ready_packets=worker.ready_count,actual_committed_T_count=worker.authoritative_count,
            operations=worker.backend.operations if worker.backend is not None else [],native_acceptance=None,
            prefill_tok_s=None,decode_tok_s=None,target_readiness=None)
        with args.report.open('x',encoding='utf-8')as stream:json.dump(value,stream,indent=2);stream.write('\n')
    return 0 if native_closed and worker.error is None and not transport_error else 1


if __name__=='__main__':raise SystemExit(main())
