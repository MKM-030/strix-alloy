"""Cold exact PP512/2048/8192/16384 and TG128 through the Alloy gateway."""
import argparse,asyncio,hashlib,json,statistics,time
from pathlib import Path
import aiohttp
from article_metrics import (validate_backend,backend_validation_finished,benchmark_input_sizes,
                             calibrated_prompt,cold_sample,memory_snapshot,acceptance,verified_prompt,
                             checked_profile_hash,halogen_backend_directory)
from clock_probe import ClockProbe
import sys
P=argparse.ArgumentParser(description=__doc__)
P.add_argument('--backend',choices=['halogen-v2','halogen-w4b','gufo','projfix'],required=True)
P.add_argument('--context',type=int,required=True)
P.add_argument('--sizes',type=int,nargs='+',default=[512,2048])
P.add_argument('--prompts',type=Path,required=True)
P.add_argument('--output',type=Path,required=True)
P.add_argument('--token-file',type=Path,required=True)
P.add_argument('--profile',type=Path,required=True)
a=P.parse_args();R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'server'))
from host_frames import frame
if not 4096<=a.context<=262144:raise ValueError('Unsupported context')
sizes=benchmark_input_sizes(a.sizes,a.context)
if not a.output.resolve().is_relative_to((R/'server/.local').resolve()):
    raise ValueError('Raw benchmark output must stay under server/.local')
a.output.mkdir(parents=True,exist_ok=False)
manifest_path=a.prompts/'manifest.json'
input_manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else None
profile=json.loads(a.profile.read_text(encoding='utf-8-sig'))
key=a.token_file.read_text(encoding='ascii').strip();clock=None;rows=[]
if a.backend.startswith('halogen'):
    backend=halogen_backend_directory(R,profile)
    machine=json.loads((backend/'.local/machine.json').read_text())
    clock=ClockProbe(machine['distro'],machine['user'])
