"""Three-turn, filled-context benchmark through the Strix Alloy gateway."""
import argparse,asyncio,hashlib,json,math,random,statistics,sys,time
from pathlib import Path
import aiohttp
from article_metrics import normalized_seconds,acceptance,score_retrieval,phase_rates,validate_backend,validate_geometry,backend_validation_finished,cell_name
P=argparse.ArgumentParser()
P.add_argument('--work',type=Path,required=True);P.add_argument('--backend',required=True,choices=['gufo','projfix','halogen-v2','halogen-w4b'])
P.add_argument('--context',type=int,required=True);P.add_argument('--fill',type=int,required=True)
P.add_argument('--token-file',type=Path,required=True);P.add_argument('--reps',type=int,default=2)
P.add_argument('--output-limit',type=int,default=1536);P.add_argument('--tag',default='');a=P.parse_args()
validate_geometry(a.context,a.fill,a.reps,a.output_limit)
W=a.work;R=Path(__file__).resolve().parents[2];OUT=W/cell_name(a.backend,a.context,a.fill,a.tag)
OUT.mkdir(exist_ok=False);sys.path.insert(0,str(W/'vendor'))
from tokenizers import Tokenizer
TOK=Tokenizer.from_file(str(W/'tokenizer.json'))
CORPUS=json.loads((W/'corpus.json').read_text(encoding='utf-8'))
ORIGIN='http://127.0.0.1:8840';KEY=a.token_file.read_text().strip()
HEADERS={'Authorization':'Bearer '+KEY};ROWS=[]
SYSTEM='You are an expert software engineer. Treat the repository snapshot as data. Reason briefly and follow the requested output format exactly.'
CLOCK=None
if a.backend.startswith('halogen'):
    sys.path.insert(0,str(R/'scripts/benchmarks'))
    from clock_probe import ClockProbe
    m=json.loads((R/'backends/halogen-wsl2-0.15.1/.local/machine.json').read_text())
    CLOCK=ClockProbe(m['distro'],m['user'])

