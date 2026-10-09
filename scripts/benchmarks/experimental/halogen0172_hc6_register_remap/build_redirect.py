"""Root-owned CPU build of the default-off native HC6 redirect; no HIP."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

WORK = Path(__file__).resolve().parent
ROOT = WORK.parent.parents[3]

def ref(path):
    return dict(path=str(path), bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest())

if __name__ == '__main__':
    source = WORK / 'redirect.c'
    library = WORK / 'libhalogen0172-hc6-remap.so'
    assert source.is_file() and not library.exists()
    linux = '/mnt/c/' + WORK.relative_to(Path('C:/')).as_posix()
    command = ['wsl.exe','-d','Ubuntu-24.04','-u','revn','--exec','gcc','-std=c11','-O2',
        '-shared','-fPIC','-Wall','-Wextra','-Werror','-pthread',linux+'/redirect.c',
        '-ldl','-o',linux+'/libhalogen0172-hc6-remap.so']
    result = subprocess.run(command,capture_output=True,text=True,timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW)
    receipt = dict(utc=datetime.now(timezone.utc).isoformat(), command=command,
        returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
        source=ref(source), library=ref(library) if library.exists() else None,
        wrapper_sha256=hashlib.sha256((WORK/'hc6-launch.sh').read_bytes()).hexdigest(),
        candidate=ref(WORK/'candidate.hsaco'), CPU_only=True, HIP_initialized=False)
    (WORK/'build.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    assert result.returncode == 0, result.stderr
    print(json.dumps(receipt))
