"""Build a reviewed native GUFO source tree; never stage or run the result."""

from __future__ import annotations

import argparse
import base64
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from . import build_identity as identity
from . import runtime_package
from .winjob import OwnedProcess


GIB = 1024 ** 3
RAM_FLOOR = 24 * GIB
DISK_FLOOR = 25 * GIB
SAMPLE_MAX_AGE_SECONDS = 5
CONFIGURE_DEADLINE_SECONDS = 45 * 60
BUILD_DEADLINE_SECONDS = 6 * 60 * 60


def validate_jobs(jobs: int) -> int:
    if type(jobs) is not int or jobs not in (1, 2):
        raise ValueError('jobs_must_be_integer_1_or_2')
    return jobs


def cache_values(paths: dict[str, str], head: str) -> dict[str, str]:
    sdk, vcpkg = paths['sdk'], paths['vcpkg']
    return {
        'CMAKE_BUILD_TYPE': 'RelWithDebInfo', 'BUILD_TESTING': 'ON',
        'GUFO_BUILD_TOOLS': 'OFF', 'ENGINE_ENABLE_HIP': 'ON',
        'CMAKE_HIP_ARCHITECTURES': 'gfx1151',
        'CMAKE_HIP_FLAGS_RELWITHDEBINFO': '-O2 -DNDEBUG -g0',
        'CMAKE_C_COMPILER': sdk + '/lib/llvm/bin/clang.exe',
        'CMAKE_CXX_COMPILER': sdk + '/lib/llvm/bin/clang++.exe',
        'CMAKE_HIP_COMPILER': sdk + '/lib/llvm/bin/clang++.exe',
        'CMAKE_PREFIX_PATH': sdk, 'CMAKE_LINKER_TYPE': 'LLD',
        'CMAKE_TOOLCHAIN_FILE': vcpkg + '/scripts/buildsystems/vcpkg.cmake',
        'VCPKG_TARGET_TRIPLET': 'x64-windows', 'GUFO_VERSION': head,
        'CMAKE_MAKE_PROGRAM': paths['ninja'],
        'Python3_EXECUTABLE': paths['python'],
    }


def configure_argv(paths: dict[str, str], values: dict[str, str]) -> list[str]:
    return [paths['cmake'], '-S', paths['source'], '-B', paths['build'], '-G', 'Ninja',
            *(f'-D{key}={value}' for key, value in values.items())]


def build_argv(paths: dict[str, str], jobs: int) -> list[str]:
    validate_jobs(jobs)
    return [paths['cmake'], '--build', paths['build'], '--target', 'gufo',
            '--parallel', str(jobs)]


def _cache_proof(paths: dict[str, str], values: dict[str, str]) -> dict[str, str]:
    return {**values, 'CMAKE_HOME_DIRECTORY': paths['source'],
            'CMAKE_CACHEFILE_DIR': paths['build'], 'CMAKE_GENERATOR': 'Ninja'}


def child_environment(paths: dict[str, str], inherited: dict[str, str]) -> dict[str, str]:
    env = dict(inherited)
    prefix = [paths['sdk'] + '/bin', paths['sdk'] + '/lib/llvm/bin',
              str(Path(paths['ninja']).parent)]
    env['PATH'] = os.pathsep.join([*prefix, env.get('PATH', '')])
    env['HIP_PATH'] = paths['sdk']
    env['HIP_DEVICE_LIB_PATH'] = paths['sdk'] + '/lib/llvm/amdgcn/bitcode'
    env['VCPKG_MANIFEST_MODE'] = 'OFF'
    env['VCPKG_MANIFEST_INSTALL'] = 'OFF'
    return env


class _MemoryStatus(ctypes.Structure):
    _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]


def sample_resources(build_parent: Path) -> dict:
    if os.name != 'nt':
        raise ValueError('Windows_resource_sample_required')
    memory = _MemoryStatus()
    memory.dwLength = ctypes.sizeof(memory)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        raise OSError('GlobalMemoryStatusEx_failed')
    return {'available_ram_bytes': int(memory.ullAvailPhys),
            'free_disk_bytes': shutil.disk_usage(build_parent).free,
            'sampled_at': time.monotonic()}


