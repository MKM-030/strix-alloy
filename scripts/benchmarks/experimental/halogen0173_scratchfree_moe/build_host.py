"""Windows LLVM produces Linux DSOs without loading libc, HIP or an engine."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
HERE=Path(__file__).resolve().parent
TOOLS=Path('C:/AI/sdk/therock1151-10.2.0a20260930/lib/llvm/bin')
def ref(p):return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    record=dict(schema='alloy0173.scratchfree-moe.host-offline-build.v1',utc=datetime.now(timezone.utc).isoformat(),
        freestanding_linux_abi=True,wsl_invoked=False,runtime_loaded=False,hardware_executed=False,
        inputs=[ref(HERE/p) for p in ('capture.c','replay.c','linux_abi.h','mapped_pins.h','capture.map','replay.map')],stages=[])
    def run(label,cmd):
        r=subprocess.run(cmd,stdin=subprocess.DEVNULL,capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
        out=a.out/(label+'.txt');err=a.out/(label+'-stderr.txt');out.write_bytes(r.stdout);err.write_bytes(r.stderr)
        record['stages'].append(dict(name=label,arguments=cmd,tool=ref(Path(cmd[0])),exit_code=r.returncode,stdout=ref(out),stderr=ref(err)))
        assert r.returncode==0,label+' failed'
    try:
        record['outputs']={}
        for name in ('capture','replay'):
            obj=a.out/(name+'.o');library=a.out/('libhalogen0173_fl_'+name+'.so')
            run(name+'-compile',[str(TOOLS/'clang.exe'),'--target=x86_64-unknown-linux-gnu','-std=c11','-O2',
                '-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fPIC','-ffreestanding','-fno-builtin',
                '-fno-stack-protector','-fvisibility=hidden','-DALLOY_FREESTANDING_LINUX=1','-c',str(HERE/(name+'.c')),'-o',str(obj)])
            run(name+'-link',[str(TOOLS/'ld.lld.exe'),'-shared','-z','relro','-z','now','-z','noexecstack',
                '--version-script='+str(HERE/(name+'.map')),str(obj),'-o',str(library)])
            run(name+'-metadata',[str(TOOLS/'llvm-readobj.exe'),'--file-headers','--dynamic-table','--dyn-symbols',str(library)])
            record['outputs'][name]=ref(library)
        record['passed']=True
    except BaseException as e:record.update(passed=False,error=type(e).__name__+': '+str(e))
    (a.out/'build.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=record['passed'],error=record.get('error'),receipt=str(a.out/'build.json'))))
    return 0 if record['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
