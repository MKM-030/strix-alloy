"""Bounded CPU-only native query/selected-HT source receipt; no engine execution."""
from pathlib import Path
import hashlib
import json
import re
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PREP = HERE.parent
ROOT = PREP.parents[3]
sys.path.insert(0, str(PREP / 'static-compatibility-audit'))
from passive_elf_review import Elf

ENGINE = PREP / 'runtime-inventory/static-audit-data/usr/local/bin/flash_serve.data'
TOOL = Path('C:/AI/sdk/therock1151-10.2.0a20260930/lib/llvm/bin/llvm-objdump.exe')
SHA = 'ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913'
TOOL_SHA = 'f51d8a61cd527b24eb33e844050755886e6a0556499df89e928675ce3105a2c2'
engine = ENGINE.read_bytes()
assert len(engine) == 26178504 and hashlib.sha256(engine).hexdigest() == SHA
assert hashlib.sha256(TOOL.read_bytes()).hexdigest() == TOOL_SHA
elf = Elf(engine)
plans = [
    ('mtp-query-call.txt', 0x17F1C68, 0x17F1CC2, [(0x17F1BF0, 0x17F1CC2)]),
    ('reduced-consumer.txt', 0x17F2080, None,
     [(0x17F2118, 0x17F2168), (0x17F2292, 0x17F2509)]),
    ('reduced-q4-arguments.txt', 0x17F4750, 0x17F6F1B,
     [(0x17F4750, 0x17F47BC), (0x17F47BC, 0x17F4821),
      (0x17F688D, 0x17F699E), (0x17F6EE7, 0x17F6F1B)]),
    ('native-selected-ht-contract.txt', 0x1814DC0, 0x1814F04,
     [(0x1814DC0, 0x1814F04)]),
    ('original-ht-caller.txt', 0x17E48F0, 0x17E4940,
     [(0x17E48F0,0x17E4940)]),
    ('native-ht-one-query.txt', 0x18266F0, 0x1828620,
     [(0x18266F0, 0x1826780), (0x1826970, 0x1826A3F),
      (0x1827304, 0x1827354), (0x1827D09, 0x1827E8F),
      (0x1828601, 0x1828620)]),
]
receipt = {'schema': 'halogen0172.mtp-native-query-source.v1',
           'engine_sha256': SHA, 'tool_sha256': TOOL_SHA,
           'engine_executed': False, 'hardware_access': False, 'host_excerpts': []}
for name, selected, stop, spans in plans:
    function = elf.unwind_range(selected)
    start = function['start_rva']
    stop = stop or function['end_rva_exclusive']
    assert start < stop <= function['end_rva_exclusive'] and stop-start <= 16384
    command = [str(TOOL), '--disassemble', '--x86-asm-syntax=intel',
               f'--start-address={hex(start)}', f'--stop-address={hex(stop)}', str(ENGINE)]
    result = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL,
                            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0 and not result.stderr and len(result.stdout) < 1024*1024
    ins = []
    for line in result.stdout.decode().splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)(.*?)\s*$', line)
        if not m:
            continue
        address, raw, asm = int(m[1], 16), bytes.fromhex(m[2]), m[3].strip()
        if asm:
            ins.append([address, raw, asm])
        else:
            assert ins and address == ins[-1][0]+len(ins[-1][1])
            ins[-1][1] += raw
    expected = start
    for address, raw, asm in ins:
        assert address == expected and 0 < len(raw) <= 15
        offset = elf.offset(address, len(raw))
        assert engine[offset:offset+len(raw)] == raw
        expected += len(raw)
    assert stop <= expected <= stop+14
    lines = [f'Pinned ELF SHA256 {SHA}', f'Unwind function {hex(start)}..{hex(function["end_rva_exclusive"])}',
             'Every decoded instruction byte verified; only bounded excerpts retained.', '']
    saved = []
    for lo, hi in spans:
        rows = [x for x in ins if lo <= x[0] < hi]
        assert rows
        lines += [f'EXCERPT {hex(rows[0][0])}..{hex(rows[-1][0]+len(rows[-1][1]))}']
        lines += [f'{address:08x}: {raw.hex(" "):44} {asm.split(" <")[0]}' for address, raw, asm in rows]
        lines += ['']
        saved.append({'start_rva': rows[0][0], 'end_rva_exclusive': rows[-1][0]+len(rows[-1][1]),
                      'code_sha256': hashlib.sha256(b''.join(x[1] for x in rows)).hexdigest()})
    payload = ('\n'.join(lines)+'\n').encode()
    (HERE/name).write_bytes(payload)
    receipt['host_excerpts'].append({'file': name, 'bytes': len(payload),
        'sha256': hashlib.sha256(payload).hexdigest(), 'function': function,
        'command': command, 'excerpts': saved})

