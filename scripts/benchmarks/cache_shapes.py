"""Read-only inference experiment: distinguish prefix shapes and cache modes."""
import argparse,hashlib,json,time,urllib.request,urllib.error
from pathlib import Path
P=argparse.ArgumentParser(description=__doc__)
P.add_argument('--mode',choices=['Exact','Flexible'],required=True)
P.add_argument('--drafter',choices=['serial','mtp'],default='serial')
P.add_argument('--backend',type=Path,required=True)
P.add_argument('--prompt-file',type=Path,required=True)
P.add_argument('--output',type=Path,required=True)
P.add_argument('--context',type=int,default=262144)
a=P.parse_args()
if a.prompt_file.stat().st_size>1024**2: raise ValueError('Prompt fixture is too large')
B=a.backend
key=(B/'.local/api-token.txt').read_text().strip()
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args): raise ValueError('Redirect refused')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def call(path,body=None):
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request('http://127.0.0.1:8731'+path,data,{'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    t=time.perf_counter()
    with opener.open(req,timeout=180) as resp: result=json.load(resp)
    return result,time.perf_counter()-t
until=time.monotonic()+1100
while True:
    state=json.loads((B/'.local/current-service.json').read_text())
    if state.get('phase')=='ready' and state.get('prompt_cache')==a.mode:break
    if state.get('phase') in ('failed','stopped'):raise RuntimeError('Backend did not start: '+str(state.get('outcome')))
    if time.monotonic()>until:raise TimeoutError('Readiness timeout')
    time.sleep(2)
health,_=call('/health');assert health['context']==a.context and health['slots']==1
assert health['prompt_cache']['mode']=={'Exact':1,'Flexible':2}[a.mode]
assert health['version']=={'api':'0.15.1','engine':'0.15.1','match':True}
run=state['run_id'];out=a.output;out.mkdir(parents=True,exist_ok=False)
base=a.prompt_file.read_text(encoding='utf-8')
query='Summarize the document, then write a detailed story of at least 500 words inspired by it.'
cases={
 'exact-single':[{'role':'user','content':base}],
 'longer-single':[{'role':'user','content':base+'\nAdditional instruction: write continuously and use complete paragraphs.'}],
 'system-document':[{'role':'system','content':'Document context for this experiment.\n'+base},{'role':'user','content':query}],
 'history-document':[{'role':'user','content':'Read and retain this document.\n'+base},{'role':'assistant','content':'I have read the document.'},{'role':'user','content':query}]}
rows=[]
for label,messages in cases.items():
    for rep in range(3):
        current=json.loads((B/'.local/current-service.json').read_text());assert current['run_id']==run
        h,_=call('/health');assert not h['busy'] and not h['queued']
        pre,_=call('/cache')
        body={'model':'halogen-qwen3.8-flash-next','messages':messages,'max_tokens':64,
              'temperature':0,'seed':1,'drafter':a.drafter,'enable_thinking':False,'reasoning_effort':'none'}
        result,wall=call('/v1/chat/completions',body)
        post,_=call('/cache');msg=result['choices'][0]['message']
        output=(msg.get('reasoning_content') or '')+(msg.get('content') or '')
        row={'label':label,'rep':rep,'mode':a.mode,'wall_seconds':wall,'timings':result['timings'],
             'usage':result['usage'],'sha256':hashlib.sha256(output.encode()).hexdigest(),
             'cache_hits_delta':post['hits']-pre['hits'],'cache_stores_delta':post['stores']-pre['stores'],
             'cache_entries':post['entries'],'prompt_sha256':hashlib.sha256(json.dumps(messages).encode()).hexdigest()}
        rows.append(row)
        with (out/'samples.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        print(label,rep,'cached',row['timings'].get('cache_n',0),'wall',round(wall,3),flush=True)
summary={'mode':a.mode,'drafter':a.drafter,'run_id':run,'context':a.context,'health_cache':health['prompt_cache'],'rows':rows,
         'identical_by_case':{label:len({r['sha256'] for r in rows if r['label']==label})==1 for label in cases}}
(out/'summary.json').write_text(json.dumps(summary,indent=2))
print('COMPLETE',json.dumps(summary['identical_by_case']),flush=True)
