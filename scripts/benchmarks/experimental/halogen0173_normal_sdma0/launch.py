"""Explicit SDMA0 through the normal controller/service lifecycle; default off."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

WORK=Path(__file__).resolve().parent
PREP=WORK.parent
ROOT=PREP.parents[3]
BACKEND=ROOT/'backends/halogen-wsl2-0.17.3'
PROFILE=PREP/'halogen0173-migration-20261009/thinking-latest-profile.json'
PYTHON=ROOT/'server/.local/venv/Scripts/python.exe'
IMAGE='ghcr.io/peonist-ai/halogen-flash-server@sha256:3bca0132db3c859c997d52d148e6ea4b7b497b8a695c5ccab97135193fde592a'
PRELOAD='/candidate/libhalogen0173-v2-preflight.so:/candidate/hip-register-private-rw.so'

def check_seal():
    seal=json.loads((WORK/'seal.json').read_bytes())
    for item in seal['inputs']:
        path=Path(item['path'])
        assert path.stat().st_size==item['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],str(path)
    return seal

def apply_candidate(m):
    env=m['environment']
    assert m['version']=='0.17.3' and m['image']==IMAGE and m['context']==262144 and m['slots']==1
    assert env['LD_PRELOAD']==PRELOAD and env['HSA_ENABLE_SDMA']=='1'
    assert not any(key.startswith('ALLOY_BULK_BN64') for key in env)
    before=dict(env)
    env['HSA_ENABLE_SDMA']='0'
    assert {key for key in before if before[key]!=env[key]}=={'HSA_ENABLE_SDMA'}
    m['sdma0_candidate']=dict(enabled=True,default_off=True,normal_lifecycle=True,only_environment_change='HSA_ENABLE_SDMA=0')
    return m

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--role',choices=('controller','service'),default='controller')
    p.add_argument('--run',action='store_true')
    args=p.parse_args()
    assert not any(key=='LD_PRELOAD' or key.startswith(('ALLOY_BULK_BN64','PLE0172_','HG0172_','HSA_ENABLE_')) for key in os.environ)
    seal=check_seal()
    profile=json.loads(PROFILE.read_bytes());engine=profile['engine']
    assert (engine['context'],engine['draft_tokens'],engine['prefill_chunk'],engine['max_prefill_tokens'])==(262144,2,8192,8192)
    assert engine['speculation_policy']=={'HALOGEN_PLD':'3,3'}
    if not args.run:
        fixture=dict(version='0.17.3',image=IMAGE,context=262144,slots=1,environment=dict(LD_PRELOAD=PRELOAD,HSA_ENABLE_SDMA='1'))
        assert apply_candidate(fixture)['environment']['HSA_ENABLE_SDMA']=='0'
        fixture['environment']['HSA_ENABLE_SDMA']='unexpected'
        try: apply_candidate(fixture)
        except AssertionError: pass
        else: raise AssertionError('Unexpected source configuration accepted')
        print(json.dumps(dict(validated=True,launched=False,only_change='HSA_ENABLE_SDMA=0')))
        return 0
    assert os.name=='nt' and Path(sys.executable).resolve()==PYTHON.resolve()
    if args.role=='controller':
        sys.path.insert(0,str(ROOT/'server'))
        import controller
        expected=controller.halogen_launch_command(engine,BACKEND)
        normal=controller.JobChild
        replacement=[str(PYTHON),'-B','-u',str(Path(__file__)),'--role','service','--run']
        class CandidateChild(normal):
            def __init__(self,command,*,cwd,env,stdout_path,stderr_path):
                assert list(command)==expected and Path(cwd).resolve()==BACKEND.resolve()
                assert env.get('ALLOY_MANAGED')=='1' and check_seal()==seal
                super().__init__(replacement,cwd=cwd,env=env,stdout_path=stdout_path,stderr_path=stderr_path)
        controller.JobChild=CandidateChild
        sys.argv=[str(ROOT/'server/controller.py'),'run','--config',str(PROFILE),'--port','8840']
        return controller.main()
    assert os.environ.get('ALLOY_MANAGED')=='1'
    sys.path.insert(0,str(BACKEND/'scripts'))
    import service
    assert service.r.IMAGE==IMAGE and tuple(service.floors(262144,'v2'))==(35,131)
    original=service.build_manifest
    def manifest(options,attempt,run_id):
        assert check_seal()==seal
        return apply_candidate(original(options,attempt,run_id))
    service.build_manifest=manifest
    options=['--checkpoint','v2','--context-size','262144','--prompt-cache','Off','--serve-seconds','0','--startup-timeout','900',
             '--draft-tokens','2','--prefill-chunk','8192','--max-prefill-tokens','8192',
             '--speculation-policy-json',json.dumps(engine['speculation_policy']),
             '--api-defaults-json',json.dumps(engine['api_defaults'])]
    return service.main(options)

if __name__=='__main__': raise SystemExit(main())
