"""Exact 0.18.5 source-only candidate; no compiler, activation, or ELF execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ENGINE_SHA = 'cfbf55629838dc83e72daf8159745de1d7db9548b034c15b0948618e8fbf1464'
ENGINE_BYTES = 27220912
SITE_OFFSET = 0x1993c4f
SITE_RVA = 0x1994c4f
FUNCTION_OFFSET = 0x1993590
FUNCTION_END = 0x1994618
FUNCTION_SHA = 'f7c94cdacf73de7d79197c5a1e954ca08a229a6b5afbd6d24e3de0fe3e822286'
SIGNATURE = bytes.fromhex('488b4424504801d04c29f80f870d080000')
SOURCES = {'halogen-preflight-bridge.c': 'c958304ee67d78a4b6c9168d9f875998b1d6a562f80693666489deb4790f0217', 'halogen-preflight-trampoline.S': '77f30756961d2e1680af8e162c2634e57b1e638ac2cf963796ad1f5fc409aa99', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': 'de4be86ca17b730155b490b29584fcd1672bfae663470c07f8e24b946d8c9a69', 'hip-register-private-rw.c': '7fe23337662d79fe9463cfdfed05ea796712e7ccedf5ad0409deac380375afab'}
ORIGINAL_SOURCES = {'halogen-preflight-bridge.c': 'f921bd8a0ca21403f2ca42c49b099c6ca8b27aa2de6a80227aa82e6cb11ad21b', 'halogen-preflight-trampoline.S': '77f30756961d2e1680af8e162c2634e57b1e638ac2cf963796ad1f5fc409aa99', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': '272bd9b7dabc205417a1c7ae283a187961d22bbc8ca8f56673c84675298f13ae', 'hip-register-private-rw.c': '59cc8a080f7e6c37b08f09aa703a031df251217df848a1ec49d1bd7d6d1e1a7a'}
ORIGINAL_GENERATOR_SHA = '41d30736779133555236d1a5de08775df4723b5dba58b1427ecbfc9a75bb834d'


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
        'schema': 'halogen0185.source-only-preflight-candidate.v1',
        'engine_sha256': ENGINE_SHA, 'engine_bytes': ENGINE_BYTES,
        'site_rva': hex(SITE_RVA), 'site_file_offset': hex(SITE_OFFSET),
        'signature_hex': SIGNATURE.hex(), 'abi_function_sha256': FUNCTION_SHA,
        'abi_function_file_range': [hex(FUNCTION_OFFSET), hex(FUNCTION_END)],
        'original_sources': ORIGINAL_SOURCES, 'original_generator_sha256': ORIGINAL_GENERATOR_SHA,
        'candidate_sources': {name: sha(data) for name, data in prepared.items()},
        'profiles': ['flash0185-v2-device64-chunk64-v1', 'flash0185-copy48-v1'],
        'hybrid_profiles': ['vgm64-0185-v2-device64-v1', 'vgm64-0185-copy48-v1'],
        'library': 'libhalogen0185-preflight.so',
        'default_off': True, 'production_bound': False, 'built': False,
        'runtime_qualified': False,
        'limitations': 'Exact 0.18.5 ELF/window/function pins and finite direct helper evidence; indirect semantic ABI, loader/HIP closure, CPU/build and runtime qualification remain separate gates.'
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
