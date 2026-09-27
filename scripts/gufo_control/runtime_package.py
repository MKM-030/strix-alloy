"""Static, pinned GUFO runtime staging. This module never executes GUFO."""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
from uuid import uuid4


POLICY_PATH = Path(__file__).resolve().parents[2] / 'config/gufo-runtime-pins.json'
REVIEWED_POLICY_SHA256 = 'C363650BDFF6B79B3482B198D7EFBEE03E25C9D52A298B51B9B54724316F6B63'
SERVICE_POLICY_PATH = Path(__file__).resolve().parents[2] / 'config/gufo-service-runtime-pins.json'
REVIEWED_SERVICE_POLICY_SHA256 = '5AA64C7E718619E4654DCF4B5997D77AAE47B41611DCAA897020224FD0F0A5E8'
POLICY_VARIANTS = {
    'baseline': (POLICY_PATH, REVIEWED_POLICY_SHA256,
                 'cff564964e8506c0abb3e530cecb55332187ac6c',
                 42429952, 'E7F5B899C54C747EE5038C0598016394D2A70F25EE69AFBB1E02859FD223D943'),
    'service-ar4k-v1': (SERVICE_POLICY_PATH, REVIEWED_SERVICE_POLICY_SHA256,
                        '139aa9c58dadcb75c1bd0741aad0823fc65a0547',
                        42439168, '66798D3BCAD27B7E2BEC16980B225F83CC3F017FAD9088ADA8D64D604BC4F209'),
}
RESERVE_BYTES = 1 << 30
REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
_SDK_NAMES = ('amdhip64_7.dll', 'amd_comgr.dll', 'rocm_kpack.dll', 'hipblas.dll',
              'rocsolver.dll', 'rocblas.dll', 'libhipblaslt.dll',
              'libtensilelite-host.dll', 'origami.dll')
_VCPKG_NAMES = ('icudt78.dll', 'icuin78.dll', 'icuuc78.dll', 'jpeg62.dll',
                'libcrypto-3-x64.dll', 'libcurl.dll', 'libpng16.dll', 'z.dll')
