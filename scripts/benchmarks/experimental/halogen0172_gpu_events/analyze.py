"""CPU-only sampled native-stream brackets, no busy-timeline inference."""
import argparse,hashlib,json,math,statistics,struct
from collections import Counter,defaultdict
from pathlib import Path
DEFAULT_WORK=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--evidence-dir',type=Path,default=DEFAULT_WORK,
    help='directory containing retained evidence and receiving analysis.json')
WORK=parser.parse_args().evidence_dir.resolve()
HEADER=struct.Struct('<8s4I2Q2I2Q');WIRE=struct.Struct('<9Q7I5ifI')
def read(p):return json.loads(p.read_bytes())
def ref(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def require(condition,message):
    if not condition:raise ValueError(message)

raw=(WORK/'gpu-events.bin').read_bytes()
require(len(raw)>=HEADER.size,'truncated event header')
h=HEADER.unpack_from(raw)
require(h[0]==b'HGGE0172' and h[1:5]==(1,64,128,7) and h[8:10]==(512,32),
    'unsupported event header/clock/pool/sampling contract')
require(h[6]==32*1024*1024 and len(raw)<=h[6] and (len(raw)-64)%128==0,
    'invalid event byte count or output cap')
rows=list(WIRE.iter_unpack(raw[64:]))
require(all(r[0]==i+1 for i,r in enumerate(rows)),'noncontiguous append sequence')
require(all(r[15] in (1,2,3,4) for r in rows),'unknown event record type')
boundaries=read(WORK/'request-boundaries.json')
require(h[7]==boundaries['target_process_id'],'event/boundary PID mismatch')
require(boundaries.get('clock_alignment_valid') is True and
    boundaries.get('clock_domain')=='linux_CLOCK_BOOTTIME_ns','unqualified request clock alignment')
mapping=read(WORK/'descriptor-map.json')
names={e['descriptor_rva']:e['symbol'] for e in mapping['entries']}
require(len(names)==len(mapping['entries']),'duplicate descriptor-map identity')
samples={r[7]:r for r in rows if r[15] in (1,4) and r[7]}
require(len(samples)==sum(r[15] in (1,4) and bool(r[7]) for r in rows),
    'duplicate sampled launch ID')
times={r[7]:r for r in rows if r[15]==2}
require(len(times)==sum(r[15]==2 for r in rows),'duplicate timing ID')
require(set(samples)==set(times),'sampled-launch/timing ID sets differ')
require(set(samples)==set(range(1,len(samples)+1)) and len(samples)<=8192,
    'noncontiguous sample IDs or lifetime sample cap exceeded')
for sample_id,t in times.items():
    launch=samples[sample_id]
    require(t[1:15]==launch[1:15] and t[16:19]==launch[16:19],
        f'launch/timing metadata or marker-status mismatch for sample {sample_id}')
    require(t[0]>launch[0],f'timing precedes launch for sample {sample_id}')
require(all(r[2]>=r[1] for r in rows if r[15] in (1,4)),'launch host timestamps reversed')

snapshots=[r for r in rows if r[15]==3]
require(bool(snapshots) and rows[-1][15]==3,'closed export needs a final snapshot')
cumulative_fields=(3,4,5,7,8,9,10,12,13,16,22)
previous=None
prefix_seen=prefix_selected=prefix_timings=0
for r in rows:
    if r[15] in (1,4):
        prefix_seen+=1;prefix_selected+=bool(r[7])
    elif r[15]==2:prefix_timings+=1
    else:
        require(r[1]==r[2],'snapshot timestamps differ')
        require(r[6]==r[4]-r[5]-r[22],'snapshot sample disposition balance mismatch')
        require(r[6]<=h[8] and r[4]<=8192 and r[13]<=r[12]<=2*h[8],
            'snapshot pool/sample/handle limit mismatch')
        require(r[16]==r[22],'snapshot deferred/retired pair count mismatch')
        require(r[9] in (0,1,2),'unknown snapshot timing-disabled state')
        require((r[3],r[4],r[5]+r[22])==(prefix_seen,prefix_selected,prefix_timings),
            'snapshot counters disagree with preceding wire records')
        if previous is not None:
            require(r[1]>=previous[1] and all(r[i]>=previous[i] for i in cumulative_fields),
                'snapshot cumulative counter or clock decreased')
        previous=r
last=snapshots[-1]
require(last[6]==0 and last[12]==last[13] and last[9] in (1,2),
    'export is not closed or event handles were not destroyed')

receipt_path=WORK/'live-export-receipt.json'
if receipt_path.exists():
    receipt=read(receipt_path);closed=receipt['closed'];engine=closed['engine']
    require(engine['pid']==h[7] and engine['sha256']==mapping.get('engine_sha256'),
        'descriptor map does not bind to retained live engine PID/image')
    require(receipt['raw']['bytes']==len(raw) and closed['bytes']==len(raw) and
        receipt['raw']['sha256']==hashlib.sha256(raw).hexdigest(),'raw export receipt mismatch')
    require(closed.get('close_confirmed') is True and closed['last']==list(last),
        'closure receipt does not match final event snapshot')
    observer=receipt.get('manifest_observer',{})
    if 'source_sha256' in observer:
        require(observer['source_sha256']==hashlib.sha256((WORK/'gpu_events.c').read_bytes()).hexdigest(),
            'observer source does not match retained manifest')
report=dict(schema='halogen0172.sampled-stream-brackets.v1',
    raw=ref(WORK/'gpu-events.bin'),source=ref(WORK/'gpu_events.c'),map=ref(WORK/'descriptor-map.json'),
    boundaries=ref(WORK/'request-boundaries.json'),record_count=len(rows),
    sample_probability_denominator=h[9],pool_pairs=h[8],seed=h[10],
    phase_classification='unclassified; group exact launch geometry',
    hidden_library_PTDS_graph_runtime_launches_covered=False,
    absolute_GPU_timestamps=False,GPU_busy_time=False,qualified_post_rates=False,
    stream_brackets_include_marker_overhead_and_possible_default_stream_dependencies=True,
    windows=[])
for w in boundaries['requests']:
    launches=[r for r in rows if r[15] in (1,4) and w['request_start_ns']<=r[1]<w['request_end_ns']]
    groups=defaultdict(list)
    for r in launches:groups[(r[15],r[4],r[5],tuple(r[9:12]),tuple(r[12:15]),r[8],r[3])].append(r)
    classified=[]
    for (api,fn,stream,grid,block,shared,caller),ls in groups.items():
        eligible=[times[r[7]] for r in ls if r[7] in times]
        good=[t for t in eligible if all(t[i]==0 for i in (16,17,18,19,20)) and math.isfinite(t[21]) and t[21]>=0]
        ms=[t[21] for t in good]
        rva=fn-h[5] if api==1 else None
        entry=dict(kernel_descriptor_rva=hex(rva) if rva is not None else None,
            caller_rva=hex(caller) if caller!=(1<<64)-1 else None,
            symbol=names.get(rva,'unknown'),API='hipLaunchKernel' if api==1 else 'hipModuleLaunchKernel',
            phase='unclassified',stream=hex(stream),grid=list(grid),block=list(block),shared_bytes=shared,
            observed_launches=len(ls),selected=sum(bool(r[7]) for r in ls),
            harvested=len(eligible),valid=len(good),invalid=len(eligible)-len(good),
            pending=sum(bool(r[7]) and r[7] not in times for r in ls),
            native_errors=sum(r[16]!=0 for r in ls),
            mean_bracket_ms=statistics.mean(ms) if ms else None,
            median_bracket_ms=statistics.median(ms) if ms else None,
            observed_sample_sum_ms=sum(ms),
            observed_count_times_sample_mean_ms=statistics.mean(ms)*len(ls) if ms else None,
            sampling_sparsity='fewer-than8-valid-samples' if len(ms)<8 else 'at-least8-valid-samples',
            nominal_probability_expansion_ms=sum(ms)*h[9],
            expansion_is_diagnostic_estimate_not_complete_kernel_time=True)
        if (rva==0x18f4300 and all(x==1 for x in grid[1:]) and grid[0]>0 and grid[0]%400==0
            and all(r[3]==0x17d3e59 for r in ls) and block==(256,1,1) and shared==0):
            entry['source_geometry_derived_N']=grid[0]//400
        classified.append(entry)
    classified.sort(key=lambda e:e['observed_count_times_sample_mean_ms'] or 0,reverse=True)
    report['windows'].append(dict(name=w['phase'],observed_launches=len(launches),
        samples_selected=sum(bool(r[7]) for r in launches),
        native_errors=sum(r[16]!=0 for r in launches),stream_counts=dict(Counter(hex(r[5]) for r in launches)),
        groups=classified,wall_seconds=w['wall_seconds'],
        output_sha256=w['output_sha256'],acceptance=w['acceptance']))
report['final_counters']=dict(seen=last[3],selected=last[4],harvested=last[5],pending=last[6],
    capacity_dropped=last[7],reentrant_skipped=last[8],timing_disabled=last[9],capture_skips=last[10],
    event_handles_created=last[12],event_handles_destroyed=last[13],
    retired=last[22],deferred_cleanup=last[16])
(WORK/'analysis.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(dict(final=report['final_counters'],windows=[dict(name=w['name'],launches=w['observed_launches'],
    samples=w['samples_selected'],top=w['groups'][:8]) for w in report['windows']]),indent=2))
