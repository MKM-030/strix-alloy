"""Frozen 8K MTP request, one excluded warmup and three measured repetitions."""
import argparse
import asyncio
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time
import aiohttp

ROOT=Path(r'C:\Projects\strix-alloy-clean')
WORK=Path(__file__).resolve().parent
PREP=WORK.parent
sys.path.insert(0,str(ROOT/'server'))
from controller import atomic,read
from host_frames import frame
sys.path.insert(0,str(ROOT/'scripts/benchmarks'))
from article_metrics import cold_sample,acceptance
from clock_probe import ClockProbe
PROFILE=PREP/'servicenow-thinking-defaults-20261008/thinking-latest-profile.json'
PROFILE_SHA='b5d3692b2623034f5a9c4a5f90b234ba6b792793196963fc0e7b474b3937c839'
PROMPT=PREP/'fixed-depth2-comparison/prompts/prompt-8192-prose.txt'
PROMPT_SHA='0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1'
OUTPUT_SHA='0fbe27247d33d2829aa90b66964ff3bb946679be7ce79b379e2555f60ec74fa6'

async def run(window):
    folder=WORK/window
    folder.mkdir(exist_ok=False)
    assert hashlib.sha256(PROFILE.read_bytes()).hexdigest()==PROFILE_SHA
    assert hashlib.sha256(PROMPT.read_bytes()).hexdigest()==PROMPT_SHA
    profile=read(PROFILE)
    token=Path(profile['token_file']).read_text(encoding='ascii').strip()
    initial=read(ROOT/'server/.local/current.json')
    backend=read(ROOT/'backends/halogen-wsl2-0.17.2/.local/current-service.json')
    assert initial['phase']==backend['phase']=='ready' and initial['profile_sha256']==PROFILE_SHA
    manifest=read(Path(backend['attempt'])/'manifest.json')
    if window=='candidate': assert manifest['native_attn_bt4_opt_candidate']['enabled'] and manifest['environment']['HALOGEN_ATTN_QS_BT4_OPT']=='0'
    else: assert '_hg_flash_serve' not in manifest['environment'] and 'HALOGEN_ATTN_QS_BT4_OPT' not in manifest['environment']
    body=dict(model=backend['model'],messages=[dict(role='user',content=PROMPT.read_text(encoding='utf-8'))],
        temperature=0,seed=1,stream=False,cache_prompt=False,enable_thinking=False,reasoning_effort='none',
        chat_template_kwargs=dict(enable_thinking=False),max_tokens=128,drafter='mtp')
    rows=[]
    atomic(folder/'identity.json',dict(window=window,controller=initial,backend=backend,
        manifest=manifest,profile_sha256=PROFILE_SHA,client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        prompt_sha256=PROMPT_SHA,request_sha256=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()))
    clock=ClockProbe('Ubuntu-24.04','revn')
    try:
        async with aiohttp.ClientSession(trust_env=False,timeout=aiohttp.ClientTimeout(total=180)) as client:
            for rep in range(4):
                current=read(ROOT/'server/.local/current.json')
                assert current['run_id']==initial['run_id'] and current['phase']=='ready'
                async with client.get('http://127.0.0.1:8840/health',headers={'Authorization':'Bearer '+token}) as response:
                    health=await response.json()
                assert health['status']=='ok' and health['active_requests']==0 and not health['draining']
                sample=frame();minimum={key:sample[key] for key in ('available_bytes','commit_headroom_bytes')}
                assert min(minimum.values())>=18*2**30
                done=asyncio.Event()
                async def watch():
                    while not done.is_set():
                        sample=frame()
                        for key in minimum: minimum[key]=min(minimum[key],sample[key])
                        try: await asyncio.wait_for(done.wait(),timeout=.2)
                        except asyncio.TimeoutError: pass
                watcher=asyncio.create_task(watch())
                before=clock.sample();start=time.perf_counter()
                try:
                    async with client.post('http://127.0.0.1:8840/v1/chat/completions',
                        headers={'Authorization':'Bearer '+token},json=body) as response:
                        value=await response.json()
                        assert response.status==200,response.status
                finally:
                    wall=time.perf_counter()-start
                    done.set();await watcher
                after=clock.sample();calibration=clock.compare(before,after)
                atomic(folder/f'response-{rep}.json',value)
                checked=cold_sample(value,8192,128)
                assert checked['output_sha256']==OUTPUT_SHA,'Candidate changed the frozen greedy response'
                assert checked['accepted']==70 and checked['drafted']==113,'Attention candidate changed frozen acceptance counters'
                assert min(minimum.values())>=18*2**30
                ratio=calibration['monotonic_per_raw']
                row=dict(rep=rep,phase='warmup' if rep==0 else 'measured',wall_seconds=wall,
                    clock_calibration=calibration,pp_tps=checked['timings']['prompt_per_second']*ratio,
                    decode_tps=checked['timings']['predicted_per_second']*ratio,
                    observed_minimum_memory_bytes=minimum,**checked)
                rows.append(row)
                atomic(folder/'samples.json',rows)
                print(json.dumps(dict(window=window,rep=rep,phase=row['phase'],prefill=row['pp_tps'],
                    decode=row['decode_tps'],acceptance=checked['acceptance'],wall_seconds=wall)),flush=True)
        cohort=rows[1:]
        summary=dict(window=window,version='0.17.2',actual_input_tokens=8192,output_tokens=128,
            excluded_warmups=1,measured_repetitions=3,passed=True,rows=rows,
            prefill_mean=statistics.fmean(row['pp_tps'] for row in cohort),
            decode_mean=statistics.fmean(row['decode_tps'] for row in cohort),
            prefill_stdev=statistics.stdev(row['pp_tps'] for row in cohort),
            decode_stdev=statistics.stdev(row['decode_tps'] for row in cohort),
            acceptance=acceptance(cohort),controller_run_id=initial['run_id'],backend_run_id=backend['run_id'],
            request_sha256=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),
            completed_utc=datetime.now(timezone.utc).isoformat())
        atomic(folder/'summary.json',summary)
        print(json.dumps({key:value for key,value in summary.items() if key!='rows'}),flush=True)
    finally: clock.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('window',choices=('before','candidate','after'))
    args=parser.parse_args()
    try: asyncio.run(run(args.window))
    except Exception as exc:
        atomic(WORK/(args.window+'-failure.json'),dict(error=type(exc).__name__+': '+str(exc)))
        raise
