"""Exact 0.17.3 source-only candidate; no compiler, activation, or ELF execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ENGINE_SHA = 'af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7'
ENGINE_BYTES = 26188824
SITE_OFFSET = 0x1897d20
SITE_RVA = 0x1898d20
FUNCTION_OFFSET = 0x18976e0
FUNCTION_END = 0x18986dc
FUNCTION_SHA = '641f1f0b8f7df2bb6e5c1250aa42ad709be2a2fb709d165febd10f723d310917'
SIGNATURE = bytes.fromhex('488b4424584801d04829f04c8b6c24300f87fb070000')
SOURCES = {'halogen-preflight-bridge.c': '0be6adf86587f6d334887d6e1d61eb26fbb5a156908eb33881e95c4e685baf61', 'halogen-preflight-trampoline.S': '77f30756961d2e1680af8e162c2634e57b1e638ac2cf963796ad1f5fc409aa99', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': '25d04669935eefc6d3d39cf5e9918dbbb36325f88de048d46b1fae807b215342', 'hip-register-private-rw.c': 'c998ac7b1a9aee191742a6a7de9944bcd9946c919a1bcf2b2c8cd93dbba61900'}
ORIGINAL_SOURCES = {'halogen-preflight-bridge.c': 'dab46e62d168b8cfaa04c135fab909f3af1594b40da018115cd0a546d843ae19', 'halogen-preflight-trampoline.S': 'ec46e7f698bfa0acdfa8b431118017631d1cefd05dbfd55ab09545e8d18717b3', 'hip-preflight-plan.h': '9341e612937780f16265940173220103fd421cce64d44e2cd92d8cd28a784176', 'hip-register-hybrid.c': 'e74796dba8b92b3980959994a6495ed6b764afa75abf88b348505d6006c6be38', 'hip-register-private-rw.c': 'dd31073d824c1ba458ec7ba34965ef0c3273b6d9754d79b19ac5be9c31105fd6'}
ORIGINAL_GENERATOR_SHA = '16425e68087642b3b61e69e4a4cd142683a3edae7dd56fde93c0bfe8ea7e0782'


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
        'schema': 'halogen0173.source-only-preflight-candidate.v1',
        'engine_sha256': ENGINE_SHA, 'engine_bytes': ENGINE_BYTES,
        'site_rva': hex(SITE_RVA), 'site_file_offset': hex(SITE_OFFSET),
        'signature_hex': SIGNATURE.hex(), 'abi_function_sha256': FUNCTION_SHA,
        'abi_function_file_range': [hex(FUNCTION_OFFSET), hex(FUNCTION_END)],
        'original_sources': ORIGINAL_SOURCES, 'original_generator_sha256': ORIGINAL_GENERATOR_SHA,
        'candidate_sources': {name: sha(data) for name, data in prepared.items()},
        'profiles': ['flash0173-v2-device64-chunk64-v1', 'flash0173-copy48-v1'],
        'hybrid_profiles': ['vgm64-0173-v2-device64-v1', 'vgm64-0173-copy48-v1'],
        'library': 'libhalogen0173-preflight.so',
        'default_off': True, 'production_bound': False, 'built': False,
        'runtime_qualified': False,
        'limitations': 'Exact 0.17.3 signature/frame and bounded eight-function source delta reviewed; runtime qualification is separate.'
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