# Only exact known descriptors are recovered; no new kernel inventory is created.
wanted = {0x18F5D78, 0x18F3BE8, 0x18F4E30}
fixed = bytes.fromhex('4889df4889ca41b8ffffffff4531c9')
cursor = 0
bindings = []
while (cursor := engine.find(fixed, cursor)) >= 0:
    begin = cursor-14
    raw = engine[begin:begin+46]
    cursor += len(fixed)
    if raw[:3] != bytes.fromhex('488d35') or raw[7:10] != bytes.fromhex('488d0d'):
        continue
    registration = elf.mapped(begin, 46, executable=True)['span_rva']
    descriptor = registration+7+struct.unpack_from('<i', raw, 3)[0]
    if descriptor not in wanted:
        continue
    if raw[29:37] == bytes.fromhex('6a006a006a006a00'):
        call = 37
    else:
        call = 29
    assert raw[call] == 0xe8 and registration+call+5+struct.unpack_from('<i',raw,call+1)[0] == 0x18F25C0
    string_rva = registration+14+struct.unpack_from('<i', raw, 10)[0]
    at = elf.offset(string_rva)
    name = engine[at:engine.index(b'\0',at,at+1024)].decode('ascii')
    bindings.append({'descriptor_rva': descriptor, 'registration_rva': registration,
                     'registration_bytes_hex': raw[:call+5].hex(), 'name_rva': string_rva, 'name': name})
assert {x['descriptor_rva'] for x in bindings} == wanted and len(bindings) == len(wanted)
receipt['exact_bindings'] = bindings

