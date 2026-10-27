"""Independent stdlib BF16-bit oracle; no Torch, HIP or device imports.

RN FP32: (((+0+a)+(+0+b))+(+0+c))+(+0+d), then *0.25 and RN-even BF16.
NaNs canonicalize to0x7fc0. Preserves FP32 cancellation/overflow, not real sum.
"""
from array import array
import argparse
import json
from pathlib import Path
import struct
import sys

def fp32(x):
    try:return struct.unpack('<f',struct.pack('<f',x))[0]
    except OverflowError:return float('-inf') if x<0 else float('inf')

def from_bf16(bits):return struct.unpack('<f',struct.pack('<I',bits<<16))[0]

def to_bf16(value):
    u=struct.unpack('<I',struct.pack('<f',fp32(value)))[0]
    if (u&0x7fffffff)>0x7f800000:return 0x7fc0
    return ((u+0x7fff+((u>>16)&1))>>16)&0xffff

def mean_bits(values):
    if len(values)!=4 or any(type(x) is not int or not 0<=x<=65535 for x in values):raise ValueError('four BF16 words required')
    accum=[fp32(0.0+from_bf16(x)) for x in values]
    value=accum[0]
    for item in accum[1:]:value=fp32(value+item)
    return to_bf16(fp32(value*.25))

def patterns():
    b=to_bf16
    return [list(map(b,p)) for p in ([1,2,3,4],[2**24,1,-2**24,1],[2**24,-2**24,1,1],
        [1,2**-8,0,0],[1,3*2**-8,0,0],[-1,-2,-3,-4],[2**100,2**-100,-2**100,2**-100])]+[
        [0x7f7f]*4,[1,1,1,1],[1,0,0,0],[0x8000]*4,[0x7f80]*4,[0x7f80,0xff80,0,0],[0x7fc1,0,0,0]]

def make_fixture(full_rows,source_first,rows,tap,destination_first,destination_rows=None):
    if (any(type(x) is not int for x in (full_rows,source_first,rows,tap,destination_first)) or
        not 1<=full_rows<=8192 or not 0<=source_first<full_rows or not 1<=rows<=full_rows-source_first or
        not 0<=tap<5 or destination_first<0):raise ValueError('invalid fixture geometry')
    destination_rows=destination_rows or min(8192,destination_first+rows+1)
    if destination_rows<destination_first+rows or destination_rows>8192:raise ValueError('invalid destination')
    ps=patterns()
    one=array('H',(ps[col%len(ps)][stream] for stream in range(4) for col in range(2560)))
    raw=one*full_rows
    for row in range(full_rows):
        raw[row*10240]=to_bf16(1+row%32)
        raw[row*10240+3*2560+2559]=to_bf16(-1-row%32)
    expected=array('H',[0x55aa])*(destination_rows*12800)
    out=array('H',(mean_bits(ps[col%len(ps)]) for col in range(2560)))
    for row in range(rows):
        begin=(destination_first+row)*12800+tap*2560
        expected[begin:begin+2560]=out
        source=(source_first+row)*10240
        for col in (0,2559):
            expected[begin+col]=mean_bits([raw[source+s*2560+col] for s in range(4)])
    return raw,expected

def write_fixture(directory,full_rows,source_first,rows,tap,destination_first):
    if sys.byteorder!='little':raise ValueError('little-endian fixture host required')
    raw,expected=make_fixture(full_rows,source_first,rows,tap,destination_first)
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    (directory/'raw.u16').write_bytes(raw.tobytes());(directory/'expected.u16').write_bytes(expected.tobytes())
    meta=dict(full_rows=full_rows,source_first=source_first,rows=rows,tap=tap,destination_first=destination_first,
              destination_rows=len(expected)//12800,raw_elements=len(raw),output_elements=len(expected),sentinel=0x55aa)
    (directory/'fixture.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--full-rows',type=int,default=4)
    p.add_argument('--source-first',type=int,default=2);p.add_argument('--rows',type=int,default=2)
    p.add_argument('--tap',type=int,default=3);p.add_argument('--destination-first',type=int,default=1)
    a=p.parse_args();write_fixture(a.directory,a.full_rows,a.source_first,a.rows,a.tap,a.destination_first)
