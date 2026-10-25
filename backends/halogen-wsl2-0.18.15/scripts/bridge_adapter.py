"""Exact 0.18.15 source-only candidate; no compiler, activation, or ELF execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ENGINE_SHA = 'ce1c375eb2d92a4c7b2b0e1d969acd865bb72bb248c52498eedb170cbaea8a89'
ENGINE_BYTES = 32523520
SITE_OFFSET = 0x1ea0222
SITE_RVA = 0x1ea1222
FUNCTION_OFFSET = 0x1e9fb50
FUNCTION_END = 0x1ea1454
FUNCTION_SHA = '5c037fd7f6986c6521c37f5f8dfdad551a2ba68df3c636303a9e7fc9982a74fd'
SIGNATURE = bytes.fromhex('488b8424a8000000488b9424b80000004801d04c29f80f87eb0f0000')
SOURCES = {'halogen-preflight-bridge.c': '0df1515cd89d8225fb746cd605ef6254b9c03ad12bf3b14dfa9f31f991ef74a6', 'halogen-preflight-trampoline.S': '8a75b3619c471297cb26dbbf2c2364c1778b26a2e1d97e301cae9189cf5e3356', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': '7d3b6165d09cc2ebce90c0b455f65c1c36305b92fea5c9950d25cc917a3dcb58', 'hip-register-private-rw.c': 'a216b0a0136a053916d49bc7e832b517da00e955c338abd0a9a48edbb08fcc02'}
ORIGINAL_SOURCES = {'halogen-preflight-bridge.c': '7474d7813c7574af80f21f2d8a6c24f888a4d4cb93c20a21663dd8d47709981a', 'halogen-preflight-trampoline.S': '77f30756961d2e1680af8e162c2634e57b1e638ac2cf963796ad1f5fc409aa99', 'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b', 'hip-register-hybrid.c': '52898d0831e1c3820413ec9056ebd9103cd17a21460e6e00755f5612104285d3', 'hip-register-private-rw.c': 'ef82773986c19e426b567d7cd99af84bafdd258d8dc541151c519fc984f26f14'}
ORIGINAL_GENERATOR_SHA = 'f7afb3eca7e7fb77561f2b20fbfc2558248d97e5ea45aaf988f9082ca9223d81'


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
        'schema': 'halogen01815.source-only-preflight-candidate.v1',
        'engine_sha256': ENGINE_SHA, 'engine_bytes': ENGINE_BYTES,
        'site_rva': hex(SITE_RVA), 'site_file_offset': hex(SITE_OFFSET),
        'signature_hex': SIGNATURE.hex(), 'abi_function_sha256': FUNCTION_SHA,
        'detour_bytes': 8, 'call_return_delta': 5, 'native_resume_delta': 8,
        'detour': 'CALL rel32 plus three NOP bytes', 'old_function_equivalence_claimed': False,
        'abi_function_file_range': [hex(FUNCTION_OFFSET), hex(FUNCTION_END)],
        'original_sources': ORIGINAL_SOURCES, 'original_generator_sha256': ORIGINAL_GENERATOR_SHA,
        'candidate_sources': {name: sha(data) for name, data in prepared.items()},
        'profiles': ['flash01815-v2-device64-chunk64-v1', 'flash01815-copy48-v1'],
        'hybrid_profiles': ['vgm64-01815-v2-device64-v1', 'vgm64-01815-copy48-v1'],
        'library': 'libhalogen01815-preflight.so',
        'default_off': True, 'production_bound': False, 'built': False,
        'runtime_qualified': False,
        'limitations': 'Exact 0.18.15 ELF/window/function pins and fresh finite demand dataflow contract; old function/helper equivalence is not claimed. Indirect/loader/HIP closure and CPU/runtime qualification remain separate gates.'
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
