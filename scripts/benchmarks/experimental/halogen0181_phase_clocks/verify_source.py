"""Read-only verification of frozen source and extracted0.18.1 bytes.

No generator, compiler, subprocess, ELF/native-library load or live call.
"""
import hashlib
import importlib.util
import json
from pathlib import Path


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    here=Path(__file__).resolve().parent;root=here.parents[3]
    pins=json.loads((here/'source-pins.json').read_bytes())
    for name,pin in pins['files'].items():
        raw=(here/name).read_bytes();assert len(raw)==pin['bytes'] and sha(raw)==pin['sha256'],name
    record=json.loads((here/'static-map.json').read_bytes())
    prep=root/'server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008'
    parser=prep/'static-compatibility-audit/passive_elf_review.py'
    assert sha(parser.read_bytes())=='671297d02e798107827e5b51def19a288479a8c733c41b2221854bc96af9eddd'
    spec=importlib.util.spec_from_file_location('readonly_phase_elf',parser);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    extract=prep/'halogen0180-normal-bridge-preparation-20261011/halogen0181-extracted-20261012'
    raw=(extract/'flash_serve').read_bytes();assert len(raw)==record['engine_bytes'] and sha(raw)==record['engine_sha256']
    elf=m.Elf(raw)
    for f in record['functions']:
        actual=elf.unwind_range(f['start_rva']);assert actual['start_rva']==f['start_rva'] and actual['end_rva_exclusive']==f['end_rva_exclusive']
        assert sha(raw[actual['start_file_offset']:actual['end_file_offset_exclusive']])==f['sha256']
    for w in record['windows']:
        at=elf.offset(int(w['rva'],16),w['bytes']);actual=raw[at:at+w['bytes']]
        assert actual.hex()==w['instruction_bytes_hex'] and sha(actual)==w['sha256']
    for name,key in [('receipt.json','cpu_provider_receipt_sha256'),('stdout.json','cpu_provider_stdout_sha256')]:
        assert sha((extract/'cpu-provider'/name).read_bytes())==record[key]
    provider=(extract/'cpu-provider/files/libstdc++.so.6.0.33').read_bytes()
    assert len(provider)==record['provider_bytes'] and sha(provider)==record['provider_sha256']
    print(json.dumps(dict(schema='halogen0181.passive-source-check.v1',source_files=len(pins['files']),
        FDE_functions=len(record['functions']),instruction_windows=len(record['windows']),
        actual_source_and_image_bytes_verified=True,observer_built=False,C_fixture_executed=False,
        live_engine_provider_binding_verified=False,phase_clock_qualified=False,hardware_accessed=False)))


if __name__=='__main__':main()