_TREE_NAMES = ('hipblaslt', 'rocblas')


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _valid_hash(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789ABCDEF' for c in value)


def _valid_record(row, *, named=True) -> bool:
    keys = {'size_bytes', 'sha256', 'name' if named else 'path'}
    return (type(row) is dict and set(row) == keys
            and type(row['size_bytes']) is int and row['size_bytes'] >= 0
            and _valid_hash(row['sha256']) and type(row['name' if named else 'path']) is str)


def _variant_pin(variant: str) -> tuple:
    if type(variant) is not str or variant not in POLICY_VARIANTS:
        raise ValueError(f'unknown_runtime_variant:{variant}')
    return POLICY_VARIANTS[variant]


def load_policy(*, variant: str = 'baseline') -> dict:
    """Read one of the two reviewed policies by closed variant name."""
    policy_path, policy_sha256, source_commit, exe_size, exe_sha256 = _variant_pin(variant)
    raw = policy_path.read_bytes()
    if _digest_bytes(raw) != policy_sha256:
        raise ValueError('runtime_policy_changed_unreviewed')
    try:
        policy = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('runtime_policy_invalid_json') from error
    if (type(policy) is not dict or set(policy) != {'schema', 'kind', 'source_commit',
            'sdk_version', 'executable', 'sdk_dlls', 'vcpkg_dlls', 'trees', 'host_openmp'}
            or type(policy['schema']) is not int or policy['schema'] != 1
            or policy['kind'] != 'gufo-native-static-runtime'
            or policy['source_commit'] != source_commit
            or policy['sdk_version'] != '10.2.0'):
        raise ValueError('runtime_policy_schema_or_identity_invalid')
    exe = policy['executable']
    if not _valid_record(exe) or exe['name'] != 'gufo.exe' or (exe['size_bytes'], exe['sha256']) != (
            exe_size, exe_sha256):
        raise ValueError('runtime_policy_executable_invalid')
    for key, names in (('sdk_dlls', _SDK_NAMES), ('vcpkg_dlls', _VCPKG_NAMES)):
        rows = policy[key]
        if (type(rows) is not list or len(rows) != len(names)
                or tuple(row.get('name') for row in rows if type(row) is dict) != names
                or not all(_valid_record(row) for row in rows)):
            raise ValueError(f'runtime_policy_{key}_invalid')
    trees = policy['trees']
    if (type(trees) is not list or len(trees) != 2
            or tuple(row.get('name') for row in trees if type(row) is dict) != _TREE_NAMES):
        raise ValueError('runtime_policy_trees_invalid')
    for row, expected in zip(trees, ((100, 13164894, '79EB8214145013B0F9CAFDD128942B94542C10FCEFB80B827472940EB4D4BB56'),
                                     (150, 17243350, 'D160DEE878CB2DF152A39DB55506085C2918CAA83041C61E58096EA8B8E64D06'))):
        if (type(row) is not dict or set(row) != {'name', 'count', 'bytes', 'digest'}
                or type(row['count']) is not int or type(row['bytes']) is not int
                or (row['count'], row['bytes'], row['digest']) != expected):
            raise ValueError('runtime_policy_tree_invalid')
    host = policy['host_openmp']
    if (not _valid_record(host) or host['name'] != 'libomp140.x86_64.dll'
            or (host['size_bytes'], host['sha256']) != (
                634936, '9AB1CB787E52B2A36133899C01C1DB1F876067D1471CD224EAD85F40A8152B99')):
        raise ValueError('runtime_policy_host_invalid')
    return policy


def _is_reparse(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & REPARSE)


def _check_components(path: Path) -> None:
    """Reject links/reparse points even in existing ancestors of a missing path."""
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.exists() or current.is_symlink():
            if _is_reparse(current):
                raise ValueError(f'reparse_point_refused:{current}')
        else:
            break


def _root(path: Path, *, must_exist: bool) -> Path:
    path = Path(path)
    raw = str(path)
    if (not path.is_absolute() or raw.startswith('\\\\') or raw.startswith('//')
            or raw.startswith('\\?\\') or raw.startswith('\\.\\')):
        raise ValueError(f'absolute_local_path_required:{raw}')
    _check_components(path)
    resolved = path.resolve(strict=False)
    if not resolved.is_absolute() or str(resolved).startswith('\\\\'):
        raise ValueError(f'local_path_required:{path}')
    if must_exist and not resolved.is_dir():
        raise ValueError(f'directory_missing:{resolved}')
    return resolved


def _canonical_historical_root(value: str) -> bool:
    """Validate recorded provenance syntax without accessing an old source tree."""
    if type(value) is not str or not value or value.startswith(('\\\\', '//')):
        return False
    path = Path(value)
    return (path.is_absolute() and str(path) == value
            and not any(part in ('.', '..') for part in path.parts)
            and not any(part.endswith((' ', '.')) for part in path.parts[1:]))


def _owned_directory(path: Path, identity: tuple[int, int]) -> None:
    _check_components(path)
    if (not path.is_dir() or _is_reparse(path)
            or (path.stat().st_dev, path.stat().st_ino) != identity):
        raise ValueError(f'staging_directory_changed:{path}')


def _owned_destination(staging_root: Path, identity: tuple[int, int],
                       destination: Path) -> None:
    _owned_directory(staging_root, identity)
    root_parts = tuple(part.casefold() for part in staging_root.parts)
    destination_parts = tuple(part.casefold() for part in destination.parts)
    if destination_parts[:len(root_parts)] != root_parts or len(destination_parts) <= len(root_parts):
        raise ValueError(f'destination_outside_staging:{destination}')
    _check_components(destination.parent)


def _overlap(a: Path, b: Path) -> bool:
    left = tuple(part.casefold() for part in a.parts)
    right = tuple(part.casefold() for part in b.parts)
    return left[:len(right)] == right or right[:len(left)] == left


def _relative(value: str) -> str:
    if (type(value) is not str or not value or value.startswith('/') or '\\' in value
            or ':' in value or value.startswith('//')):
        raise ValueError(f'invalid_payload_path:{value}')
    parts = value.split('/')
    if any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in parts):
        raise ValueError(f'invalid_payload_path:{value}')
    return value