def check_resources(sample: dict, *, now: float | None = None) -> dict:
    current = time.monotonic() if now is None else now
    if (type(sample) is not dict or type(sample.get('available_ram_bytes')) is not int
            or type(sample.get('free_disk_bytes')) is not int
            or not isinstance(sample.get('sampled_at'), (int, float))
            or not 0 <= current - sample['sampled_at'] <= SAMPLE_MAX_AGE_SECONDS
            or sample['available_ram_bytes'] < RAM_FLOOR
            or sample['free_disk_bytes'] < DISK_FLOOR):
        raise ValueError('resource_floor_or_sample_unavailable')
    return sample


def run_owned(argv: list[str], *, cwd: Path, env: dict[str, str], log_prefix: Path,
              deadline_seconds: int | float, owner_factory=OwnedProcess,
              resources=None) -> dict:
    if resources is None:
        resources = lambda: sample_resources(log_prefix.parent)
    check_resources(resources())
    stdout = log_prefix.with_name(log_prefix.name + '.stdout.log')
    stderr = log_prefix.with_name(log_prefix.name + '.stderr.log')
    start = time.monotonic()
    with owner_factory(argv, cwd=cwd, env=env, stdout_path=stdout,
                       stderr_path=stderr) as child:
        child.resume()
        while True:
            check_resources(resources())
            remaining = deadline_seconds - (time.monotonic() - start)
            if remaining <= 0:
                raise TimeoutError(f'command_deadline_exceeded:{argv[0]}')
            if child.wait(min(2000, max(1, int(remaining * 1000)))):
                code = child.exit_code()
                break
        if code != 0:
            raise RuntimeError(f'command_exit_{code}:{Path(argv[0]).name}')
    return {'argv': argv, 'exit_code': code, 'stdout_log': str(stdout),
            'stderr_log': str(stderr), 'duration_seconds': time.monotonic() - start}


def write_manifest(path: Path, record: dict) -> None:
    pending = path.with_name(path.name + '.pending')
    if pending.exists():
        raise ValueError(f'pending_manifest_exists:{pending}')
    with pending.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write('\n')
    os.replace(pending, path)


def _vcvars_environment(paths: dict[str, str], pins: dict) -> tuple[dict, dict]:
    # The complete environment crosses only an in-memory pipe into this process.
    # It is never printed or written to a manifest/log.
    system = Path(os.environ['SystemRoot'])
    cmd = identity.checked_path(system / 'System32/cmd.exe')
    powershell = identity.checked_path(system / 'System32/WindowsPowerShell/v1.0/powershell.exe')
    if any(c in paths['vcvars'] for c in '%!"&|<>^\r\n'):
        raise ValueError('unsupported_shell_path:vcvars')
    quoted_cmd = str(cmd).replace("'", "''")
    quoted_vcvars = paths['vcvars'].replace("'", "''")
    script = (f"$lines = & '{quoted_cmd}' /d /c ('\"' + '{quoted_vcvars}' + '\" >nul && set'); "
              "if ($LASTEXITCODE -ne 0) { exit 3 }; "
              "$values = @{}; foreach ($line in $lines) { "
              "if ($line -match '^([^=]+)=(.*)$') { $values[$matches[1]] = $matches[2] } }; "
              "ConvertTo-Json -InputObject $values -Compress")
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    completed = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive',
                                '-EncodedCommand', encoded],
                               capture_output=True, text=True, timeout=60,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if completed.returncode:
        raise ValueError(f'vcvars_import_failed:{completed.returncode}')
    try:
        env = {key.upper(): value for key, value in json.loads(completed.stdout).items()}
    except json.JSONDecodeError as error:
        raise ValueError('vcvars_environment_invalid') from error
    selected = {key: env.get(key.upper(), '') for key in ('VisualStudioVersion',
                'VCToolsVersion', 'VCToolsInstallDir', 'WindowsSdkDir', 'WindowsSDKVersion')}
    if (selected['VisualStudioVersion'] != pins['visual_studio_version']
            or selected['VCToolsVersion'] != pins['vc_tools_version']
            or selected['WindowsSDKVersion'].rstrip('\\/') != pins['windows_sdk_version']
            or not Path(selected['VCToolsInstallDir']).is_dir()
            or not Path(selected['WindowsSdkDir']).is_dir()):
        raise ValueError('vcvars_toolchain_identity_mismatch')
    selected['vcvars_path'] = paths['vcvars']
    selected['vcvars_sha256'] = identity.file_hash(Path(paths['vcvars']))
    return env, selected


