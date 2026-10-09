"""Frozen 0.17.3 bulk-BN64 window: one excluded warmup and three measurements.

Source-only preparation. Root owns all launches, APIs and hardware execution.
The before window establishes the greedy-output and speculative-counter baseline.
"""
import argparse
import asyncio
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
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
PROFILE=PREP/'halogen0173-migration-20261009/thinking-latest-profile.json'
PROFILE_SHA='78e1888d9ecc93a2117be679cd27ffeec1f8f9b99165e18647cef04104bfc141'
PROMPT=PREP/'fixed-depth2-comparison/prompts/prompt-8192-prose.txt'
PROMPT_SHA='0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1'
VERSION='0.17.3'
MEMORY_FIELDS=('available_bytes','commit_headroom_bytes')
EQUALITY_FIELDS=('output_sha256','accepted','drafted','finish_reason')
POWERSHELL=r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'

def fresh_load_snapshot(folder):
    # Only process identity and GPU counters: no command lines, tokens or env.
    # This read-only subprocess finishes before any request or memory watcher.
    code=r"""$ErrorActionPreference='Stop'
$gaming=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -match 'League|Riot'} | Select-Object ProcessId,Name,CreationDate)
$gpu=Get-Counter '\GPU Engine(*)\Utilization Percentage' -SampleInterval 1 -MaxSamples 1 -ErrorAction Stop
$samples=@($gpu.CounterSamples)
$invalid=@($samples|Where-Object {$_.Status -notin @(0,1) -or [double]::IsNaN($_.CookedValue) -or [double]::IsInfinity($_.CookedValue) -or $_.CookedValue -lt 0})
$valid=@($samples|Where-Object {$_.Status -in @(0,1) -and -not [double]::IsNaN($_.CookedValue) -and -not [double]::IsInfinity($_.CookedValue) -and $_.CookedValue -ge 0})
[pscustomobject]@{utc=[DateTime]::UtcNow.ToString('o');observation_only=$true;gaming=$gaming;sample_count=$samples.Count;invalid_sample_count=$invalid.Count;active=@($valid|Where-Object {$_.CookedValue -gt 1}|Select-Object InstanceName,CookedValue,Status)} | ConvertTo-Json -Depth 5 -Compress
"""
    result=subprocess.run([POWERSHELL,'-NoProfile','-NonInteractive','-Command',code],
        capture_output=True,text=True,timeout=20,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        atomic(folder/'load-before.json',dict(observation_only=True,passed=False,returncode=result.returncode))
        raise RuntimeError('Read-only process/GPU snapshot failed; no window request was sent')
    load=json.loads(result.stdout)
    atomic(folder/'load-before.json',load)
    assert load['sample_count']>0,'GPU load snapshot returned no counters'
    assert load['invalid_sample_count']==0,'GPU load snapshot returned invalid/nonfinite counters'
    assert not load['gaming'],'League/Riot process observed; root must assess before measuring'
    assert not load['active'],'GPU load above 1 percent observed; root must assess before measuring'
    return load

def equality_signature(checked):
    assert type(checked['drafted']) is int and type(checked['accepted']) is int and checked['drafted']>0, 'Missing MTP acceptance counters'
    return {key:checked[key] for key in EQUALITY_FIELDS}

async def run(window):
    folder=WORK/window
    folder.mkdir(exist_ok=False)
    assert hashlib.sha256(PROFILE.read_bytes()).hexdigest()==PROFILE_SHA
    assert hashlib.sha256(PROMPT.read_bytes()).hexdigest()==PROMPT_SHA
    profile=read(PROFILE)
    assert profile['engine']['directory']=='backends/halogen-wsl2-0.17.3'
    assert profile['engine']['draft_tokens']==2 and profile['engine']['speculation_policy']=={'HALOGEN_PLD':'3,3'}
    assert profile['engine']['prompt_cache']=='Off'
    entry_memory=frame()
    atomic(folder/'memory-entry.json',entry_memory)
    assert min(entry_memory[key] for key in MEMORY_FIELDS)>=22*2**30,'Window entry requires 22/22 GiB physical/commit headroom'
    token=Path(profile['token_file']).read_text(encoding='ascii').strip()
    initial=read(ROOT/'server/.local/current.json')
    backend=read(ROOT/'backends/halogen-wsl2-0.17.3/.local/current-service.json')
    assert initial['phase']==backend['phase']=='ready' and initial['profile_sha256']==PROFILE_SHA
    manifest=read(Path(backend['attempt'])/'manifest.json')
    env=manifest['environment']
    assert manifest['version']==VERSION and manifest['run_id']==backend['run_id']
    assert manifest['checkpoint']=='v2' and manifest['context']==262144 and manifest['slots']==1
    expected_env={'HALOGEN_MTP_DEPTH':'2','HALOGEN_PLD':'3,3','HALOGEN_PROMPT_CACHE':'0',
        'HALOGEN_PREFILL_CHUNK':'8192','HALOGEN_MAX_TOK':'8192','HALOGEN_HOST_RESERVE_GIB':'18'}
    assert all(env.get(key)==value for key,value in expected_env.items()),'Frozen MTP/cache/prefill settings changed'
    if window=='candidate':
        assert manifest['bulk_bn64_candidate']['enabled'] is True and env['ALLOY_BULK_BN64_ENABLE']=='1'
    else:
        assert 'bulk_bn64_candidate' not in manifest and '_hg_flash_serve' not in env
        assert not any(key.startswith('ALLOY_BULK_BN64_') for key in env),'Stock window inherited BN64 environment'
    body=dict(model=backend['model'],messages=[dict(role='user',content=PROMPT.read_text(encoding='utf-8'))],
        temperature=0,seed=1,stream=False,cache_prompt=False,enable_thinking=False,reasoning_effort='none',
        chat_template_kwargs=dict(enable_thinking=False),max_tokens=128,drafter='mtp')
    rows=[]
    request_sha=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
    client_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    baseline=None
    if window!='before':
        before=read(WORK/'before/summary.json')
        assert before['passed'] is True and before['version']==VERSION
        assert before['profile_sha256']==PROFILE_SHA and before['prompt_sha256']==PROMPT_SHA
        assert before['request_sha256']==request_sha and before['client_sha256']==client_sha,'Before request/client identity changed'
        assert len(before['rows'])==4 and all(equality_signature(row)==before['equality_baseline'] for row in before['rows'])
        baseline=before['equality_baseline']
    atomic(folder/'identity.json',dict(window=window,controller=initial,backend=backend,
        manifest=manifest,profile_sha256=PROFILE_SHA,client_sha256=client_sha,
        prompt_sha256=PROMPT_SHA,request_sha256=request_sha,equality_baseline=baseline))
    load=fresh_load_snapshot(folder)
    fresh_memory=frame()
    atomic(folder/'memory-before-requests.json',fresh_memory)
    assert min(fresh_memory[key] for key in MEMORY_FIELDS)>=22*2**30,'Window entry reserve changed during load snapshot'
    clock=ClockProbe('Ubuntu-24.04','revn')
    try:
        async with aiohttp.ClientSession(trust_env=False,timeout=aiohttp.ClientTimeout(total=180)) as client:
            for rep in range(4):
                current=read(ROOT/'server/.local/current.json')
                assert current['run_id']==initial['run_id'] and current['phase']=='ready'
                async with client.get('http://127.0.0.1:8840/health',headers={'Authorization':'Bearer '+token}) as response:
                    health=await response.json()
                assert health['status']=='ok' and health['active_requests']==0 and not health['draining']
                if rep==0:
                    first_health=health
                    atomic(folder/'health-before.json',health)
                sample=frame();minimum={key:sample[key] for key in MEMORY_FIELDS}
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
                signature=equality_signature(checked)
                if baseline is None: baseline=signature
                assert signature==baseline,'Window changed the before greedy output or speculative acceptance counters'
                assert min(minimum.values())>=18*2**30
                row=dict(rep=rep,phase='warmup' if rep==0 else 'measured',wall_seconds=wall,
                    clock_calibration=calibration,pp_tps=checked['timings']['prompt_per_second'],
                    decode_tps=checked['timings']['predicted_per_second'],
                    observed_minimum_memory_bytes=minimum,**checked)
                rows.append(row)
                atomic(folder/'samples.json',rows)
                print(json.dumps(dict(window=window,rep=rep,phase=row['phase'],prefill=row['pp_tps'],
                    decode=row['decode_tps'],acceptance=checked['acceptance'],wall_seconds=wall)),flush=True)
            async with client.get('http://127.0.0.1:8840/health',headers={'Authorization':'Bearer '+token}) as response:
                final_health=await response.json()
            atomic(folder/'health-after.json',final_health)
            assert final_health['status']=='ok' and final_health['active_requests']==0 and not final_health['draining']
            assert final_health['completed']-first_health['completed']==4
            assert final_health['cancelled']==first_health['cancelled']
        cohort=rows[1:]
        summary=dict(window=window,version=VERSION,actual_input_tokens=8192,output_tokens=128,
            excluded_warmups=1,measured_repetitions=3,passed=True,rows=rows,
            prefill_mean=statistics.fmean(row['pp_tps'] for row in cohort),
            decode_mean=statistics.fmean(row['decode_tps'] for row in cohort),
            prefill_stdev=statistics.stdev(row['pp_tps'] for row in cohort),
            decode_stdev=statistics.stdev(row['decode_tps'] for row in cohort),
            acceptance=acceptance(cohort),controller_run_id=initial['run_id'],backend_run_id=backend['run_id'],
            profile_sha256=PROFILE_SHA,prompt_sha256=PROMPT_SHA,request_sha256=request_sha,
            client_sha256=client_sha,equality_baseline=baseline,load_before=load,
            entry_memory_bytes=entry_memory,
            completed_utc=datetime.now(timezone.utc).isoformat(),first_health=first_health,final_health=final_health)
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
