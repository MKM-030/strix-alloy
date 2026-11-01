"""Exact 0.18.22 source-only candidate; no compiler, activation, or ELF execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ENGINE_SHA = 'c69d064b528e21e5b722ab4a0618b67c29a9d84dd09ba3aa70c6a928b5741aca'
ENGINE_BYTES = 33705024
SITE_OFFSET = 0x1fbfab2
SITE_RVA = 0x1fc0ab2
FUNCTION_OFFSET = 0x1fbf3e0
FUNCTION_END = 0x1fc0ce4
FUNCTION_SHA = 'b4ef98df124696b80d305acb36358c25ca88545a231d96f43142961597586fbd'
SIGNATURE = bytes.fromhex('488b8424a8000000488b9424b80000004801d04c29f80f87eb0f0000')
SOURCES = {'halogen-preflight-bridge.c': '6ef84afed5c71284c516b26c9daa3245700fd4aa7eb0018bec9a7ab51e264f33', 'halogen-preflight-trampoline.S': '8a75b3619c471297cb26dbbf2c2364c1778b26a2e1d97e301cae9189cf5e3356', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': '830b104c89bc39c60986a79c63eeb899adef00e7d0a99f5b625b717146c32b9b', 'hip-register-private-rw.c': 'e2a2a105c2af87628ca4c149359b63b6386c45fd19335101df6ae16134aad85f'}
ORIGINAL_SOURCES = {'halogen-preflight-bridge.c': 'c88e82665fcd8b5b1139bb50b06440dfd59f22c3cbb7220dfa9f43323e121fd8', 'halogen-preflight-trampoline.S': '8a75b3619c471297cb26dbbf2c2364c1778b26a2e1d97e301cae9189cf5e3356', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': 'cb50b44f7d4dce09c1c13d43445677273e9c648ae5840394bedad14f360d80df', 'hip-register-private-rw.c': '4718d3da5be49c4aaf6235791ecf61c645b99717515f54687073b48e2f6bdc43'}
ORIGINAL_GENERATOR_SHA = '4ef9887ae1d44f3963024fba81723b37665707354902a87bc19ccb340c61db11'


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
        'schema': 'halogen01822.source-only-preflight-candidate.v1',
        'engine_sha256': ENGINE_SHA, 'engine_bytes': ENGINE_BYTES,
        'site_rva': hex(SITE_RVA), 'site_file_offset': hex(SITE_OFFSET),
        'signature_hex': SIGNATURE.hex(), 'abi_function_sha256': FUNCTION_SHA,
        'detour_bytes': 8, 'call_return_delta': 5, 'native_resume_delta': 8,
        'detour': 'CALL rel32 plus three NOP bytes', 'old_function_equivalence_claimed': False,
        'abi_function_file_range': [hex(FUNCTION_OFFSET), hex(FUNCTION_END)],
        'original_sources': ORIGINAL_SOURCES, 'original_generator_sha256': ORIGINAL_GENERATOR_SHA,
        'candidate_sources': {name: sha(data) for name, data in prepared.items()},
        'profiles': ['flash01822-v2-device64-chunk64-v1', 'flash01822-copy48-v1'],
        'hybrid_profiles': ['vgm64-01822-v2-device64-v1', 'vgm64-01822-copy48-v1'],
        'library': 'libhalogen01822-preflight.so',
        'default_off': True, 'production_bound': False, 'built': False,
        'runtime_qualified': False,
        'limitations': 'Exact 0.18.22 ELF/window/function pins and fresh finite demand dataflow contract; old function/helper equivalence is not claimed. Indirect/loader/HIP closure and CPU/runtime qualification remain separate gates.'
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
