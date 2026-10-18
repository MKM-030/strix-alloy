"""Exact 0.18.7 source-only candidate; no compiler, activation, or ELF execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ENGINE_SHA = '84218050a29f342536053e1dbe50bb1acfb25d3aeec3b4eeff6326ae99ead6ae'
ENGINE_BYTES = 27223664
SITE_OFFSET = 0x199458f
SITE_RVA = 0x199558f
FUNCTION_OFFSET = 0x1993ed0
FUNCTION_END = 0x1994f58
FUNCTION_SHA = '486db1ff927d49d89cd47a635e4020ad8ae7a91f17f7c64f449a6949d12d93f3'
SIGNATURE = bytes.fromhex('488b4424504801d04c29f80f870d080000')
SOURCES = {'halogen-preflight-bridge.c': '3234ae6c0c1db0f7313a79e016bd02f5bbca8fc577f95b270be98a9293ae6a88', 'halogen-preflight-trampoline.S': '77f30756961d2e1680af8e162c2634e57b1e638ac2cf963796ad1f5fc409aa99', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': 'f817c3010e961d11db29ee4e74ed41ecafaa472a45bb7e984285f35a7d28f4a8', 'hip-register-private-rw.c': '7b1bf1f513c93a53523db6835427b0d8a1f69881bb364977cfd61c18cfb8bcd1'}
ORIGINAL_SOURCES = {'halogen-preflight-bridge.c': 'c958304ee67d78a4b6c9168d9f875998b1d6a562f80693666489deb4790f0217', 'halogen-preflight-trampoline.S': '77f30756961d2e1680af8e162c2634e57b1e638ac2cf963796ad1f5fc409aa99', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': 'de4be86ca17b730155b490b29584fcd1672bfae663470c07f8e24b946d8c9a69', 'hip-register-private-rw.c': '7fe23337662d79fe9463cfdfed05ea796712e7ccedf5ad0409deac380375afab'}
ORIGINAL_GENERATOR_SHA = '1e3475ddc0a81ba43bf436ab93b9d4eb0a23d38280a5b9397fade44879dba720'


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
        'schema': 'halogen0187.source-only-preflight-candidate.v1',
        'engine_sha256': ENGINE_SHA, 'engine_bytes': ENGINE_BYTES,
        'site_rva': hex(SITE_RVA), 'site_file_offset': hex(SITE_OFFSET),
        'signature_hex': SIGNATURE.hex(), 'abi_function_sha256': FUNCTION_SHA,
        'abi_function_file_range': [hex(FUNCTION_OFFSET), hex(FUNCTION_END)],
        'original_sources': ORIGINAL_SOURCES, 'original_generator_sha256': ORIGINAL_GENERATOR_SHA,
        'candidate_sources': {name: sha(data) for name, data in prepared.items()},
        'profiles': ['flash0187-v2-device64-chunk64-v1', 'flash0187-copy48-v1'],
        'hybrid_profiles': ['vgm64-0187-v2-device64-v1', 'vgm64-0187-copy48-v1'],
        'library': 'libhalogen0187-preflight.so',
        'default_off': True, 'production_bound': False, 'built': False,
        'runtime_qualified': False,
        'limitations': 'Exact 0.18.7 ELF/window/function pins and finite direct helper evidence; indirect semantic ABI, loader/HIP closure, CPU/build and runtime qualification remain separate gates.'
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
