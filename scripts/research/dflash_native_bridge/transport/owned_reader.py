"""Owned binary reader. Import/default CLI performs no provider or device work.

The explicit ProviderReceiver accepts a caller-prepared worker/stamp. No native
address in Binding is ever dereferenced. Only owned bytes reach tensor creation.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import json
import struct
from typing import BinaryIO
import zlib

HEADER_BYTES, ROW_BYTES, WIDTH, MASK_ID, MAX_CHUNK_ROWS = 256, 25600, 12800, 248077, 128
LAYERS = (4, 16, 24, 36, 44)
MAGIC = b'HGNDTH01'

@dataclass(frozen=True)
class Binding:
    session: bytes
    ticket: int
    lease_generation: int
    cache_generation: int
    holder: int
    model: int
    wire: int
    request: int
    birth: int
    slot: int
    total: int

@dataclass(frozen=True)
class Packet:
    packet_sequence: int
    kind: int
    source: int
    final: bool
    binding: Binding
    capture_sequence: int
    round: int
    anchor: int
    next_current: int
    verified_rows: int
    committed_rows: int
    row_offset: int
    row_count: int
    ids: tuple[int, ...]
    bf16_concat: bytes

    @property
    def positions(self):
        return tuple(range(self.anchor+self.row_offset, self.anchor+self.row_offset+self.row_count))

def _exact(stream: BinaryIO, count: int) -> bytes:
    parts=[]
    while count:
        data=stream.read(count)
        if not data:raise ValueError('Truncated owned transport frame')
        parts.append(data);count-=len(data)
    return b''.join(parts)

def read_packet(stream: BinaryIO) -> Packet | None:
    prefix=stream.read(1)
    if not prefix:return None
    h=prefix+_exact(stream,HEADER_BYTES-1)
    u32=lambda off:struct.unpack_from('<I',h,off)[0]
    u64=lambda off:struct.unpack_from('<Q',h,off)[0]
    i32=lambda off:struct.unpack_from('<i',h,off)[0]
    if h[:8]!=MAGIC or u32(8)!=1 or u32(12)!=HEADER_BYTES:raise ValueError('Unknown owned transport framing')
    copy=bytearray(h);struct.pack_into('<I',copy,212,0)
    if zlib.crc32(copy)!=u32(212):raise ValueError('Header CRC mismatch')
    if u32(44) or any(h[216:]):raise ValueError('Nonzero reserved header bytes')
    kind,source,flags=u32(32),u32(36),u32(40)
    if kind not in (1,3) or source not in (0,1,2) or flags not in (0,1):raise ValueError('Invalid frame kind/source/flags')
    if u32(176)!=WIDTH or u32(180)!=ROW_BYTES or struct.unpack_from('<5I',h,184)!=LAYERS or u32(204)!=1:raise ValueError('Unknown feature shape/order/encoding')
    count=u32(172);length=u64(16)
    if count>MAX_CHUNK_ROWS or length!=count*(ROW_BYTES+4) or (kind==3 and (count or flags)) or (kind==1 and not count):raise ValueError('Unbounded or inconsistent payload length')
    payload=_exact(stream,length)
    if zlib.crc32(payload)!=u32(208):raise ValueError('Payload CRC mismatch')
    b=Binding(h[48:64],*(u64(off) for off in range(64,128,8)),i32(128),u32(132))
    if any(v<=0 for v in (b.ticket,b.lease_generation,b.cache_generation,b.holder,b.model,b.wire,b.request,b.birth,b.total)) or b.slot<0 or b.total>262140:raise ValueError('Incomplete Binding')
    ids=struct.unpack_from(f'<{count}i',payload) if count else ()
    if any(not 0<=i<MASK_ID for i in ids):raise ValueError('Nonordinary input ID')
    return Packet(u64(24),kind,source,bool(flags),b,u64(136),u64(144),i32(152),i32(156),u32(160),u32(164),u32(168),count,ids,payload[count*4:])

class OwnedReader:
    """Exact cold-supplied Binding; one bounded packet is retained at a time."""
    def __init__(self, binding: Binding, *, capacity=16640):
        if not isinstance(binding,Binding) or type(capacity) is not int or not 1<=capacity<=262140 or not 0<binding.total<=capacity:raise ValueError('Explicit bounded Binding required')
        self.binding,self.capacity=binding,capacity
        self.packet_sequence=None
        self.prefill_rows=0
        self.prefill_complete=False
        self.position=0
        self.last_capture_sequence=self.last_round=0
        self.retired=False

    def accept(self, packet: Packet) -> Packet:
        try:return self._accept(packet)
        except Exception:
            self.retired=True
            raise

    def _accept(self, packet: Packet) -> Packet:
        if self.retired or packet.binding!=self.binding:raise ValueError('Retired or foreign Binding')
        if packet.kind not in (1,3) or packet.source not in (0,1,2) or len(packet.ids)!=packet.row_count or len(packet.bf16_concat)!=packet.row_count*ROW_BYTES or packet.row_count>MAX_CHUNK_ROWS:raise ValueError('Invalid owned packet shape')
        if packet.kind==1 and (not packet.row_count or any(not 0<=i<MASK_ID for i in packet.ids)):raise ValueError('Invalid owned packet inputs')
        if packet.kind==3 and (packet.row_count or packet.final):raise ValueError('Invalid owned retirement')
        if packet.packet_sequence<=0 or (self.packet_sequence is not None and packet.packet_sequence!=self.packet_sequence+1):raise ValueError('Stale, duplicate or missing transport packet')
        self.packet_sequence=packet.packet_sequence
        if packet.kind==3:
            self.retired=True
            return packet
        if packet.source==0:
            if self.prefill_complete or packet.capture_sequence or packet.round or packet.anchor or packet.next_current!=-1 or packet.verified_rows!=self.binding.total or packet.committed_rows!=self.binding.total:raise ValueError('Invalid prefill source metadata')
            end=self.prefill_rows+packet.row_count
            if packet.row_offset!=self.prefill_rows or end>self.binding.total or packet.final!=(end==self.binding.total):raise ValueError('Incomplete/out-of-order prefill')
            self.prefill_rows=end
            if packet.final:self.prefill_complete=True;self.position=end
        else:
            expected_verified=4 if packet.source==1 else 1
            if not self.prefill_complete or not packet.final or packet.row_offset or packet.row_count!=packet.committed_rows or not 1<=packet.committed_rows<=expected_verified or packet.verified_rows!=expected_verified:raise ValueError('Invalid committed decode source/count')
            if packet.capture_sequence<=self.last_capture_sequence or packet.round<=self.last_round or packet.anchor!=self.position or not 0<=packet.next_current<MASK_ID:raise ValueError('Stale sequence/round/frontier')
            end=packet.anchor+packet.committed_rows
            if end>self.capacity:raise ValueError('Bounded context capacity exceeded')
            self.position=end
            self.last_capture_sequence,self.last_round=packet.capture_sequence,packet.round
        return packet

    def receive(self, stream: BinaryIO) -> Packet | None:
        try:
            packet=read_packet(stream)
            if packet is None:
                if not self.retired:raise ValueError('Transport EOF without explicit owned retirement')
                return None
            return self.accept(packet)
        except Exception:
            self.retired=True
            raise

class ProviderReceiver:
    """Explicit external-worker adapter; no preparation/device discovery here."""
    def __init__(self, worker, stamp, binding: Binding):
        expected=(stamp.session_hex,stamp.pending_ticket,stamp.lease_generation,stamp.cache_generation,
                  stamp.holder_identity,stamp.model_address,stamp.wire_id,stamp.request_address,stamp.slot,stamp.total_prefill)
        actual=(binding.session.hex(),binding.ticket,binding.lease_generation,binding.cache_generation,
                binding.holder,binding.model,binding.wire,binding.request,binding.slot,binding.total)
        if expected!=actual or stamp.request_birth!=str(binding.birth):raise ValueError('Provider stamp differs from complete Binding')
        self.worker,self.stamp=worker,stamp
        self.reader=OwnedReader(binding,capacity=worker.capacity)

    def receive(self,stream: BinaryIO):
        try:
            p=self.reader.receive(stream)
            if p is None or p.kind==3:
                self.worker.retire()
                return p
            torch=self.worker.torch
            # Both bytearray and clone own host data; Linux/native pointers are
            # only metadata. Device movement happens inside the explicit worker.
            features=torch.frombuffer(bytearray(p.bf16_concat),dtype=torch.bfloat16).clone().reshape(p.row_count,WIDTH)
            if p.source==0:
                self.worker.append_prefill(stamp=self.stamp,features=features,input_ids=p.ids,positions=p.positions,final=p.final)
            elif p.source==1:
                self.worker.apply_committed_verify(stamp=self.stamp,native_round=p.round,position=p.anchor,
                    retained_features=features,retained_ids=p.ids,verified_rows=p.verified_rows,committed_rows=p.committed_rows,
                    authoritative_next_current=p.next_current)
            else:
                self.worker.apply_scalar(stamp=self.stamp,native_round=p.round,position=p.anchor,current_id=p.ids[0],
                    current_features=features,authoritative_next_current=p.next_current)
            return p
        except Exception:
            self.reader.retired=True
            self.worker.retire()
            raise

def main():
    parser=argparse.ArgumentParser(description='Default-off owned transport reader; CPU inspection only')
    parser.add_argument('--inspect-cpu',type=str)
    args=parser.parse_args()
    if not args.inspect_cpu:
        print(json.dumps({'enabled':False,'provider_executed':False}))
        return
    with open(args.inspect_cpu,'rb') as stream:
        while (p:=read_packet(stream)) is not None:
            print(json.dumps({'kind':p.kind,'source':p.source,'ticket':p.binding.ticket,'generation':p.binding.lease_generation,
                'capture_sequence':p.capture_sequence,'round':p.round,'positions':p.positions,'input_ids':p.ids,
                'bf16_bytes':len(p.bf16_concat),'final':p.final}))
if __name__=='__main__':main()
