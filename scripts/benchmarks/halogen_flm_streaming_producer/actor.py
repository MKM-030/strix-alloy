"""Serial state transactions; ready queries only inspect immutable publications.

This module opens no DLL, process, device, socket or model. The injected backend
is owned exclusively by the actor thread. Native calls are never made by query.
"""
from contextlib import contextmanager
from dataclasses import dataclass,field
import hashlib
import re
import struct
import threading
import time

ROWS=248070
HEAD_ROWS=248320
SEED=512
LIMIT=128
LOOKAHEAD=3
HASH_DOMAIN=b'halogen-authoritative-token-ids-v1\0'


def need(value,message):
    if not value:raise ValueError(message)


def checked_ids(values,upper=HEAD_ROWS):
    need(type(values)in(list,tuple)and all(type(t)is int and 0<=t<upper for t in values),
         'Bounded integer token IDs required')
    return tuple(values)


def digest_ids(values):
    h=hashlib.sha256(HASH_DOMAIN)
    for token in checked_ids(values):h.update(struct.pack('<i',token))
    return h


def prefix_hash(values):return digest_ids(values).hexdigest()


@dataclass(frozen=True)
class PrefixKey:
    request_id:int
    prompt_count:int
    epoch:str
    nonce:int
    global_t_count:int
    prefix_sha256:str
    current_token:int

    def __post_init__(self):
        need(type(self.request_id)is int and 0<=self.request_id<1<<63,'Nonnegative int64 request required')
        need(type(self.prompt_count)is int and SEED<=self.prompt_count<=262144,'Prompt count out of range')
        need(type(self.epoch)is str and re.fullmatch('[0-9a-f]{32}',self.epoch),'Fresh epoch16 required')
        need(type(self.nonce)is int and 0<=self.nonce<1<<64,'Unsigned prefix nonce required')
        need(type(self.global_t_count)is int and 0<=self.global_t_count<=LIMIT,'Only128 actual T IDs are qualified')
        need(type(self.prefix_sha256)is str and re.fullmatch('[0-9a-f]{64}',self.prefix_sha256),'Full prefix SHA required')
        need(type(self.current_token)is int and (self.current_token==-1 if self.global_t_count==0
             else 0<=self.current_token<HEAD_ROWS),'Current authoritative token differs')


@dataclass(frozen=True)
class OwnedRow:
    greedy_id:int
    data:bytes
    sha256:str=field(init=False)

    def __post_init__(self):
        need(type(self.greedy_id)is int and 0<=self.greedy_id<ROWS,'Shared greedy ID required')
        # NativeBackend requires exactly ROWS*2 BF16 bytes; fake CPU backends
        # may use a shorter immutable state fingerprint to test transactions.
        need(type(self.data)is bytes and 0<len(self.data)<=ROWS*2,'Deep-owned immutable row required')
        object.__setattr__(self,'sha256',hashlib.sha256(self.data).hexdigest())


@dataclass(frozen=True)
class Ready:
    key:PrefixKey
    token_ids:tuple
    ready_sequence:int
    ready_qpc_ns:int
    owned_row_sha256:str


class Mailbox:
    def __init__(self):self.lock=threading.Lock();self.value=()

    def publish(self,value):
        with self.lock:self.value=value or ()

    def query(self,key):
        if not self.lock.acquire(blocking=False):return None
        try:return next((record for record in self.value if record.key==key),None)
        finally:self.lock.release()

    def snapshot(self):
        if not self.lock.acquire(blocking=False):return ()
        try:return self.value
        finally:self.lock.release()


@dataclass
class _Prefix:
    local_count:int
    incoming_token:object
    snapshot:object
    row:OwnedRow