async def run():
    deadline=time.monotonic()+1200
    async with aiohttp.ClientSession(trust_env=False,timeout=aiohttp.ClientTimeout(total=180)) as client:
        while True:
            state=json.loads((R/'server/.local/current.json').read_text())
            if state['phase'] in ('stopped','failed'):raise RuntimeError('Controller terminal')
            if state['context']!=a.context:raise ValueError('Wrong context capacity')
            model=validate_backend(a.backend,state['backend'])
            inner=json.loads((backend/'.local/current-service.json').read_text()) if clock else None
            if state['phase']=='ready' and backend_validation_finished(a.backend,a.context,inner):break
            if time.monotonic()>deadline:raise TimeoutError('Startup validation did not complete')
            await asyncio.sleep(1)
        run_id=state['run_id']
        profile_sha256=checked_profile_hash(state,a.profile)
        if state.get('minimum_reserve_gib',0)<18:
            raise ValueError('Benchmark requires an isolated profile with an 18 GiB reserve')
        if clock:
            engine_manifest=json.loads((Path(inner['attempt'])/'manifest.json').read_text())
            if engine_manifest['environment']['HALOGEN_PROMPT_CACHE']!='0':raise ValueError('Cold controls require cache Off')
        (a.output/'identity.json').write_text(json.dumps({'backend':a.backend,'context':a.context,
            'managed_run_id':run_id,'halogen_run_id':inner['run_id'] if clock else None,
            'profile_sha256':profile_sha256,'profile':profile,
            'input_manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest() if input_manifest else None,
            'client_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2))
        async def query(body):
            current=json.loads((R/'server/.local/current.json').read_text())
            if current['run_id']!=run_id or current['phase']!='ready':raise RuntimeError('Runtime changed')
            checked_profile_hash(current,a.profile)
            async with client.get('http://127.0.0.1:8840/health',headers={'Authorization':'Bearer '+key}) as health_response:
                health=await health_response.json()
            if (health_response.status!=200 or health.get('active_requests')!=0 or health.get('draining')
                    or health.get('backend')!=model or health.get('context')!=a.context):
                raise RuntimeError('Gateway is not idle on the selected backend')
            memory_before=memory_snapshot(current)
            physical_before=frame();minimum={field:physical_before[field]
                for field in ('available_bytes','commit_headroom_bytes')}
            finished=asyncio.Event()
            async def watch_memory():
                while not finished.is_set():
                    sample=frame()
                    for field in minimum:minimum[field]=min(minimum[field],sample[field])
                    try:await asyncio.wait_for(finished.wait(),timeout=.2)
                    except asyncio.TimeoutError:pass
            if min(minimum.values())<18*1024**3:raise ValueError('Memory reserve below 18 GiB')
            watcher=asyncio.create_task(watch_memory())
            first=clock.sample() if clock else None;start=time.perf_counter()
            try:
                async with client.post('http://127.0.0.1:8840/v1/chat/completions',
                        headers={'Authorization':'Bearer '+key},json=body) as response:
                    if response.status!=200:raise RuntimeError('Inference HTTP '+str(response.status))
                    value=await response.json()
            finally:
                finished.set();await watcher
            wall=time.perf_counter()-start;last=clock.sample() if clock else None
            physical_after=frame()
            for field in minimum:minimum[field]=min(minimum[field],physical_after[field])
            if min(minimum.values())<18*1024**3:raise ValueError('Memory reserve crossed during request')
            after=json.loads((R/'server/.local/current.json').read_text())
            if after['run_id']!=run_id or after['phase']!='ready':raise RuntimeError('Runtime changed during request')
            cal=clock.compare(first,last) if clock else {'monotonic_per_raw':1.0}
            return value,wall,cal,{'before':memory_before,'after':memory_snapshot(after),
                                    'observed_minimum':minimum}
        for size in sizes:
            prompt=verified_prompt(a.prompts/f'prompt-{size}-prose.txt',size,input_manifest)
            base={'model':model,'messages':[{'role':'user','content':prompt}],
                  'temperature':0,'seed':1,'stream':False,'cache_prompt':False,
                  'enable_thinking':False,'reasoning_effort':'none',
                  'chat_template_kwargs':{'enable_thinking':False},'max_tokens':1}
            async def measure(candidate):
                base['messages'][0]['content']=candidate
                value,_,_,_=await query(base)
                return value['usage']['prompt_tokens']
            prompt=await calibrated_prompt(prompt,size,measure)
            base['messages'][0]['content']=prompt
            with (a.output/f'prompt-{size}-prose.txt').open('x',encoding='utf-8') as stream:stream.write(prompt)
            for output in (1,128):
                for rep in range(4):
                    modes=['serial'] if output==1 else (['serial','mtp'] if rep%2 else ['mtp','serial'])
                    if not clock:modes=['configured-native']
                    for mode in modes:
                        body={**base,'max_tokens':output}
                        if clock:body['drafter']=mode
                        value,wall,cal,memory=await query(body)
                        checked=cold_sample(value,size,output)
                        usage=checked['usage'];timing=checked['timings']
                        message=value['choices'][0]['message']
                        row={**checked,'size':size,'output':output,'drafter':mode,'rep':rep,
                             'phase':'warmup' if rep==0 else 'measured',
                             'wall_seconds':wall,'clock_calibration':cal,
                             'pp_tps':timing['prompt_per_second']*cal['monotonic_per_raw'],
                             'decode_tps':timing['predicted_per_second']*cal['monotonic_per_raw'] if output>1 else None,
                             'request_sha256':hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),
                             'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                             'host_memory':memory,
                             'reasoning_present':bool(message.get('reasoning_content'))}
                        rows.append(row)
                        with (a.output/'samples.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
                        print('COLD',a.backend,size,output,mode,rep,round(row['pp_tps'],2),
                              round(row['decode_tps'],2) if output>1 else 'n/a',flush=True)
        measured=[r for r in rows if r['phase']=='measured'];summary=[]
        for size,output,mode in sorted({(r['size'],r['output'],r['drafter']) for r in measured}):
            cohort=[r for r in measured if (r['size'],r['output'],r['drafter'])==(size,output,mode)]
            if len({r['output_sha256'] for r in cohort})!=1:raise ValueError('Repeated greedy output changed')
            summary.append({'size':size,'output':output,'drafter':mode,'n':len(cohort),
                            'pp_mean':statistics.fmean(r['pp_tps'] for r in cohort),
                            'decode_mean':statistics.fmean(r['decode_tps'] for r in cohort) if output>1 else None,
                            'pp_stdev':statistics.stdev(r['pp_tps'] for r in cohort),
                            'decode_stdev':statistics.stdev(r['decode_tps'] for r in cohort) if output>1 else None,
                            'acceptance':acceptance(cohort)})
        result={'backend':a.backend,'context':a.context,'run_id':run_id,'passed':True,
                'rows':summary,'samples':len(measured),'measured_at':time.time(),
                'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'route':'http://127.0.0.1:8840/v1/chat/completions','cache':'Off',
                'host_memory_floor_bytes':{field:min(r['host_memory']['observed_minimum'][field]
                    for r in measured) for field in ('available_bytes','commit_headroom_bytes')},
                'memory_scope':'0.2-second host RAM/commit samples plus controller snapshots; not VRAM peak'}
        (a.output/'summary.json').write_text(json.dumps(result,indent=2))
        print('COLD_COMPLETE',json.dumps(result),flush=True)
try:asyncio.run(run())
except Exception as exc:
    (a.output/'failure.json').write_text(json.dumps({'error':type(exc).__name__+': '+str(exc),'completed_requests':len(rows)}))
    raise
finally:
    if clock:clock.close()
