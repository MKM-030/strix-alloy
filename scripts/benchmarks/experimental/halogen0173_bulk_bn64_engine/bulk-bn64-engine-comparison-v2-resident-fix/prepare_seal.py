"""Seal CPU-built adapter and normal sources without launching devices."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys

WORK=Path(__file__).resolve().parent
PREP=WORK.parent
ROOT=PREP.parents[3]
sys.path.insert(0,str(ROOT/'server'))
from controller import atomic
BACKEND=ROOT/'backends/halogen-wsl2-0.17.3'
CANDIDATE=PREP/'bulk-bn64-engine-candidate-v2-resident-fix'

def ref(path):
    return dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def main():
    import importlib.util
    spec=importlib.util.spec_from_file_location('candidate_launcher',WORK/'launch.py')
    launch=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    assert ref(launch.SOURCE)['sha256']==launch.SOURCE_SHA
    assert ref(launch.SO)['sha256']==launch.SO_SHA
    binary=launch.SO.read_bytes()
    assert binary[:6]==b'\x7fELF\x02\x01' and binary[16:20]==b'\x03\x00\x3e\x00'
    assert launch.SOURCE_SHA in launch.REVIEW.read_text(encoding='utf-8-sig')
    inventory=json.loads((BACKEND/'profiles/sources.json').read_text(encoding='utf-8'))
    inputs=[BACKEND/name for name,digest in inventory['files'].items()]
    for name,digest in inventory['files'].items():
        assert ref(BACKEND/name)['sha256']==digest,name
    inputs += [BACKEND/'profiles/sources.json',launch.PROFILE,launch.SOURCE,launch.SO,
        launch.REVIEW,CANDIDATE/'host-map.json',CANDIDATE/'README.md',
        CANDIDATE/'independent-resident-skip-review.md',
        PREP/'prefill-bulk-moe-retile-scope-20261009/host-route-proof-v1.activation64-exact.md']
    inputs += [ROOT/'server'/name for name in ('controller.py','gateway.py','owned_child.py','host_frames.py','winjob.py')]
    seal=dict(utc=datetime.now(timezone.utc).isoformat(),schema='halogen0173.bn64.engine-seal.v1',
        launch_sha256=ref(WORK/'launch.py')['sha256'],inputs=[ref(path) for path in inputs],
        adapter_source_sha256=launch.SOURCE_SHA,adapter_so_sha256=launch.SO_SHA,
        reviewed=True,root_cpu_build_exit_code=0,build_command=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fPIC','-shared','adapter.c','-ldl','-lpthread','-o','libbulk-bn64.so'],
        no_HIP_initialized_in_build=True,serving_gain_qualified=False)
    path=WORK/'seal.json'
    assert not path.exists(),'Retain existing seal; do not silently reseal a launched candidate'
    atomic(path,seal)
    launch.check_seal()
    print(json.dumps(dict(sealed=True,inputs=len(inputs),CPU_build_passed=True,devices_started=False)))

if __name__=='__main__': main()