def _canonical_paths(args) -> dict[str, str]:
    roots = identity.validate_roots(args.source_dir, args.build_dir, args.sdk_dir,
                                    args.vcpkg_dir)
    values = {key: path.as_posix() for key, path in roots.items()}
    for key, value in [('python', args.python_exe), ('git', args.git_exe),
                       ('vcvars', args.vcvars64), ('cmake', args.cmake_exe),
                       ('ninja', args.ninja_exe)]:
        values[key] = identity.checked_path(value).as_posix()
    identity.checked_path(roots['vcpkg'] / 'scripts/buildsystems/vcpkg.cmake')
    return values


def build_gufo(args, *, pins=None, owner_factory=OwnedProcess, resources=None,
               vcvars_loader=None) -> dict:
    """Internal injection seams support offline tests; no bypass reaches the CLI."""
    jobs = validate_jobs(args.jobs)
    pins = identity.load_pins() if pins is None else pins
    paths = _canonical_paths(args)
    build = Path(paths['build'])
    source = Path(paths['source'])
    git = Path(paths['git'])
    source_record = identity.verify_git(source, git, remote=pins['source_remote'],
        head=None, tree=pins['source_tree'], base=pins['source_base'])
    source_record.update(identity.verify_reviewed_patch(pins))
    vcpkg_record = identity.verify_git(Path(paths['vcpkg']), git,
        remote='https://github.com/microsoft/vcpkg.git', head=pins['vcpkg_commit'],
        tree=None,
        base=pins['vcpkg_commit'])
    sdk_record = identity.verify_sdk(Path(paths['sdk']), pins)
    tools_record = identity.verify_tools(paths, pins)
    ports = identity.verify_ports(Path(paths['vcpkg']), pins)
    dependency_policy = runtime_package.load_policy()
    dll_records = identity.verify_dependency_dlls(Path(paths['vcpkg']), dependency_policy)
    loader = _vcvars_environment if vcvars_loader is None else vcvars_loader
    vcenv, vc_record = loader(paths, pins)
    env = child_environment(paths, vcenv)
    values = cache_values(paths, source_record['head'])
    check_resources((resources or (lambda: sample_resources(build.parent)))())

    manifest_path = build / 'build-manifest.json'
    if build.exists() and any(build.iterdir()):
        if not manifest_path.is_file():
            raise ValueError(f'foreign_build_dir:{build}')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        expected_input = {'paths': paths, 'source': source_record, 'vcpkg': vcpkg_record,
                          'sdk': sdk_record, 'tools': tools_record, 'vcvars': vc_record,
                          'ports': ports, 'dependency_dlls': dll_records,
                          'build_pins_sha256': identity.file_hash(identity.PINS_PATH),
                          'runtime_pins_sha256': identity.file_hash(runtime_package.POLICY_PATH)}
        if (manifest.get('status') != 'built' or manifest.get('inputs') != expected_input
                or manifest.get('jobs') != jobs or manifest.get('target') != 'gufo'
                or manifest.get('cache_expected') != values
                or manifest.get('runtimeStaged') is not False
                or manifest.get('runtime_qualified') is not False):
            raise ValueError('foreign_or_incomplete_build_dir')
        effective = identity.verify_cache(build / 'CMakeCache.txt', _cache_proof(paths, values))
        if manifest.get('cache_effective') != effective:
            raise ValueError('foreign_or_incomplete_build_dir')
        exe = identity.checked_path(build / 'gufo.exe')
        if manifest.get('executable') != {'path': str(exe), 'size_bytes': exe.stat().st_size,
                                         'sha256': identity.file_hash(exe)}:
            raise ValueError('built_executable_identity_mismatch')
        return manifest
    else:
        identity.validate_build_dir(build)
        build.mkdir(parents=False, exist_ok=True)

    record = {'schema': 1, 'kind': 'gufo-native-build', 'status': 'failed',
              'created_utc': datetime.now(timezone.utc).isoformat(),
              'runtimeStaged': False, 'runtime_qualified': False,
              'target': 'gufo', 'jobs': jobs,
              'inputs': {'paths': paths, 'source': source_record,
                         'vcpkg': vcpkg_record, 'sdk': sdk_record,
                         'tools': tools_record, 'vcvars': vc_record,
                         'ports': ports, 'dependency_dlls': dll_records,
                         'build_pins_sha256': identity.file_hash(identity.PINS_PATH),
                         'runtime_pins_sha256': identity.file_hash(runtime_package.POLICY_PATH)},
              'cache_expected': values, 'commands': []}
    write_manifest(manifest_path, record)
    try:
        command = configure_argv(paths, values)
        record['commands'].append({'argv': command,
            'stdout_log': str(build / 'configure.stdout.log'),
            'stderr_log': str(build / 'configure.stderr.log'), 'status': 'started'})
        write_manifest(manifest_path, record)
        result = run_owned(command, cwd=source, env=env,
            log_prefix=build / 'configure', deadline_seconds=CONFIGURE_DEADLINE_SECONDS,
            owner_factory=owner_factory, resources=resources)
        record['commands'][-1].update(result, status='succeeded')
        record['cache_effective'] = identity.verify_cache(build / 'CMakeCache.txt',
                                                          _cache_proof(paths, values))
        write_manifest(manifest_path, record)
        command = build_argv(paths, jobs)
        record['commands'].append({'argv': command,
            'stdout_log': str(build / 'build.stdout.log'),
            'stderr_log': str(build / 'build.stderr.log'), 'status': 'started'})
        write_manifest(manifest_path, record)
        result = run_owned(command, cwd=source, env=env,
            log_prefix=build / 'build', deadline_seconds=BUILD_DEADLINE_SECONDS,
            owner_factory=owner_factory, resources=resources)
        record['commands'][-1].update(result, status='succeeded')
        final_source = identity.verify_git(source, git, remote=pins['source_remote'],
            head=None, tree=pins['source_tree'], base=pins['source_base'])
        final_source.update(identity.verify_reviewed_patch(pins))
        final_vcpkg = identity.verify_git(Path(paths['vcpkg']), git,
            remote='https://github.com/microsoft/vcpkg.git', head=pins['vcpkg_commit'],
            tree=None, base=pins['vcpkg_commit'])
        final_inputs = {'paths': paths, 'source': final_source, 'vcpkg': final_vcpkg,
                        'sdk': identity.verify_sdk(Path(paths['sdk']), pins),
                        'tools': identity.verify_tools(paths, pins),
                        'vcvars': {**vc_record,
                                   'vcvars_sha256': identity.file_hash(Path(paths['vcvars']))},
                        'ports': identity.verify_ports(Path(paths['vcpkg']), pins),
                        'dependency_dlls': identity.verify_dependency_dlls(
                            Path(paths['vcpkg']), dependency_policy),
                        'build_pins_sha256': identity.file_hash(identity.PINS_PATH),
                        'runtime_pins_sha256': identity.file_hash(runtime_package.POLICY_PATH)}
        if final_inputs != record['inputs']:
            raise ValueError('build_inputs_changed_during_compile')
        check_resources((resources or (lambda: sample_resources(build.parent)))())
        exe = identity.checked_path(build / 'gufo.exe')
        record['executable'] = {'path': str(exe), 'size_bytes': exe.stat().st_size,
                                'sha256': identity.file_hash(exe)}
        record['status'] = 'built'
    except BaseException as error:
        record['error'] = f'{type(error).__name__}:{error}'
        if record['commands'] and record['commands'][-1]['status'] == 'started':
            record['commands'][-1]['status'] = 'failed'
            match = re.search(r'command_exit_(\d+)', str(error))
            if match:
                record['commands'][-1]['exit_code'] = int(match.group(1))
        write_manifest(manifest_path, record)
        raise
    write_manifest(manifest_path, record)
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Reviewed native GUFO Windows build')
    for name in ('python-exe', 'git-exe', 'source-dir', 'build-dir', 'sdk-dir',
                 'vcpkg-dir', 'vcvars64', 'cmake-exe', 'ninja-exe'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args(argv)
    try:
        record = build_gufo(args)
    except (ValueError, OSError, RuntimeError, TimeoutError) as error:
        print(f'refused: {error}', file=sys.stderr)
        return 2
    print(json.dumps({'status': record['status'], 'manifest': str(Path(args.build_dir) /
                                                               'build-manifest.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
