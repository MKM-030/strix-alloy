"""Confirm actual registration substitution on the live owned engine, no inference."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
WORK=Path(__file__).resolve().parent
PREP=WORK.parent
ROOT=PREP.parents[3]
sys.path.insert(0,str(ROOT/'server'))
from controller import atomic,read
if __name__=='__main__':
    label=sys.argv[1]
    assert label in ('before','after')
    dest=WORK/('candidate-registration-'+label+'.json')
    assert not dest.exists()
    backend=read(ROOT/'backends/halogen-wsl2-0.17.2/.local/current-service.json')
    current=read(ROOT/'server/.local/current.json')
    assert backend['phase']==current['phase']=='ready'
    manifest=read(Path(backend['attempt'])/'manifest.json')
    assert manifest['hc6_registration_candidate']['enabled']
    assert manifest['environment']['HG0172_HC6_REGISTER_REMAP']=='1'
    log=Path(backend['attempt'])/'engine.log'
    rows=re.findall(r'^.*?(HGHC6_REGISTER_V1 pid=(\d+) bundle=([0-9a-f]{64}) payload=([0-9a-f]{64}) changed_bytes=14 handle=(0x[0-9a-f]+) status=nonnull).*$',log.read_text(errors='replace'),re.MULTILINE)
    assert len(rows)==1,'Expected exactly one actual registration receipt'
    line,pid,bundle,payload,handle=rows[0]
    assert bundle=='f668c44ee907d72d07e4cc89eb3234dc384a9ec5c39b8e702b49e616690892ff'
    assert payload=='39053af36ed652892f7082af4eca5cd153b593260448b3c91a67f277cd0f1259'
    code='import os,sys; pid=int(sys.argv[1]); assert os.readlink("/proc/"+str(pid)+"/exe")=="/usr/local/bin/flash_serve"; print(pid)'
    command=['wsl.exe','-d','Ubuntu-24.04','-u','revn','--exec','docker','exec',backend['container_id'],'python3','-c',code,pid]
    result=subprocess.run(command,capture_output=True,text=True,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()==pid
    assert read(ROOT/'server/.local/current.json')['run_id']==current['run_id']
    assert read(ROOT/'backends/halogen-wsl2-0.17.2/.local/current-service.json')['run_id']==backend['run_id']
    record=dict(utc=datetime.now(timezone.utc).isoformat(),label=label,controller_run_id=current['run_id'],
                backend_run_id=backend['run_id'],container_id=backend['container_id'],engine_namespace_pid=int(pid),
                registration_receipt=line,handle_nonnull=True,changed_bytes=14,complete_bundle_sha256=bundle,
                payload_sha256=payload,original_host_dispatch=True,launch_hook=False,inference_performed=False)
    atomic(dest,record)
    print(json.dumps(record))
