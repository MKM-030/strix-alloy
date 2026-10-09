"""Default-off native registration adapter through the normal managed lifecycle."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

WORK=Path(__file__).resolve().parent
PREP=WORK.parent
ROOT=PREP.parents[3]
BASE=PREP/'ple0172-native-worker-detour-v1/native_worker_launcher_0172.py'
BASE_SHA='93076e4e9451d5881900ea86ebb90c0abf10c963823f4c7584315f4af62f78a7'
PROFILE=PREP/'servicenow-thinking-defaults-20261008/thinking-latest-profile.json'
PROFILE_SHA='b5d3692b2623034f5a9c4a5f90b234ba6b792793196963fc0e7b474b3937c839'
PYTHON=ROOT/'server/.local/venv/Scripts/python.exe'
BACKEND=ROOT/'backends/halogen-wsl2-0.17.2'

def require(condition,message):
    if not condition: raise RuntimeError(message)

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def normal():
    require(sha(BASE)==BASE_SHA and sha(PROFILE)==PROFILE_SHA,'Normal wrapper/profile changed')
    spec=importlib.util.spec_from_file_location('sealed_normal',BASE)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module,module.load_receipt(argparse.Namespace(mode='stock',launcher_sha256=BASE_SHA,receipt=None))

def candidate():
    build=json.loads((WORK/'build.json').read_bytes())
    require(build['returncode']==0 and build['CPU_only'] and not build['HIP_initialized'],'Build not qualified')
    for entry in build['files']:
        path=WORK/entry['name']
        require(path.stat().st_size==entry['bytes'] and sha(path)==entry['sha256'],'Candidate build source changed')
    require(build['mock_passed'],'Mock registration failed')
    return build

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role',choices=('controller','service'),default='controller')
    parser.add_argument('--launcher-sha256',required=True)
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    require(sha(Path(__file__))==args.launcher_sha256,'Independent launcher seal changed')
    require(not any(k=='LD_PRELOAD' or k.startswith(('HG0172_','PLE0172_','HALOGEN_')) for k in os.environ),'Inherited experimental environment refused')
    base,receipt=normal()
    build=candidate()
    if not args.run:
        print(json.dumps(dict(validated=True,launched=False,normal_lifecycle=True,build_sha256=sha(WORK/'build.json'))))
        return 0
    require(os.name=='nt' and Path(sys.executable).resolve()==PYTHON.resolve(),'Normal project Python required')
    if args.role=='service':
        service=base.import_normal('service',BACKEND/'scripts')
        original=service.build_manifest
        def manifest(options,attempt,run_id):
            require(normal()[1]==receipt and candidate()==build,'Source inventory changed')
            m=original(options,attempt,run_id)
            env=m['environment']
            expected={'HALOGEN_CTX':'262144','HALOGEN_MTP_DEPTH':'2','HALOGEN_PLD':'3,3',
                      'HALOGEN_PREFILL_CHUNK':'8192','HALOGEN_MAX_TOK':'8192',
                      'HALOGEN_PROMPT_CACHE':'0','HALOGEN_HOST_RESERVE_GIB':'18'}
            require(m['image']==base.IMAGE and m['version']=='0.17.2' and m['slots']==1
                    and env['LD_PRELOAD']==base.PRELOAD and m['sources']==receipt['backend_sources']
                    and all(env.get(k)==v for k,v in expected.items()),'Normal manifest changed')
            require(re.fullmatch('[0-9a-f]{32}',run_id) and '_hg_flash_serve' not in env
                    and not any(k.startswith(('HG0172_','PLE0172_')) for k in env),'Unexpected candidate environment')
            for name in ('register-launch.sh','libhalogen0172-hc6-register.so'):
                dest='/candidate/'+name
                require(dest not in m['mounts'],'Mount already present')
                m['mounts'][dest]=service.r.linux_path(WORK/name)
            env.update(_hg_flash_serve='/candidate/register-launch.sh',HG0172_HC6_REGISTER_REMAP='1')
            m['hc6_registration_candidate']=dict(enabled=True,launcher_sha256=args.launcher_sha256,
                  build_sha256=sha(WORK/'build.json'),original_host_dispatch=True,
                  changed_bytes=14,launch_hook=False,module_api_route=False,normal_lifecycle=True)
            return m
        service.build_manifest=manifest
        configuration=json.loads(PROFILE.read_bytes())['engine']
        controller=base.import_normal('controller',ROOT/'server')
        command=controller.halogen_launch_command(configuration,BACKEND)
        require(command[:4]==[str(PYTHON),'-u','-B',str(BACKEND/'scripts/service.py')],'Normal service command changed')
        sys.argv=[command[3]]+command[4:]
        return service.main()
    controller=base.import_normal('controller',ROOT/'server')
    configuration=json.loads(PROFILE.read_bytes())['engine']
    expected_command=controller.halogen_launch_command(configuration,BACKEND)
    original_child=controller.JobChild
    class CandidateChild(original_child):
        def __init__(self,command,*,cwd,env,stdout_path,stderr_path):
            require(list(command)==expected_command and Path(cwd).resolve()==BACKEND.resolve()
                    and env.get('ALLOY_MANAGED')=='1' and normal()[1]==receipt,'Unexpected managed child')
            replacement=[str(PYTHON),'-B','-u',str(Path(__file__)),
                         '--launcher-sha256',args.launcher_sha256,'--role','service','--run']
            super().__init__(replacement,cwd=cwd,env=env,stdout_path=stdout_path,stderr_path=stderr_path)
    controller.JobChild=CandidateChild
    sys.argv=[str(ROOT/'server/controller.py'),'run','--config',str(PROFILE),'--port','8840']
    return controller.main()

if __name__=='__main__': raise SystemExit(main())
