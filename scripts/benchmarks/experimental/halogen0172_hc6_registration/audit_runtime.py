"""Bounded inert installed-runtime disassembly and original registration scope."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

WORK = Path(__file__).resolve().parent
PREP = WORK.parent
LIB = WORK/'installed-libamdhip64.so.7.data'
ENGINE = PREP/'runtime-inventory/static-audit-data/usr/local/bin/flash_serve.data'
PIN = '6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5'

def ref(path):
    return dict(path=str(path),bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def disassemble(path, start, end, name):
    linux = '/mnt/c/' + path.relative_to(Path('C:/')).as_posix()
    result = subprocess.run(['wsl.exe','-d','Ubuntu-24.04','-u','revn','--exec','objdump','-d',
                             '--start-address='+hex(start),'--stop-address='+hex(end),linux],
                            capture_output=True,text=True,timeout=60,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode==0,result.stderr
    out = WORK/name
    out.write_text(result.stdout,encoding='utf-8',newline='\n')
    return ref(out)

if __name__ == '__main__':
    assert ref(LIB)['sha256']==PIN and ref(LIB)['bytes']==28933697
    assert ref(ENGINE)['sha256']=='ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913'
    ranges=[('api-register',0x536820,0x5369c0),('dispatch-table',0x5358d0,0x535a10),
            ('native-register',0x470980,0x470ab0),('add-fatbinary',0x1b1f80,0x1b23e0),
            ('digest-fatbinary',0x1b1cc0,0x1b1f80),('remove-fatbinary',0x1b2840,0x1b2d50),
            ('api-unregister',0x537350,0x5374f0),('native-unregister',0x4717a0,0x4718a0)]
    saved=[disassemble(LIB,start,end,name+'.txt') for name,start,end in ranges]
    saved.append(disassemble(ENGINE,0x1876900,0x1876960,'engine-bundle0-lifecycle.txt'))
    saved.append(disassemble(ENGINE,0x1865e30,0x1876900,'engine-bundle0-function-registration.txt'))
    report=dict(utc=datetime.now(timezone.utc).isoformat(),library=ref(LIB),engine=ref(ENGINE),
                disassembly=saved,inert_only=True,runtime_initialized=False,revision_identity_asserted=False)
    (WORK/'runtime-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(files=len(saved),inert_only=True,runtime_initialized=False)))
