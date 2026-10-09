"""Pin passive dataflow evidence and build with Windows LLVM only.

Never invokes WSL, upstream ELF, a device runtime, or a live patch.
"""
from pathlib import Path
import ctypes, hashlib, json, random, struct, subprocess, sys
OUT=Path(__file__).resolve().parent
PREP=OUT.parent
sys.path.insert(0,str(PREP/'static-compatibility-audit'))
from passive_elf_review import Elf
ENGINE=PREP/'updates-20261009-0202/runtime-data/usr/local/bin/flash_serve.data'
PROVIDER=PREP.parent/'rocr-base-image-libs/libstdc++.so.6'
BIN=Path('C:/AI/runtimes/ironenv/Lib/site-packages/llvm-aie/bin')
ENGINE_SHA='af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7'
PROVIDER_SHA='972bb2a18b71140dab0240f8a1f68ab3fb1d56bcd4c4f824a91b70888faf5a00'
spans=[('prefill_start',0x1746b31,0x1746b44),('prefill_end',0x1746f11,0x1746f48),
       ('decode_start',0x17490a3,0x17490c2),('decode_end',0x174c9fa,0x174ca31),
       ('move_ctor_id',0x1747c4b,0x1747c51),('move_ctor_scalar',0x1747f1d,0x1747f35),
       ('move_assign_id',0x174a0fb,0x174a101),('move_assign_scalar',0x174a603,0x174a61b),
       ('stack_insertion',0x173d711,0x173d726),('vector_handle',0x172ed03,0x172ed13),
       ('heap_element',0x1745e64,0x1745e7b),('formatter_argument',0x1745f6a,0x1745f75),
       ('formatter_call',0x1746202,0x1746213),('formatter_request_id',0x174c9c4,0x174c9d2),
       ('formatter_native_start',0x174c9fa,0x174ca01)]
