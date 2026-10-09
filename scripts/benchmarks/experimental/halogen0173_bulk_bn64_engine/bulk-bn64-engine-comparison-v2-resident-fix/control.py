"""Observe owned normal/candidate handles and perform regular lifecycle stops."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

WORK=Path(__file__).resolve().parent
PREP=WORK.parent
ROOT=PREP.parents[3]
PROFILE=PREP/'halogen0173-migration-20261009/thinking-latest-profile.json'
BACKEND=ROOT/'backends/halogen-wsl2-0.17.3'
STATE=PREP.parent/'continuation-current.json'
sys.path.insert(0,str(ROOT/'server'))
from controller import atomic,read
spec=importlib.util.spec_from_file_location('migration_identity',PREP/'halogen0173-migration-20261009/migrate.py')
migration=importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

def utc(): return datetime.now(timezone.utc).isoformat()

def checkpoint(window,session=None):
    current=read(ROOT/'server/.local/current.json')
    inner=read(BACKEND/'.local/current-service.json')
    assert current['phase']==inner['phase']=='ready'
    assert 0<=time.time()-current['heartbeat']<=15
    assert current['profile_sha256']==hashlib.sha256(PROFILE.read_bytes()).hexdigest()
    ids=dict(controller=migration.identity(current['pid']),backend=migration.identity(inner['controller_pid']))
    assert ids['controller'] and ids['backend']
    manifest=read(Path(inner['attempt'])/'manifest.json')
    assert manifest['version']=='0.17.3' and manifest['context']==262144
    if window=='candidate':
        assert manifest['bulk_bn64_candidate']['enabled'] is True
        assert manifest['environment']['ALLOY_BULK_BN64_ENABLE']=='1'
    else:
        assert 'bulk_bn64_candidate' not in manifest
        assert not any(k.startswith('ALLOY_BULK_BN64') for k in manifest['environment'])
    record=dict(utc=utc(),window=window,controller=current,backend=inner,identities=ids,
        health=migration.health(read(PROFILE)),engine_tool_session=session)
    path=WORK/(window+'-ready.json')
    if path.exists():
        previous=read(path)
        assert previous['controller']['run_id']==current['run_id'] and previous['identities']==ids
    atomic(path,record)
    state=read(STATE)
    state['active0173_bn64_comparison']=dict(phase='ready-'+window,ready_receipt=str(path),
        engine_tool_session=session,benchmark_tool_session=None,serving_gain_qualified=False)
    state['active_engine_sessions']=[dict(role=window,version='0.17.3',phase='ready',
        controller=dict(pid=current['pid'],run_id=current['run_id'],identity=ids['controller']),
        backend=dict(pid=inner['controller_pid'],run_id=inner['run_id'],identity=ids['backend']),
        tool_session_id=session)]
    state['active_session']=dict(role=window,engine_session_id=session,benchmark_session_id=None,
        controller_pid=current['pid'],controller_run_id=current['run_id'],
        backend_pid=inner['controller_pid'],backend_run_id=inner['run_id'])
    state['timestamp_utc']=utc()
    atomic(STATE,state)
    print(json.dumps(dict(ready=True,window=window,controller_pid=current['pid'],backend_pid=inner['controller_pid'],receipt=str(path))),flush=True)
    return record

def stop(window):
    saved=read(WORK/(window+'-ready.json'))
    record=checkpoint(window,saved['engine_tool_session'])
    assert record['controller']['run_id']==saved['controller']['run_id'] and record['identities']==saved['identities']
    current=record['controller'];inner=record['backend']
    atomic(ROOT/'server/.local/stop.json',dict(run_id=current['run_id']))
    print(json.dumps(dict(window=window,normal_stop_requested=True,run_id=current['run_id'])),flush=True)
    while True:
        latest=read(ROOT/'server/.local/current.json')
        assert latest['run_id']==current['run_id']
        live=migration.identity(current['pid'])
        assert live is None or live==saved['identities']['controller']
        if latest['phase'] in ('stopped','failed') and live is None:
            final=read(BACKEND/'.local/current-service.json')
            assert final['run_id']==inner['run_id'] and migration.identity(inner['controller_pid']) is None
            outcome=read(Path(final['attempt'])/'outcome.json')
            assert outcome['cleanup'] and outcome['recovery']
            record.update(terminal_utc=utc(),final_controller=latest,final_backend=final,outcome=outcome,own_handles_closed=True)
            atomic(WORK/(window+'-stop.json'),record)
            print(json.dumps(dict(window=window,stopped=True,cleanup=True,recovery=True)),flush=True)
            return
        time.sleep(.25)

def launch_after():
    current=read(ROOT/'server/.local/current.json')
    assert current['phase'] in ('stopped','failed') and migration.identity(current['pid']) is None
    inner=read(BACKEND/'.local/current-service.json')
    assert migration.identity(inner['controller_pid']) is None
    outcome=read(Path(inner['attempt'])/'outcome.json')
    assert outcome['cleanup'] and outcome['recovery']
    path=WORK/'after-visible-launch.json'
    assert not path.exists(),'Continue the retained after console'
    command=[r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe','-NoProfile','-NoExit','-ExecutionPolicy','Bypass','-File',str(PREP/'halogen0173-migration-20261009/Start-Latest.ps1')]
    process=subprocess.Popen(command,cwd=str(ROOT),close_fds=True,creationflags=subprocess.CREATE_NEW_CONSOLE)
    console=migration.identity(process.pid)
    assert console
    atomic(path,dict(utc=utc(),console_identity=console,command=command))
    print(json.dumps(dict(window='after',console_pid=process.pid,receipt=str(path))),flush=True)

def audit(name):
    inner=read(BACKEND/'.local/current-service.json')
    assert inner['phase']=='ready' and migration.identity(inner['controller_pid'])
    manifest=read(Path(inner['attempt'])/'manifest.json')
    assert manifest['bulk_bn64_candidate']['enabled'] is True
    assert name in ('before','after')
    result=subprocess.run([r'C:\Windows\System32\wsl.exe','-d','Ubuntu-24.04','-u','revn','--exec',
        'docker','exec',inner['container_id'],'cat','/tmp/alloy-bulk-bn64.jsonl'],
        capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode==0 and result.stdout and len(result.stdout.encode())<=1024**2
    rows=[json.loads(line) for line in result.stdout.splitlines()]
    assert rows[0]['type']=='enabled_pinned_0173'
    assert all(row['failures']==0 and row['rolled_back']==0 for row in rows)
    assert rows[-1]['started']==rows[-1]['committed']
    path=WORK/('candidate-audit-'+name+'.jsonl')
    assert not path.exists()
    path.write_text(result.stdout,encoding='utf-8')
    print(json.dumps(dict(audit=name,rows=len(rows),committed=rows[-1]['committed'],started=rows[-1]['started'],failures=0,rolled_back=0)),flush=True)

def observe(window,session=None):
    end=time.monotonic()+1200
    last=None
    while time.monotonic()<end:
        current=read(ROOT/'server/.local/current.json')
        inner=read(BACKEND/'.local/current-service.json')
        phase=(current['phase'],inner['phase'])
        if phase!=last:
            print(json.dumps(dict(window=window,controller_phase=phase[0],backend_phase=phase[1],controller_pid=current['pid'],backend_pid=inner['controller_pid'])),flush=True)
            last=phase
        if phase==('ready','ready'):
            checkpoint(window,session)
            return
        if current['phase']=='failed' and migration.identity(current['pid']) is None:
            raise RuntimeError('Retained controller failed: '+str(current.get('error')))
        time.sleep(1)
    raise TimeoutError('Observation ended; preserve actual retained server handles')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('checkpoint','stop','launch_after','audit','observe'))
    p.add_argument('--window',choices=('before','candidate','after'))
    p.add_argument('--session',type=int)
    a=p.parse_args()
    if a.action=='launch_after': launch_after()
    elif a.action=='audit': audit(a.window)
    elif a.action=='stop': stop(a.window)
    elif a.action=='observe': observe(a.window,a.session)
    else: checkpoint(a.window,a.session)
