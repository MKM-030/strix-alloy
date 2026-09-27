"""Offline contract tests for the guarded GUFO build entrypoint."""

import base64
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from gufo_control import build_identity, build_setup


class BuildIdentityTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('git'), 'Git fixture requires local Git')
    def test_exact_tree_with_independent_head_and_base_ancestor_is_accepted(self):
        git = Path(shutil.which('git'))
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder) / 'source'
            repo.mkdir()
            def run(*parts):
                result = subprocess.run([str(git), '-C', str(repo), *parts],
                                        capture_output=True, text=True, check=True)
                return result.stdout.strip()
            run('init')
            run('remote', 'add', 'origin', 'https://github.com/pixmaate/gufo.git')
            (repo / 'base.txt').write_text('base')
            run('add', '.')
            run('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
                'commit', '-m', 'base')
            base = run('rev-parse', 'HEAD')
            (repo / 'reviewed.txt').write_text('reviewed')
            run('add', '.')
            run('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
                'commit', '-m', 'reviewed content')
            reviewed_head = run('rev-parse', 'HEAD')
            reviewed_tree = run('rev-parse', 'HEAD^{tree}')
            run('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
                'commit', '--allow-empty', '-m', 'independent metadata')
            actual_head = run('rev-parse', 'HEAD')
            self.assertNotEqual(actual_head, reviewed_head)
            record = build_identity.verify_git(repo, git,
                remote='https://github.com/pixmaate/gufo.git', head=None,
                tree=reviewed_tree, base=base)
            self.assertEqual(record['head'], actual_head)
            (repo / 'untracked.txt').write_text('dirty')
            with self.assertRaisesRegex(ValueError, 'git_identity'):
                build_identity.verify_git(repo, git,
                    remote='https://github.com/pixmaate/gufo.git', head=None,
                    tree=reviewed_tree, base=base)
            (repo / 'untracked.txt').unlink()
            with self.assertRaisesRegex(ValueError, 'git_identity'):
                build_identity.verify_git(repo, git,
                    remote='https://github.com/pixmaate/gufo.git', head=None,
                    tree='0' * 40, base=base)

    def test_paths_reject_overlap_and_foreign_build_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source'
            source.mkdir()
            with self.assertRaisesRegex(ValueError, 'overlap'):
                build_identity.validate_roots(source, source / 'build', root / 'sdk', root / 'vcpkg')
            build = root / 'build'
            build.mkdir()
            (build / 'stranger.txt').write_text('keep')
            with self.assertRaisesRegex(ValueError, 'foreign_build'):
                build_identity.validate_build_dir(build)
            self.assertEqual((build / 'stranger.txt').read_text(), 'keep')

    def test_cache_requires_every_configured_value(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / 'CMakeCache.txt'
            cache.write_text('CMAKE_BUILD_TYPE:STRING=RelWithDebInfo\nGUFO_VERSION:STRING=wrong\n')
            with self.assertRaisesRegex(ValueError, 'cache'):
                build_identity.verify_cache(cache, {'CMAKE_BUILD_TYPE': 'RelWithDebInfo',
                                                    'GUFO_VERSION': 'reviewed'})
            cache.write_text('GUFO_VERSION:STRING=wrong\nGUFO_VERSION:STRING=reviewed\n')
            with self.assertRaisesRegex(ValueError, 'cache'):
                build_identity.verify_cache(cache, {'GUFO_VERSION': 'reviewed'})

    def test_cache_accepts_windows_path_case_normalization(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / 'CMakeCache.txt'
            cache.write_text('CMAKE_CACHEFILE_DIR:INTERNAL=c:/Build/Gufo\n')
            values = build_identity.verify_cache(cache,
                {'CMAKE_CACHEFILE_DIR': 'C:/Build/Gufo'})
            self.assertEqual(values['CMAKE_CACHEFILE_DIR'], 'c:/Build/Gufo')

    def test_vcpkg_dll_hash_is_checked_against_runtime_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dll = root / 'installed/x64-windows/bin/example.dll'
            dll.parent.mkdir(parents=True)
            dll.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'dll'):
                build_identity.verify_dependency_dlls(root, root, {
                    'sdk_dlls': [], 'vcpkg_dlls': [
                        {'name': 'example.dll', 'size_bytes': 5, 'sha256': '0' * 64}]})

    def test_nine_sdk_dlls_recorded_and_missing_or_tampered_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sdk = root / 'sdk'
            vcpkg = root / 'vcpkg'
            (sdk / 'bin').mkdir(parents=True)
            names = ('amdhip64_7.dll', 'amd_comgr.dll', 'rocm_kpack.dll',
                     'hipblas.dll', 'rocsolver.dll', 'rocblas.dll',
                     'libhipblaslt.dll', 'libtensilelite-host.dll', 'origami.dll')
            pins = []
            for index, name in enumerate(names):
                data = f'fixture-{index}'.encode()
                (sdk / 'bin' / name).write_bytes(data)
                pins.append({'name': name, 'size_bytes': len(data),
                             'sha256': hashlib.sha256(data).hexdigest().upper()})
            policy = {'sdk_dlls': pins, 'vcpkg_dlls': []}
            records = build_identity.verify_dependency_dlls(sdk, vcpkg, policy)
            self.assertEqual([row['name'] for row in records], list(names))
            self.assertTrue(all(row['kind'] == 'sdk' for row in records))
            (sdk / 'bin' / names[0]).write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'sdk_dll'):
                build_identity.verify_dependency_dlls(sdk, vcpkg, policy)
            (sdk / 'bin' / names[0]).unlink()
            with self.assertRaises((ValueError, OSError)):
                build_identity.verify_dependency_dlls(sdk, vcpkg, policy)

    def test_vcpkg_exact_port_revision_and_unique_base_record(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            status = root / 'installed/vcpkg/status'
            status.parent.mkdir(parents=True)
            row = ('Package: curl\nVersion: 8.21.0\nPort-Version: 1\n'
                   'Architecture: x64-windows\nStatus: install ok installed\n')
            status.write_text(row, encoding='utf-8')
            pins = {'ports': {'curl': {'version': '8.21.0', 'port_version': 1}}}
            self.assertEqual(build_identity.verify_ports(root, pins)['curl'],
                             {'version': '8.21.0', 'port_version': 1})
            status.write_text(row.replace('Port-Version: 1', 'Port-Version: 0'))
            with self.assertRaisesRegex(ValueError, 'port'):
                build_identity.verify_ports(root, pins)
            status.write_text(row + '\n' + row)
            with self.assertRaisesRegex(ValueError, 'port'):
                build_identity.verify_ports(root, pins)

    def test_explicit_python_and_git_tools_are_identified(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = {}
            for name in ('cmake', 'ninja', 'git', 'python'):
                tool = root / (name + '.exe')
                tool.write_bytes(name.encode())
                paths[name] = str(tool)
            outputs = {'cmake': 'cmake version 4.4.3', 'ninja': '1.13.2',
                       'git': 'git version 2.51.0.windows.1', 'python': 'Python 3.12.6'}
            record = build_identity.verify_tools(paths,
                {'cmake_version': '4.4.3', 'ninja_version': '1.13.2',
                 'python_version': '3.12'},
                runner=lambda argv: outputs[Path(argv[0]).stem])
            self.assertEqual(set(record), {'cmake', 'ninja', 'git', 'python'})
            self.assertEqual(record['python']['version_output'], 'Python 3.12.6')
            outputs['cmake'] = 'cmake version 4.4.30'
            with self.assertRaisesRegex(ValueError, 'cmake_version'):
                build_identity.verify_tools(paths,
                    {'cmake_version': '4.4.3', 'ninja_version': '1.13.2',
                     'python_version': '3.12'},
                    runner=lambda argv: outputs[Path(argv[0]).stem])


class BuildSetupTests(unittest.TestCase):
    def test_exact_commands_include_reviewed_flags_and_only_gufo(self):
        paths = {key: f'C:/fixed/{key}' for key in ('source', 'build', 'sdk', 'vcpkg', 'cmake', 'ninja', 'python')}
        expected = build_setup.cache_values(paths, 'a' * 40)
        configure = build_setup.configure_argv(paths, expected)
        built = build_setup.build_argv(paths, 2)
        self.assertEqual(configure[:6], ['C:/fixed/cmake', '-S', 'C:/fixed/source', '-B',
                                         'C:/fixed/build', '-G'])
        for key, value in expected.items():
            self.assertIn(f'-D{key}={value}', configure)
        self.assertEqual(expected['GUFO_VERSION'], 'a' * 40)
        self.assertEqual(expected['CMAKE_HIP_ARCHITECTURES'], 'gfx1151')
        self.assertIn('-g0', expected['CMAKE_HIP_FLAGS_RELWITHDEBINFO'])
        self.assertEqual(expected['VCPKG_TARGET_TRIPLET'], 'x64-windows')
        self.assertEqual(built, ['C:/fixed/cmake', '--build', 'C:/fixed/build', '--target',
                                 'gufo', '--parallel', '2'])

    def test_jobs_and_resource_floor_refuse_before_launch(self):
        for jobs in (0, 3, '2', True):
            with self.subTest(jobs=jobs), self.assertRaisesRegex(ValueError, 'jobs'):
                build_setup.validate_jobs(jobs)
        with self.assertRaisesRegex(ValueError, 'resource'):
            build_setup.check_resources({'available_ram_bytes': 24 * 1024**3 - 1,
                                         'free_disk_bytes': 30 * 1024**3,
                                         'sampled_at': 10.0}, now=10.0)
        with self.assertRaisesRegex(ValueError, 'resource'):
            build_setup.check_resources({'available_ram_bytes': 30 * 1024**3,
                                         'free_disk_bytes': 30 * 1024**3,
                                         'sampled_at': 0.0}, now=10.0)

    @unittest.skipUnless(os.name == 'nt', 'PowerShell entrypoint')
    def test_powershell_front_door_rejects_fractional_jobs_before_python(self):
        script = Path(__file__).resolve().parents[2] / 'setup/build-gufo-windows.ps1'
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            argv = [str(powershell), '-NoProfile', '-NonInteractive', '-File', str(script),
                    '-PythonExe', sys.executable, '-GitExe', str(root / 'git.exe'),
                    '-SourceDir', str(root / 'source'), '-BuildDir', str(root / 'build'),
                    '-SdkDir', str(root / 'sdk'), '-VcpkgDir', str(root / 'vcpkg'),
                    '-VcVars64', str(root / 'vcvars64.bat'),
                    '-CMakeExe', str(root / 'cmake.exe'),
                    '-NinjaExe', str(root / 'ninja.exe'), '-Jobs', '1.5']
            completed = subprocess.run(argv, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn('Jobs must be exactly 1 or 2',
                          completed.stdout + completed.stderr)
            self.assertFalse((root / 'build').exists())

    def test_child_environment_is_process_only_and_disables_manifest_install(self):
        original = dict(os.environ)
        paths = {'sdk': 'C:/sdk', 'ninja': 'C:/tools/ninja.exe'}
        env = build_setup.child_environment(paths, {'PATH': 'C:/host', 'SECRET': 'private'})
        self.assertEqual(env['VCPKG_MANIFEST_MODE'], 'OFF')
        self.assertEqual(env['VCPKG_MANIFEST_INSTALL'], 'OFF')
        self.assertEqual(env['HIP_PATH'], 'C:/sdk')
        self.assertEqual(env['HIP_DEVICE_LIB_PATH'], 'C:/sdk/lib/llvm/amdgcn/bitcode')
        self.assertEqual(env['SECRET'], 'private')
        self.assertEqual(dict(os.environ), original)

    def test_owned_command_closes_on_timeout_and_keeps_logs(self):
        events = []
        class FakeOwner:
            def __init__(self, argv, **kwargs):
                events.append(('create', argv, kwargs))
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                self.close()
            def resume(self):
                events.append('resume')
            def wait(self, timeout_ms):
                events.append(('wait', timeout_ms))
                return False
            def exit_code(self):
                return None
            def close(self, timeout_ms=5000):
                events.append('close')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(TimeoutError, 'deadline'):
                build_setup.run_owned(['C:/tool.exe'], cwd=Path(folder), env={},
                                      log_prefix=Path(folder) / 'configure',
                                      deadline_seconds=0.001, owner_factory=FakeOwner,
                                      resources=lambda: {'available_ram_bytes': 30 * 1024**3,
                                                         'free_disk_bytes': 30 * 1024**3,
                                                         'sampled_at': build_setup.time.monotonic()})
            self.assertIn('close', events)
            self.assertEqual(events[0][2]['stdout_path'], Path(folder) / 'configure.stdout.log')

    @unittest.skipUnless(os.name == 'nt', 'Windows owned-child fixture')
    def test_real_owned_harmless_child_records_argv_env_and_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = dict(os.environ)
            env['GUFO_BUILD_FIXTURE'] = 'only-child'
            argv = [sys.executable, '-c',
                    'import os; print(os.environ["GUFO_BUILD_FIXTURE"])']
            record = build_setup.run_owned(argv, cwd=root, env=env,
                log_prefix=root / 'child', deadline_seconds=10,
                resources=lambda: {'available_ram_bytes': 30 * 1024**3,
                                   'free_disk_bytes': 30 * 1024**3,
                                   'sampled_at': build_setup.time.monotonic()})
            self.assertEqual(record['argv'], argv)
            self.assertEqual(record['exit_code'], 0)
            self.assertEqual((root / 'child.stdout.log').read_text().strip(), 'only-child')
            self.assertEqual((root / 'child.stderr.log').read_text(), '')
            self.assertNotIn('GUFO_BUILD_FIXTURE', os.environ)

    def test_failed_manifest_is_atomic_and_never_qualified(self):
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)
            record = {'schema': 1, 'status': 'failed', 'runtimeStaged': False,
                      'runtime_qualified': False, 'error': 'configure_exit_1'}
            build_setup.write_manifest(build / 'build-manifest.json', record)
            self.assertEqual(json.loads((build / 'build-manifest.json').read_text()), record)
            self.assertFalse((build / 'build-manifest.json.pending').exists())

    def test_vcvars_import_uses_owned_selected_output_and_uppercase_keys(self):
        values = {'PATH': 'C:/host', 'VISUALSTUDIOVERSION': '17.0',
                  'VCTOOLSVERSION': '14.44.35207', 'VCTOOLSINSTALLDIR': 'C:/tools',
                  'WINDOWSSDKDIR': 'C:/sdk', 'WINDOWSSDKVERSION': '10.0.26100.0\\',
                  'INCLUDE': 'C:/include', 'LIB': 'C:/lib', 'LIBPATH': 'C:/libpath'}
        paths = {'vcvars': 'C:/Program Files/VC/vcvars64.bat', 'python': 'C:/python.exe'}
        pins = {'visual_studio_version': '17.0', 'vc_tools_version': '14.44.35207',
                'windows_sdk_version': '10.0.26100.0'}
        payload = base64.b64encode(json.dumps(values).encode())
        with patch.object(build_setup, '_owned_vcvars_output',
                          return_value=payload) as owned, \
                patch.object(build_setup.identity, 'checked_path', side_effect=lambda p: p), \
                patch.object(build_setup.identity, 'file_hash', return_value='A' * 64), \
                patch.object(Path, 'is_dir', return_value=True):
            env, selected = build_setup._vcvars_environment(paths, pins)
        self.assertEqual(env['PATH'], 'C:/host')
        self.assertEqual(env['INCLUDE'], 'C:/include')
        self.assertEqual(selected['VCToolsVersion'], '14.44.35207')
        self.assertEqual(selected['WindowsSDKVersion'], '10.0.26100.0\\')
        self.assertEqual(owned.call_args.kwargs['deadline_seconds'], 60)
        self.assertIn('-EncodedCommand', owned.call_args.args[0])
        for payload in (b'not-base64',
                        base64.b64encode(json.dumps({**values,
                            'GUFO_BUILD_SECRET_FIXTURE': 'must-not-import'}).encode())):
            with self.subTest(payload=payload[:12]), \
                 patch.object(build_setup, '_owned_vcvars_output', return_value=payload), \
                 patch.object(build_setup.identity, 'checked_path', side_effect=lambda p: p):
                with self.assertRaisesRegex(ValueError, 'vcvars_environment_invalid'):
                    build_setup._vcvars_environment(paths, pins)

    @unittest.skipUnless(os.name == 'nt', 'Windows vcvars fixture')
    def test_vcvars_fixture_imports_only_into_child_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            vcvars = root / 'vcvars64.bat'
            vcvars.write_text('@echo off\nset "VisualStudioVersion=17.0"\n'
                'set "VCToolsVersion=14.44.35207"\n'
                f'set "VCToolsInstallDir={root}"\n'
                f'set "WindowsSdkDir={root}"\n'
                'set "WindowsSDKVersion=10.0.26100.0\\"\n'
                'set "INCLUDE=C:/fixture/include"\n'
                'set "LIB=C:/fixture/lib"\n'
                'set "LIBPATH=C:/fixture/libpath"\n'
                'set "GUFO_BUILD_SECRET_FIXTURE=child-only-secret"\n', encoding='ascii')
            original = dict(os.environ)
            with patch.dict(os.environ, {'GUFO_BUILD_SECRET_FIXTURE': 'parent-marker'}), \
                 patch.object(subprocess, 'run',
                              side_effect=AssertionError('unowned subprocess forbidden')):
                env, selected = build_setup._vcvars_environment(
                    {'vcvars': str(vcvars), 'python': sys.executable},
                    {'visual_studio_version': '17.0',
                     'vc_tools_version': '14.44.35207',
                     'windows_sdk_version': '10.0.26100.0'})
            self.assertEqual(selected['VCToolsVersion'], '14.44.35207')
            self.assertIn('PATH', env)
            self.assertEqual(env['INCLUDE'], 'C:/fixture/include')
            self.assertEqual(env['LIB'], 'C:/fixture/lib')
            self.assertEqual(env['LIBPATH'], 'C:/fixture/libpath')
            self.assertEqual(env['GUFO_BUILD_SECRET_FIXTURE'], 'parent-marker')
            self.assertEqual(dict(os.environ), original)
            self.assertEqual([item.name for item in root.iterdir()], ['vcvars64.bat'])

    @unittest.skipUnless(os.name == 'nt', 'Windows owned vcvars descendant')
    def test_vcvars_timeout_closes_harmless_descendant(self):
        import ctypes
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            marker = root / 'descendant.pid'
            helper = root / 'spawn.py'
            helper.write_text('import subprocess,sys,time\nfrom pathlib import Path\n'
                "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n"
                'Path(sys.argv[1]).write_text(str(child.pid))\ntime.sleep(60)\n')
            vcvars = root / 'vcvars64.bat'
            vcvars.write_text(f'@echo off\n"{sys.executable}" "{helper}" "{marker}"\n')
            with self.assertRaisesRegex(TimeoutError, 'deadline'):
                build_setup._vcvars_environment(
                    {'vcvars': str(vcvars), 'python': sys.executable}, {},
                    deadline_seconds=4)
            self.assertTrue(marker.is_file(), 'descendant must have started')
            pid = int(marker.read_text())
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
            kernel.OpenProcess.restype = ctypes.c_void_p
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            kernel.WaitForSingleObject.restype = ctypes.c_ulong
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = kernel.OpenProcess(0x100000, False, pid)
            if handle:
                try:
                    self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
                finally:
                    kernel.CloseHandle(handle)

    @unittest.skipUnless(os.name == 'nt', 'Windows owned stdout bounds')
    def test_vcvars_owned_output_refuses_missing_oversize_and_helper_failure(self):
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for mode, expected in (('none', 'output_missing'),
                                   ('large', 'oversized')):
                with self.subTest(mode=mode):
                    if mode == 'none':
                        script = 'exit 0'
                    else:
                        script = '[Console]::Out.Write("x" * 1048577)'
                    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
                    argv = [str(powershell), '-NoProfile', '-NonInteractive',
                            '-EncodedCommand', encoded]
                    with self.assertRaisesRegex(ValueError, expected):
                        build_setup._owned_vcvars_output(argv, root, deadline_seconds=10)
            argv[-1] = base64.b64encode('exit 7'.encode('utf-16le')).decode('ascii')
            with self.assertRaisesRegex(ValueError, 'import_failed:7'):
                build_setup._owned_vcvars_output(argv, root, deadline_seconds=10)

    def test_failed_configure_records_exit_and_never_builds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            build = root / 'build'
            build.mkdir()
            args = SimpleNamespace(jobs=2, source_dir=root, build_dir=build,
                                   sdk_dir=root, vcpkg_dir=root)
            paths = {name: str(root / name) for name in
                     ('source', 'build', 'sdk', 'vcpkg', 'python', 'git', 'vcvars',
                      'cmake', 'ninja')}
            paths['build'] = str(build)
            calls = []
            def command(argv, **kwargs):
                calls.append(argv)
                raise RuntimeError('command_exit_7:cmake.exe')
            with patch.object(build_setup, '_canonical_paths', return_value=paths), \
                 patch.object(build_setup.identity, 'verify_git', return_value={'status': '', 'head': 'a' * 40}), \
                 patch.object(build_setup.identity, 'verify_reviewed_patch', return_value={}), \
                 patch.object(build_setup.identity, 'probe', return_value='tree'), \
                 patch.object(build_setup.identity, 'verify_sdk', return_value={'version': '10.2.0'}), \
                 patch.object(build_setup.identity, 'verify_tools', return_value={}), \
                 patch.object(build_setup.identity, 'verify_ports', return_value={}), \
                 patch.object(build_setup.identity, 'verify_dependency_dlls', return_value=[]), \
                 patch.object(build_setup.runtime_package, 'load_policy', return_value={'vcpkg_dlls': []}), \
                 patch.object(build_setup.identity, 'file_hash', return_value='A' * 64), \
                 patch.object(build_setup, 'run_owned', side_effect=command):
                options = {'pins': {'source_remote': 'remote',
                    'source_tree': 'b' * 40, 'source_base': 'c' * 40,
                    'vcpkg_commit': 'd' * 40},
                    'resources': lambda: {'available_ram_bytes': 30 * 1024**3,
                                          'free_disk_bytes': 30 * 1024**3,
                                          'sampled_at': build_setup.time.monotonic()},
                    'vcvars_loader': lambda *_: ({'PATH': 'host'}, {'vcvars_sha256': 'A' * 64})}
                with self.assertRaisesRegex(RuntimeError, 'command_exit_7'):
                    build_setup.build_gufo(args, **options)
                with self.assertRaisesRegex(ValueError, 'foreign_or_incomplete'):
                    build_setup.build_gufo(args, **options)
            manifest = json.loads((build / 'build-manifest.json').read_text())
            self.assertEqual(manifest['commands'][0]['exit_code'], 7)
            self.assertEqual(manifest['commands'][0]['status'], 'failed')
            self.assertEqual(len(calls), 1)
            self.assertFalse(manifest['runtime_qualified'])

    def test_success_manifest_reuse_requires_matching_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            build = root / 'build'
            build.mkdir()
            args = SimpleNamespace(jobs=2, source_dir=root, build_dir=build,
                                   sdk_dir=root, vcpkg_dir=root)
            paths = {name: str(root / name) for name in
                     ('source', 'build', 'sdk', 'vcpkg', 'python', 'git', 'vcvars',
                      'cmake', 'ninja')}
            paths['build'] = str(build)
            commands = []
            def command(argv, **kwargs):
                commands.append(argv)
                if len(commands) == 1:
                    values = build_setup.cache_values(paths, 'a' * 40)
                    all_values = {**values, 'CMAKE_HOME_DIRECTORY': paths['source'],
                                  'CMAKE_CACHEFILE_DIR': paths['build'],
                                  'CMAKE_GENERATOR': 'Ninja'}
                    (build / 'CMakeCache.txt').write_text(''.join(
                        f'{key}:STRING={value}\n' for key, value in all_values.items()))
                else:
                    (build / 'gufo.exe').write_bytes(b'harmless-fixture')
                stdout = kwargs['log_prefix'].with_name(
                    kwargs['log_prefix'].name + '.stdout.log')
                stderr = kwargs['log_prefix'].with_name(
                    kwargs['log_prefix'].name + '.stderr.log')
                stdout.write_text('fixture output')
                stderr.write_text('')
                return {'argv': argv, 'exit_code': 0,
                        'stdout_log': str(stdout),
                        'stderr_log': str(stderr),
                        'duration_seconds': 0.1}
            with patch.object(build_setup, '_canonical_paths', return_value=paths), \
                 patch.object(build_setup.identity, 'verify_git', return_value={'status': '', 'head': 'a' * 40}) as git_check, \
                 patch.object(build_setup.identity, 'verify_reviewed_patch', return_value={}), \
                 patch.object(build_setup.identity, 'verify_sdk', return_value={'version': '10.2.0'}), \
                 patch.object(build_setup.identity, 'verify_tools', return_value={}), \
                 patch.object(build_setup.identity, 'verify_ports', return_value={}), \
                 patch.object(build_setup.identity, 'verify_dependency_dlls', return_value=[]) as dll_check, \
                 patch.object(build_setup.runtime_package, 'load_policy', return_value={'vcpkg_dlls': []}), \
                 patch.object(build_setup.identity, 'file_hash', return_value='A' * 64), \
                 patch.object(build_setup, 'run_owned', side_effect=command):
                options = {'pins': {'source_remote': 'remote', 'source_tree': 'b' * 40,
                                   'source_base': 'c' * 40, 'vcpkg_commit': 'd' * 40},
                    'resources': lambda: {'available_ram_bytes': 30 * 1024**3,
                                          'free_disk_bytes': 30 * 1024**3,
                                          'sampled_at': build_setup.time.monotonic()},
                    'vcvars_loader': lambda *_: ({'PATH': 'host'}, {'vcvars_sha256': 'A' * 64})}
                low = dict(options)
                low['resources'] = lambda: {'available_ram_bytes': 1,
                                            'free_disk_bytes': 30 * 1024**3,
                                            'sampled_at': build_setup.time.monotonic()}
                with self.assertRaisesRegex(ValueError, 'resource'):
                    build_setup.build_gufo(args, **low)
                self.assertEqual(list(build.iterdir()), [])
                self.assertEqual(commands, [])
                git_check.reset_mock()
                dll_check.reset_mock()
                first = build_setup.build_gufo(args, **options)
                self.assertEqual(first['status'], 'built')
                self.assertFalse(first['runtimeStaged'])
                self.assertEqual(len(commands), 2)
                self.assertEqual(git_check.call_count, 4)
                self.assertEqual(dll_check.call_count, 2)
                second = build_setup.build_gufo(args, **options)
                self.assertEqual(second, first)
                self.assertEqual(len(commands), 2)
                for mutation in (
                    lambda row: row.update(schema=2),
                    lambda row: row.update(kind='unknown'),
                    lambda row: row.update(commands=[]),
                    lambda row: row['commands'][0].update(argv=['wrong']),
                    lambda row: row['commands'][1].update(exit_code=1),
                    lambda row: row['commands'][0].update(stdout_log='C:/unknown.log'),
                    lambda row: row['commands'][0].update(status='failed'),
                ):
                    altered = json.loads(json.dumps(first))
                    mutation(altered)
                    (build / 'build-manifest.json').write_text(json.dumps(altered))
                    with self.assertRaisesRegex(ValueError, 'foreign_or_incomplete'):
                        build_setup.build_gufo(args, **options)
                (build / 'build-manifest.json').write_text(json.dumps(first))
                altered = dict(first)
                altered['cache_expected'] = {**first['cache_expected'], 'GUFO_VERSION': 'wrong'}
                (build / 'build-manifest.json').write_text(json.dumps(altered))
                with self.assertRaisesRegex(ValueError, 'foreign_or_incomplete'):
                    build_setup.build_gufo(args, **options)
                (build / 'build-manifest.json').write_text(json.dumps(first))
                with (build / 'CMakeCache.txt').open('a') as stream:
                    stream.write('CMAKE_HOME_DIRECTORY:INTERNAL=wrong-source\n')
                with self.assertRaisesRegex(ValueError, 'cache'):
                    build_setup.build_gufo(args, **options)
                all_values = {**build_setup.cache_values(paths, 'a' * 40),
                              'CMAKE_HOME_DIRECTORY': paths['source'],
                              'CMAKE_CACHEFILE_DIR': paths['build'],
                              'CMAKE_GENERATOR': 'Ninja'}
                (build / 'CMakeCache.txt').write_text(''.join(
                    f'{key}:STRING={value}\n' for key, value in all_values.items()))
                args.jobs = 1
                with self.assertRaisesRegex(ValueError, 'foreign_or_incomplete'):
                    build_setup.build_gufo(args, **options)
                self.assertEqual(len(commands), 2)


if __name__ == '__main__':
    unittest.main()