class StatefulActor:
    def __init__(self,backend,clock_ns=time.perf_counter_ns):
        self.backend=backend;self.clock=clock_ns;self.mailbox=Mailbox()
        self._owner=None;self._running=False;self._ring=[];self._key=None
        self._actual=();self._hasher=None;self._sequence=0;self._epochs=set()

    @property
    def committed_ids(self):return self._actual

    @property
    def ring_size(self):return len(self._ring)

    @property
    def key(self):return self._key

    @contextmanager
    def _serial(self):
        thread=threading.get_ident()
        if self._owner is None:self._owner=thread
        if self._owner!=thread or self._running:raise RuntimeError('Only one non-reentrant native actor is allowed')
        self._running=True
        try:yield
        finally:self._running=False

    def _context(self,expected):
        need(self.backend.context_length()==expected,'Native context differs from exact cached prefix')

    def _free(self,nodes):
        for node in nodes:self.backend.free(node.snapshot)

    def _retire(self):
        self.mailbox.publish(None);nodes,self._ring=self._ring,[]
        self._key=None;self._hasher=None;self._actual=()
        self._free(nodes)

    def _publish(self):
        # Prospective keys are never authority: the independent native consumer
        # requires actual T/current/hash before selecting any one of these rows.
        h=self._hasher.copy();records=[];key=self._key
        for index,node in enumerate(self._ring):
            if index:
                token=node.incoming_token;h.update(struct.pack('<i',token))
                key=PrefixKey(self._key.request_id,self._key.prompt_count,self._key.epoch,self._key.nonce,
                    self._key.global_t_count+index,h.hexdigest(),token)
            remaining=LIMIT-key.global_t_count
            if remaining<=0:break
            tokens=tuple(p.row.greedy_id for p in self._ring[index:index+min(LOOKAHEAD,remaining)])
            self._sequence+=1
            records.append(Ready(key,tokens,self._sequence,self.clock(),node.row.sha256))
        self.mailbox.publish(tuple(records))

    def query(self,key):return self.mailbox.query(key)

    def begin(self,key,prompt_ids):
        with self._serial():
            prompt=checked_ids(prompt_ids)
            need(isinstance(key,PrefixKey)and key.global_t_count==0 and len(prompt)==key.prompt_count,
                 'BEGIN needs exact full prompt and G0 key')
            need(key.epoch not in self._epochs,'Retired epochs cannot be reused')
            hasher=digest_ids(prompt);need(hasher.hexdigest()==key.prefix_sha256,'BEGIN full prefix hash differs')
            checked_ids(prompt[-SEED:],ROWS)
            self._retire();self._epochs.add(key.epoch)
            try:
                row=self.backend.seed(prompt[-SEED:]);self._context(SEED)
                need(isinstance(row,OwnedRow),'Owned seed row required')
                snapshot=self.backend.save()
                self._ring=[_Prefix(SEED,None,snapshot,row)]
                self._key=key;self._hasher=hasher;self._actual=();self._publish()
            except BaseException:self._retire();raise

    def prepare_one(self):
        with self._serial():
            if self._key is None:return False
            depth=len(self._ring)-1
            if depth>=min(LOOKAHEAD,LIMIT-self._key.global_t_count):return False
            try:
                last=self._ring[-1];self._context(last.local_count)
                token=last.row.greedy_id;row=self.backend.forward(token)
                self._context(last.local_count+1);need(isinstance(row,OwnedRow),'Owned speculative row required')
                snapshot=self.backend.save()
                self._ring.append(_Prefix(last.local_count+1,token,snapshot,row))
                need(len(self._ring)<=4,'Opaque state ring exceeded four slots')
                self._publish();return True
            except BaseException:self._retire();raise

    def commit(self,previous_key,new_key,actual_ids):
        with self._serial():
            # Validate the entire authority transaction before any native call.
            need(self._key is not None and previous_key==self._key,'Feedback has a stale committed prefix')
            actual=checked_ids(actual_ids,ROWS)
            need(1<=len(actual)<=LOOKAHEAD,'One to three observed true IDs required')
            h=self._hasher.copy()
            for token in actual:h.update(struct.pack('<i',token))
            expected=PrefixKey(self._key.request_id,self._key.prompt_count,self._key.epoch,self._key.nonce,
                self._key.global_t_count+len(actual),h.hexdigest(),actual[-1])
            need(new_key==expected,'Feedback count, hash, epoch, nonce or true current ID differs')
            self.mailbox.publish(None)
            try:
                matched=0
                while matched<min(len(actual),len(self._ring)-1)and actual[matched]==self._ring[matched+1].incoming_token:
                    matched+=1
                if matched==len(actual):
                    discarded=self._ring[:matched];self._ring=self._ring[matched:]
                    self._ring[0].incoming_token=None;self._free(discarded)
                else:
                    # All matched IDs are now true authority. Only restore if
                    # native inputs extend past that prefix. At the physical
                    # tail there is nothing to reject; still require its exact
                    # native context before forwarding actual corrections.
                    chosen=self._ring[matched]
                    if chosen is not self._ring[-1]:
                        need(self.backend.restore(chosen.snapshot)==chosen.local_count,'Opaque restore length differs')
                    self._context(chosen.local_count)
                    discarded=[node for node in self._ring if node is not chosen]
                    self._ring=[chosen];self._free(discarded)
                    row=chosen.row;count=chosen.local_count
                    for token in actual[matched:]:
                        row=self.backend.forward(token);count+=1;self._context(count)
                        need(isinstance(row,OwnedRow),'Owned authoritative row required')
                    snapshot=self.backend.save()
                    self._ring=[_Prefix(count,None,snapshot,row)]
                    self._free([chosen])
                self._actual+=actual;self._key=new_key;self._hasher=h
                need(self._ring[0].local_count==SEED+len(self._actual),'Committed prefix count differs')
                self._context(self._ring[-1].local_count)
                self._publish()
            except BaseException:self._retire();raise

    def cancel(self):
        with self._serial():self._retire()
