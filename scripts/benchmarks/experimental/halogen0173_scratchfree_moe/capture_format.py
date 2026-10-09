"""Private captured operation metadata, with no tensor payload in the report."""
import hashlib
from pathlib import Path
import struct
def inspect(path):
    path=Path(path)
    with path.open('rb') as f:
        header=f.read(32)
        if len(header)!=32:raise ValueError('Incomplete FL capture header')
        magic,version,n,e,complete,scale_bytes=struct.unpack('<8sIIIIq',header)
        if (magic,version,n,complete)!=(b'H0173FL1',1,3,1) or not 1<=e<=30 or scale_bytes!=e*2560*320:
            raise ValueError('Unsupported or incomplete actual FL capture')
        spans={};at=32
        for name,size in [('weights',e*2560*330),('input',30*640*2),('indices',30*4),('routes',30*4),
                          ('metadata',2560*2),('residual',3*2560*2),('scalar',3*4),('map',30*4),
                          ('counters_before',60*4),('original_experts',e*4),('counters_after',60*4),('gold',3*2560*2)]:
            spans[name]=dict(offset=at,bytes=size);at+=size
        if path.stat().st_size!=at:raise ValueError('Captured operation extent differs')
        def ints(name,count,signed=True):
            f.seek(spans[name]['offset']);return struct.unpack('<'+('i' if signed else 'I')*count,f.read(count*4))
        indices=ints('indices',30);task_map=ints('map',30);original=ints('original_experts',e)
        before=ints('counters_before',60,False);after=ints('counters_after',60,False)
        if any(x<0 or x>=e for x in indices) or sorted(task_map)!=list(range(30)):
            raise ValueError('Original-task coverage or compact expert binding differs')
        if len(set(original))!=e or any(x<0 or x>=512 for x in original) or any(before) or any(after):
            raise ValueError('Native zero-counter postcondition or source expert binding differs')
    with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(schema='alloy0173.scratchfree-moe.actual-fl-capture.v1',path=str(path.resolve()),bytes=at,sha256=digest,
                tokens=n,route_tasks=30,selected_experts=e,spans=spans,task_map_permutation=True,
                counters_before_all_zero=True,counters_after_all_zero=True,
                native_bf16_outputs=7680,tensor_payload_published=False,synthetic_inputs=False)