def sha(b):return hashlib.sha256(b).hexdigest()
def run(command,name):
    result=subprocess.run([str(x) for x in command],capture_output=True,timeout=60,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (OUT/(name+'.stdout')).write_bytes(result.stdout)
    (OUT/(name+'.stderr')).write_bytes(result.stderr)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    return dict(command=[str(x) for x in command],exit_code=result.returncode)
def main():
    b=ENGINE.read_bytes();p=PROVIDER.read_bytes()
    assert sha(b)==ENGINE_SHA and sha(p)==PROVIDER_SHA
    elf=Elf(b);rows=[];header=['/* Generated only from pinned passive ELF data. */',
       '#define HGN_ENGINE_SHA_HEX "'+ENGINE_SHA+'"',
       '#define HGN_PROVIDER_SHA_HEX "'+PROVIDER_SHA+'"',
       '#define HGN_ENGINE_BYTES '+str(len(b))+'ULL']
    for name,begin,end in spans:
        offset=elf.offset(begin,end-begin);blob=b[offset:offset+end-begin]
        f=elf.unwind_range(begin)
        rows.append(dict(name=name,rva=hex(begin),file_offset=hex(offset),bytes=len(blob),
            instruction_bytes_hex=blob.hex(),window_sha256=sha(blob),function=f,
            function_sha256=sha(b[f['start_file_offset']:f['end_file_offset_exclusive']])))
        header.append('static const h_u8 hgn_'+name+'[]={'+','.join(hex(x) for x in blob)+'};')
    header+=['struct hgn_pin { unsigned long rva; unsigned size; const h_u8 *bytes; };',
        'static const struct hgn_pin hgn_pins[]={'+','.join('{'+row['rva']+'UL,sizeof(hgn_'+row['name']+'),hgn_'+row['name']+'}' for row in rows)+'};',
        '#define HGN_PIN_COUNT (sizeof(hgn_pins)/sizeof(hgn_pins[0]))']
    for name,blob in [('engine_sha',bytes.fromhex(ENGINE_SHA)),('provider_sha',bytes.fromhex(PROVIDER_SHA)),('provider_code',p[0xd5490:0xd54b7])]:
        header.append('static const h_u8 hgn_'+name+'[]={'+','.join(hex(x) for x in blob)+'};')
    (OUT/'phase_clock_pins.h').write_text('\n'.join(header)+'\n')
    manifest=dict(schema='halogen0173.phase-clock-static-pins.v2',engine=str(ENGINE),
        engine_sha256=ENGINE_SHA,engine_bytes=len(b),provider_reference=str(PROVIDER),
        provider_sha256=PROVIDER_SHA,provider_bytes=len(p),
        provider_symbol_rva='0xd5490',provider_symbol_bytes_hex=p[0xd5490:0xd54b7].hex(),
        phase_windows=rows,upstream_executed=False,devices_used=False)
    (OUT/'static-pins.json').write_text(json.dumps(manifest,indent=2)+'\n')
    receipt=dict(schema='halogen0173.phase-clock-cpu-build.v2',builds=[],
        wsl_invoked=False,upstream_executed=False,gpu_npu_used=False,engine_runtime_qualified=False)
    flags=['--target=x86_64-unknown-linux-gnu','-O2','-std=c11','-Wall','-Wextra','-Werror',
        '-fPIC','-ffreestanding','-fno-builtin','-fno-stack-protector','-fvisibility=hidden',
        '-mno-avx','-mno-avx2','-mno-avx512f']
    receipt['builds'].append(run([BIN/'clang.exe',*flags,'-c',OUT/'phase_clock.c','-o',OUT/'phase_clock.o'],'linux-compile'))
    receipt['builds'].append(run([BIN/'clang.exe','--target=x86_64-unknown-linux-gnu','-fPIC','-c',OUT/'phase_clock_entry.S','-o',OUT/'phase_clock_entry.o'],'linux-entry'))
    receipt['builds'].append(run([BIN/'ld.lld.exe','-shared','-z','relro','-z','now','-z','noexecstack',
        '--version-script='+str(OUT/'phase_clock.map'),OUT/'phase_clock.o',OUT/'phase_clock_entry.o',
        '-o',OUT/'libhalogen0173_phase_clock.so'],'linux-link'))
    library=OUT/'libhalogen0173_phase_clock.so';assert library.read_bytes()[:7]==b'\x7fELF\x02\x01\x01'
    receipt['adapter_sha256']=sha(library.read_bytes());receipt['adapter_bytes']=library.stat().st_size
    # This Windows DLL contains only the numeric core and SHA routines, not the
    # Linux adapter, provider, engine, or any accelerator integration.
    test_source='''#include "phase_clock_core.h"
__declspec(dllexport) int test_delta(h_i64 n,h_u64 s,h_u64 e,h_i64 expected,h_i64 *out) { return hgn_phase_delta(n,s,e,expected,out); }
__declspec(dllexport) unsigned test_lookup(const struct h_pair *p,unsigned count,unsigned phase,h_u64 key,h_u64 stack,h_i64 tid,h_i64 request_id,unsigned *free_slot,unsigned *matches) { return hgn_pair_lookup(p,count,phase,key,stack,tid,request_id,free_slot,matches); }
__declspec(dllexport) void test_sha(const h_u8 *b,h_u64 size,h_u64 split,h_u8 *out) { struct hgn_sha256 s;hgn_sha_init(&s);hgn_sha_update(&s,b,split);hgn_sha_update(&s,b+split,size-split);hgn_sha_final(&s,out); }
'''
    (OUT/'core_host_test.c').write_text(test_source)
    receipt['builds'].append(run([BIN/'clang.exe','--target=x86_64-pc-windows-msvc','-O2','-ffreestanding','-fno-builtin','-fno-stack-protector','-c',OUT/'core_host_test.c','-o',OUT/'core_host_test.obj'],'host-core-compile'))
    receipt['builds'].append(run([BIN/'lld-link.exe','/dll','/noentry','/nodefaultlib','/out:'+str(OUT/'core_host_test.dll'),OUT/'core_host_test.obj'],'host-core-link'))
    dll=ctypes.CDLL(str(OUT/'core_host_test.dll'))
    dll.test_sha.argtypes=[ctypes.c_void_p,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_void_p]
    dll.test_delta.argtypes=[ctypes.c_int64,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_int64,ctypes.POINTER(ctypes.c_int64)]
    class Pair(ctypes.Structure):
        _fields_=[('key',ctypes.c_uint64),('stack',ctypes.c_uint64),('tid',ctypes.c_int64),
            ('native_start',ctypes.c_int64),('request_id',ctypes.c_int64),('raw_start',ctypes.c_uint64),
            ('pair_id',ctypes.c_uint64),('phase',ctypes.c_uint),('valid',ctypes.c_uint)]
    dll.test_lookup.argtypes=[ctypes.POINTER(Pair),ctypes.c_uint,ctypes.c_uint,ctypes.c_uint64,
        ctypes.c_uint64,ctypes.c_int64,ctypes.c_int64,ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_uint)]
    dll.test_lookup.restype=ctypes.c_uint
    def lookup(table,phase,key,stack,tid,rid):
        free_slot,matches=ctypes.c_uint(999),ctypes.c_uint(999)
        found=dll.test_lookup(table,len(table),phase,key,stack,tid,rid,ctypes.byref(free_slot),ctypes.byref(matches))
        return found,free_slot.value,matches.value
    table=(Pair*4)()
    table[0]=Pair(0x1000,0x2000,17,777,-17,123,1,2,1)
    assert lookup(table,2,0x5000,0x6000,18,-17)==(0,1,1)
    assert lookup(table,2,0x1000,0x2000,17,-18)==(4,1,0)
    table[1]=Pair(0x9999,0x8888,99,777,-17,123,2,2,1)
    assert lookup(table,2,0x5000,0x6000,18,-17)==(0,2,2)
    table[1].valid=0;table[0].phase=1
    assert lookup(table,1,0x1000,0x2000,17,-17)==(0,1,1)
    assert lookup(table,1,0x5000,0x2000,17,-17)==(4,1,0)
    assert lookup(table,1,0x1000,0x3000,17,-17)==(4,1,0)
    assert lookup(table,1,0x1000,0x2000,18,-17)==(4,1,0)
    randomizer=random.Random(173)
    vector_bytes=[b'',b'abc',b'a'*1000000]+[randomizer.randbytes(n) for n in [1,55,56,63,64,65,127,128,8192]]
    tests=0
    for vector in vector_bytes:
        expected=hashlib.sha256(vector).digest()
        for split in sorted({0,len(vector),len(vector)//2,min(63,len(vector)),min(64,len(vector))}):
            output=ctypes.create_string_buffer(32);dll.test_sha(vector,len(vector),split,output)
            assert output.raw==expected,(len(vector),split);tests+=1
    # Independent integer equations, large absolute clock offsets and rejects.
    success=0
    for _ in range(1000):
        n=randomizer.randrange(0,8_000_000_000_000_000_000)
        start=randomizer.randrange(0,8_000_000_000_000_000_000)
        delta=randomizer.randrange(0,1_000_000_000_000)
        output=ctypes.c_int64(-123)
        assert dll.test_delta(n,start,start+delta,n,ctypes.byref(output))==1
        assert output.value-n==delta;success+=1
    for n,s,e,expected in [(-1,1,2,-1),(1,2,1,1),(1,1,2,2),((1<<63)-1,1,2,(1<<63)-1),(0,0,(1<<64)-1,0)]:
        output=ctypes.c_int64(717)
        assert dll.test_delta(n,s,e,expected,ctypes.byref(output))==0 and output.value==717
    receipt['host_core_tests']=dict(sha_vectors=tests,phase_precision_vectors=success,rejected_invalid_pairs=5,
        pairing_identity_cases=7,only_numeric_host_dll_loaded=True,linux_adapter_loaded=False)
    receipt['source_pins']={x.name:sha(x.read_bytes()) for x in [OUT/'phase_clock.c',OUT/'phase_clock_core.h',OUT/'phase_clock_entry.S',OUT/'phase_clock.map',OUT/'phase_clock_pins.h']}
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['builds','source_pins']}))
if __name__=='__main__':main()
