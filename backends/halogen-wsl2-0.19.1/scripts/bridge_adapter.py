"""Exact 0.19.1 source-only candidate; no compiler, activation, or ELF execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ENGINE_SHA = '9dcf048b93111aba93032aa2ba0bea07496bc14c0cd4316a21dc39d2db749d46'
ENGINE_BYTES = 33867072
SITE_OFFSET = 0x1fe6232
SITE_RVA = 0x1fe7232
FUNCTION_OFFSET = 0x1fe5b60
FUNCTION_END = 0x1fe7464
FUNCTION_SHA = '539a02158604e4966992a2d95bc4da8353a85be906bc98a0b4e3c543e37514df'
SIGNATURE = bytes.fromhex('488b8424a8000000488b9424b80000004801d04c29f80f87eb0f0000')
SOURCES = {'halogen-preflight-bridge.c': 'd6e7d361766869f4c48646e52bc9bfb4cef4d0ce43f8eb9963f9b1d5507f836d', 'halogen-preflight-trampoline.S': '8a75b3619c471297cb26dbbf2c2364c1778b26a2e1d97e301cae9189cf5e3356', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': '5bc4a1ac78d2ff5004793c37a69ff36ca827ed803e01377fab15a8438da9172f', 'hip-register-private-rw.c': '4aa563c72666faef032c48db7c16cca79c9e0fc3fd7a9e2322fada58cbf878ea'}
ORIGINAL_SOURCES = {'halogen-preflight-bridge.c': '6ef84afed5c71284c516b26c9daa3245700fd4aa7eb0018bec9a7ab51e264f33', 'halogen-preflight-trampoline.S': '8a75b3619c471297cb26dbbf2c2364c1778b26a2e1d97e301cae9189cf5e3356', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': '830b104c89bc39c60986a79c63eeb899adef00e7d0a99f5b625b717146c32b9b', 'hip-register-private-rw.c': 'e2a2a105c2af87628ca4c149359b63b6386c45fd19335101df6ae16134aad85f'}
ORIGINAL_GENERATOR_SHA = '38c8d871df3383cfaf51183f73d8fcd9f0e5a45936135b1ad5b887574b0eaf18'


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
        'schema': 'halogen0191.source-only-preflight-candidate.v1',
        'engine_sha256': ENGINE_SHA, 'engine_bytes': ENGINE_BYTES,
        'site_rva': hex(SITE_RVA), 'site_file_offset': hex(SITE_OFFSET),
        'signature_hex': SIGNATURE.hex(), 'abi_function_sha256': FUNCTION_SHA,
        'detour_bytes': 8, 'call_return_delta': 5, 'native_resume_delta': 8,
        'detour': 'CALL rel32 plus three NOP bytes', 'old_function_equivalence_claimed': False,
        'abi_function_file_range': [hex(FUNCTION_OFFSET), hex(FUNCTION_END)],
        'original_sources': ORIGINAL_SOURCES, 'original_generator_sha256': ORIGINAL_GENERATOR_SHA,
        'candidate_sources': {name: sha(data) for name, data in prepared.items()},
        'profiles': ['flash0191-v2-device64-chunk64-v1', 'flash0191-copy48-v1'],
        'hybrid_profiles': ['vgm64-0191-v2-device64-v1', 'vgm64-0191-copy48-v1'],
        'library': 'libhalogen0191-preflight.so',
        'default_off': True, 'production_bound': False, 'built': False,
        'runtime_qualified': False,
        'limitations': 'Exact 0.19.1 ELF/window/function pins and fresh finite demand dataflow contract; old function/helper equivalence is not claimed. Indirect/loader/HIP closure and CPU/runtime qualification remain separate gates.'
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
