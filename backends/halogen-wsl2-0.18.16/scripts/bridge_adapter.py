"""Exact 0.18.16 source-only candidate; no compiler, activation, or ELF execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ENGINE_SHA = '8c184edfcb5d249d4ce525db5afe8afb32186126c7b01f1e2f007510a6c54132'
ENGINE_BYTES = 32526416
SITE_OFFSET = 0x1ea0d72
SITE_RVA = 0x1ea1d72
FUNCTION_OFFSET = 0x1ea06a0
FUNCTION_END = 0x1ea1fa4
FUNCTION_SHA = 'ac7b44af9c2258f5a662f8983572cc79d3d20d272a824f8ecdefe4c66db176d2'
SIGNATURE = bytes.fromhex('488b8424a8000000488b9424b80000004801d04c29f80f87eb0f0000')
SOURCES = {'halogen-preflight-bridge.c': 'c88e82665fcd8b5b1139bb50b06440dfd59f22c3cbb7220dfa9f43323e121fd8', 'halogen-preflight-trampoline.S': '8a75b3619c471297cb26dbbf2c2364c1778b26a2e1d97e301cae9189cf5e3356', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': 'cb50b44f7d4dce09c1c13d43445677273e9c648ae5840394bedad14f360d80df', 'hip-register-private-rw.c': '4718d3da5be49c4aaf6235791ecf61c645b99717515f54687073b48e2f6bdc43'}
ORIGINAL_SOURCES = {'halogen-preflight-bridge.c': '0df1515cd89d8225fb746cd605ef6254b9c03ad12bf3b14dfa9f31f991ef74a6', 'halogen-preflight-trampoline.S': '8a75b3619c471297cb26dbbf2c2364c1778b26a2e1d97e301cae9189cf5e3356', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': '7d3b6165d09cc2ebce90c0b455f65c1c36305b92fea5c9950d25cc917a3dcb58', 'hip-register-private-rw.c': 'a216b0a0136a053916d49bc7e832b517da00e955c338abd0a9a48edbb08fcc02'}
ORIGINAL_GENERATOR_SHA = '4b453ce11bc944d88aef281688233411b5ba691065964714646e75ce3dbdaec5'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_abi(data):
    if data[SITE_OFFSET:SITE_OFFSET + len(SIGNATURE)] != SIGNATURE:
        raise ValueError('site signature mismatch')
    if sha(data[FUNCTION_OFFSET:FUNCTION_END]) != FUNCTION_SHA:
        raise ValueError('ABI evidence function mismatch')


def verify_engine(data):
    if len(data) != ENGINE_BYTES or data[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('ELF identity')
    if struct.unpack_from('<HH', data, 16) != (3, 62):
        raise ValueError('ELF type/machine')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    phsize, phnum = struct.unpack_from('<HH', data, 54)
    if phsize != 56 or phnum != 12 or phoff + phsize * phnum > len(data):
        raise ValueError('ELF program headers')
    spans = []
    for i in range(phnum):
        kind, flags, offset, va, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', data, phoff+i*phsize)
        if kind == 1 and flags == 5 and va <= SITE_RVA and SITE_RVA + len(SIGNATURE) <= va + size:
            spans.append(offset + SITE_RVA - va)
    if spans != [SITE_OFFSET]:
        raise ValueError('ELF executable site mapping')
    verify_abi(data)
    if sha(data) != ENGINE_SHA:
        raise ValueError('ELF sha256')


def generate(source, engine, output):
    source, engine, output = map(Path, (source, engine, output))
    allowed = Path(__file__).resolve().parents[2]
    output = output.resolve()
    if not output.is_relative_to(allowed) or output == allowed:
        raise ValueError('Output must be a new directory inside this private release preparation')
    if output.exists():
        raise FileExistsError(output)
    verify_engine(engine.read_bytes())
    prepared = {}
    for name, digest in SOURCES.items():
        data = (source / name).read_bytes()
        if sha(data) != digest:
            raise ValueError('source identity mismatch: ' + name)
        prepared[name] = data
    (output / 'patches').mkdir(parents=True)
    for name, data in prepared.items():
        (output / 'patches' / name).write_bytes(data)
    manifest = {
        'schema': 'halogen01816.source-only-preflight-candidate.v1',
        'engine_sha256': ENGINE_SHA, 'engine_bytes': ENGINE_BYTES,
        'site_rva': hex(SITE_RVA), 'site_file_offset': hex(SITE_OFFSET),
        'signature_hex': SIGNATURE.hex(), 'abi_function_sha256': FUNCTION_SHA,
        'detour_bytes': 8, 'call_return_delta': 5, 'native_resume_delta': 8,
        'detour': 'CALL rel32 plus three NOP bytes', 'old_function_equivalence_claimed': False,
        'abi_function_file_range': [hex(FUNCTION_OFFSET), hex(FUNCTION_END)],
        'original_sources': ORIGINAL_SOURCES, 'original_generator_sha256': ORIGINAL_GENERATOR_SHA,
        'candidate_sources': {name: sha(data) for name, data in prepared.items()},
        'profiles': ['flash01816-v2-device64-chunk64-v1', 'flash01816-copy48-v1'],
        'hybrid_profiles': ['vgm64-01816-v2-device64-v1', 'vgm64-01816-copy48-v1'],
        'library': 'libhalogen01816-preflight.so',
        'default_off': True, 'production_bound': False, 'built': False,
        'runtime_qualified': False,
        'limitations': 'Exact 0.18.16 ELF/window/function pins and fresh finite demand dataflow contract; old function/helper equivalence is not claimed. Indirect/loader/HIP closure and CPU/runtime qualification remain separate gates.'
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.source, args.engine, args.output)