def _check_collisions(paths) -> None:
    seen = set()
    for value in paths:
        value = _relative(value)
        folded = value.casefold()
        if folded in seen:
            raise ValueError(f'case_colliding_path:{value}')
        seen.add(folded)


def _checked_file(path: Path, expected: dict) -> dict:
    _check_components(path)
    if not path.is_file() or _is_reparse(path):
        raise ValueError(f'file_missing_or_nonregular:{path}')
    info = path.stat()
    if info.st_size != expected['size_bytes'] or _hash_file(path) != expected['sha256']:
        raise ValueError(f'file_identity_mismatch:{path}')
    return {'size_bytes': info.st_size, 'sha256': expected['sha256']}


def tree_digest(records) -> str:
    ordered = sorted(records, key=lambda row: row['path'])
    text = ''.join(f"{row['path']}|{row['size_bytes']}|{row['sha256'].lower()}\n"
                   for row in ordered)
    return _digest_bytes(text.encode('utf-8'))


def _tree_files(tree: Path, name: str) -> list[dict]:
    base = tree / 'library/gfx1151'
    _check_components(base)
    if not base.is_dir():
        raise ValueError(f'tree_missing:{base}')
    rows = []
    for item in base.rglob('*'):
        _check_components(item)
        if _is_reparse(item):
            raise ValueError(f'tree_reparse:{item}')
        if item.is_dir():
            continue
        if not item.is_file():
            raise ValueError(f'tree_nonfile:{item}')
        relative = _relative(item.relative_to(tree).as_posix())
        rows.append({'path': f'{name}/{relative}', 'size_bytes': item.stat().st_size,
                     'sha256': _hash_file(item)})
    _check_collisions(row['path'] for row in rows)
    return sorted(rows, key=lambda row: row['path'])


def _check_tree(rows: list[dict], pin: dict, name: str) -> dict:
    local = [{'path': row['path'][len(name)+1:], 'size_bytes': row['size_bytes'],
              'sha256': row['sha256']} for row in rows]
    actual = {'name': name, 'count': len(rows),
              'bytes': sum(row['size_bytes'] for row in rows),
              'digest': tree_digest(local)}
    if actual != pin:
        raise ValueError(f'tree_identity_mismatch:{name}')
    return actual


def _host_openmp_record(policy: dict) -> dict:
    if os.name != 'nt':
        raise ValueError('Windows_host_required')
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not length or length >= len(buffer):
        raise OSError('GetSystemDirectoryW_failed')
    path = _root(Path(buffer.value), must_exist=True) / policy['host_openmp']['name']
    return {'path': str(path), **_checked_file(path, policy['host_openmp'])}


def _free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def _inventory(build_dir: Path, sdk_dir: Path, vcpkg_dir: Path, policy: dict) -> dict:
    build = _root(build_dir, must_exist=True)
    sdk = _root(sdk_dir, must_exist=True)
    vcpkg = _root(vcpkg_dir, must_exist=True)
    for first, second in ((build, sdk), (build, vcpkg), (sdk, vcpkg)):
        if _overlap(first, second):
            raise ValueError('input_roots_overlap')
    version = sdk / '.info/version'
    _check_components(version)
    if not version.is_file() or version.read_text(encoding='utf-8').strip() != policy['sdk_version']:
        raise ValueError('sdk_version_mismatch')
    files = []
    exe = policy['executable']
    _checked_file(build / exe['name'], exe)
    files.append({'path': exe['name'], 'size_bytes': exe['size_bytes'], 'sha256': exe['sha256']})
    for record in policy['sdk_dlls']:
        _checked_file(sdk / 'bin' / record['name'], record)
        files.append({'path': record['name'], 'size_bytes': record['size_bytes'], 'sha256': record['sha256']})
    for record in policy['vcpkg_dlls']:
        installed = vcpkg / 'installed/x64-windows/bin' / record['name']
        _checked_file(installed, record)
        _checked_file(build / record['name'], record)
        files.append({'path': record['name'], 'size_bytes': record['size_bytes'], 'sha256': record['sha256']})
    trees = []
    for pin in policy['trees']:
        rows = _tree_files(sdk / 'bin' / pin['name'], pin['name'])
        trees.append(_check_tree(rows, pin, pin['name']))
        files.extend(rows)
    _check_collisions(row['path'] for row in files)
    host = _host_openmp_record(policy)
    if (host['size_bytes'], host['sha256']) != (policy['host_openmp']['size_bytes'],
                                                policy['host_openmp']['sha256']):
        raise ValueError('host_openmp_mismatch')
    return {'sources': {'build_dir': str(build), 'sdk_dir': str(sdk),
                        'vcpkg_dir': str(vcpkg)}, 'files': files, 'trees': trees,
            'host_prerequisites': [host]}


