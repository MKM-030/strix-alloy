"""Reviewed identities and path/cache gates for a native GUFO build."""

from __future__ import annotations

import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import stat
import subprocess


PINS_PATH = Path(__file__).resolve().parents[2] / 'config/gufo-build-pins.json'
REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
_CACHE_PATH_KEYS = {'CMAKE_C_COMPILER', 'CMAKE_CXX_COMPILER', 'CMAKE_HIP_COMPILER',
                    'CMAKE_PREFIX_PATH', 'CMAKE_TOOLCHAIN_FILE', 'CMAKE_MAKE_PROGRAM',
                    'Python3_EXECUTABLE', 'CMAKE_HOME_DIRECTORY', 'CMAKE_CACHEFILE_DIR'}


def load_pins() -> dict:
    return json.loads(PINS_PATH.read_text(encoding='utf-8'))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest().upper()


def checked_path(value, *, directory=False, exists=True) -> Path:
    path = Path(value)
    raw = str(path)
    if not path.is_absolute() or raw.startswith(('\\\\', '//', '\\?\\', '\\.\\')):
        raise ValueError(f'absolute_local_path_required:{raw}')
    for part in (path, *path.parents):
        if not part.exists():
            continue
        info = part.lstat()
        if part.is_symlink() or getattr(info, 'st_file_attributes', 0) & REPARSE:
            raise ValueError(f'reparse_path:{part}')
    resolved = path.resolve(strict=False)
    if exists and (not resolved.is_dir() if directory else not resolved.is_file()):
        raise ValueError(f'path_missing:{resolved}')
    return resolved


def _overlap(left: Path, right: Path) -> bool:
    a = tuple(p.casefold() for p in left.parts)
    b = tuple(p.casefold() for p in right.parts)
    return a[:len(b)] == b or b[:len(a)] == a


def validate_roots(source, build, sdk, vcpkg) -> dict[str, Path]:
    roots = {name: checked_path(value, directory=True, exists=False)
             for name, value in [('source', source), ('build', build),
                                 ('sdk', sdk), ('vcpkg', vcpkg)]}
    names = list(roots)
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            if _overlap(roots[first], roots[second]):
                raise ValueError(f'input_roots_overlap:{first}:{second}')
    for name in ('source', 'sdk', 'vcpkg'):
        if not roots[name].is_dir():
            raise ValueError(f'path_missing:{roots[name]}')
    return roots


def validate_build_dir(build: Path) -> None:
    if build.exists() and (not build.is_dir() or any(build.iterdir())):
        raise ValueError(f'foreign_build_dir:{build}')


def probe(argv: list[str], *, cwd: Path | None = None, timeout=15) -> str:
    result = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, check=False,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError(f'identity_probe_failed:{Path(argv[0]).name}:{result.returncode}')
    return result.stdout.strip()


def verify_git(repo: Path, git: Path, *, remote: str, head: str | None,
               tree: str | None, base: str, runner=probe) -> dict:
    def run(*args):
        return runner([str(git), '-C', str(repo), *args]).strip()
    values = {'remote': run('remote', 'get-url', 'origin'),
              'head': run('rev-parse', 'HEAD'),
              'tree': run('rev-parse', 'HEAD^{tree}'),
              'status': run('status', '--porcelain=v1', '--untracked-files=all'),
              'base': run('merge-base', 'HEAD', base)}
    if (values['remote'].rstrip('/') != remote.rstrip('/')
            or (head is not None and values['head'] != head)
            or (tree is not None and values['tree'] != tree)
            or values['status'] or values['base'] != base):
        raise ValueError(f'git_identity_mismatch:{repo}')
    return values


def verify_reviewed_patch(pins: dict) -> dict:
    root = Path(__file__).resolve().parents[2] / 'engine-patches/gufo'
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest.get('reviewed_source_head') != pins['source_reviewed_head']
            or manifest.get('reviewed_source_tree') != pins['source_tree']
            or manifest.get('base_commit') != pins['source_base']
            or manifest.get('patch', {}).get('sha256') != pins['patch_sha256']
            or file_hash(root / manifest['patch']['file']) != pins['patch_sha256']):
        raise ValueError('reviewed_patch_identity_mismatch')
    return {'reviewed_head': pins['source_reviewed_head'],
            'reviewed_tree': pins['source_tree'],
            'patch_sha256': pins['patch_sha256']}


