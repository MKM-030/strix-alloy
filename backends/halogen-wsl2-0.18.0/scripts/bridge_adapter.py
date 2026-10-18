"""Exact 0.18.0 source-only candidate; no compiler, activation, or ELF execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ENGINE_SHA = '71d72b283f0937aec024baf6b6ec919e27dacd57cfc043832468ffdd603c8e08'
ENGINE_BYTES = 27078280
SITE_OFFSET = 0x1970f70
SITE_RVA = 0x1971f70
FUNCTION_OFFSET = 0x1970930
FUNCTION_END = 0x197192c
FUNCTION_SHA = 'c1b41a1bcf21ae450dda58d89fd35931b3ada05ad846c388792a2126be497bdc'
SIGNATURE = bytes.fromhex('488b4424584801d04829f04c8b6c24300f87fb070000')
SOURCES = {'halogen-preflight-bridge.c': '387979fefa9483e96b25c0492767cf7f7e4ef68d9c3fd9628f90e42b7ea81eb1', 'halogen-preflight-trampoline.S': '77f30756961d2e1680af8e162c2634e57b1e638ac2cf963796ad1f5fc409aa99', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': '5a550951560abd23a91565a9a544dfe736793448f449afb88a8d3c4825aac35d', 'hip-register-private-rw.c': 'f430e949803683d588b87c1f7ae6b7230535274f923655a4b164577f8fe12749'}
ORIGINAL_SOURCES = {'halogen-preflight-bridge.c': '7f127d0f60dc1a621d9ca3a830b099229e39756000de694e506c91206a37a662', 'halogen-preflight-trampoline.S': '77f30756961d2e1680af8e162c2634e57b1e638ac2cf963796ad1f5fc409aa99', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': 'f173a1c9faae090c0ae20b2cb0515add2bedd7b272a9efb7ae75346c034373dd', 'hip-register-private-rw.c': '2ce44e5794e6bb37e8c92feefee2415901fa9a4136ebd47bfb9c8c1140ae2730'}
ORIGINAL_GENERATOR_SHA = 'b783a50ad457492b111ac66902a131e56d56837b9ad1afde1f6bfcb396d4aa0b'


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
        'schema': 'halogen0180.source-only-preflight-candidate.v1',
        'engine_sha256': ENGINE_SHA, 'engine_bytes': ENGINE_BYTES,
        'site_rva': hex(SITE_RVA), 'site_file_offset': hex(SITE_OFFSET),
        'signature_hex': SIGNATURE.hex(), 'abi_function_sha256': FUNCTION_SHA,
        'abi_function_file_range': [hex(FUNCTION_OFFSET), hex(FUNCTION_END)],
        'original_sources': ORIGINAL_SOURCES, 'original_generator_sha256': ORIGINAL_GENERATOR_SHA,
        'candidate_sources': {name: sha(data) for name, data in prepared.items()},
        'profiles': ['flash0180-v2-device64-chunk64-v1', 'flash0180-copy48-v1'],
        'hybrid_profiles': ['vgm64-0180-v2-device64-v1', 'vgm64-0180-copy48-v1'],
        'library': 'libhalogen0180-preflight.so',
        'default_off': True, 'production_bound': False, 'built': False,
        'runtime_qualified': False,
        'limitations': 'Exact 0.18.0 ELF/window/function pins and finite direct helper evidence; indirect semantic ABI, loader/HIP closure, CPU/build and runtime qualification remain separate gates.'
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
