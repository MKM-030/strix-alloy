"""Generate a pinned local PROJFIX profile; never start a process or download weights."""
import argparse,hashlib,json
from pathlib import Path
PINS=Path(__file__).with_name('compatibility.json')

def command(runtime,model,draft,context,mode="serial"):
    if type(context) is not int or context not in (32768,65536,131072,262144):
        raise ValueError('Use a reviewed 32K, 64K, 128K or 256K capacity')
    if mode not in ("serial","mtp"): raise ValueError("Choose serial or mtp explicitly")
    args=[str(Path(runtime)/'llama-server.exe'),'-m',str(model),
        '--alias','projfix-flash-next','-dev','ROCm0','-ngl','99','-fa','on',
        '-fit','off','--load-mode','none','--lazy-mode','on',
        '-ctk','f16','-ctv','f16','-c',str(context),'-b','2048','-ub','512',
        '--parallel','1','--host','127.0.0.1','--port','8826','--seed','1234','--jinja',
        '-md',str(draft),'--spec-type','draft-mtp','--spec-draft-device','ROCm0',
        '--spec-draft-ngl','99','--spec-draft-n-max','2','--reasoning','on',
        '--reasoning-effort','low']
    if mode=='serial':
        remove={'-md','--spec-type','--spec-draft-device','--spec-draft-ngl','--spec-draft-n-max'}
        result=[];index=0
        while index<len(args):
            if args[index] in remove: index+=2
            else: result.append(args[index]);index+=1
        result += ['-ot', r'^blk[.](?:[0-9]|1[0-7])[.]ffn_(?:gate|up|down)_exps[.]weight$=CPU']
        return result
    return args

def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def validate_runtime(runtime,pins):
    root=Path(runtime).resolve(strict=True)
    for name,expected in pins['runtime_files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe manifest path')
        target=(root/relative).resolve(strict=True)
        if not target.is_relative_to(root) or digest(target)!=expected:
            raise ValueError('Runtime component differs from measured configuration: '+name)
    return root

def make_profile(runtime,models,token_file,context,pins,mode="serial"):
    runtime=validate_runtime(runtime,pins);models=Path(models).resolve(strict=True)
    files=[models/name for name in pins['model_files'] if mode=='mtp' or name!=pins['draft']]
    for path in files:
        if not path.is_file() or path.stat().st_size!=pins['model_files'][path.name]:
            raise ValueError('Missing or wrong-size measured model component: '+path.name)
        with path.open('rb') as stream:
            if stream.read(4)!=b'GGUF':raise ValueError('Invalid GGUF header')
    target=models/pins['target'];draft=models/pins['draft']
    token=str(Path(token_file).resolve(strict=True))
    return {'schema':1,'token_file':token,'backend_token_file':token,'concurrency':1,
        'body_bytes':16777216,'request_seconds':1800,
        'backend':{'identifier':'projfix-flash-next','model':'projfix-flash-next',
            'upstream':'http://127.0.0.1:8826','checkpoint':'IQ4_NL-PROJFIX','context':context,
            'expected':{'status':'ok'},'routes':['/v1/chat/completions']},
        'engine':{'kind':'native','qualified':True,'command':command(runtime,target,draft,context,mode),
            'api_key_from_backend_token':True,'executable_sha256':pins['runtime_files']['llama-server.exe'],
            'runtime_hashes':{k:v for k,v in pins['runtime_files'].items() if '/' not in k and k.endswith('.dll')},
            'environment':{'HSA_OVERRIDE_GFX_VERSION':'11.5.1'}},
        'qualification':{'scope':'Explicit local registration of measured runtime/loading policy. Model size/header checks are not complete-file checksums or general model-quality certification.',
            'decoding_mode':mode,'placement':'pinned-host-experts-0-17' if mode=='serial' else 'legacy-device-resident','sdk_runtime':pins['sdk_runtime'],'source':'docs/integration/projfix-decode-restored-20261001.md',
            'manifest_sha256':digest(PINS)}}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime','models','token-file'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--context',type=int,default=262144)
    parser.add_argument('--mode',choices=['serial','mtp'],default='serial')
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path);group.add_argument('--register',action='store_true')
    args=parser.parse_args();pins=json.loads(PINS.read_text(encoding='utf-8'))
    root=Path(__file__).resolve().parents[2]
    target=root/'server/.local/qualified-projfix.json' if args.register else args.output
    if target.exists():raise ValueError('Existing profile retained; archive it explicitly before replacement')
    state=root/'server/.local/current.json'
    if args.register and state.exists():
        if json.loads(state.read_text(encoding='utf-8-sig'))['phase'] in ('starting','ready','stopping'):
            raise ValueError('Stop the managed engine before registration')
    value=make_profile(args.runtime,args.models,args.token_file,args.context,pins,args.mode)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2)
    print('Wrote local PROJFIX profile. No model started; no API-key value stored.')
    return 0
if __name__=='__main__':raise SystemExit(main())
