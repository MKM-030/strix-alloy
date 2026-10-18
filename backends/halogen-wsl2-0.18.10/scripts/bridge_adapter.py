"""Exact 0.18.10 source-only candidate; no compiler, activation, or ELF execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ENGINE_SHA = '8ace2f4c075240af862dd3e033513d04c4626e61e3b4b4527c969285981208e7'
ENGINE_BYTES = 27644144
SITE_OFFSET = 0x19fa27f
SITE_RVA = 0x19fb27f
FUNCTION_OFFSET = 0x19f9bc0
FUNCTION_END = 0x19fac48
FUNCTION_SHA = '9a99a44aa914d7bee477e3f3a54c568e3ac09fb29c2b7c9247ae1191e830812d'
SIGNATURE = bytes.fromhex('488b4424504801d04c29f80f870d080000')
SOURCES = {'halogen-preflight-bridge.c': 'd52c9d8fed751293928bd9d8360b7af0d8183249882045843b4a05bb6971263a', 'halogen-preflight-trampoline.S': '77f30756961d2e1680af8e162c2634e57b1e638ac2cf963796ad1f5fc409aa99', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': '999aaf120555693d297f52211f0cdd44c0628950b6a0763340bf1de470ea964a', 'hip-register-private-rw.c': 'e3e33a8f05ed557515b0d334a200fb99e8e492a5040483320f8b14e54bf22ba3'}
ORIGINAL_SOURCES = {'halogen-preflight-bridge.c': 'cf800e6fe2f03250380f8e40c98389fd1e9f474b5cd387fe30143c4f39ca702f', 'halogen-preflight-trampoline.S': '77f30756961d2e1680af8e162c2634e57b1e638ac2cf963796ad1f5fc409aa99', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': '56f69594eb7f740cb28bf57bbdab0fc5e2b503d8dae748ca9c5eb9c6904b66d2', 'hip-register-private-rw.c': 'e97ec15f4e4be651983a91e58b2ff61753236bd24bc2899a96fba7ec223ebb53'}
ORIGINAL_GENERATOR_SHA = '1a672be6b14d58d0ad5e9d42e9d2c3f1e29702c2fa3d1feb0acbdce789c238e3'


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
    if phsize != 56 or phnum != 11 or phoff + phsize * phnum > len(data):
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
        'schema': 'halogen01810.source-only-preflight-candidate.v1',
        'engine_sha256': ENGINE_SHA, 'engine_bytes': ENGINE_BYTES,
        'site_rva': hex(SITE_RVA), 'site_file_offset': hex(SITE_OFFSET),
        'signature_hex': SIGNATURE.hex(), 'abi_function_sha256': FUNCTION_SHA,
        'abi_function_file_range': [hex(FUNCTION_OFFSET), hex(FUNCTION_END)],
        'original_sources': ORIGINAL_SOURCES, 'original_generator_sha256': ORIGINAL_GENERATOR_SHA,
        'candidate_sources': {name: sha(data) for name, data in prepared.items()},
        'profiles': ['flash01810-v2-device64-chunk64-v1', 'flash01810-copy48-v1'],
        'hybrid_profiles': ['vgm64-01810-v2-device64-v1', 'vgm64-01810-copy48-v1'],
        'library': 'libhalogen01810-preflight.so',
        'default_off': True, 'production_bound': False, 'built': False,
        'runtime_qualified': False,
        'limitations': 'Exact 0.18.10 ELF/window/function pins and finite direct helper evidence; indirect semantic ABI, loader/HIP closure, CPU/build and runtime qualification remain separate gates.'
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
