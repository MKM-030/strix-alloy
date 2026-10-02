"""Create a separate benchmark configuration; never start or register it."""
import argparse,copy,hashlib,json
from pathlib import Path

def resized_profile(profile,context):
    if type(context) is not int or not 4096<=context<=262144:
        raise ValueError('Unsupported benchmark capacity')
    result=copy.deepcopy(profile)
    engine=result.get('engine',{});backend=result.get('backend',{})
    if engine.get('kind')!='native' or engine.get('qualified') is not True:
        raise ValueError('An existing explicitly qualified native profile is required')
    if backend.get('identifier') not in ('gufo-flash-next','projfix-flash-next'):
        raise ValueError('Unreviewed native profile type')
    command=engine.get('command',[])
    indices=[i for i,x in enumerate(command) if x in ('--context','-c','--ctx-size')]
    if len(indices)!=1 or indices[0]+1>=len(command):
        raise ValueError('Exactly one context argument is required')
    index=indices[0]+1
    if str(backend.get('context'))!=command[index]:
        raise ValueError('Profile metadata and engine context disagree')
    command[index]=str(context);backend['context']=context
    result['benchmark_geometry']={'context':context,'qualification_scope':'Inherited operator/runtime identity only; this capacity must still pass live testing.'}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--context',type=int,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();raw=args.source.read_bytes()
    result=resized_profile(json.loads(raw.decode('utf-8-sig')),args.context)
    result['benchmark_geometry']['source_profile_sha256']=hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print('Created separate benchmark profile; no engine or default profile changed.')

if __name__=='__main__':main()
