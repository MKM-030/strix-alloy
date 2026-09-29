"""Exact 0.15.0 binding; generates separate sources, never edits public inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

ENGINE_SHA = 'a7c096afa6c882cc8ee5fadae1311f49826c047ecf7731a5339efa3b7a413181'
OLD_SHA = '39382df17e7bd922a302d7dbfaaaa80d5dbb4a813e50268265a74c70c8679625'
SITE_OFFSET = 0x116d750
SITE_RVA = 0x116e750
FUNCTION_OFFSET = 0x116d110
FUNCTION_END = 0x116e112
FUNCTION_SHA = 'f058767ca92c2d370640e7cc10fe948d9e853fa8b357018b1c35d77eed602bcb'
SIGNATURE = bytes.fromhex('488b4424584801d04829f04c8b6c24304c8b7c24080f871f080000')
SOURCES = {
    'halogen-preflight-bridge.c': '3a365e6a36e12b70980b69ed07d42b933a9a639177d6a70955035c227f294e93',
    'halogen-preflight-trampoline.S': '77f30756961d2e1680af8e162c2634e57b1e638ac2cf963796ad1f5fc409aa99',
    'hip-preflight-plan.h': 'bbf72a9dd29efd4a3c70caa9dc67b1393203ff412c140184eaee90c4bc25397b',
    'hip-register-hybrid.c': '6580422cd5f50e6e99f9a716b0c073922333e64dc484e48854c9764c03825dc0',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_abi(data):
    if data[SITE_OFFSET:SITE_OFFSET + len(SIGNATURE)] != SIGNATURE:
        raise ValueError('site signature mismatch')
    if sha(data[FUNCTION_OFFSET:FUNCTION_END]) != FUNCTION_SHA:
        raise ValueError('ABI evidence function mismatch')


def verify_engine(data):
    if len(data) < 64 or data[:7] != b'\x7fELF\x02\x01\x01':
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


def replace_once(data, old, new):
    if data.count(old) != 1:
        raise ValueError('substitution not unique: ' + repr(old))
    return data.replace(old, new)


def generate(source, engine, output):
    source, engine, output = map(Path, (source, engine, output))
    if output.exists():
        raise FileExistsError(output)
    verify_engine(engine.read_bytes())
    prepared = {}
    for name, digest in SOURCES.items():
        data = (source / name).read_bytes()
        if sha(data) != digest:
            raise ValueError('source identity mismatch: ' + name)
        if name == 'halogen-preflight-bridge.c':
            data = replace_once(data, OLD_SHA.encode(), ENGINE_SHA.encode())
            data = replace_once(data, b'0xc8f020', b'0x116e750')
        if name in ('halogen-preflight-bridge.c', 'hip-register-hybrid.c'):
            data = replace_once(data, b'flash0138-copy48-v1', b'flash0150-copy48-v1')
        prepared[name] = data
    (output / 'patches').mkdir(parents=True)
    for name, data in prepared.items():
        (output / 'patches' / name).write_bytes(data)
    manifest = {'engine_sha256': ENGINE_SHA, 'site_rva': hex(SITE_RVA),
                'site_file_offset': hex(SITE_OFFSET), 'signature_hex': SIGNATURE.hex(),
                'abi_function_sha256': FUNCTION_SHA, 'original_sources': SOURCES,
                'candidate_sources': {name: sha(data) for name, data in prepared.items()},
                'profile': 'flash0150-copy48-v1', 'library': 'libhalogen0150-preflight.so'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def build(output):
    output = Path(output)
    manifest = json.loads((output / 'manifest.json').read_text())
    for name, digest in manifest['candidate_sources'].items():
        if sha((output / 'patches' / name).read_bytes()) != digest:
            raise ValueError('generated source changed')
    library = output / 'libhalogen0150-preflight.so'
    if library.exists():
        raise FileExistsError(library)
    command = ['gcc', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
               '-DHALOGEN_RESEARCH_VGM64=1', '-DHALOGEN_PREFLIGHT_V1=1',
               '-mno-avx', '-mno-avx2', '-mno-avx512f']
    command += [str(output / 'patches' / name) for name in
                ('hip-register-hybrid.c', 'halogen-preflight-bridge.c', 'halogen-preflight-trampoline.S')]
    command += ['-ldl', '-pthread', '-Wl,-z,relro,-z,now,-z,noexecstack,-z,defs', '-o', str(library)]
    subprocess.run(command, check=True)
    manifest['library_sha256'] = sha(library.read_bytes())
    manifest['build_command'] = command
    manifest['compiler'] = subprocess.check_output(['gcc', '--version'], text=True).splitlines()[0]
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    generate(args.source, args.engine, args.output)
    if args.build:
        build(args.output)
