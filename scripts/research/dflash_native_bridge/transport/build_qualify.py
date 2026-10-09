"""Windows ordinary CPU tests only; never imports/resolves HIP or executes ELF."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
WORK=Path(__file__).resolve().parent
OWNER=WORK.parent/'dflash-prefill-owner-20261009'
CLANG='C:/Program Files/AMD/ROCm/7.2/bin/clang++.exe'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(argv):
    p=subprocess.run(argv,cwd=WORK,capture_output=True,text=True,timeout=60)
    print(json.dumps({'argv':argv,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr}))
    if p.returncode:raise RuntimeError(f'CPU qualification failed: {p.returncode}')
    return {'argv':argv,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
def main():
    commands=[]
    flags=['-std=c++20','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-exceptions','-fno-rtti','-fno-stack-protector','-nostdlib','-fuse-ld=lld','-Wl,/entry:main,/subsystem:console']
    commands.append(run([CLANG,*flags,'owned_transport.cpp',str(OWNER/'pending_owner.cpp'),str(OWNER/'decode_capture.cpp'),'transport_cpu_test.cpp','-o','transport-cpu-test.exe']))
    commands.append(run([str(WORK/'transport-cpu-test.exe')]))
    commands.append(run([CLANG,*flags,'owned_transport.cpp',str(OWNER/'pending_owner.cpp'),str(OWNER/'decode_capture.cpp'),'hip_backend_cpu_test.cpp','-o','hip-backend-cpu-test.exe']))
    commands.append(run([str(WORK/'hip-backend-cpu-test.exe')]))
    ordinary=['-std=c++20','-O2','-Wall','-Wextra','-Werror','-fno-builtin','-D_CRT_SECURE_NO_WARNINGS','-DTRANSPORT_ORDINARY_CRT=1']
    commands.append(run([CLANG,*ordinary,'owned_transport.cpp','worker_io.cpp',str(OWNER/'pending_owner.cpp'),str(OWNER/'decode_capture.cpp'),'wire_cpu_fixture.cpp','-o','wire-cpu-fixture.exe']))
    commands.append(run([str(WORK/'wire-cpu-fixture.exe')]))
    commands.append(run([sys.executable,'-B','reader_cpu_test.py']))
    commands.append(run([sys.executable,'-B','owned_reader.py']))
    files={p.name:sha(p) for p in sorted(WORK.iterdir()) if p.is_file() and p.suffix in {'.cpp','.h','.py','.exe','.md','.bin'}}
    dependencies={p.name:sha(p) for p in [OWNER/'pending_owner.h',OWNER/'pending_owner.cpp',OWNER/'decode_capture.h',OWNER/'decode_capture.cpp',OWNER/'delivery-seal.json']}
    receipt={'schema':'halogen0173.dflash.owned-transport-cpu.v1','commands':commands,'owner_dependencies':dependencies,'files':files,'hardware_initialized':False,'hip_runtime_loaded':False,'native_installed':False,'wsl_executed':False}
    (WORK/'qualification_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    seal={'schema':'halogen0173.dflash.owned-transport-delivery.v1','files':files,'owner_dependencies':dependencies,'qualification_receipt_sha256':sha(WORK/'qualification_receipt.json'),'default_off':True,'owned_copied_staging_only':True,'borrow_held_through_worker_d2h_fence':True,'failed_fence_retains_until_successful_worker_drain':True,'full_binding_and_sequence_ack':True,'cpu_fixtures_passed':True,'linux_compiled':False,'hip_loaded':False,'hardware_initialized':False,'provider_executed':False,'native_installed':False,'root_required':['Linux/runtime HIP qualification','Worker-owned cold resources and binary sink','Exact independent model/tokenizer/drafter ownership pins','Causal barrier and exact first native current/position outside ready lookup','Exact Ready publication and terminal retirement control','Actual numerical/serving/acceptance/latency qualification']}
    (WORK/'delivery_seal.json').write_text(json.dumps(seal,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'delivery_seal_sha256':sha(WORK/'delivery_seal.json'),'qualification_receipt_sha256':sha(WORK/'qualification_receipt.json')}))
if __name__=='__main__':main()
