"""Pinned passive review plus bounded WSL CPU compilation/harness only.

No Halogen ELF execution, engine/API call, HIP resolution, accelerator access,
container/service/lifecycle mutation or source write outside this private folder.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

WORK = Path(__file__).resolve().parent
PREP = WORK.parent
ELF = PREP / 'updates-20261009-0202/runtime-data/usr/local/bin/flash_serve.data'
TEXT = PREP / 'native0173-phase-clock-20261009/current-text.txt'
ELF_SHA = 'af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7'
TEXT_SHA = '1c7ace3b584ec57139b052413381522a414c6d012d93da237dc4d5942f8a7f73'
PARSER_SHA = '671297d02e798107827e5b51def19a288479a8c733c41b2221854bc96af9eddd'
RETAINED_SHA = '585d56a6c787bf9ec0c3426be4e93ffb13747b2d475cf7a85232f2473f3b0226'
RETIREMENT_CASES = [
    'pending holder destruction during an in-flight copy',
    'normal materialized holder destruction during transfer stays exempt',
    'materialized record abandonment during transfer retains no native IDs',
    'Request destruction during a fence query blocks feature publication',
    'decode retirement during a copy records its fence and drains',
    'retained Lane contention defers pending retirement and rejects foreign bindings',
    'retained Lane contention defers Request retirement through an outstanding borrow',
    'retained Lane contention defers exact materialized-record abandonment',
    'pending destruction stays cancellation when materialization progresses',
    'Request destruction under the owner lock preserves an existing borrow',
    'foreign holder Request wire and full prompt IDs cannot queue retirement',
    'decode retired staging stays borrowed until exact release',
    'decode stale and foreign generations leave current capture intact',
    'decode retirement during polling blocks feature publication',
    'decode retirement during admission rejects the new capture',
    'rejected foreign generation preserves admitted round10 and rejects its replay',
]
SITES = {
    'PendingPublication': (0x173CC3D, '48 8b 44 24 08'),
    'InitialFlagJoin': (0x173CC71, '48 8b b0 80 01 00 00'),
    'ChunkFlagJoin': (0x1746C96, '49 8d 86 28 03 00 00'),
    'ChunkForward': (0x1746EDB, 'e8 00 ec 0b 00'),
    'ChunkForwardReturned': (0x1746EE0, '45 03 ae 10 04 00 00'),
    'RecordMaterialize': (0x1747C40, '41 57'),
    'PendingDestructor': (0x174CF00, '48 85 ff'),
    'SuccessfulBirthA': (0x1732C7E, '48 8d bc 24 d0 01 00 00'),
    'SuccessfulBirthB': (0x173D711, '48 8d bc 24 d0 01 00 00'),
    'RequestDestructor': (0x1770630, '41 57'),
    'RecordDestructor': (0x17466E0, '41 57'),
    'HC': (0x17F22C4, '49 8b 86 e0 05 00 00'),
    'VerifyBegin': (0x173FE32, 'e8 a9 a2 0b 00'),
    'VerifyReturned': (0x173FE37, '4c 8b bb 08 01 00 00'),
    'CommitBegin': (0x173FEA0, 'e8 bb c4 0b 00'),
    'CommitReturned': (0x173FEA5, '48 8b 44 24 10'),
    'ScalarBegin': (0x1740488, 'e8 53 56 0c 00'),
    'ScalarReturned': (0x174048D, 'c7 84 24 00 0a 00 00 00 00 00 00'),
    'CommonOutcome': (0x17411FB, '83 f8 fe'),
}
SPANS = {
    'prefill_generation_assignments_and_actual_cache_branch': (0x173CC3D, 0x173CC94),
    'record_move_then_holder_destructor_before_birth': (0x173D39D, 0x173D3DC),
    'chunk_native_inputs_absolute_position_and_return': (0x1746EB8, 0x1746EF8),
    'ordinary_HC_to_common_capture': (0x17F22AA, 0x17F22D0),
    'profiled_HC_to_common_capture': (0x17F2630, 0x17F268F),
    'FFN_reuses_HC_helper': (0x17F2440, 0x17F2451),
    'authoritative_commit_count': (0x173FE8D, 0x173FEA5),
    'unconstrained_scalar_forward': (0x1740479, 0x174048D),
}
SOURCES = ('pending_owner.h','pending_owner.cpp','hip_copy_backend.h','hip_copy_backend.cpp',
           'native_adapter.h','native_adapter.cpp','decode_capture.h','decode_capture.cpp',
           'native_decode_adapter.h','native_decode_adapter.cpp','retained_lease_bridge.h','pending_owner_cpu_test.cpp')

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def run(argv: list[str], label: str) -> dict:
    result = subprocess.run(argv,cwd=WORK,capture_output=True,text=True,timeout=60)
    (WORK/(label+'.stdout')).write_text(result.stdout,encoding='utf-8')
    (WORK/(label+'.stderr')).write_text(result.stderr,encoding='utf-8')
    return dict(argv=argv,exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)

def main() -> None:
    blob,text_bytes = ELF.read_bytes(),TEXT.read_bytes()
    assert sha(blob)==ELF_SHA and len(blob)==26188824,'Runtime pin changed'
    assert sha(text_bytes)==TEXT_SHA,'Disassembly pin changed'
    parser=PREP/'static-compatibility-audit/passive_elf_review.py'
    parser_bytes=parser.read_bytes();assert sha(parser_bytes)==PARSER_SHA,'Passive parser pin changed'
    classes=[n for n in ast.parse(parser_bytes).body if isinstance(n,ast.ClassDef) and n.name=='Elf']
    assert len(classes)==1
    ns={'struct':struct};exec(compile(ast.Module(body=classes,type_ignores=[]),'passive_Elf_only','exec'),ns)
    elf=ns['Elf'](blob)
    pattern=re.compile(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} ){0,14}[0-9a-f]{2})\s+(.+)$')
    instructions={int(m[1],16):(bytes.fromhex(m[2]),m[3],line) for line in text_bytes.decode().splitlines() if (m:=pattern.match(line))}
    hooks={}
    for name,(address,expected) in SITES.items():
        raw,assembly,_=instructions[address];assert raw==bytes.fromhex(expected),(name,raw.hex())
        off=elf.offset(address,len(raw));assert blob[off:off+len(raw)]==raw,name
        hooks[name]=dict(rva=hex(address),first_instruction_bytes=raw.hex(' '),assembly=assembly,
                         containing_native_fde=elf.unwind_range(address))
    evidence=[];checked=0
    for name,(start,end) in SPANS.items():
        evidence.append(f'\n[{name}]\n');cursor=start
        for address,(raw,_,line) in instructions.items():
            if not start<=address<end:continue
            assert address==cursor,(name,hex(cursor),hex(address))
            off=elf.offset(address,len(raw));assert blob[off:off+len(raw)]==raw
            cursor+=len(raw);checked+=1;evidence.append(line+'\n')
        assert cursor==end,(name,hex(cursor),hex(end))
    (WORK/'native-capture-spans.txt').write_text(''.join(evidence),encoding='utf-8')
    retained=PREP/'dflash-retained-controller-20261009/retained_controller.h'
    retained_sha=sha(retained.read_bytes())
    assert retained_sha==RETAINED_SHA,'Frozen controller header pin changed'
    compiler=['wsl.exe','-d','Ubuntu-24.04','--exec','g++','-std=c++20','-O2','-Wall','-Wextra','-Werror','-pthread']
    units=['pending_owner.cpp','hip_copy_backend.cpp','native_adapter.cpp','decode_capture.cpp','native_decode_adapter.cpp']
    build=run(compiler+units+['pending_owner_cpu_test.cpp','-o','pending-owner-cpu-test'],'cpu-build')
    assert build['exit_code']==0,build['stderr']
    test=run(['wsl.exe','-d','Ubuntu-24.04','--exec','./pending-owner-cpu-test'],'cpu-harness')
    assert test['exit_code']==0,test['stderr']
    library=run(compiler+['-fPIC','-shared']+units+['-o','libdflash_prefill_capture_cpu.so'],'component-build')
    assert library['exit_code']==0,library['stderr']
    assert sha(retained.read_bytes())==retained_sha,'Controller header changed during qualification; rerun after its source settles'
    receipt=dict(schema='halogen0173.dflash.owned-prefill-capture.v1',runtime_sha256=ELF_SHA,
        disassembly_sha256=TEXT_SHA,passive_parser_sha256=PARSER_SHA,passive_instruction_checks=checked,
        hook_sites=hooks,sources={name:sha((WORK/name).read_bytes()) for name in SOURCES},
        retained_controller_header_sha256=retained_sha,
        build=build,harness=test,component_build=library,
        harness_sha256=sha((WORK/'pending-owner-cpu-test').read_bytes()),
        component_sha256=sha((WORK/'libdflash_prefill_capture_cpu.so').read_bytes()),
        default_off=True,cpu_component_source_complete=True,portable_component_built=True,
        installed_native_relays=False,live_capture_exporter_complete=False,
        pending_ticket_states=['Pending','Materialized','Request','Retired'],
        deferred_retirement=dict(generation_bound=True,native_id_pointers_retained=False,
            lease_retirement_acknowledged=True,drained_on_successful_entry_and_exit=True,
            exact_binding_retained_until_ack=True,normal_materialized_holder_exemption=True,
            staging_retained_through_fences_and_borrows=True,focused_cpu_cases=RETIREMENT_CASES,
            rejected_admission_preserves_round_history=True,identity_readers_closed_before_reclamation=True,
            decode_generation_upper_bound_exclusive=2**63),
        capture_layout=dict(dtype='native_BF16',trained_taps=[3,15,23,35,43],native_boundaries=[4,16,24,36,44],
            row_shape=[12800],row_bytes=25600,prefill_positions='0..total-1',decode_positions='anchor..anchor+k-1',
            decode_slots=8,verification_rows=4,scalar_rows=1,
            publication='native committed k input rows only after complete continuing native output',
            next_current='unprocessed correction/bonus, no hidden row'),
        wsl_cpu_only=True,native_elf_executed=False,hardware_initialized=False,api_requests=0,
        model_downloads=0,lifecycle_mutations=0,all_writes_confined_to=str(WORK))
    (WORK/'cpu-source-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    seal_files=list(SOURCES)+['README.md','qualify_cpu.py','native-capture-spans.txt','cpu-source-receipt.json','pending-owner-cpu-test','libdflash_prefill_capture_cpu.so']
    seal=dict(schema='halogen0173.dflash.prefill-owner-seal.v1',files={name:sha((WORK/name).read_bytes()) for name in seal_files},
              retained_controller_header_sha256=retained_sha,default_off=True,source_only_offline_cpu=True)
    (WORK/'delivery-seal.json').write_text(json.dumps(seal,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:receipt[key] for key in ('schema','passive_instruction_checks','default_off','cpu_component_source_complete','portable_component_built')}))

if __name__=='__main__':
    main()