def inventory_sources(build_dir: Path, sdk_dir: Path, vcpkg_dir: Path,
                      *, variant: str = 'baseline') -> dict:
    _variant_pin(variant)
    return _inventory(build_dir, sdk_dir, vcpkg_dir, load_policy(variant=variant))


def _source_path(row: dict, inventory: dict, policy: dict) -> Path:
    sources = inventory['sources']
    name = row['path']
    if name == policy['executable']['name'] or name in _VCPKG_NAMES:
        return Path(sources['build_dir']) / name
    return Path(sources['sdk_dir']) / 'bin' / name


def _copy_file_exclusive(source: Path, destination: Path,
                         staging_root: Path, staging_identity: tuple[int, int]) -> None:
    _owned_destination(staging_root, staging_identity, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _owned_destination(staging_root, staging_identity, destination)
    with source.open('rb') as reader, destination.open('xb') as writer:
        shutil.copyfileobj(reader, writer, length=1024 * 1024)


def _scan_package(runtime: Path) -> list[str]:
    paths = []
    for item in runtime.rglob('*'):
        _check_components(item)
        if _is_reparse(item):
            raise ValueError(f'package_reparse:{item}')
        if item.is_file():
            paths.append(_relative(item.relative_to(runtime).as_posix()))
        elif not item.is_dir():
            raise ValueError(f'package_nonfile:{item}')
    _check_collisions(paths)
    return paths


def _verify_payload(runtime: Path, files: list[dict], trees: list[dict]) -> None:
    expected = [row['path'] for row in files] + ['runtime-manifest.json']
    _check_collisions(expected)
    actual = _scan_package(runtime)
    if {path.casefold() for path in actual} != {path.casefold() for path in expected}:
        raise ValueError('runtime_payload_set_mismatch')
    if set(actual) != set(expected):
        raise ValueError('runtime_payload_case_mismatch')
    for row in files:
        _checked_file(runtime / row['path'], row)
    for pin in trees:
        name = pin['name']
        rows = [row for row in files if row['path'].startswith(f'{name}/')]
        _check_tree(rows, pin, name)


def _validate_manifest(manifest: dict, policy: dict, policy_sha256: str) -> None:
    keys = {'schema', 'kind', 'status', 'created_utc', 'expected_source_commit',
            'sdk_version', 'policy_sha256', 'sources', 'files', 'trees',
            'host_prerequisites', 'runtime_qualified'}
    if type(manifest) is not dict or set(manifest) != keys:
        raise ValueError('runtime_manifest_schema_invalid')
    if (type(manifest['schema']) is not int or manifest['schema'] != 1
            or manifest['kind'] != 'gufo-native-static-runtime'
            or manifest['status'] != 'staged-static-only'
            or manifest['runtime_qualified'] is not False
            or manifest['expected_source_commit'] != policy['source_commit']
            or manifest['sdk_version'] != policy['sdk_version']
            or manifest['policy_sha256'] != policy_sha256):
        raise ValueError('runtime_manifest_identity_invalid')
    try:
        created = datetime.fromisoformat(manifest['created_utc'])
    except (TypeError, ValueError) as error:
        raise ValueError('runtime_manifest_time_invalid') from error
    if created.utcoffset() is None or created.utcoffset().total_seconds() != 0:
        raise ValueError('runtime_manifest_time_not_utc')
    sources = manifest['sources']
    if (type(sources) is not dict or set(sources) != {'build_dir', 'sdk_dir', 'vcpkg_dir'}
            or not all(_canonical_historical_root(value) for value in sources.values())):
        raise ValueError('runtime_manifest_sources_invalid')
    files = manifest['files']
    if type(files) is not list or not all(_valid_record(row, named=False) for row in files):
        raise ValueError('runtime_manifest_files_invalid')
    _check_collisions(row['path'] for row in files)
    expected_named = [policy['executable'], *policy['sdk_dlls'], *policy['vcpkg_dlls']]
    expected = {row['name']: (row['size_bytes'], row['sha256']) for row in expected_named}
    flat = [row for row in files if '/' not in row['path']]
    if ({row['path']: (row['size_bytes'], row['sha256']) for row in flat} != expected
            or len(flat) != len(expected)):
        raise ValueError('runtime_manifest_dll_set_invalid')
    trees = manifest['trees']
    if (type(trees) is not list or len(trees) != len(policy['trees'])
            or not all(type(row) is dict and set(row) == {'name', 'count', 'bytes', 'digest'}
                       and type(row['name']) is str and type(row['digest']) is str
                       and type(row['count']) is int and type(row['bytes']) is int
                       for row in trees)
            or trees != policy['trees']):
        raise ValueError('runtime_manifest_tree_records_invalid')
    for pin in trees:
        name = pin['name']
        rows = [row for row in files if row['path'].startswith(f'{name}/')]
        if not all(row['path'].startswith(f'{name}/library/gfx1151/') for row in rows):
            raise ValueError('runtime_manifest_tree_path_invalid')
        _check_tree(rows, pin, name)
    if len(files) != len(flat) + sum(row['count'] for row in trees):
        raise ValueError('runtime_manifest_extra_file_records')
    hosts = manifest['host_prerequisites']
    if (type(hosts) is not list or len(hosts) != 1
            or not _valid_record(hosts[0], named=False)
            or (hosts[0]['size_bytes'], hosts[0]['sha256']) != (
                policy['host_openmp']['size_bytes'], policy['host_openmp']['sha256'])):
        raise ValueError('runtime_manifest_host_invalid')


def verify_runtime(runtime_dir: Path, *, variant: str = 'baseline') -> dict:
    policy_sha256 = _variant_pin(variant)[1]
    policy = load_policy(variant=variant)
    runtime = _root(runtime_dir, must_exist=True)
    manifest_path = runtime / 'runtime-manifest.json'
    _check_components(manifest_path)
    if not manifest_path.is_file() or _is_reparse(manifest_path):
        raise ValueError('runtime_manifest_missing')
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('runtime_manifest_json_invalid') from error
    _validate_manifest(manifest, policy, policy_sha256)
    host = _host_openmp_record(policy)
    if (host['size_bytes'], host['sha256']) != (
            policy['host_openmp']['size_bytes'], policy['host_openmp']['sha256']):
        raise ValueError('host_openmp_mismatch')
    _verify_payload(runtime, manifest['files'], manifest['trees'])
    return manifest


def stage_runtime(build_dir: Path, sdk_dir: Path, vcpkg_dir: Path,
                  runtime_dir: Path, *, variant: str = 'baseline') -> dict:
    policy_sha256 = _variant_pin(variant)[1]
    policy = load_policy(variant=variant)
    target = _root(runtime_dir, must_exist=False)
    parent = _root(target.parent, must_exist=True)
    parent_identity = (parent.stat().st_dev, parent.stat().st_ino)
    inventory = _inventory(build_dir, sdk_dir, vcpkg_dir, policy)
    for source in inventory['sources'].values():
        if _overlap(target, Path(source)):
            raise ValueError('runtime_overlaps_input')
    if target.exists():
        if not target.is_dir():
            raise ValueError('runtime_target_not_directory')
        if any(target.iterdir()):
            return verify_runtime(target, variant=variant)
        target_identity = (target.stat().st_dev, target.stat().st_ino)
    else:
        target_identity = None
    payload_bytes = sum(row['size_bytes'] for row in inventory['files'])
    if _free_bytes(parent) < payload_bytes + RESERVE_BYTES:
        raise ValueError('insufficient_runtime_free_space')
    lock = parent / f'{target.name}.stage.lock'
    _owned_directory(parent, parent_identity)
    _check_components(lock)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ValueError(f'runtime_stage_lock_exists:{lock}') from error
    lock_identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    temporary = parent / f'{target.name}.staging-{uuid4().hex}'
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(str(temporary))
        _owned_directory(parent, parent_identity)
        temporary.mkdir()
        staging_identity = (temporary.stat().st_dev, temporary.stat().st_ino)
        _owned_directory(temporary, staging_identity)
        for row in inventory['files']:
            source = _source_path(row, inventory, policy)
            destination = temporary / row['path']
            _copy_file_exclusive(source, destination, temporary, staging_identity)
            _checked_file(source, row)
            _checked_file(destination, row)
        manifest = {
            'schema': 1, 'kind': 'gufo-native-static-runtime',
            'status': 'staged-static-only',
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'expected_source_commit': policy['source_commit'],
            'sdk_version': policy['sdk_version'],
            'policy_sha256': policy_sha256,
            'sources': inventory['sources'], 'files': inventory['files'],
            'trees': inventory['trees'],
            'host_prerequisites': inventory['host_prerequisites'],
            'runtime_qualified': False,
        }
        manifest_path = temporary / 'runtime-manifest.json'
        pending = temporary / 'runtime-manifest.json.pending'
        _owned_destination(temporary, staging_identity, pending)
        with pending.open('x', encoding='utf-8') as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write('\n')
        _owned_destination(temporary, staging_identity, manifest_path)
        os.replace(pending, manifest_path)
        _owned_directory(temporary, staging_identity)
        _validate_manifest(manifest, policy, policy_sha256)
        _verify_payload(temporary, inventory['files'], inventory['trees'])
        # Recheck all sources after copying, including installed vcpkg counterparts.
        _inventory(Path(inventory['sources']['build_dir']), Path(inventory['sources']['sdk_dir']),
                   Path(inventory['sources']['vcpkg_dir']), policy)
        _owned_directory(parent, parent_identity)
        _owned_directory(temporary, staging_identity)
        if target.exists():
            current_identity = (target.stat().st_dev, target.stat().st_ino)
            if (target_identity is None or current_identity != target_identity
                    or not target.is_dir() or _is_reparse(target) or any(target.iterdir())):
                raise ValueError(f'runtime_target_appeared_or_changed:{target}')
            target.rmdir()  # Existing empty target only; never recursive.
        if target.exists():
            raise ValueError(f'runtime_target_appeared:{target}')
        _owned_directory(parent, parent_identity)
        _owned_directory(temporary, staging_identity)
        temporary.rename(target)  # Windows refuses an independently created target.
        return manifest
    except (ValueError, OSError) as error:
        raise type(error)(f'{error}; retained_staging={temporary}') from error
    finally:
        if lock.exists() and (lock.stat().st_dev, lock.stat().st_ino) == lock_identity:
            lock.unlink()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Pinned static GUFO runtime package')
    commands = parser.add_subparsers(dest='command', required=True)
    stage = commands.add_parser('stage')
    for name in ('build-dir', 'sdk-dir', 'vcpkg-dir', 'runtime-dir'):
        stage.add_argument(f'--{name}', required=True, type=Path)
    stage.add_argument('--runtime-variant', choices=tuple(POLICY_VARIANTS), default='baseline')
    verify = commands.add_parser('verify')
    verify.add_argument('--runtime-dir', required=True, type=Path)
    verify.add_argument('--runtime-variant', choices=tuple(POLICY_VARIANTS), default='baseline')
    args = parser.parse_args(argv)
    try:
        if args.command == 'stage':
            result = stage_runtime(args.build_dir, args.sdk_dir, args.vcpkg_dir,
                                   args.runtime_dir, variant=args.runtime_variant)
        else:
            result = verify_runtime(args.runtime_dir, variant=args.runtime_variant)
    except (ValueError, OSError) as error:
        print(f'refused: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
