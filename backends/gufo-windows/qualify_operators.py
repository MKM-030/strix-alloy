"""Execute original numerical tests; this never marks a model as fully qualified."""
import argparse,hashlib,json,os,socket,subprocess,time
from pathlib import Path
from verify_toolchain import PINS,check_sdk,check_source,digest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();pins=json.loads(PINS.read_text(encoding='utf-8'))
    identity={**check_sdk(args.sdk,pins),**check_source(args.source,pins)}
    if args.output.exists():raise ValueError('Use a new qualification output directory')
    for port in (8731,8840,8826,8836,18808):
        with socket.socket() as sock:
            sock.settimeout(.5)
            if sock.connect_ex(('127.0.0.1',port))==0:
                raise ValueError('Stop active inference before operator qualification')
    for name,expected in pins['runtime_hashes'].items():
        if digest(args.build/name)!=expected:
            raise ValueError('App-local runtime does not match qualified SDK: '+name)
    args.output.mkdir(parents=True)
    env={k:v for k,v in os.environ.items() if not k.startswith(('GUFO_','A3B_','HIP_','HSA_','GGML_'))}
    env['PATH']=str(args.build.resolve())+os.pathsep+env.get('PATH','')
    rows=[]
    for mode in ('default','none'):
        for name in pins['tests']:
            executable=args.build/('qwen38_flash_next_'+name+'_test.exe')
            if not executable.is_file():raise ValueError('Missing original test executable: '+name)
            options=dict(env)
            if mode=='none':options['GUFO_PLATFORM_TUNING']='none'
            started=time.perf_counter()
            try:
                result=subprocess.run([str(executable.resolve())],cwd=args.build,env=options,
                    capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
                code=result.returncode;output=result.stdout+'\n'+result.stderr
            except subprocess.TimeoutExpired:
                code=124;output='Original test exceeded the finite 120-second deadline.'
            (args.output/(mode+'-'+name+'.log')).write_text(output,encoding='utf-8')
            row={'mode':mode,'test':name,'exit':code,'seconds':time.perf_counter()-started,
                 'executable_sha256':digest(executable)}
            rows.append(row);print(json.dumps(row),flush=True)
            (args.output/'samples.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    # Detect source/SDK changes during testing; never bless a mixed run.
    check_sdk(args.sdk,pins);check_source(args.source,pins)
    report={'schema':1,**identity,'passed':all(r['exit']==0 for r in rows),
            'scope':'original numerical operators only; not whole-model quality or performance',
            'runtime_hashes':pins['runtime_hashes'],'tests':rows}
    (args.output/'qualification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return 0 if report['passed'] else 2

if __name__=='__main__':raise SystemExit(main())
