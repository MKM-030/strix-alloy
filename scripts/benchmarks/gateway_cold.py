"""Cold PP512/PP2048 and TG128 through the authenticated Alloy gateway."""
import argparse,asyncio,hashlib,json,statistics,time
from pathlib import Path
import aiohttp
from article_metrics import validate_backend,backend_validation_finished
from clock_probe import ClockProbe
P=argparse.ArgumentParser(description=__doc__)
P.add_argument('--backend',choices=['halogen-v2','halogen-w4b','gufo','projfix'],required=True)
P.add_argument('--context',type=int,required=True)
P.add_argument('--prompts',type=Path,required=True)
P.add_argument('--output',type=Path,required=True)
P.add_argument('--token-file',type=Path,required=True)
a=P.parse_args();R=Path(__file__).resolve().parents[2]
if not 4096<=a.context<=262144:raise ValueError('Unsupported context')
a.output.mkdir(parents=True,exist_ok=False)
key=a.token_file.read_text(encoding='ascii').strip();clock=None;rows=[]
if a.backend.startswith('halogen'):
    backend=R/'backends/halogen-wsl2-0.15.1'
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
        if clock:
            manifest=json.loads((Path(inner['attempt'])/'manifest.json').read_text())
            if manifest['environment']['HALOGEN_PROMPT_CACHE']!='0':raise ValueError('Cold controls require cache Off')
        (a.output/'identity.json').write_text(json.dumps({'backend':a.backend,'context':a.context,
            'managed_run_id':run_id,'halogen_run_id':inner['run_id'] if clock else None,
            'client_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2))
        async def query(body):
            current=json.loads((R/'server/.local/current.json').read_text())
            if current['run_id']!=run_id or current['phase']!='ready':raise RuntimeError('Runtime changed')
            first=clock.sample() if clock else None;start=time.perf_counter()
            async with client.post('http://127.0.0.1:8840/v1/chat/completions',
                    headers={'Authorization':'Bearer '+key},json=body) as response:
                if response.status!=200:raise RuntimeError('Inference HTTP '+str(response.status))
                value=await response.json()
            wall=time.perf_counter()-start;last=clock.sample() if clock else None
            cal=clock.compare(first,last) if clock else {'monotonic_per_raw':1.0}
            return value,wall,cal
        for size in (512,2048):
            prompt=(a.prompts/f'prompt-{size}-prose.txt').read_text(encoding='utf-8')
            base={'model':model,'messages':[{'role':'user','content':prompt}],
                  'temperature':0,'seed':1,'stream':False,'cache_prompt':False,
                  'enable_thinking':False,'reasoning_effort':'none',
                  'chat_template_kwargs':{'enable_thinking':False},'max_tokens':1}
            if not clock:
                for _ in range(6):
                    value,_,_=await query(base);delta=size-value['usage']['prompt_tokens']
                    if delta==0:break
                    if delta>0:prompt=' a'*delta+prompt
                    elif prompt.startswith(' a'*(-delta)):prompt=prompt[-delta*2:]
                    else:prompt=prompt.split(' ',max(1,(-delta+1)//2))[-1]
                    base['messages'][0]['content']=prompt
                else:raise ValueError('Cannot calibrate exact input length')
            with (a.output/f'prompt-{size}-prose.txt').open('x',encoding='utf-8') as stream:stream.write(prompt)
            for output in (1,128):
                for rep in range(4):
                    modes=['serial'] if output==1 else (['serial','mtp'] if rep%2 else ['mtp','serial'])
                    if not clock:modes=['configured-native']
                    for mode in modes:
                        body={**base,'max_tokens':output}
                        if clock:body['drafter']=mode
                        value,wall,cal=await query(body);usage=value['usage'];timing=value['timings']
                        if usage['prompt_tokens']!=size or usage['completion_tokens']!=output:raise ValueError('Unexpected token count')
                        if timing.get('cache_n',0)!=0:raise ValueError('Cold measurement hit prefix cache')
                        message=value['choices'][0]['message']
                        text=(message.get('reasoning_content') or '')+(message.get('content') or '')
                        row={'size':size,'output':output,'drafter':mode,'rep':rep,
                             'phase':'warmup' if rep==0 else 'measured','timings':timing,'usage':usage,
                             'wall_seconds':wall,'clock_calibration':cal,
                             'pp_tps':timing['prompt_per_second']*cal['monotonic_per_raw'],
                             'decode_tps':timing['predicted_per_second']*cal['monotonic_per_raw'],
                             'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                             'output_sha256':hashlib.sha256(text.encode()).hexdigest(),
                             'reasoning_present':bool(message.get('reasoning_content'))}
                        rows.append(row)
                        with (a.output/'samples.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
                        print('COLD',a.backend,size,output,mode,rep,round(row['pp_tps'],2),round(row['decode_tps'],2),flush=True)
        measured=[r for r in rows if r['phase']=='measured'];summary=[]
        for size,output,mode in sorted({(r['size'],r['output'],r['drafter']) for r in measured}):
            cohort=[r for r in measured if (r['size'],r['output'],r['drafter'])==(size,output,mode)]
            if len({r['output_sha256'] for r in cohort})!=1:raise ValueError('Repeated greedy output changed')
            summary.append({'size':size,'output':output,'drafter':mode,'n':len(cohort),
                            'pp_mean':statistics.fmean(r['pp_tps'] for r in cohort),
                            'decode_mean':statistics.fmean(r['decode_tps'] for r in cohort),
                            'pp_stdev':statistics.stdev(r['pp_tps'] for r in cohort),
                            'decode_stdev':statistics.stdev(r['decode_tps'] for r in cohort)})
        result={'backend':a.backend,'context':a.context,'run_id':run_id,'passed':True,
                'rows':summary,'samples':len(measured),'measured_at':time.time(),
                'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'route':'http://127.0.0.1:8840/v1/chat/completions','cache':'Off'}
        (a.output/'summary.json').write_text(json.dumps(result,indent=2))
        print('COLD_COMPLETE',json.dumps(result),flush=True)
try:asyncio.run(run())
except Exception as exc:
    (a.output/'failure.json').write_text(json.dumps({'error':type(exc).__name__+': '+str(exc),'completed_requests':len(rows)}))
    raise
finally:
    if clock:clock.close()
