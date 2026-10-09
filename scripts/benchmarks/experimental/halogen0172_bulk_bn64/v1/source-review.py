"""CPU-only source/ABI/routing/memory preflight. Never compiles or loads HIP."""
from pathlib import Path
import ctypes as c,hashlib,json,re,heapq
P=Path(__file__).resolve().parent;PREP=P.parent;SRC=P/'host.c'
source=SRC.read_text()
class Projection(c.Structure):
 _fields_=[('weight',c.c_uint64),('packed',c.c_uint64),('scale',c.c_uint64),('stride',c.c_uint64),('codebook',c.c_float*16)]+[(x,c.c_uint64) for x in ('metadata0','metadata1','input','permutation','items','count','output')]
class Items(c.Structure):
 _fields_=[('ids',c.c_uint64),('prefix',c.c_uint64),('raw',c.c_uint64),('rows',c.c_int32),('pad',c.c_uint32)]+[(x,c.c_uint64) for x in ('gu_items','dn_items','counts')]
class Fold(c.Structure):
 _fields_=[('dense',c.c_uint64),('inverse',c.c_uint64),('tokens',c.c_int32),('pad',c.c_uint32)]+[(x,c.c_uint64) for x in ('weights','channel','residual','scalar','output')]
assert (c.sizeof(Projection),c.sizeof(Items),c.sizeof(Fold))==(152,56,64)
assert Projection.metadata0.offset==96 and Projection.input.offset==112 and Projection.output.offset==144
assert Items.gu_items.offset==32 and Items.counts.offset==48 and Fold.weights.offset==24 and Fold.output.offset==56
inv=json.loads((PREP/'gpu-moe-compute-20261008/native-moe-kernel-inventory.json').read_text())
kernels={v['kernel']['.name']:v['kernel'] for v in inv}
symbols=re.findall(r'"(_ZN[^"\n]+)"',source)
assert len(symbols)==7 and len(set(symbols))==7
expected=[(56,512,2048),(152,256,36864),(152,256,36864),(56,512,2048),(152,256,34816),(152,256,34816),(64,256,0)]
records=[]
for sym,(size,block,lds) in zip(symbols,expected):
 k=kernels[sym]
 assert k['.kernarg_segment_size']==size and k['.max_flat_workgroup_size']==block and k['.group_segment_fixed_size']==lds and k['.wavefront_size']==32
 records.append({'symbol':sym,'kernargs':size,'block':block,'fixed_LDS':lds,'dynamic_LDS':0})
co=PREP/'gpu-moe-compute-20261008/bundle0-gfx1151-code-object.data'
assert co.stat().st_size==17765424 and hashlib.sha256(co.read_bytes()).hexdigest()=='18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039'
N=8192;R=81920;E=512;boundary=[1,15,16,17,31,32,33,47,48,49,63,64,65,79,80,81,95,96,97,111,112,113,127,128,129,159,160,161,255,256,257]
route_records=[]
for pattern in (0,1):
 target=[160]*E
 if pattern:
  deficit=sum(160-z for z in boundary);target[:len(boundary)]=boundary
  e=len(boundary)
  while deficit:target[e]+=1;deficit-=1;e=e+1 if e+1<E else len(boundary)
 assert sum(target)==R and max(target)<=N and min(target)>0
 heap=[(-z,e) for e,z in enumerate(target)];heapq.heapify(heap);routes=[]
 for n in range(N):
  if pattern:
   chosen=[heapq.heappop(heap) for _ in range(10)]
   assert all(z<0 for z,e in chosen)
   es=[e for z,e in chosen]
   for z,e in chosen:heapq.heappush(heap,(z+1,e))
  else:es=[(10*n+j)%E for j in range(10)]
  assert len(set(es))==10;routes.extend(es)
 observed=[0]*E
 for e in routes:observed[e]+=1
 assert observed==target
 prefix=[0]
 for z in target:prefix.append(prefix[-1]+z)
 cursor=prefix[:-1].copy();forward=[-1]*R;inverse=[-1]*R
 for s,e in enumerate(routes):q=cursor[e];cursor[e]+=1;forward[q]=s;inverse[s]=q
 assert all(forward[inverse[s]]==s for s in range(R))
 counts={}
 for bn in (128,64):
  segments=sum((z+bn-1)//bn for z in target);capacity=R//bn+E
  assert segments<=capacity
  items=[(e,h,prefix[e]+u,min(bn,z-u)) for e,z in enumerate(target) for u in range(0,z,bn) for h in range(5)]
  assert len(items)==5*segments
  covered=sum(rows for e,h,start,rows in items if h==0);assert covered==R
  counts[str(bn)]={'segments':segments,'GU_items':5*segments,'DN_items':10*segments,'capacity':capacity}
 route_records.append({'pattern':'boundary_tails' if pattern else 'uniform512x160','histogram':target,'ten_distinct_experts_per_token':True,'P_I_inverse':True,'variants':counts})
sizes=[865075200,432537600,N*2560*2,R*4,R*4,E*4,(E+1)*4,(E+2)*4,R*4,2560,1280,5120,N*2560*2,N*4,5*1792*16,10*1792*16,8,R*640*2,R*2560*2,N*2560*2,R*640*2,R*2560*2,N*2560*2]
device=sum(sizes)+len(sizes)*8192
assert device<3*1024**3
assert 'const int poison=bn==128?0xa5:0x5a;' in source and 'clear_outputs(bn)' in source
bounds=PREP/'prefill-bulk-moe-retile-scope-20261009/host-route-proof-v1.activation-bounds.md'
assert bounds.exists()
out={'result':'PASS_CPU_SOURCE_ABI_ROUTE_AND_BUDGET_CHECKS','compiled':False,'hardware':False,'source_sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'kernels':records,'GPU_allocation_bytes':device,'GPU_GiB':device/1024**3,'host_peak_bound_bytes':2*4*1024**2+3*R*4+16384,'activation_bounds_sha256':hashlib.sha256(bounds.read_bytes()).hexdigest(),'activation_conservative_envelope':'[-8,L+512), within initialized4096byte prefix/suffix','route_patterns':route_records,'limits':['C source has not been compiled or device-launched.','Full outputs must be compared at unchanged bitwise equality before any performance result is qualified.']}
(P/'source-review.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('kernels','route_patterns','limits')},indent=2))
