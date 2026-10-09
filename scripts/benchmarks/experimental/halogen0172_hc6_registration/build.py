"""CPU-only adapter/mock build; production HIP is never initialized."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

WORK=Path(__file__).resolve().parent
PREP=WORK.parent
LINUX='/mnt/c/'+WORK.relative_to(Path('C:/')).as_posix()

def ref(name):
    path=WORK/name
    return dict(name=name,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def execute(arguments):
    command=['wsl.exe','-d','Ubuntu-24.04','-u','revn','--exec']+arguments
    result=subprocess.run(command,capture_output=True,text=True,timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode==0,result.stderr+result.stdout
    return dict(command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)

if __name__=='__main__':
    assert not (WORK/'build.json').exists()
    records=[]
    common=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pthread']
    records.append(execute(common+['-shared','-fPIC',LINUX+'/registration.c','-ldl',
                                  '-o',LINUX+'/libhalogen0172-hc6-register.so']))
    records.append(execute(common+[LINUX+'/test_registration.c','-ldl','-o',LINUX+'/test-registration']))
    def linux(path): return '/mnt/c/'+path.relative_to(Path('C:/')).as_posix()
    fixtures=[linux(PREP/'runtime-inventory/static-audit-data/usr/local/bin/flash_serve.data'),
              LINUX+'/installed-libamdhip64.so.7.data',linux(PREP/'hc6-register-remap-v1/candidate.hsaco')]
    cases=['off','unrelated','enabled','native-null','wrong-magic','wrong-version','wrong-dummy',
           'wrong-binary','wrong-bundle','wrong-engine-file','wrong-runtime-file','wrong-runtime-inode','wrong-load-range']
    for case in cases:
        result=execute([LINUX+'/test-registration',case]+fixtures)
        assert 'PASS '+case in result['stdout']
        records.append(result)
    symbols=execute(['nm','-D','--defined-only',LINUX+'/libhalogen0172-hc6-register.so'])
    assert '__hipRegisterFatBinary' in symbols['stdout']
    assert 'hipLaunchKernel' not in symbols['stdout'] and 'hipModuleLaunchKernel' not in symbols['stdout']
    records.append(symbols)
    receipt=dict(utc=datetime.now(timezone.utc).isoformat(),returncode=0,CPU_only=True,
                 HIP_initialized=False,mock_passed=True,mock_cases=cases,records=records,
                 files=[ref(name) for name in ('registration.c','test_registration.c','libhalogen0172-hc6-register.so','register-launch.sh')])
    (WORK/'build.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(returncode=0,CPU_only=True,HIP_initialized=False,mock_passed=True,mock_cases=len(cases),files=receipt['files'])))
