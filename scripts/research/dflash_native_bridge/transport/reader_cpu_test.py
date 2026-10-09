"""CPU bytes/metadata tests only: no torch/HIP/provider import or execution."""
import io
from dataclasses import replace
from pathlib import Path
import struct
import zlib
from owned_reader import Binding, OwnedReader, Packet, ProviderReceiver, read_packet

def reject(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('Expected rejection')

def packets(blob):
    stream=io.BytesIO(blob);result=[]
    while (p:=read_packet(stream)) is not None:result.append(p)
    return result

def main():
    blob=Path('cpu-wire-fixture.bin').read_bytes();p=packets(blob)
    assert len(p)==4
    b=Binding(bytes([1])+bytes(15),1,1,9,100,200,300,400,5,0,5)
    assert all(x.binding==b for x in p)
    r=OwnedReader(b)
    for x in p:r.accept(x)
    assert r.prefill_complete and r.position==8 and r.last_round==9 and r.last_capture_sequence==2
    assert [x.source for x in p]==[0,0,1,2]
    assert [x.ids for x in p]==[(11,12,13,14),(15,),(31,32),(99,)]
    assert [x.positions for x in p]==[(0,1,2,3),(4,),(5,6),(7,)]
    for x in p:
        words=struct.unpack('<'+'H'*(len(x.bf16_concat)//2),x.bf16_concat)
        for row in range(x.row_count):
            for tap in range(5):
                for column in range(2560):
                    expected=(100*tap+10*(x.row_offset+row)+column%10) if x.source==0 else (1000+100*tap+10*row+column%10)
                    assert words[row*12800+tap*2560+column]==expected
    reject(lambda:r.accept(p[-1]))
    for field in ('ticket','lease_generation','cache_generation','holder','model','wire','request','birth','slot','total'):
        altered=replace(b,**{field:getattr(b,field)+1})
        reject(lambda altered=altered:OwnedReader(b).accept(replace(p[0],binding=altered)))
    reject(lambda:OwnedReader(b).accept(replace(p[0],binding=replace(b,session=bytes(16)))))
    reject(lambda:OwnedReader(b).accept(replace(p[0],row_offset=1)))
    reject(lambda:OwnedReader(b).accept(replace(p[0],final=True)))
    reject(lambda:OwnedReader(b).accept(p[2]))
    r=OwnedReader(b);r.accept(p[0]);reject(lambda:r.accept(p[2]))
    r=OwnedReader(b);r.accept(p[0]);r.accept(p[1]);reject(lambda:r.accept(replace(p[2],row_count=3)))
    r=OwnedReader(b);r.accept(p[0]);r.accept(p[1]);reject(lambda:r.accept(replace(p[2],anchor=6)))
    r=OwnedReader(b);r.accept(p[0]);r.accept(p[1]);r.accept(p[2]);reject(lambda:r.accept(replace(p[3],capture_sequence=1)))
    r=OwnedReader(b);r.accept(p[0]);r.accept(p[1]);r.accept(p[2]);reject(lambda:r.accept(replace(p[3],round=7)))
    r=OwnedReader(b,capacity=7);r.accept(p[0]);r.accept(p[1]);r.accept(p[2]);reject(lambda:r.accept(p[3]))
    abort=replace(p[0],kind=3,row_count=0,ids=(),bf16_concat=b'',final=False)
    r=OwnedReader(b);r.accept(abort);assert r.retired;reject(lambda:r.accept(p[0]))
    r=OwnedReader(b);reject(lambda:r.receive(io.BytesIO()));assert r.retired
    r=OwnedReader(b);reject(lambda:r.receive(io.BytesIO(blob[:20])));assert r.retired
    broken=bytearray(blob);broken[70]^=1;reject(lambda:packets(broken))
    broken=bytearray(blob);broken[300]^=1;reject(lambda:packets(broken))
    broken=bytearray(blob);struct.pack_into('<Q',broken,16,2**63);struct.pack_into('<I',broken,212,0);struct.pack_into('<I',broken,212,zlib.crc32(broken[:256]));reject(lambda:packets(broken))
    # A fake explicit worker tests metadata dispatch without importing torch,
    # model weights, actual provider modules, device discovery or numerical work.
    class Tensor:
        def clone(self):return self
        def reshape(self,*shape):self.shape=shape;return self
    class Torch:
        bfloat16=object()
        def frombuffer(self,data,dtype):assert isinstance(data,bytearray);return Tensor()
    class Worker:
        capacity=16640;torch=Torch()
        def __init__(self):self.calls=[];self.retired=False
        def append_prefill(self,**kw):self.calls.append(('prefill',kw))
        def apply_committed_verify(self,**kw):self.calls.append(('verify',kw))
        def apply_scalar(self,**kw):self.calls.append(('scalar',kw))
        def retire(self):self.retired=True
    class Stamp:
        session_hex=b.session.hex();pending_ticket=1;lease_generation=1;cache_generation=9
        holder_identity=100;model_address=200;wire_id=300;request_address=400;request_birth='5';slot=0;total_prefill=5
    w=Worker();adapter=ProviderReceiver(w,Stamp(),b);stream=io.BytesIO(blob)
    for _ in range(4):assert adapter.receive(stream)
    assert [name for name,_ in w.calls]==['prefill','prefill','verify','scalar']
    verify=w.calls[2][1];assert verify['native_round']==7 and verify['position']==5 and verify['retained_ids']==(31,32) and verify['retained_features'].shape==(2,12800)
    scalar=w.calls[3][1];assert scalar['native_round']==9 and scalar['position']==7 and scalar['current_id']==99 and scalar['current_features'].shape==(1,12800)
    reject(lambda:adapter.receive(stream));assert w.retired
    print('CPU reader: exact full Binding, IDs, positions, sources and every BF16 word; malformed/stale/loss/terminal paths passed')
if __name__=='__main__':main()
