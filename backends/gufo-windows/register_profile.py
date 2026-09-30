"""Register an explicitly selected experimental text profile after operator tests."""
import argparse,json
from pathlib import Path
from verify_toolchain import PINS,check_sdk,check_source,digest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('sdk','source','build','model','mtp','token-file','qualification'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--context',type=int,choices=[32768,129024,262144],default=262144)
    p.add_argument('--register',action='store_true',help='Explicitly create the managed local profile')
    args=p.parse_args();pins=json.loads(PINS.read_text(encoding='utf-8'))
    check_sdk(args.sdk,pins);check_source(args.source,pins)
    proof=json.loads(args.qualification.read_text(encoding='utf-8'))
    required={(mode,test) for mode in ('default','none') for test in pins['tests']}
    observed={(r['mode'],r['test']) for r in proof.get('tests',[]) if r.get('exit')==0}
    if (not proof.get('passed') or proof.get('source_commit')!=pins['source_commit']
        or proof.get('sdk_version')!=pins['sdk_version']
        or proof.get('compiler_sha256')!=pins['compiler_sha256']
        or proof.get('source_patch_sha256')!=pins.get('source_patch',{}).get('sha256')
        or proof.get('runtime_hashes')!=pins['runtime_hashes']
        or proof.get('gufo_executable_sha256')!=digest(args.build/'gufo.exe') or observed!=required
        or len(proof.get('tests',[]))!=len(required)):
        raise ValueError('Complete matching operator qualification is required')
    for row in proof['tests']:
        name='qwen38_flash_next_'+row['test']+'_test.exe'
        if digest(args.build/name)!=row['executable_sha256']:
            raise ValueError('Test executable changed since qualification')
    for name,expected in pins['runtime_hashes'].items():
        if digest(args.build/name)!=expected:raise ValueError('App-local runtime changed')
    for path in (args.model,args.mtp):
        if not path.is_file() or path.suffix.lower()!='.gguf':raise ValueError('Existing GGUF files required')
        with path.open('rb') as stream:
            if stream.read(4)!=b'GGUF':raise ValueError('Invalid GGUF header')
    if 'shared' not in args.mtp.name.lower():raise ValueError('Flash-Next needs the shared MTP sidecar')
    if len(args.token_file.read_text(encoding='ascii').strip())<32:raise ValueError('A strong existing API key is required')
    executable=(args.build/'gufo.exe').resolve(strict=True)
    command=[str(executable),'serve','llm','--model',str(args.model.resolve()),
      '--mtp-model',str(args.mtp.resolve()),'--speculative','mtp','--draft-tokens','3',
      '--context',str(args.context),'--sessions','1','--host','127.0.0.1','--port','8836',
      '--served-model-name','gufo-flash-next','--think','off','--temperature','0',
      '--max-tokens','8192','--prefill-chunk','2048','--max-connections','8',
      '--max-pending','1','--max-pending-per-client','1','--request-timeout-ms','1800000',
      '--max-request-bytes','16777216','--verbose']
    profile={'schema':1,'token_file':str(args.token_file.resolve()),
      'backend_token_file':str(args.token_file.resolve()),'concurrency':1,
      'body_bytes':16777216,'request_seconds':1800,
      'backend':{'identifier':'gufo-flash-next','upstream':'http://127.0.0.1:8836',
        'model':'gufo-flash-next','checkpoint':args.model.parent.name,'context':args.context,
        'expected':{'status':'ok'},'routes':['/v1/chat/completions']},
      'engine':{'kind':'native','qualified':True,'command':command,
        'api_key_from_backend_token':True,'executable_sha256':digest(executable),
        'runtime_hashes':pins['runtime_hashes'],'environment':{}},
      'qualification':{'source_commit':pins['source_commit'],'sdk':pins.get('sdk_build',pins['sdk_version']),
        'compiler_sha256':pins['compiler_sha256'],
        'source_patch_sha256':pins.get('source_patch',{}).get('sha256'),
        'scope':'Original operator gates passed; model profile explicitly selected by local operator. Not independent model-quality certification.',
        'operator_proof_sha256':digest(args.qualification)}}
    root=Path(__file__).resolve().parents[2]
    target=root/'server/.local/qualified-gufo.json'
    if not args.register:
        print(json.dumps(profile,indent=2));return 0
    state=root/'server/.local/current.json'
    if state.exists() and json.loads(state.read_text())['phase'] in ('starting','ready','stopping'):
        raise ValueError('Stop the managed server before registering a different backend')
    if target.exists():raise ValueError('Existing local GUFO profile retained; archive it explicitly before replacement')
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as stream:json.dump(profile,stream,indent=2)
    print('Registered experimental gufo-flash-next profile. No API key value was written; no model started.')
    return 0

if __name__=='__main__':raise SystemExit(main())
