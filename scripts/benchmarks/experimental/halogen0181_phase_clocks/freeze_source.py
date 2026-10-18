"""Freeze this source packet; explicit prior-hash check for a reviewed revision."""
from pathlib import Path
import argparse
import hashlib
import json


def main():
    here=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replace-sha256');parser.add_argument('--offline-tests',type=int)
    args=parser.parse_args();target=here/'source-pins.json'
    if args.replace_sha256:
        if hashlib.sha256(target.read_bytes()).hexdigest()!=args.replace_sha256:raise ValueError('Prior source manifest SHA differs')
    if args.offline_tests is not None and args.offline_tests<=0:raise ValueError('Positive observed fixture count required')
    files={}
    for path in sorted(here.rglob('*')):
        if path.is_file() and path.name!='source-pins.json' and '__pycache__' not in path.parts:
            raw=path.read_bytes();files[path.relative_to(here).as_posix()]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    value=dict(schema='halogen0181.passive-observer-source.v1',status='source_only_pending_root_build',
        engine_sha256='d946e7b32a46400884ee7309b909da73f4a6586140cd9f9b94fa9ff583b3c3ab',
        current_image_cpu_provider_file_verified=True,default_off=True,native_clock_returns_unchanged_by_design=True,
        observer_built=False,C_mock_harness_executed=False,live_engine_provider_binding_verified=False,
        actual_engine_phase_stamps_available=False,measured_overhead_available=False,qualified_token_rates_available=False,
        Python_fixture_tests_observed=args.offline_tests,phase_count_scope_qualified=False,
        supersedes_source_pins_sha256=args.replace_sha256,files=files)
    with target.open('w' if args.replace_sha256 else 'x',encoding='utf-8',newline='\n') as stream:stream.write(json.dumps(value,indent=2)+'\n')
    print(json.dumps(dict(source_files=len(files),source_pins_sha256=hashlib.sha256((here/'source-pins.json').read_bytes()).hexdigest())))


if __name__=='__main__':main()
