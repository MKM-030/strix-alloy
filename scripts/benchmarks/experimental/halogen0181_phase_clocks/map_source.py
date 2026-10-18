"""Host-only current-version phase map. Reads ELF; executes Windows objdump only.

No Linux code is loaded. Generates evidence under this directory only.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import struct
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREP = ROOT/'server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008'
EXTRACT = PREP/'halogen0180-normal-bridge-preparation-20261011/halogen0181-extracted-20261012'
ENGINE = EXTRACT/'flash_serve'
ENGINE_SHA = 'd946e7b32a46400884ee7309b909da73f4a6586140cd9f9b94fa9ff583b3c3ab'
PROVIDER_SHA = '972bb2a18b71140dab0240f8a1f68ab3fb1d56bcd4c4f824a91b70888faf5a00'
IMAGE = 'ghcr.io/peonist-ai/halogen-flash-server@sha256:f0b39c8908f9897f27ab0a64e964c775e136a7cf7a1bafeb4de0c6d5d1e07e29'
LLVM = Path('C:/AI/runtimes/ironenv/Lib/site-packages/llvm-aie/bin/llvm-objdump.exe')
FUNCTION_STARTS = [0x17fdc40,0x18161a0,0x18171a0,0x1817730,0x18186f0,0x1819950,0x181b7c0,0x181e750]
SPANS = [
 ('prefill_start',0x1818701,0x1818714), ('prefill_end',0x1818d5b,0x1818d95),
 ('prefill_progress_native_start',0x18188b5,0x18188c8),
 ('decode_start',0x181a8c4,0x181a8e3), ('decode_end',0x181e7aa,0x181e7e9),
 ('formatter_request_id',0x181e771,0x181e782), ('formatter_native_start',0x181e7aa,0x181e7b1),
 ('formatter_counts_and_prefill',0x181e78a,0x181e7aa),
 ('move_ctor_id',0x18171ab,0x18171b1), ('move_ctor_counts',0x1817203,0x181720b),
 ('move_ctor_scalar',0x18174c9,0x18174e1), ('move_assign_id',0x181b7cb,0x181b7d1),
 ('move_assign_counts',0x181b873,0x181b87c), ('move_assign_scalar',0x181bd3e,0x181bd56),
 ('append_and_growth',0x1817730,0x181785c),
 ('stack_insertion_session',0x1800652,0x180066a), ('stack_insertion',0x180c6ff,0x180c714),
 ('stack_insertion_alternate',0x180ea2d,0x180ea42), ('vector_handle',0x17fdf0e,0x17fdf1e),
 ('heap_element',0x18161b6,0x18161cd), ('formatter_call',0x181655e,0x1816572),
 ('prefill_to_request_primary',0x180e0ab,0x180e0d1),
 ('prefill_to_request_alternate',0x180e212,0x180e23b),
 ('prefill_to_request_later',0x180c4fd,0x180c528),
 ('formatter_D_literal',0x181e8dd,0x181e8e4), ('formatter_snprintf',0x181e977,0x181e97c),
]


def sha(data):
 return hashlib.sha256(data).hexdigest()


def main():
 data = ENGINE.read_bytes()
 assert len(data)==27096728 and sha(data)==ENGINE_SHA
 assert sha(LLVM.read_bytes())=='feaaf3874824cd550505b9be47ab6519240301f0ea80562d2c9720fc98fef5d1'
 parser = PREP/'static-compatibility-audit/passive_elf_review.py'
 assert sha(parser.read_bytes())=='671297d02e798107827e5b51def19a288479a8c733c41b2221854bc96af9eddd'
 spec=importlib.util.spec_from_file_location('phase_elf_parser',parser)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 elf=module.Elf(data);evidence=HERE/'evidence';evidence.mkdir(exist_ok=True)
 functions=[];decoded={}
 for start in FUNCTION_STARTS:
  f=elf.unwind_range(start);assert f['start_rva']==start and f['bytes']<=128*1024
  cmd=[str(LLVM),'--disassemble','--x86-asm-syntax=intel','--start-address='+hex(start),'--stop-address='+hex(f['end_rva_exclusive']),str(ENGINE)]
  run=subprocess.run(cmd,capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
  assert run.returncode==0,run.stderr
  path=evidence/('function-'+format(start,'x')+'.txt')
  path.write_text(run.stdout,encoding='utf-8')
  rows=module.parse_disassembly(path,elf,f)
  decoded[start]={r['address']:r for r in rows}
  functions.append(dict(**f,sha256=sha(data[f['start_file_offset']:f['end_file_offset_exclusive']]),
                        disassembly_path=str(path.relative_to(HERE)),disassembly_sha256=sha(path.read_bytes())))
 windows=[]
 for name,start,end in SPANS:
  f=elf.unwind_range(start);rows=decoded[f['start_rva']];assert start in rows
  cursor=start
  while cursor<end:
   assert cursor in rows;cursor+=len(rows[cursor]['raw'])
  assert cursor==end
  off=elf.offset(start,end-start);blob=data[off:off+end-start]
  windows.append(dict(name=name,rva=hex(start),end_rva_exclusive=hex(end),file_offset=hex(off),
                      bytes=len(blob),instruction_bytes_hex=blob.hex(),sha256=sha(blob),function_start=hex(f['start_rva'])))
 plt=0x19d1fc0;blob=data[elf.offset(plt,16):elf.offset(plt,16)+16]
 assert blob.hex()=='ff254a7700006830000000e9e0fcffff'
 got=plt+6+struct.unpack_from('<i',blob,2)[0]
 assert elf.relocation_names()[got]==dict(symbol='_ZNSt6chrono3_V212steady_clock3nowEv',relocation_type=7,addend=0)
 assert struct.unpack_from('<d',data,elf.offset(0x13df0,8))[0]==1000000.0
 cpu=json.loads((EXTRACT/'cpu-provider/stdout.json').read_bytes());receipt=json.loads((EXTRACT/'cpu-provider/receipt.json').read_bytes())
 assert receipt['image']==IMAGE and receipt['completed'] and receipt['owned_container_closed_removed']
 assert not receipt['engine_started'] and not receipt['model_access'] and not receipt['GPU_NPU_access']
 assert not cpu['GPU_devices_present'] and not cpu['GPU_calls'] and not cpu['NPU_calls'] and not cpu['engine_started']
 chrono=[v for v in cpu['providers'] if v['file']['sha256']==PROVIDER_SHA]
 assert len(chrono)==1 and chrono[0]['file']['bytes']==2497768
 assert chrono[0]['symbols']==[dict(name='_ZNSt6chrono3_V212steady_clock3nowEv',
   provider='/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.33',symbol='_ZNSt6chrono3_V212steady_clock3nowEv')]
 provider=EXTRACT/'cpu-provider/files/libstdc++.so.6.0.33'
 p=provider.read_bytes();assert len(p)==2497768 and sha(p)==PROVIDER_SHA
 pe=module.Elf(p);code=p[pe.offset(0xd5490,39):pe.offset(0xd5490,39)+39]
 assert code.hex()=='f30f1efa4883ec18bf010000004889e6e8eb83fcff4869042400ca9a3b48034424084883c418c3'
 # Preserve the complete root-produced provider receipt, including chrono
 # dladdr result, rather than manufacturing a live engine binding.
 record=dict(schema='halogen0181.phase-static-map.v1',engine_sha256=ENGINE_SHA,engine_bytes=len(data),image=IMAGE,
  functions=functions,windows=windows,clock_plt_rva=hex(plt),clock_got_rva=hex(got),clock_symbol_version='GLIBCXX_3.4.19',
  millisecond_divisor_rva='0x13df0',millisecond_divisor=1000000.0,D_literal_rva='0x15067',
  field_contract=dict(signed_request_id=0,prompt_count=0x54,predicted_count=0x58,prefill_accumulator=0x458,
                      request_prefill_ms=0x1c0,request_decode_start_ns=0x1c8,request_stride=0x338,
                      scalar_move_begin=0x1b8,scalar_move_end=0x239,request_stack_base=0xae0,prefill_stack_store=0xca0),
  phase_calls=dict(prefill_begin=0x181870a,prefill_end=0x1818d5b,decode_begin=0x181a8d7,decode_end=0x181e7bd),
  phase_returns=dict(prefill_begin=0x181870f,prefill_end=0x1818d60,decode_begin=0x181a8dc,decode_end=0x181e7c2),
  provider_sha256=PROVIDER_SHA,provider_bytes=len(p),provider_symbol_rva='0xd5490',provider_code_hex=code.hex(),
  cpu_provider_receipt_sha256=sha((EXTRACT/'cpu-provider/receipt.json').read_bytes()),
  cpu_provider_stdout_sha256=sha((EXTRACT/'cpu-provider/stdout.json').read_bytes()),
  cpu_provider_receipt=receipt,cpu_provider_stdout=cpu,
  current_image_cpu_provider_bytes_verified=True,live_engine_provider_binding_verified=False,
  upstream_executed=False,hardware_accessed=False,phase_clock_qualified=False)
 (HERE/'static-map.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
 lines=['/* Generated from independently decoded exact0.18.1 ELF. */',
 '#define HGN_ENGINE_SHA_HEX "'+ENGINE_SHA+'"','#define HGN_PROVIDER_SHA_HEX "'+PROVIDER_SHA+'"',
 '#define HGN_ENGINE_BYTES 27096728ULL']
 for w in windows:
  lines.append('static const h_u8 hgn_'+w['name']+'[]={'+','.join(hex(x) for x in bytes.fromhex(w['instruction_bytes_hex']))+'};')
 lines+=['struct hgn_pin { unsigned long rva; unsigned size; const h_u8 *bytes; };',
 'static const struct hgn_pin hgn_pins[]={'+','.join('{'+w['rva']+'UL,sizeof(hgn_'+w['name']+'),hgn_'+w['name']+'}' for w in windows)+'};',
 '#define HGN_PIN_COUNT (sizeof(hgn_pins)/sizeof(hgn_pins[0]))']
 for name,v in [('engine_sha',bytes.fromhex(ENGINE_SHA)),('provider_sha',bytes.fromhex(PROVIDER_SHA)),('provider_code',code)]:
  lines.append('static const h_u8 hgn_'+name+'[]={'+','.join(hex(x) for x in v)+'};')
 (HERE/'phase_clock_pins.h').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps(dict(functions=len(functions),windows=len(windows),native_phase_clock_qualified=False,
                       engine_sha256=ENGINE_SHA,static_map_sha256=sha((HERE/'static-map.json').read_bytes()))))


if __name__=='__main__':main()
