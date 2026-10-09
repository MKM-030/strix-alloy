"""One sealed, explicit BN64 experiment through the original controller lifecycle."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

WORK=Path(__file__).resolve().parent
PREP=WORK.parent
ROOT=PREP.parents[3]
BACKEND=ROOT/'backends/halogen-wsl2-0.17.3'
PROFILE=PREP/'halogen0173-migration-20261009/thinking-latest-profile.json'
SOURCE=PREP/'bulk-bn64-engine-candidate-v1/adapter.c'
SO=SOURCE.with_name('libbulk-bn64.so')
REVIEW=SOURCE.with_name('independent-abi-transaction-review.md')
PYTHON=ROOT/'server/.local/venv/Scripts/python.exe'
PRELOAD='/candidate/libhalogen0173-v2-preflight.so:/candidate/hip-register-private-rw.so'
SO_DEST='/candidate/libbulk-bn64.so'
IMAGE='ghcr.io/peonist-ai/halogen-flash-server@sha256:3bca0132db3c859c997d52d148e6ea4b7b497b8a695c5ccab97135193fde592a'
SOURCE_SHA='1168a01f8ffd7346f6b63144b4b1f28e8801c15bc84ecaa56c5364961dba7da7'
SO_SHA='3231682f43d01afdde4ba6646eabf0c485ffa1e775000e26e95d1e096f0d3518'
PROFILE_SHA='78e1888d9ecc93a2117be679cd27ffeec1f8f9b99165e18647cef04104bfc141'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def ref(path):
    return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path))

def check_seal():
    assert sha(SOURCE)==SOURCE_SHA and sha(SO)==SO_SHA and sha(PROFILE)==PROFILE_SHA
    assert SOURCE_SHA in REVIEW.read_text(encoding='utf-8-sig')
    value=json.loads((WORK/'seal.json').read_text(encoding='utf-8'))
    for item in value['inputs']:
        assert ref(Path(item['path']))==item,item['path']
    assert value['adapter_source_sha256']==SOURCE_SHA and value['adapter_so_sha256']==SO_SHA
    assert value['launch_sha256']==sha(Path(__file__))
    return value

def import_normal(name,directory):
    sys.path.insert(0,str(directory))
    module=__import__(name)
    assert Path(module.__file__).resolve()==(directory/(name+'.py')).resolve()
    return module

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--role',choices=('controller','service'),default='controller')
    p.add_argument('--run',action='store_true')
    args=p.parse_args()
    assert not any(key=='LD_PRELOAD' or key.startswith(('ALLOY_BULK_BN64','PLE0172_','HG0172_')) for key in os.environ)
    seal=check_seal()
    profile=json.loads(PROFILE.read_bytes())
    engine=profile['engine']
    assert engine['directory']=='backends/halogen-wsl2-0.17.3'
    assert (engine['context'],engine['draft_tokens'],engine['prefill_chunk'],engine['max_prefill_tokens'])==(262144,2,8192,8192)
    assert engine['speculation_policy']=={'HALOGEN_PLD':'3,3'}
    assert engine['api_defaults']=={'enable_thinking':True,'reasoning_effort':'medium','max_thinking_tokens':2048}
    if not args.run:
        print(json.dumps(dict(validated=True,launched=False,normal_lifecycle=True,explicit_candidate=True)))
        return 0
    assert os.name=='nt' and Path(sys.executable).resolve()==PYTHON.resolve()
    if args.role=='controller':
        controller=import_normal('controller',ROOT/'server')
        expected=controller.halogen_launch_command(engine,BACKEND)
        normal=controller.JobChild
        replacement=[str(PYTHON),'-B','-u',str(Path(__file__)), '--role','service','--run']
        class CandidateChild(normal):
            def __init__(self,command,*,cwd,env,stdout_path,stderr_path):
                assert list(command)==expected and Path(cwd).resolve()==BACKEND.resolve()
                assert env.get('ALLOY_MANAGED')=='1' and check_seal()==seal
                super().__init__(replacement,cwd=cwd,env=env,stdout_path=stdout_path,stderr_path=stderr_path)
        controller.JobChild=CandidateChild
        sys.argv=[str(ROOT/'server/controller.py'),'run','--config',str(PROFILE),'--port','8840']
        return controller.main()
    assert os.environ.get('ALLOY_MANAGED')=='1'
    service=import_normal('service',BACKEND/'scripts')
    assert service.r.IMAGE==IMAGE
    original=service.build_manifest
    def manifest(options,attempt,run_id):
        assert check_seal()==seal
        m=original(options,attempt,run_id)
        env=m['environment']
        target={'HALOGEN_CTX':'262144','HALOGEN_MTP_DEPTH':'2','HALOGEN_PLD':'3,3','HALOGEN_PREFILL_CHUNK':'8192','HALOGEN_MAX_TOK':'8192','HALOGEN_PROMPT_CACHE':'0','HALOGEN_HOST_RESERVE_GIB':'18'}
        assert m['version']=='0.17.3' and m['image']==IMAGE and m['slots']==1
        assert env['LD_PRELOAD']==PRELOAD and all(env.get(k)==v for k,v in target.items())
        assert tuple(service.floors(262144,'v2'))==(35,131)
        assert SO_DEST not in m['mounts'] and not any(k.startswith('ALLOY_BULK_BN64') for k in env)
        m['mounts'][SO_DEST]=service.r.linux_path(SO)
        env.update(LD_PRELOAD=PRELOAD+':'+SO_DEST,ALLOY_BULK_BN64_ENABLE='1',ALLOY_BULK_BN64_LOG='/tmp/alloy-bulk-bn64.jsonl')
        m['bulk_bn64_candidate']=dict(enabled=True,adapter_source_sha256=SOURCE_SHA,adapter_sha256=SO_SHA,seal_sha256=sha(WORK/'seal.json'),default_off=True,normal_lifecycle=True,new_device_code=False)
        assert service.command(m).count('type=bind,src='+service.r.linux_path(SO)+',dst='+SO_DEST+',readonly')==1
        return m
    service.build_manifest=manifest
    normal_options=['--checkpoint','v2','--context-size','262144','--prompt-cache','Off','--serve-seconds','0','--startup-timeout','900','--draft-tokens','2','--prefill-chunk','8192','--max-prefill-tokens','8192','--speculation-policy-json',json.dumps(engine['speculation_policy']),'--api-defaults-json',json.dumps(engine['api_defaults'])]
    return service.main(normal_options)

if __name__=='__main__':
    raise SystemExit(main())
