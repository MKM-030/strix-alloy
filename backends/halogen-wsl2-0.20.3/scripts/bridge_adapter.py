"""Exact 0.20.3 source-only candidate; no compiler, activation, or ELF execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ENGINE_SHA = 'bf84053705d1e89c214ff64c79ad1276c5fe353d80a9bb0f38ef3bac6645b97c'
ENGINE_BYTES = 35410384
SITE_OFFSET = 0x215dcc2
SITE_RVA = 0x215ecc2
FUNCTION_OFFSET = 0x215d5e0
FUNCTION_END = 0x215ef14
FUNCTION_SHA = '34969a2962be36d2888ca53a8680924b32d00696b75bed33cf4f9d3be1a1fc8d'
SIGNATURE = bytes.fromhex('488b8424a8000000488b9424b80000004801d04c29f80f870b100000')
SOURCES = {'halogen-preflight-bridge.c': '7bb7b83f8a4a404d44826a3cc5a4586dade9a6fdd5fbb777ae612a3f6b13ff2b', 'halogen-preflight-trampoline.S': '8a75b3619c471297cb26dbbf2c2364c1778b26a2e1d97e301cae9189cf5e3356', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': 'bf9f9659b7f125a164c586f63e7abfb272b68a9f1429e027c357392640f70464', 'hip-register-private-rw.c': 'aa9a0e8af7585498e93a96657d90fcfa2fcef5efe0e198d815fffcea797e1e9d'}
ORIGINAL_SOURCES = {'halogen-preflight-bridge.c': '24416a246c6f051524d40ec8428d335b3a872ea3ae87598eae9536cbad07dc7d', 'halogen-preflight-trampoline.S': '8a75b3619c471297cb26dbbf2c2364c1778b26a2e1d97e301cae9189cf5e3356', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': 'f0063bb4257230b1a2859b6153326d0407773292b9d3c4e0810313a855b1892c', 'hip-register-private-rw.c': 'cd41d91479a5e0723d19168272cdc796003883a46535ceefdc90ebeb5f9ab45b'}
ORIGINAL_GENERATOR_SHA = 'caeefc92cb52e7bff150aa6cec24b9686d22f1dcb6f6806fdcd05b5ffa7152bf'


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
        'schema': 'halogen0203.source-only-preflight-candidate.v1',
        'engine_sha256': ENGINE_SHA, 'engine_bytes': ENGINE_BYTES,
        'site_rva': hex(SITE_RVA), 'site_file_offset': hex(SITE_OFFSET),
        'signature_hex': SIGNATURE.hex(), 'abi_function_sha256': FUNCTION_SHA,
        'detour_bytes': 8, 'call_return_delta': 5, 'native_resume_delta': 8,
        'detour': 'CALL rel32 plus three NOP bytes', 'old_function_equivalence_claimed': False,
        'abi_function_file_range': [hex(FUNCTION_OFFSET), hex(FUNCTION_END)],
        'original_sources': ORIGINAL_SOURCES, 'original_generator_sha256': ORIGINAL_GENERATOR_SHA,
        'candidate_sources': {name: sha(data) for name, data in prepared.items()},
        'profiles': ['flash0203-v2-device64-chunk64-v1', 'flash0203-copy48-v1'],
        'hybrid_profiles': ['vgm64-0203-v2-device64-v1', 'vgm64-0203-copy48-v1'],
        'library': 'libhalogen0203-preflight.so',
        'default_off': True, 'production_bound': False, 'built': False,
        'runtime_qualified': False,
        'limitations': 'Exact 0.20.3 ELF/window/function pins and fresh finite demand dataflow contract; old function/helper equivalence is not claimed. Indirect/loader/HIP closure and CPU/runtime qualification remain separate gates.'
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
