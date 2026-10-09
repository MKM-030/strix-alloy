"""Windows offline device compile. Never loads HIP or initializes a device."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[4]
PREP=ROOT/'server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008'
SDK=Path('C:/AI/sdk/therock1151-10.2.0a20260930')
TOOLS=SDK/'lib/llvm/bin'
def ref(p):
    return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    source=Path(__file__).with_name('kernel.cpp')
    record=dict(schema='alloy0173.scratchfree-moe.offline-build.v1',utc=datetime.now(timezone.utc).isoformat(),
                source=ref(source),runtime_loaded=False,hardware_executed=False,engine_changed=False,stages=[])
    bundle=a.out/'owner512.bundle';obj=a.out/'owner512.hsaco'
    commands=[('compile',[str(TOOLS/'clang++.exe'),'-x','hip','--offload-device-only','--offload-arch=gfx1151',
                '-mcode-object-version=6','-O3','-fno-fast-math','-ffp-contract=off',
                '--rocm-path='+str(SDK),'--hip-path='+str(SDK),
                '--rocm-device-lib-path='+str(SDK/'lib/llvm/amdgcn/bitcode'),str(source),'-o',str(bundle)]),
              ('unbundle',[str(TOOLS/'clang-offload-bundler.exe'),'--type=o','--unbundle',
                '--targets=hipv4-amdgcn-amd-amdhsa--gfx1151','--input='+str(bundle),'--output='+str(obj)]),
              ('metadata',[str(TOOLS/'llvm-readobj.exe'),'--file-headers','--notes','--symbols',str(obj)]),
              ('disassembly',[str(TOOLS/'llvm-objdump.exe'),'-d','--mcpu=gfx1151',str(obj)])]
    try:
        for name,cmd in commands:
            result=subprocess.run(cmd,stdin=subprocess.DEVNULL,capture_output=True,timeout=60,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            out=a.out/(name+'.txt');err=a.out/(name+'-stderr.txt')
            out.write_bytes(result.stdout);err.write_bytes(result.stderr)
            record['stages'].append(dict(name=name,arguments=cmd,tool=ref(Path(cmd[0])),exit_code=result.returncode,
                                         stdout=ref(out),stderr=ref(err)))
            assert result.returncode==0, name+' failed'
        record.update(passed=True,code_object=ref(obj))
        assert record['source']==ref(source)
    except BaseException as e: record.update(passed=False,error=type(e).__name__+': '+str(e))
    (a.out/'build.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=record['passed'],error=record.get('error'),receipt=str(a.out/'build.json'))))
    return 0 if record['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
