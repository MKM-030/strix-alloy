"""Portable profile generation. Native candidates are not silently promoted."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from controller import atomic,control
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
PACKAGE=REPO/'backends/halogen-wsl2-0.16.2'


def make_profile(backend, checkpoint, context, prompt_cache='Off', halogen_version='0.16.2'):
    if type(context) is not int or not 4096<=context<=262144:
        raise ValueError('Context must be 4096..262144 positions')
    if checkpoint not in ('w4b','v2'): raise ValueError('Unknown checkpoint')
    if prompt_cache not in ('Off','Exact','Flexible'): raise ValueError('Unknown cache policy')
    if halogen_version not in ('0.16.2','0.17.0','0.17.1','0.17.2','0.17.3'):
        raise ValueError('Unsupported managed Halogen version')
    if backend!='Halogen':
        if halogen_version!='0.16.2':
            raise ValueError('Halogen version selection applies only to the Halogen backend')
        local=ROOT/'.local'/('qualified-'+backend.lower()+'.json')
        if not local.is_file():
            raise ValueError(backend+' has no qualified managed profile; no model was started')
        data=json.loads(local.read_text(encoding='utf-8'))
        if data.get('engine',{}).get('qualified') is not True:
            raise ValueError('Native candidate has not passed qualification')
        if data.get('backend',{}).get('context')!=context:
            raise ValueError('Native profile capacity differs; qualify a matching profile first')
        return data
    package=PACKAGE if halogen_version=='0.16.2' else REPO/('backends/halogen-wsl2-'+halogen_version)
    machine=package/'.local/machine.json'; token=package/'.local/api-token.txt'
    if not machine.is_file() or not token.is_file():
        raise ValueError('Install and qualify the Halogen backend before generating a gateway profile')
    settings=json.loads(machine.read_text(encoding='utf-8-sig'))
    if halogen_version!='0.16.2':
        release=json.loads((package/'profiles/release.json').read_text(encoding='utf-8-sig'))
        if (release.get('version')!=halogen_version or settings.get('version')!=halogen_version or
                settings.get('image')!=release.get('image') or not release.get('image')):
            raise ValueError('Selected Halogen machine receipt does not match its pinned release')
    identifier='halogen-'+checkpoint
    return {'schema':1,'minimum_reserve_gib':18,'token_file':str(token),'backend_token_file':str(token),
        'concurrency':1,'body_bytes':16*1024**2,'request_seconds':1800,
        'backend':{'identifier':identifier,'upstream':'http://127.0.0.1:8731',
            'model':'halogen-qwen3.8-flash-next','checkpoint':checkpoint,'context':context,
            'expected':{'status':'ok','version.api':halogen_version,'version.engine':halogen_version,
                        'version.match':True,'context':context,'slot_ctx':context,
                        'kv_pool_positions':context,'slots':1},
            'routes':['/v1/chat/completions','/v1/completions','/v1/responses',
                      '/v1/messages','/v1/messages/count_tokens']},
        'engine':{'kind':'halogen','directory':package.relative_to(REPO).as_posix(),
                  'checkpoint':checkpoint,'context':context,'prompt_cache':prompt_cache,
                  'powershell':settings['pwsh']}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['start','status','stop','describe'])
    p.add_argument('--backend',choices=['Halogen','GUFO','Projfix'],default='Halogen')
    p.add_argument('--halogen-version',choices=['0.16.2','0.17.0','0.17.1','0.17.2','0.17.3'],default='0.16.2')
    p.add_argument('--checkpoint',choices=['w4b','v2'],default='v2')
    p.add_argument('--context',type=int,default=129024)
    p.add_argument('--prompt-cache',choices=['Off','Exact','Flexible'],default='Off')
    p.add_argument('--port',type=int,default=8840)
    args=p.parse_args()
    if args.action in ('status','stop'): return control(args.action)
    config=make_profile(args.backend,args.checkpoint,args.context,args.prompt_cache,args.halogen_version)
    if args.action=='describe':
        print(json.dumps(config,indent=2)); return 0
    LOCAL=ROOT/'.local'; LOCAL.mkdir(parents=True,exist_ok=True)
    version_suffix='-'+args.halogen_version if args.backend=='Halogen' and args.halogen_version!='0.16.2' else ''
    profile=LOCAL/(args.backend.lower()+version_suffix+'-'+args.checkpoint+'-'+str(args.context)+'-'+args.prompt_cache+'.json')
    atomic(profile,config)
    return subprocess.call([sys.executable,'-u',str(ROOT/'controller.py'),'run',
                            '--config',str(profile),'--port',str(args.port)])

if __name__=='__main__': raise SystemExit(main())