def verify_sdk(sdk: Path, pins: dict, *, runner=probe) -> dict:
    version_file = checked_path(sdk / '.info/version')
    version = version_file.read_text(encoding='utf-8').strip()
    if version != pins['sdk_version']:
        raise ValueError('sdk_version_mismatch')
    clang = checked_path(sdk / 'lib/llvm/bin/clang.exe')
    clangxx = checked_path(sdk / 'lib/llvm/bin/clang++.exe')
    checked_path(sdk / 'lib/llvm/amdgcn/bitcode', directory=True)
    output = runner([str(clang), '--version'])
    if pins['clang_version'] not in output or pins['llvm_revision'] not in output:
        raise ValueError('compiler_identity_mismatch')
    outputxx = runner([str(clangxx), '--version'])
    if pins['clang_version'] not in outputxx or pins['llvm_revision'] not in outputxx:
        raise ValueError('cxx_compiler_identity_mismatch')
    return {'version': version, 'clang': str(clang), 'clangxx': str(clangxx),
            'clang_version_output': output, 'clangxx_version_output': outputxx}


def verify_tools(paths: dict, pins: dict, *, runner=probe) -> dict:
    identities = {}
    for name, switch, version in [('cmake', '--version', pins['cmake_version']),
                                  ('ninja', '--version', pins['ninja_version']),
                                  ('python', '--version', 'Python ' + pins['python_version'])]:
        output = runner([paths[name], switch])
        if name == 'python':
            matched = re.search(r'^' + re.escape(version) + r'\.\d+\b', output)
        else:
            matched = re.search(r'(?<![0-9.])' + re.escape(version) + r'(?![0-9.])', output)
        if not matched:
            raise ValueError(f'{name}_version_mismatch')
        identities[name] = {'path': paths[name], 'version_output': output,
                            'sha256': file_hash(Path(paths[name]))}
    output = runner([paths['git'], '--version'])
    if not output.startswith('git version '):
        raise ValueError('git_version_unknown')
    identities['git'] = {'path': paths['git'], 'version_output': output,
                         'sha256': file_hash(Path(paths['git']))}
    return identities


def verify_ports(vcpkg: Path, pins: dict) -> dict:
    status_path = checked_path(vcpkg / 'installed/vcpkg/status')
    records = {}
    for block in re.split(r'\r?\n\r?\n', status_path.read_text(encoding='utf-8')):
        fields = {}
        for line in block.splitlines():
            if ': ' in line:
                key, value = line.split(': ', 1)
                fields[key] = value
        if fields.get('Architecture') == 'x64-windows' and 'Feature' not in fields:
            name = fields.get('Package')
            if name in records:
                raise ValueError(f'vcpkg_port_duplicate:{name}')
            records[name] = fields
    verified = {}
    for package, pin in pins['ports'].items():
        row = records.get(package)
        revision = row.get('Port-Version', '0') if row else ''
        if (not row or row.get('Version') != pin['version']
                or not revision.isdecimal() or int(revision) != pin['port_version']
                or row.get('Status') != 'install ok installed'):
            raise ValueError(f'vcpkg_port_mismatch:{package}')
        verified[package] = {'version': row['Version'], 'port_version': int(revision)}
    return verified


def verify_dependency_dlls(sdk: Path, vcpkg: Path, policy: dict) -> list[dict]:
    records = []
    for kind, root, pins in (
            ('sdk', sdk / 'bin', policy['sdk_dlls']),
            ('vcpkg', vcpkg / 'installed/x64-windows/bin', policy['vcpkg_dlls'])):
        for pin in pins:
            path = checked_path(root / pin['name'])
            if path.stat().st_size != pin['size_bytes'] or file_hash(path) != pin['sha256']:
                raise ValueError(f'{kind}_dll_identity_mismatch:{pin["name"]}')
            records.append({'kind': kind, 'path': str(path), **pin})
    return records


def verify_cache(cache: Path, expected: dict[str, str]) -> dict[str, str]:
    cache = checked_path(cache)
    values = {}
    for line in cache.read_text(encoding='utf-8', errors='replace').splitlines():
        if line and not line.startswith(('#', '//')) and ':' in line and '=' in line:
            key, tail = line.split(':', 1)
            if key in values:
                raise ValueError(f'cache_duplicate_key:{key}')
            values[key] = tail.split('=', 1)[1]
    for key, value in expected.items():
        actual = values.get(key)
        if (actual is None or (ntpath.normcase(ntpath.normpath(actual)) !=
                ntpath.normcase(ntpath.normpath(value)) if key in _CACHE_PATH_KEYS
                else actual != value)):
            raise ValueError(f'cache_identity_mismatch:{key}')
    return {key: values[key] for key in expected}