# Three exact bound device symbols; no device-kernel inventory is saved.
DEVICE = PREP/'ple0172-math-delta-audit/engine0172-gfx1151-bundle0.hsaco'
device = DEVICE.read_bytes()
device_sha = hashlib.sha256(device).hexdigest()
assert device_sha == '18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039'
section_at = struct.unpack_from('<Q',device,40)[0]
section_count = struct.unpack_from('<H',device,60)[0]
sections = [struct.unpack_from('<IIQQQQIIQQ',device,section_at+i*64) for i in range(section_count)]
device_plans = [
    ('native-ht-butterfly.device.txt', 0x18F4E30, 0x524600, 0x5267D8,
     [(0x524600,0x524740),(0x524794,0x5249C0),(0x5262F4,0x5267D8)]),
    ('native-q4-query-format.device.txt', 0x18F5D78, 0x73B600, 0x73BC4C,
     [(0x73B600,0x73BC4C)]),
    ('native-reduced-scatter.device.txt', 0x18F3BE8, 0x226800, 0x2268E8,
     [(0x226800,0x2268E8)]),
]
receipt['device_excerpts'] = []
for filename, descriptor, start, stop, spans in device_plans:
    bound = next(x for x in bindings if x['descriptor_rva'] == descriptor)
    exact = set()
    for section in sections:
        if section[1] not in (2,11):
            continue
        strings_section = sections[section[6]]
        strings = device[strings_section[4]:strings_section[4]+strings_section[5]]
        for at in range(section[4],section[4]+section[5],section[9]):
            ni,info,other,index,value,size = struct.unpack_from('<IBBHQQ',device,at)
            if strings[ni:strings.find(b'\0',ni)] == bound['name'].encode():
                exact.add((value,size,index))
    assert len(exact) == 1
    value,size,index = exact.pop()
    assert (value,value+size,index) == (start,stop,7)
    text_section = sections[index]
    va,offset,text_size = text_section[3:6]
    command = [str(TOOL),'--disassemble','--mcpu=gfx1151',f'--start-address={hex(start)}',
               f'--stop-address={hex(stop)}',str(DEVICE)]
    result = subprocess.run(command,capture_output=True,stdin=subprocess.DEVNULL,
                            timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0 and not result.stderr and len(result.stdout)<1024*1024
    rows = []
    decoded = start
    for line in result.stdout.decode().splitlines():
        m = re.search(r'//\s*([0-9a-fA-F]+):\s*((?:[0-9a-fA-F]{8}\s*)+)\s*(?:<.*)?$',line)
        if not m:
            continue
        address = int(m[1],16)
        raw = b''.join(struct.pack('<I',int(x,16)) for x in m[2].split())
        assert decoded == address and va<=address<address+len(raw)<=va+text_size
        assert device[offset+address-va:offset+address-va+len(raw)] == raw
        decoded += len(raw)
        if any(lo<=address<hi for lo,hi in spans):
            rows.append(line)
    assert decoded == stop and rows
    payload = (f'Device SHA256 {device_sha}\nExact symbol {bound["name"]}\n'
               f'Symbol {hex(start)}..{hex(stop)}; bounded windows only.\n'
               'Every decoded instruction word byte-checked.\n'+'\n'.join(rows)+'\n').encode()
    (HERE/filename).write_bytes(payload)
    receipt['device_excerpts'].append({'file':filename,'bytes':len(payload),
        'sha256':hashlib.sha256(payload).hexdigest(),'device_sha256':device_sha,'command':command,
        'symbol':bound['name'],'start_rva':start,'end_rva_exclusive':stop,'windows':spans,
        'decoded_words_verified_against_device_bytes':True})

data = (PREP/'hip-host-direct-census-20261008/host-census.bin').read_bytes()
assert hashlib.sha256(data).hexdigest() == '57c11ac1f904c3fc28175844ebf7d8e850fb6fd1351c420117f21de2dc8fe0fb'
base = struct.unpack_from('<Q',data,24)[0]
counts = {}
for at in range(64,len(data),96):
    row = struct.unpack_from('<10QiiII',data,at)
    if row[12] == 6 and row[3] in {0x17F6F03,0x17F24B7,0x1828616}:
        key = f'{row[3]:x}/{row[9]-base:x}'
        entry = counts.setdefault(key,{'launches':0,'host_interval_ns':0,'streams':set(),'results':set()})
        entry['launches'] += 1
        entry['host_interval_ns'] += row[2]-row[1]
        entry['streams'].add(row[8]);entry['results'].add(row[10])
for entry in counts.values():
    entry['streams'] = sorted(entry['streams']);entry['results'] = sorted(entry['results'])
receipt['retained_host_census'] = {'sha256':hashlib.sha256(data).hexdigest(),
    'both_requests_combined':True,'kernel_arguments_not_recorded':True,'GPU_durations_not_recorded':True,
    'targeted_counts':counts}
source_root = Path('C:/Projects/strix-alloy-clean')
source_inputs = [
    source_root/'scripts/benchmarks/experimental/halogen0172_host_census/host_census.c',
    source_root/'scripts/benchmarks/halogen0162_mtp_full_event_tap.c',
    source_root/'scripts/benchmarks/hgn_ht_slice.py',
    PREP/'hip-host-direct-census-20261008/census_client.py',
    PREP/'hip-host-direct-census-20261008/request-boundaries.json',
    PREP/'fixed-depth2-comparison/prompts/prompt-8192-prose.txt',
    PREP/'static-compatibility-audit/passive_elf_review.py',
    Path('C:/AI/sdk/therock1151-10.2.0a20260930/include/hip/amd_detail/amd_hip_runtime_pt_api.h'),
]
receipt['reused_source_inputs'] = [{'path':str(path),'bytes':len(raw),
    'sha256':hashlib.sha256(raw).hexdigest()}
    for path in source_inputs for raw in [path.read_bytes()]]
receipt['native_query_storage'] = {'dtype':'BF16','width_words':2560,'bytes':5120,
    'proof':'Q4 arg1 is s[6:7]; direct loads 0x73b864..0x73b8a8 feed v_dot2_f32_bf16 from 0x73b94c.'}
receipt['native_ht_dimensions'] = {'descriptor_0x4c':'O (int32 output rows)',
    'descriptor_0x50':'K (uint64 width)','required_alignment_rows_and_width':128,
    'original_caller':'CL=1, R8D=O, R9D=N, stack K=2560 at 0x17e4925'}
(HERE/'source-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'exact_bindings':bindings,'retained_census':counts,'host_files':len(plans),
                  'device_words_byte_checked':True},indent=2))
