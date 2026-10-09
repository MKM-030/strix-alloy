"""Root-only bounded sequential real requests with exact native byte intervals."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import socket
import sys
import time
import aiohttp
import capture_control as control
import capture_launch as launch

WORK=launch.WORK
CORPUS=launch.PREP/'selector-real-request-provenance-20261009'
sys.path.insert(0,str(launch.ROOT/'scripts/benchmarks'))
from article_metrics import cold_sample
spec=importlib.util.spec_from_file_location('load_window',launch.PREP/'normal-sdma0-comparison-20261009/window.py')
frozen=importlib.util.module_from_spec(spec);spec.loader.exec_module(frozen)
def utc(): return datetime.now(timezone.utc).isoformat()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    with p.open('x',encoding='utf-8',newline='\n') as f: json.dump(value,f,indent=2)
def snapshot(cid,offset=None):
    code='from pathlib import Path;import json,struct,sys;p=Path(sys.argv[1]);b=p.read_bytes();o=int(sys.argv[2]);print(json.dumps(dict(bytes=len(b),events=[dict(zip(("kind","flags","seq","birth","cookie","epoch","round","wire_id"),struct.unpack_from("<II6Q",b,i))) for i in range(o,len(b)-511,512)])))'
    return json.loads(control.docker('exec',cid,'python3','-c',code,launch.JOURNAL,str(offset if offset is not None else 128)))

async def run(mode):
    corpus=json.loads((CORPUS/'manifest.json').read_bytes())
    assert sha(CORPUS/'manifest.json')=='76de0b548bfb48f028e50bf8517e8f9514d2cbbc03eb48668d445b834b59960c'
    assert len(corpus['requests'])==16
    folder=WORK/mode;folder.mkdir(exist_ok=False)
    checked=control.checkpoint('capture' if mode=='capture' else 'normal')
    outer,backend=checked['controller'],checked['backend']
    capture=mode=='capture';profile_path=launch.PROFILE if capture else control.m.PROFILE
    profile=control.read(profile_path);port=8842 if capture else 8840
    secret=Path(profile['token_file']).read_text(encoding='ascii').strip()
    headers={'Authorization':'Bearer '+secret};origin='http://127.0.0.1:'+str(port)
    logpath=Path(backend['log_file']);cid=backend['container_id']
    if capture:
        with socket.socket() as sock: assert sock.connect_ex(('127.0.0.1',8840))!=0
        startup=json.loads(control.docker('exec',cid,'cat',launch.STATUS))
        assert startup['full_elf_verified'] and startup['native_pins_verified'] and startup['capture_enabled']
        write(folder/'startup.json',startup)
    start=time.perf_counter();results=[]
    async with aiohttp.ClientSession(trust_env=False,timeout=aiohttp.ClientTimeout(total=90)) as client:
        for item in corpus['requests']:
            assert time.perf_counter()-start<1800
            request_dir=folder/item['request_id'];request_dir.mkdir(exist_ok=False)
            for name in ('payload','document'):
                assert sha(CORPUS/item[name]['path'])==item[name]['sha256']
            body=json.loads((CORPUS/item['payload']['path']).read_bytes())
            assert min(control.frame()[k] for k in frozen.MEMORY_FIELDS)>=22*2**30
            load=frozen.fresh_load_snapshot(request_dir)
            assert min(control.frame()[k] for k in frozen.MEMORY_FIELDS)>=22*2**30
            before=control.health(profile);write(request_dir/'health-before.json',before)
            now=control.read(launch.ROOT/'server/.local/current.json')
            assert now['run_id']==outer['run_id'] and now['profile_sha256']==sha(profile_path)
            assert control.m.identity(outer['pid'])==checked['identities']['controller']
            assert control.m.identity(backend['controller_pid'])==checked['identities']['backend']
            current_backend=control.read(launch.BACKEND/'.local/current-service.json')
            assert current_backend['phase']=='ready' and all(current_backend[k]==backend[k] for k in ('run_id','container_id','controller_pid','log_file'))
            lo=logpath.stat().st_size
            if capture:
                watermark=snapshot(cid);jb=watermark['bytes'];assert jb>=128 and (jb-128)%512==0
            else: jb=None
            write(request_dir/'intent.json',dict(utc=utc(),request_id=item['request_id'],controller_run_id=outer['run_id'],backend_run_id=backend['run_id'],log_before_bytes=lo,journal_before_bytes=jb,request_sent_once=True))
            minimum={k:control.frame()[k] for k in frozen.MEMORY_FIELDS};done=asyncio.Event()
            async def watch():
                while not done.is_set():
                    sample=control.frame()
                    for k in minimum: minimum[k]=min(minimum[k],sample[k])
                    if min(minimum.values())<18*2**30: raise RuntimeError('Runtime reserve below18 GiB')
                    try: await asyncio.wait_for(done.wait(),timeout=.2)
                    except asyncio.TimeoutError: pass
            async def send():
                async with client.post(origin+'/v1/chat/completions',headers=headers,json=body,allow_redirects=False) as response:
                    value=await response.json();assert response.status==200,response.status
                    return value
            begun=utc();qpc=time.perf_counter();request=asyncio.create_task(send());watcher=asyncio.create_task(watch())
            try:
                finished,_=await asyncio.wait((request,watcher),return_when=asyncio.FIRST_COMPLETED)
                if watcher in finished: await watcher
                value=await request
            finally:
                wall=time.perf_counter()-qpc;done.set()
                if not request.done(): request.cancel()
                await asyncio.gather(request,watcher,return_exceptions=True)
            ended=utc();write(request_dir/'response.json',value)
            actual_input=value['usage']['prompt_tokens'];actual_output=value['usage']['completion_tokens']
            assert type(actual_input) is int and 0<actual_input<=4096 and type(actual_output) is int and 0<actual_output<=128
            metrics=cold_sample(value,actual_input,actual_output)
            assert metrics['timings'].get('disk_restore_n',0)==0
            assert value['usage'].get('completion_tokens_details',{}).get('reasoning_tokens',0)==0
            assert type(metrics['accepted']) is int and type(metrics['drafted']) is int
            after=control.health(profile);write(request_dir/'health-after.json',after)
            assert after['completed']-before['completed']==1 and after['cancelled']==before['cancelled']
            assert control.read(launch.ROOT/'server/.local/current.json')['run_id']==outer['run_id']
            current_backend=control.read(launch.BACKEND/'.local/current-service.json')
            assert current_backend['phase']=='ready' and all(current_backend[k]==backend[k] for k in ('run_id','container_id','controller_pid','log_file'))
            assert control.m.identity(outer['pid'])==checked['identities']['controller']
            assert control.m.identity(backend['controller_pid'])==checked['identities']['backend']
            if capture:
                # Wait for the existing writer to publish retirement; never resend the API.
                limit=time.monotonic()+10
                while True:
                    water=snapshot(cid,jb);events=water['events']
                    births=[e for e in events if e['kind']==1];retires=[e for e in events if e['kind']==4]
                    if len(births)==len(retires)==1 and (water['bytes']-128)%512==0: break
                    assert time.monotonic()<limit,'Request finished but journal retirement not observed'
                    await asyncio.sleep(.2)
                b,r=births[0],retires[0]
                assert (b['birth'],b['wire_id'])==(r['birth'],r['wire_id'])
                assert not any(e['kind']==7 for e in events)
                ja=water['bytes']
            else: ja=None;b=r=None
            hi=logpath.stat().st_size
            log=logpath.read_bytes()[lo:hi]
            ids=sorted({int(s)%(2**64) for s in re.findall(rb'flash_serve:\s+req\s+(-?\d+)\b',log)})
            assert len(ids)==1 and (not capture or ids==[b['wire_id']])
            record=dict(request_id=item['request_id'],passed=True,capture_only=True,performance_cohort=False,NPU_executed=False,prompt_tokens=actual_input,completion_tokens=actual_output,host_request_seconds=wall,request_started_utc=begun,request_finished_utc=ended,memory_minimum_bytes=minimum,metrics=metrics,native_log_before_bytes=lo,native_log_after_bytes=hi,native_log_wire_ids=ids,journal_before_bytes=jb,journal_after_bytes=ja,birth=b,retire=r)
            write(request_dir/'result.json',record);results.append(record)
            control.atomic(folder/'progress.json',dict(phase='collecting',completed=len(results),total=16,current=item['request_id']))
            print(json.dumps(dict(mode=mode,request_id=item['request_id'],completed=len(results),input_tokens=actual_input,output_tokens=actual_output,prefill_api_tps=metrics['timings']['prompt_per_second'],decode_api_tps=metrics['timings']['predicted_per_second'],accepted=metrics['accepted'],drafted=metrics['drafted'],host_seconds=wall)),flush=True)
    write(folder/'summary.json',dict(completed=True,requests=results,performance_cohort=False,NPU_executed=False,elapsed_seconds=time.perf_counter()-start))
    control.atomic(folder/'progress.json',dict(phase='completed',completed=16,total=16))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('capture','normal'));args=parser.parse_args()
    asyncio.run(run(args.mode))
