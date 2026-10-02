"""Stage opt-in upstream patches in a separate, unbuilt GUFO checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent
RELATIVE = Path('src/models/qwen38_flash_next/kernels/rocm/kernels.hip.cpp')
PATCH = ROOT / 'patches/attention-window-optin.patch'
EXPECTED_SHA256 = 'a5b28f33f6d03ff7b7c0ee12c66638e099159a539721e29a3b1f22c03207be4e'
GREEDY_RELATIVE = Path('src/core/sampling.cpp')
GREEDY_PATCH = ROOT / 'patches/greedy-penalties-optin.patch'
GREEDY_SHA256 = '094c3dad5b9ea93768224ce94ffb558eaea2edd18b4e11ba9fc5d1f5cc9e21eb'


def verify(source, kind='attention'):
    source = Path(source).resolve(strict=True)
    relative, expected, _ = {
        'attention': (RELATIVE, EXPECTED_SHA256, PATCH),
        'greedy': (GREEDY_RELATIVE, GREEDY_SHA256, GREEDY_PATCH),
    }[kind]
    target = (source / relative).resolve(strict=True)
    if not target.is_relative_to(source):
        raise ValueError('Source path escapes checkout')
    if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise ValueError('Expected exact pinned GUFO source (numerics-patched for attention)')
    if not (source / '.git').exists():
        raise ValueError('Expected a separate Git source checkout')
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--patch', choices=('attention', 'greedy'), default='attention')
    parser.add_argument('--apply', action='store_true', help='Explicitly change the experimental source checkout')
    args = parser.parse_args()
    source = verify(args.source, args.patch)
    patch = PATCH if args.patch == 'attention' else GREEDY_PATCH
    if args.apply and (source / 'build/gpu-test/gufo.exe').exists():
        raise ValueError('Refusing to alter a built/possibly active GUFO checkout')
    subprocess.run(['git', '-C', str(source), 'apply', '--check', str(patch)], check=True)
    if args.apply:
        subprocess.run(['git', '-C', str(source), 'apply', str(patch)], check=True)
    print(json.dumps({'source': str(source), 'patch': str(patch),
                      'applied': args.apply, 'runtime_changed': False}))


if __name__ == '__main__':
    main()
