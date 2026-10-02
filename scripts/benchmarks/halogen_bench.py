"""Authenticated local PP/TG benchmark; engine timings, not HTTP wall as decode."""
import argparse, datetime, hashlib, json, math, statistics, sys, time
import urllib.request, urllib.error
from pathlib import Path
from gufo_prompts import synthetic_text, TASKS
from clock_probe import ClockProbe
P=argparse.ArgumentParser()
P.add_argument('--backend',required=True,type=Path)
P.add_argument('--workdir',required=True,type=Path)
P.add_argument('--context',required=True,type=int)
P.add_argument('--suite',choices=['core','serving'],default='core')
P.add_argument('--reps',type=int,default=3)
a=P.parse_args()
if not 1<=a.reps<=10: raise ValueError('reps must be 1..10')
a.workdir.mkdir(parents=True,exist_ok=True)
local=a.backend/'.local'; out=a.workdir/f'{a.suite}-ctx{a.context}'
out.mkdir(exist_ok=False)
secret=(local/'api-token.txt').read_text(encoding='ascii').strip()
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args): raise ValueError('Redirect refused')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
API='http://127.0.0.1:8731'
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def request(path,body=None):
    data=None if body is None else json.dumps(body).encode('utf-8')
    req=urllib.request.Request(API+path,data,{'Authorization':'Bearer '+secret,'Content-Type':'application/json'})
    started=time.perf_counter()
    with opener.open(req,timeout=180) as response: result=json.load(response)
    return result,time.perf_counter()-started
state=read(local/'current-service.json'); run_id=state['run_id']
if state['context']!=a.context: raise ValueError('Wrong context capacity')
deadline=time.monotonic()+1000
while state['phase']!='ready':
    if state['phase'] in ('failed','stopped'): raise RuntimeError(str(state.get('outcome')))
    if time.monotonic()>deadline: raise TimeoutError('Readiness deadline')
    time.sleep(2); state=read(local/'current-service.json')
    if state['run_id']!=run_id: raise RuntimeError('Validation run replaced')