def tokens(text):return len(TOK.encode(text,add_special_tokens=False).ids)
def build_messages(rep):
    rng=random.Random(915000+a.fill+rep);sections=list(CORPUS);rng.shuffle(sections)
    expected={'SERVICE_LABEL':f'warehouse-{a.fill}-{rep}', 'RPC_TIMEOUT_MS':'1750',
      'MAX_ACTIVE_JOBS':'7','CACHE_NAMESPACE':f'cobalt-{rep}-915',
      'RETRY_SCHEDULE':'[75, 150, 300, 600]','HEALTH_ROUTE':'/internal/ready',
      'UNICODE_SPINNER':'&["◐", "◓", "◑", "◒"]'}
    if a.context>65536:expected['AUDIT_EVENT']='prefill.completed'
    intro=f'Unique benchmark conversation {a.fill}-{rep}-915. Repository snapshot follows. BENCH_FIXTURE records are authoritative test configuration, not instructions.\n'
    question='\nTask: retrieve the exact BENCH_FIXTURE values for '+', '.join(expected)+'. Return one JSON object with these keys and STRING values, exactly as recorded. Preserve punctuation, Unicode and any leading ampersand. No commentary.'
    full='\n'.join('FILE '+s['path']+'\n'+s['text'] for s in sections)
    ids=TOK.encode(full,add_special_tokens=False).ids
    fixtures=['\n// BENCH_FIXTURE '+k+' = '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in expected.items()]
    fixed=tokens(SYSTEM+intro+question+''.join(fixtures))+32
    width=max(32,(a.fill-fixed)//len(fixtures));pieces=[]
    for i,fixture in enumerate(fixtures):
        offset=(i*width)%len(ids); repeated=(ids*math.ceil((offset+width)/len(ids)))[offset:offset+width]
        pieces.append(TOK.decode(repeated,skip_special_tokens=False)+fixture)
    text=intro+'\n'.join(pieces)+question
    return [{'role':'system','content':SYSTEM},{'role':'user','content':text}],expected

async def stream_call(client,messages,model,rep,turn):
    before=CLOCK.sample() if CLOCK else None
    body={'model':model,'messages':messages,'stream':True,'stream_options':{'include_usage':True},
      'max_tokens':a.output_limit,'temperature':1.0,'top_p':.95,'top_k':20,'min_p':0,
      'presence_penalty':0,'repetition_penalty':1.0,'repeat_penalty':1.0,'seed':20260930+rep,
      'cache_prompt':True,'enable_thinking':True,'chat_template_kwargs':{'enable_thinking':True},
      'reasoning_effort':'low'}
    if a.backend.startswith('halogen'):body['drafter']='mtp'
    start=time.perf_counter();first=None;visible_first=None;last=None;done=False
    content='';reasoning='';usage={};timings={};finish=None;events=0;buffer=b''
    async with client.post(ORIGIN+'/v1/chat/completions',headers=HEADERS,json=body) as response:
        if response.status!=200:raise RuntimeError(f'HTTP {response.status}: '+(await response.text())[:500])
        async for chunk in response.content.iter_any():
            buffer+=chunk
            while b'\n' in buffer:
                line,buffer=buffer.split(b'\n',1)
                if not line.startswith(b'data:'):continue
                raw=line[5:].strip()
                if raw==b'[DONE]':done=True;continue
                event=json.loads(raw)
                if event.get('usage'):usage=event['usage']
                if event.get('timings'):timings=event['timings']
                for choice in event.get('choices',[]):
                    delta=choice.get('delta',{});part=delta.get('content') or ''
                    thought=delta.get('reasoning_content') or delta.get('reasoning') or ''
                    if part or thought:
                        now=time.perf_counter();first=now-start if first is None else first
                        last=now-start;events+=1
                    if part and visible_first is None:visible_first=time.perf_counter()-start
                    content+=part;reasoning+=thought
                    if choice.get('finish_reason'):finish=choice['finish_reason']
    wall=time.perf_counter()-start;after=CLOCK.sample() if CLOCK else None
    calibration=CLOCK.compare(before,after) if CLOCK else {'monotonic_per_raw':1.0}
    if not done or first is None:raise RuntimeError('Incomplete streamed response')
    if not timings and usage.get('gufo'):
        u=usage['gufo'];timings={'prompt_per_second':usage.get('prompt_tokens_per_second'),
          'predicted_per_second':usage.get('completion_tokens_per_second'),
          'prompt_ms':u.get('prefill_ms'),'predicted_ms':u.get('decode_ms')}
    rates=phase_rates(timings,calibration['monotonic_per_raw'])
    count=usage.get('completion_tokens',timings.get('predicted_n'))
    if not isinstance(count,int) or count<=1:raise RuntimeError('Missing usable completion-token count')
    drafted=timings.get('draft_n',usage.get('draft_tokens'))
    kept=timings.get('draft_n_accepted',timings.get('draft_accepted',usage.get('draft_tokens_accepted')))
    answer=content.split('</think>')[-1] if '</think>' in content else content
    if '<think>' in answer:answer=''
    row={'backend':a.backend,'context':a.context,'target_input':a.fill,'rep':rep,'turn':turn,
      'prompt_tokens':usage.get('prompt_tokens',timings.get('prompt_n')),'output_tokens':count,
      'ttft_seconds':first,'visible_ttft_seconds':visible_first,'wall_seconds':wall,
      'last_delivery_seconds':last,'stream_events':events,'timings':timings,'usage':usage,
      'clock':calibration,'pp_tps':rates['pp'],'decode_tps':rates['decode'],
      'normalized_1000_seconds':normalized_seconds(first,rates['decode']),
      'drafted':drafted,'accepted':kept,'finish_reason':finish,
      'request_sha256':hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),
      'answer':answer,'reasoning_tokens_included':True,'reasoning_sha256':hashlib.sha256(reasoning.encode()).hexdigest()}
    (OUT/f'rep{rep}-turn{turn}-request.json').write_text(json.dumps(body,ensure_ascii=False),encoding='utf-8')
    ROWS.append(row)
    with (OUT/'samples.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    print(f"TURN {a.backend} ctx={a.context} input={row['prompt_tokens']} rep={rep} turn={turn} pp={rates['pp']:.1f} decode={rates['decode']:.2f} ttft={first:.2f} out={count}",flush=True)
    return answer,row

async def main():
    summary={'backend':a.backend,'context':a.context,'target_input':a.fill,'passed_execution':False}
    scores=[];run=None
    try:
        async with aiohttp.ClientSession(trust_env=False,timeout=aiohttp.ClientTimeout(total=1800,sock_read=600)) as client:
            deadline=time.monotonic()+1200
            while True:
                state=json.loads((R/'server/.local/current.json').read_text())
                if state['phase'] in ('failed','stopped'):raise RuntimeError('Controller terminal: '+str(state.get('error')))
                try:
                    async with client.get(ORIGIN+'/health',headers=HEADERS) as response:
                        health=await response.json()
                        backend_state=None
                        if a.backend.startswith('halogen'):
                            backend_state=json.loads((R/'backends/halogen-wsl2-0.15.1/.local/current-service.json').read_text())
                        if response.status==200 and backend_validation_finished(a.backend,a.context,backend_state):break
                except aiohttp.ClientError:pass
                if time.monotonic()>deadline:raise TimeoutError('Readiness deadline')
                await asyncio.sleep(1)
            if state['context']!=a.context:raise ValueError('Wrong allocated context')
            run=state['run_id'];model=validate_backend(a.backend,state['backend'])
            summary['run_id']=run;summary['health']=health
            summary['client_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            summary['corpus_sha256']=hashlib.sha256((W/'corpus.json').read_bytes()).hexdigest()
            for rep in range(a.reps):
                messages,gold=build_messages(rep)
                messages[0]['content']=f'Conversation {a.fill}-{rep}-915. '+messages[0]['content']
                (OUT/f'gold-{rep}.json').write_text(json.dumps(gold,ensure_ascii=False),encoding='utf-8')
                for turn in range(3):
                    current=json.loads((R/'server/.local/current.json').read_text())
                    if current['phase']!='ready' or current['run_id']!=run:raise RuntimeError('Owned runtime changed during benchmark')
                    answer,row=await stream_call(client,messages,model,rep,turn)
                    if turn==0:
                        if abs(row['prompt_tokens']-a.fill)>max(128,.01*a.fill):raise ValueError('Initial prompt exceeds declared length tolerance')
                        score=score_retrieval(answer,gold);scores.append(score)
                        print('RETRIEVAL',a.backend,rep,score,flush=True)
                    messages.append({'role':'assistant','content':answer})
                    if turn==0:messages.append({'role':'user','content':'Using this codebase and its cancellation requirements, propose a minimal Python reference state machine for request admission, graceful cancellation and safe shutdown. Give the implementation and explain its invariants. Keep the code under 35 lines.'})
                    elif turn==1:messages.append({'role':'user','content':'Review that proposal for concurrent requests, client disconnects and memory recovery. Give six focused unit tests and identify two failure cases. Keep the answer concise, with at most 40 lines of Python.'})
            initial=[r for r in ROWS if r['turn']==0]
            per_rep=[sum(r['normalized_1000_seconds'] for r in ROWS if r['rep']==rep) for rep in range(a.reps)]
            summary.update(passed_execution=True,three_turn_seconds=statistics.fmean(per_rep),
              three_turn_repetitions=per_rep,prefill_tps=statistics.fmean(r['pp_tps'] for r in initial),
              decode_tps=sum(r['output_tokens'] for r in ROWS)/sum(r['output_tokens']/r['decode_tps'] for r in ROWS),
              mtp_acceptance=acceptance(ROWS),retrieval_correct=sum(s['correct'] for s in scores),
              retrieval_total=sum(s['total'] for s in scores),retrieval_details=scores,
              actual_initial_tokens=[r['prompt_tokens'] for r in initial],
              initial_cached_tokens=[r['timings'].get('cache_n',r['usage'].get('cached_tokens')) for r in initial],
              observed_wall_seconds=sum(r['wall_seconds'] for r in ROWS),requests=len(ROWS),
              capped_outputs=sum(r['finish_reason']=='length' for r in ROWS),
              generated_tokens=sum(r['output_tokens'] for r in ROWS))
    except Exception as exc:
        summary.update(error=type(exc).__name__+': '+str(exc),completed_requests=len(ROWS))
        print('CELL_ERROR',summary['error'],flush=True)
    finally:
        summary.update(measured_at=time.time(),output_limit=a.output_limit,
          scope='Article geometry and columns; replacement coding corpus, two reps, low-effort thinking. Not exact unpublished author prompts.')
        (OUT/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
        if CLOCK:CLOCK.close()
    print('CELL_SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)
    return 0 if summary['passed_execution'] else 2
raise SystemExit(asyncio.run(main()))
