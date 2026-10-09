"""Finite static address slices only; no HIP, device execution or model inputs."""
from pathlib import Path
import re, bisect, json, functools
root=Path(__file__).resolve().parent
files=[root/'gu-bn64.device-disassembly.txt',root.parent/'gpu-moe-compute-20261008/q4moe-mode1-gu-bn128.device-disassembly.txt']
all_records=[]
for path in files:
 skip_ranges=[]
 rows=[]; history={}
 for line in path.read_text().splitlines():
  m=re.search(r'// ([0-9A-F]{12}):',line)
  if not m:continue
  for inst in line.split('//')[0].strip().split(' :: '):
   op,_,body=inst.partition(' '); op=op.replace('v_dual_','v_')
   aa=[a.strip() for a in re.split(r',(?![^\[]*\])',body)]
   i=len(rows); rows.append((int(m[1],16),op,aa,inst))
   if op.startswith(('v_','s_')) and aa:
    d=aa[0]; pair=re.fullmatch(r'([vs])\[(\d+):(\d+)\]',d)
    dest=[d] if re.fullmatch(r'[vs]\d+',d) else []
    if pair:dest=[pair[1]+str(v) for v in range(int(pair[2]),int(pair[3])+1)]
    for d in dest:history.setdefault(d,[]).append(i)
 @functools.lru_cache(None)
 def val(tok, before):
  try:return frozenset([int(tok,0)]),tok
  except ValueError:pass
  seq=history.get(tok,[]); j=bisect.bisect_left(seq,before)-1
  if j<0:return None,'unbounded:'+tok
  while j>=0 and any(lo<=rows[seq[j]][0]<hi for lo,hi in skip_ranges):j-=1
  if j<0:return None,'unbounded:'+tok
  k=seq[j]; pc,op,a,raw=rows[k]
  if op=='s_load_b128' and a[1]=='s[4:5]' and a[2]=='null':
   first=int(re.search(r'\[(\d+):',a[0])[1]); field=int(tok[1:])-first
   if field==1:return frozenset(range(5)),'item.output_tile[0..4]'
  if op in ('v_mov_b32_e32','v_mov_b32','s_mov_b32'):return val(a[1],k)
  if op in ('v_and_b32_e32','v_and_b32'):
   x,xe=val(a[1],k); y,ye=val(a[2],k)
   if x is None and y is not None and len(y)==1 and max(y)<=31:return frozenset(range(max(y)+1)),f'({xe}&{ye})'
   if y is None and x is not None and len(x)==1 and max(x)<=31:return frozenset(range(max(x)+1)),f'({xe}&{ye})'
   if x is not None and y is not None:return frozenset(p&q for p in x for q in y),f'({xe}&{ye})'
  ops={'v_or_b32_e32':lambda x,y:x|y,'v_or_b32':lambda x,y:x|y,'v_add_nc_u32_e32':lambda x,y:x+y,'v_add_nc_u32':lambda x,y:x+y,'s_lshl_b32':lambda x,y:x<<y}
  if op in ops:
   x,xe=val(a[1],k);y,ye=val(a[2],k)
   if x is not None and y is not None:return frozenset(ops[op](p,q) for p in x for q in y),f'{op}({xe},{ye})'
  if op in ('v_lshlrev_b32_e32','v_lshlrev_b32'):
   x,xe=val(a[1],k);y,ye=val(a[2],k)
   if x is not None and y is not None:return frozenset(q<<p for p in x for q in y),f'({ye}<<{xe})'
  if op in ('v_ashrrev_i32_e32','v_ashrrev_i32'):
   x,xe=val(a[1],k);y,ye=val(a[2],k)
   if x is not None and y is not None and max(y)<2**31:return frozenset(q>>p for p in x for q in y),f'({ye}>>{xe})'
  return None,f'unresolved@{pc:x}:{raw}'
 loads=[i for i,r in enumerate(rows) if r[1]=='global_load_b64']
 assert len(loads)%3==0
 for n in range(0,len(loads),3):
  # These are control-flow bypasses, not approximate reaching definitions.
  # Full GU64 g4: K20 branch at e017bc resumes at e0fc24.
  # Full GU128 g8: getpc e317c8, next PC e317cc +34a30 resumes e661fc.
  skip_ranges=[]
  if path.name=='gu-bn64.device-disassembly.txt' and 10<=n//3<=17:skip_ranges=[(0xe0369c,0xe0fc24)]
  # GU64 g1 K20 branch e0e240 resumes e14d64, bypassing g4 epilogue.
  if path.name=='gu-bn64.device-disassembly.txt' and 18<=n//3<=19:skip_ranges=[(0xe0fc24,0xe14d64)]
  if path.name!='gu-bn64.device-disassembly.txt' and 54<=n//3<=69:skip_ranges=[(0xe33ee4,0xe661fc)]
  if path.name!='gu-bn64.device-disassembly.txt' and 70<=n//3<=71:skip_ranges=[(0xe661fc,0xe70558)]
  val.cache_clear()
  first=loads[n]; triple=loads[n:n+3]
  assert rows[triple[1]][2][-1]=='off offset:1280'
  shift=next(i for i in range(first-1,max(first-22,0),-1) if rows[i][1]=='v_lshlrev_b64' and rows[i][2][1]=='1')
  channel=rows[shift][2][2]; low=int(re.search(r'\[(\d+):',channel)[1]); values,expr=val('v'+str(low),shift)
  assert values is not None,(path,n,expr)
  assert values==frozenset(range(0,640,4)),(path,n,min(values),max(values),expr)
  high_values,high_expr=val('v'+str(low+1),shift)
  assert high_values==frozenset([0]),(path,n,'channel high word',high_expr)
  bases=[]
  for load_i,expected in zip(triple,['s24','s24','s26']):
   addr=rows[load_i][2][1]; addr_low=int(re.search(r'\[(\d+):',addr)[1])
   for reg,sgpr,op in [('v'+str(addr_low),expected,'v_add_co_u32'),('v'+str(addr_low+1),'s'+str(int(expected[1:])+1),'v_add_co_ci_u32_e64')]:
    seq=history[reg];j=bisect.bisect_left(seq,load_i)-1
    while j>=0 and any(lo<=rows[seq[j]][0]<hi for lo,hi in skip_ranges):j-=1
    assert j>=0 and rows[seq[j]][1]==op and sgpr in rows[seq[j]][2],(path,n,reg,rows[seq[j]])
   bases.append('Args+0x60' if expected=='s24' else 'Args+0x68')
  all_records.append({'variant':path.name,'loads':[hex(rows[i][0]) for i in triple],'bases':bases,'shift':hex(rows[shift][0]),'channel_register':channel,'channel_expression':expr,'channel_high_word':0,'channel_min':min(values),'channel_max':max(values),'channel_count':len(values),'control_flow_skips':[[hex(lo),hex(hi)] for lo,hi in skip_ranges],'first_plane_upper_exclusive':max(values)*2+8,'second_plane_upper_exclusive':max(values)*2+1280+8,'second_pointer_upper_exclusive':max(values)*2+8})
out={'schema':'host-route-proof-v1-metadata-bounds','method':'backward integer address slices, conservative masked unknowns, all static triples','triples':len(all_records),'records':all_records,'Args_0x60_bytes':2560,'Args_0x68_bytes':1280,'additional_b64_padding_bytes':0}
(root/'host-route-proof-v1.metadata-bounds.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'triples':len(all_records),'variants':{p.name:sum(r['variant']==p.name for r in all_records) for p in files},'Args_0x60_bytes':2560,'Args_0x68_bytes':1280,'additional_padding':0}))