health,_=request('/health')
assert health['version']=={'api':'0.15.1','engine':'0.15.1','match':True}
assert all(health[k]==a.context for k in ['context','slot_ctx','kv_pool_positions'])
assert health['slots']==1
manifest=read(Path(state['attempt'])/'manifest.json')
assert manifest['environment']['HALOGEN_PROMPT_CACHE']=='0'
(out/'identity.json').write_text(json.dumps({'run_id':run_id,'health':health,
    'manifest':manifest,'benchmark_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2))
print(f'BEGIN {a.suite} capacity={a.context} run={run_id}',flush=True)
rows=[]
machine=read(local/'machine.json')
clock=ClockProbe(machine['distro'],machine['user'])
def ask(prompt,n,drafter,label,phase,rep=0,thinking=False):
    current=read(local/'current-service.json')
    if current['run_id']!=run_id or current['phase']!='ready': raise RuntimeError('Server changed')
    h,_=request('/health')
    if h.get('busy') or h.get('in_flight',0) or h.get('queued',0): raise RuntimeError('Other traffic')
    body={'model':'halogen-qwen3.8-flash-next','messages':[{'role':'user','content':prompt}],
        'max_tokens':n,'temperature':0,'seed':1,'drafter':drafter,'stream':False,
        'reasoning_effort':'low' if thinking else 'none','enable_thinking':thinking}
    before=clock.sample()
    response,wall=request('/v1/chat/completions',body)
    after=clock.sample(); calibration=clock.compare(before,after)
    t=response['timings']; u=response['usage']; msg=response['choices'][0]['message']
    assert t.get('cache_n',0)==0,(label,'cache contamination',t)
    assert t['prompt_n']==u['prompt_tokens'] and t['predicted_n']==u['completion_tokens']
    assert 'max_tokens_clamped_from' not in t
    assert t['predicted_n']>0 and t['prompt_ms']>0
    if n>1: assert t['predicted_ms']>0
    # A one-token PP probe has no post-first-token decode interval.
    text=(msg.get('reasoning_content') or '')+(msg.get('content') or '')
    row={'label':label,'phase':phase,'rep':rep,'drafter':drafter,'context':a.context,
        'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'requested_output':n,
        'output_sha256':hashlib.sha256(text.encode()).hexdigest(),'usage':u,'timings':t,
        'clock_calibration':calibration,
        'calibrated_engine_pp_tps':t['prompt_per_second']*calibration['monotonic_per_raw'],
        'calibrated_engine_decode_tps':t['predicted_per_second']*calibration['monotonic_per_raw'],
        'finish_reason':response['choices'][0]['finish_reason'],'wall_seconds':wall,
        'end_to_end_output_tps':u['completion_tokens']/wall,
        'end_to_end_prompt_tps':u['prompt_tokens']/wall,'thinking':thinking}
    with (out/'samples.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(row)+'\n')
    rows.append(row)
    if phase=='measured':
        print(f"{label} {drafter} r{rep}: pp={t['prompt_per_second']:.2f} tg={t['predicted_per_second']:.2f} input={t['prompt_n']} output={t['predicted_n']} wall={wall:.3f}",flush=True)
    return row

def exact_prompt(target,task):
    key=f'prompt-{target}-{task}.txt'; cache=a.workdir/key
    if cache.exists(): return cache.read_text(encoding='utf-8')
    instruction=TASKS[task]
    words=max(1,round(target/1.20)-len(instruction.split())-25)
    for iteration in range(12):
        text=synthetic_text(100000,words)
        prompt=text+instruction
        row=ask(prompt,1,'serial','calibration','calibration')
        actual=row['usage']['prompt_tokens']; delta=target-actual
        if delta==0: break
        if 0<delta<=96:
            prompt=text+' a'*delta+instruction
            check=ask(prompt,1,'serial','calibration-pad','calibration')
            if check['usage']['prompt_tokens']==target: break
        words=max(1,words+math.floor(delta/1.15))
    else: raise RuntimeError(f'Could not calibrate exact {target} tokens')
    cache.write_text(prompt,encoding='utf-8')
    print(f'CALIBRATED {target} tokens: {task}',flush=True)
    return prompt

if a.suite=='core':
    for n in [512,2048,8192]:
        prompt=exact_prompt(n,'prose')
        for rep in range(a.reps+1):
            row=ask(prompt,1,'serial',f'pp{n}','warmup' if rep==0 else 'measured',rep)
            assert row['usage']['prompt_tokens']==n
    for size in [512,2048]:
        for task in ['prose','repetition']:
            prompt=exact_prompt(size,task)
            for rep in range(a.reps+1):
                for drafter in (['serial','mtp'] if rep%2 else ['mtp','serial']):
                    row=ask(prompt,128,drafter,f'pp{size}+tg128-'+task,'warmup' if rep==0 else 'measured',rep)
                    assert row['usage']['prompt_tokens']==size and row['usage']['completion_tokens']==128

else:
    cases={k:v for k,v in read(a.workdir/'eval-prompts.json').items() if not k.startswith('_')}
    for dr in ['serial','mtp']: ask('Write a long story about a river town.',256,dr,'warmup','warmup',thinking=True)
    for rep in range(1,a.reps+1):
        for name,prompt in cases.items():
            for dr in (['serial','mtp'] if rep%2 else ['mtp','serial']):
                ask(prompt,256,dr,'serving256-'+name,'measured',rep,thinking=True)

def stats(values):
    return {'mean':statistics.fmean(values),'stdev':statistics.stdev(values) if len(values)>1 else 0,
        'min':min(values),'max':max(values),'n':len(values)}
summary={'context':a.context,'suite':a.suite,'run_id':run_id,'reps':a.reps,'rows':[],
    'cache':'disabled; all measured cache_n verified zero','comparability':'engine timings over HTTP; not llama-bench kernel-only',
    'completed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
measured=[r for r in rows if r['phase']=='measured']
for label,dr in sorted({(r['label'],r['drafter']) for r in measured}):
    group=[r for r in measured if r['label']==label and r['drafter']==dr]
    summary['rows'].append({'label':label,'drafter':dr,
        'prompt_tokens':sorted({r['usage']['prompt_tokens'] for r in group}),
        'output_tokens':sorted({r['usage']['completion_tokens'] for r in group}),
        'clock_ratio':stats([r['clock_calibration']['monotonic_per_raw'] for r in group]),
        'calibrated_engine_pp_tps':stats([r['calibrated_engine_pp_tps'] for r in group]),
        'calibrated_engine_decode_tps':stats([r['calibrated_engine_decode_tps'] for r in group]),
        'engine_pp_tps':stats([r['timings']['prompt_per_second'] for r in group]),
        'engine_decode_tps':stats([r['timings']['predicted_per_second'] for r in group]),
        'e2e_output_tps':stats([r['end_to_end_output_tps'] for r in group]),
        'e2e_prompt_tps':stats([r['end_to_end_prompt_tps'] for r in group]),
        'deterministic_repeats':len({r['output_sha256'] for r in group})==1})
checks=[]
for label in sorted({r['label'] for r in measured}):
    serial=[r for r in measured if r['label']==label and r['drafter']=='serial']
    mtp=[r for r in measured if r['label']==label and r['drafter']=='mtp']
    if serial and mtp:
        checks.append({'label':label,'identical':all(x['output_sha256']==y['output_sha256'] for x,y in zip(serial,mtp))})
summary['serial_mtp_identity']=checks
summary['identity_passed']=all(c['identical'] for c in checks)
if a.suite=='serving':
    summary['ten_shape_mean']={dr:stats([r['timings']['predicted_per_second'] for r in measured if r['drafter']==dr]) for dr in ['serial','mtp']}
    summary['calibrated_ten_shape_mean']={dr:stats([r['calibrated_engine_decode_tps'] for r in measured if r['drafter']==dr]) for dr in ['serial','mtp']}
(out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print('COMPLETE '+json.dumps(summary),flush=True)
if not summary['identity_passed']: raise RuntimeError('Greedy serial/MTP text mismatch; report diagnostic, not qualified speed')
