"""Offline tests for the optional static GUFO package."""

import contextlib
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from gufo_control import runtime_package
from gufo_control import smoke_store


def stamp(data):
    return {'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest().upper()}


class Fixture:
    def __init__(self, root):
        self.root = Path(root)
        self.build = self.root / 'build'
        self.sdk = self.root / 'sdk'
        self.vcpkg = self.root / 'vcpkg'
        self.runtime = self.root / 'runtime'
        for directory in (self.build, self.sdk / 'bin',
                          self.vcpkg / 'installed/x64-windows/bin', self.sdk / '.info'):
            directory.mkdir(parents=True)
        (self.sdk / '.info/version').write_text('10.2.0\n', encoding='utf-8')
        self.policy = {'schema': 1, 'kind': 'gufo-native-static-runtime',
                       'source_commit': 'cff564964e8506c0abb3e530cecb55332187ac6c',
                       'sdk_version': '10.2.0',
                       'executable': {'name': 'gufo.exe', **stamp(b'exe')},
                       'sdk_dlls': [], 'vcpkg_dlls': [], 'trees': [],
                       'host_openmp': {'name': 'libomp140.x86_64.dll', **stamp(b'host')}}
        (self.build / 'gufo.exe').write_bytes(b'exe')
        for name in smoke_store.SDK_DLLS:
            data = name.encode('ascii')
            (self.sdk / 'bin' / name).write_bytes(data)
            self.policy['sdk_dlls'].append({'name': name, **stamp(data)})
        for name in smoke_store.VCPKG_DLLS:
            data = name.encode('ascii')
            (self.build / name).write_bytes(data)
            (self.vcpkg / 'installed/x64-windows/bin' / name).write_bytes(data)
            self.policy['vcpkg_dlls'].append({'name': name, **stamp(data)})
        for name in smoke_store.TREES:
            base = self.sdk / 'bin' / name
            (base / 'library/gfx1151').mkdir(parents=True)
            (base / 'library/gfx1151' / 'Z.co').write_bytes(b'Z')
            (base / 'library/gfx1151' / 'a.co').write_bytes(b'a')
            rows = [{'path': 'library/gfx1151/Z.co', **stamp(b'Z')},
                    {'path': 'library/gfx1151/a.co', **stamp(b'a')}]
            self.policy['trees'].append({'name': name, 'count': 2,
                                         'bytes': 2,
                                         'digest': runtime_package.tree_digest(rows)})
        self.host = {'path': str(self.root / 'System32/libomp140.x86_64.dll'),
                     **stamp(b'host')}

    def stage(self):
        return runtime_package.stage_runtime(self.build, self.sdk, self.vcpkg, self.runtime)

    def patches(self):
        return (patch.object(runtime_package, 'load_policy', return_value=self.policy),
                patch.object(runtime_package, '_host_openmp_record', return_value=self.host),
                patch.object(runtime_package, '_free_bytes', return_value=2**40))


@contextlib.contextmanager
def fixture_context():
    with TemporaryDirectory() as temp:
        fixture = Fixture(temp)
        with fixture.patches()[0], fixture.patches()[1], fixture.patches()[2]:
            yield fixture


class RuntimePackageTests(unittest.TestCase):
    def test_real_policy_matches_reviewed_pins(self):
        policy = runtime_package.load_policy()
        self.assertEqual(policy['source_commit'], smoke_store.PINS.source_commit)
        self.assertEqual(policy['sdk_version'], '10.2.0')
        self.assertEqual((policy['executable']['size_bytes'], policy['executable']['sha256']),
                         smoke_store.PINS.executable)
        for key, pins in (('sdk_dlls', smoke_store.SDK_DLLS),
                          ('vcpkg_dlls', smoke_store.VCPKG_DLLS)):
            self.assertEqual({row['name']: (row['size_bytes'], row['sha256'])
                              for row in policy[key]}, pins)
        self.assertEqual({row['name']: (row['count'], row['bytes'], row['digest'])
                          for row in policy['trees']}, smoke_store.TREES)

    def test_tree_digest_is_ordinal_and_case_preserving(self):
        rows = [{'path': 'library/gfx1151/a.co', **stamp(b'a')},
                {'path': 'library/gfx1151/Z.co', **stamp(b'Z')}]
        expected = hashlib.sha256(''.join(f"{row['path']}|{row['size_bytes']}|{row['sha256'].lower()}\n"
                                          for row in reversed(rows)).encode()).hexdigest().upper()
        self.assertEqual(runtime_package.tree_digest(rows), expected)

    def test_stage_verify_idempotent_and_relocatable(self):
        with fixture_context() as f:
            manifest = f.stage()
            self.assertEqual(manifest['runtime_qualified'], False)
            self.assertEqual(manifest['status'], 'staged-static-only')
            self.assertEqual(len(manifest['files']), 22)
            original = (f.runtime / 'runtime-manifest.json').read_bytes()
            self.assertEqual(f.stage(), manifest)
            self.assertEqual((f.runtime / 'runtime-manifest.json').read_bytes(), original)
            moved = f.root / 'moved'
            f.runtime.rename(moved)
            self.assertEqual(runtime_package.verify_runtime(moved), manifest)

    def test_bad_sources_and_low_space_leave_no_target(self):
        for change in ('exe', 'sdk', 'vcpkg_build', 'vcpkg_installed', 'tree', 'version', 'space'):
            with self.subTest(change=change), fixture_context() as f:
                if change == 'exe':
                    (f.build / 'gufo.exe').write_bytes(b'wrong')
                elif change == 'sdk':
                    (f.sdk / 'bin' / 'hipblas.dll').write_bytes(b'wrong')
                elif change == 'vcpkg_build':
                    (f.build / 'z.dll').write_bytes(b'wrong')
                elif change == 'vcpkg_installed':
                    (f.vcpkg / 'installed/x64-windows/bin/z.dll').write_bytes(b'wrong')
                elif change == 'tree':
                    (f.sdk / 'bin/rocblas/library/gfx1151/a.co').write_bytes(b'wrong')
                elif change == 'version':
                    (f.sdk / '.info/version').write_text('10.0.0', encoding='utf-8')
                elif change == 'space':
                    with patch.object(runtime_package, '_free_bytes', return_value=0):
                        with self.assertRaises(ValueError):
                            f.stage()
                    self.assertFalse(f.runtime.exists())
                    continue
                with self.assertRaises(ValueError):
                    f.stage()
                self.assertFalse(f.runtime.exists())

    def test_corrupt_missing_extra_payload_and_manifest_are_rejected(self):
        changes = ('corrupt_dll', 'missing_dll', 'extra_dll', 'corrupt_tree', 'extra_tree',
                   'hash', 'count', 'path', 'status', 'qualification')
        for change in changes:
            with self.subTest(change=change), fixture_context() as f:
                f.stage()
                manifest_path = f.runtime / 'runtime-manifest.json'
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                if change == 'corrupt_dll':
                    (f.runtime / 'z.dll').write_bytes(b'bad')
                elif change == 'missing_dll':
                    (f.runtime / 'z.dll').unlink()
                elif change == 'extra_dll':
                    (f.runtime / 'foreign.dll').write_bytes(b'x')
                elif change == 'corrupt_tree':
                    (f.runtime / 'rocblas/library/gfx1151/a.co').write_bytes(b'bad')
                elif change == 'extra_tree':
                    (f.runtime / 'rocblas/library/gfx1151/extra.co').write_bytes(b'x')
                elif change == 'hash':
                    manifest['files'][0]['sha256'] = '0' * 64
                elif change == 'count':
                    manifest['trees'][0]['count'] = 99
                elif change == 'path':
                    manifest['files'][0]['path'] = '../gufo.exe'
                elif change == 'status':
                    manifest['status'] = 'qualified'
                else:
                    manifest['runtime_qualified'] = True
                if change in ('hash', 'count', 'path', 'status', 'qualification'):
                    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
                with self.assertRaises((ValueError, OSError)):
                    runtime_package.verify_runtime(f.runtime)

    def test_overlap_and_symlink_rejected(self):
        with fixture_context() as f:
            for target in (f.build / 'runtime', f.root, f.sdk.parent):
                with self.assertRaises(ValueError):
                    runtime_package.stage_runtime(f.build, f.sdk, f.vcpkg, target)
            link = f.sdk / 'bin/hipblaslt/library/gfx1151/a.co'
            link.unlink()
            try:
                link.symlink_to(f.build / 'gufo.exe')
            except OSError:
                self.skipTest('symlink creation unavailable')
            with self.assertRaises(ValueError):
                f.stage()

    def test_windows_junction_is_rejected(self):
        with fixture_context() as f:
            junction = f.root / 'junction'
            created = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(junction), str(f.build)],
                                     capture_output=True, text=True, check=False)
            self.assertEqual(created.returncode, 0, created.stderr)
            with self.assertRaisesRegex(ValueError, 'reparse'):
                runtime_package.stage_runtime(junction, f.sdk, f.vcpkg, f.runtime)
            self.assertFalse(f.runtime.exists())

    def test_empty_target_can_be_replaced_and_stale_lock_refused(self):
        with fixture_context() as f:
            f.runtime.mkdir()
            lock = f.root / 'runtime.stage.lock'
            lock.write_text('stale', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'lock'):
                f.stage()
            self.assertTrue(f.runtime.is_dir())
            self.assertFalse(any(f.runtime.iterdir()))
            lock.unlink()
            self.assertEqual(f.stage()['status'], 'staged-static-only')

    def test_copy_failure_retains_diagnostic_directory(self):
        with fixture_context() as f:
            with patch.object(runtime_package, '_copy_file_exclusive', side_effect=OSError('copy failed')):
                with self.assertRaises(OSError) as caught:
                    f.stage()
            self.assertIn('copy failed', str(caught.exception))
            self.assertFalse(f.runtime.exists())
            self.assertEqual(len(list(f.root.glob('runtime.staging-*'))), 1)

    def test_source_change_during_copy_cannot_publish(self):
        with fixture_context() as f:
            real_copy = runtime_package._copy_file_exclusive
            def change_source(source, destination, *args):
                real_copy(source, destination, *args)
                if source.name == 'gufo.exe':
                    source.write_bytes(b'new')
            with patch.object(runtime_package, '_copy_file_exclusive', side_effect=change_source):
                with self.assertRaises((ValueError, OSError)):
                    f.stage()
            self.assertFalse(f.runtime.exists())

    def test_publish_race_preserves_independent_target(self):
        with fixture_context() as f:
            real_copy = runtime_package._copy_file_exclusive
            def create_race(source, destination, *args):
                real_copy(source, destination, *args)
                if source.name == 'gufo.exe':
                    f.runtime.mkdir()
                    (f.runtime / 'user.txt').write_text('keep', encoding='utf-8')
            with patch.object(runtime_package, '_copy_file_exclusive', side_effect=create_race):
                with self.assertRaises((ValueError, OSError)):
                    f.stage()
            self.assertEqual((f.runtime / 'user.txt').read_text(encoding='utf-8'), 'keep')

    def test_replaced_staging_junction_cannot_write_to_independent_directory(self):
        with fixture_context() as f:
            foreign = f.root / 'independent-destination'
            foreign.mkdir()
            real_copy = runtime_package._copy_file_exclusive
            switched = []

            def replace_before_copy(source, destination, *args):
                if not switched:
                    junction = destination.parent
                    junction.rename(junction.with_name(junction.name + '-original'))
                    created = subprocess.run(
                        ['cmd.exe', '/c', 'mklink', '/J', str(junction), str(foreign)],
                        capture_output=True, text=True, check=False)
                    self.assertEqual(created.returncode, 0, created.stderr)
                    switched.append(junction)
                real_copy(source, destination, *args)

            try:
                with patch.object(runtime_package, '_copy_file_exclusive',
                                  side_effect=replace_before_copy):
                    with self.assertRaises((ValueError, OSError)):
                        f.stage()
                self.assertTrue(switched)
                self.assertEqual(list(foreign.iterdir()), [])
            finally:
                for junction in switched:
                    junction.rmdir()  # Only the test-owned junction, nonrecursive.

    def test_owned_destination_must_be_below_staging_root(self):
        with fixture_context() as f:
            staging = f.root / 'owned-stage'
            staging.mkdir()
            identity = (staging.stat().st_dev, staging.stat().st_ino)
            with self.assertRaises(ValueError):
                runtime_package._owned_destination(staging, identity, f.root)

    def test_manifest_tree_and_host_numbers_require_exact_integer_types(self):
        with fixture_context() as f:
            manifest = f.stage()
            for section, field in (('trees', 'count'), ('trees', 'bytes'),
                                   ('host_prerequisites', 'size_bytes')):
                with self.subTest(section=section, field=field):
                    changed = copy.deepcopy(manifest)
                    changed[section][0][field] = float(changed[section][0][field])
                    with self.assertRaises(ValueError):
                        runtime_package._validate_manifest(changed, f.policy)

    def test_manifest_historical_source_paths_must_be_canonical_absolute_local(self):
        with fixture_context() as f:
            manifest = f.stage()
            for source in ('../relative', 'not an absolute path', 'X',
                           'C:\\old\\..\\build', '\\\\server\\share\\build'):
                with self.subTest(source=source):
                    changed = copy.deepcopy(manifest)
                    changed['sources']['build_dir'] = source
                    with self.assertRaises(ValueError):
                        runtime_package._validate_manifest(changed, f.policy)

    def test_stage_verify_do_not_launch_subprocess(self):
        with fixture_context() as f, patch('subprocess.run', side_effect=AssertionError('spawned')):
            f.stage()
            runtime_package.verify_runtime(f.runtime)

    def test_wrapper_quotes_spaces_and_preserves_environment(self):
        with TemporaryDirectory(prefix='gufo wrapper ') as temp:
            helper = Path(temp) / 'fake python.exe'
            helper.write_text('@echo off\r\necho %*\r\necho PYPATH=%PYTHONPATH%\r\n', encoding='utf-8')
            # A .cmd stub is an executable path for PowerShell's call operator.
            helper = helper.rename(helper.with_suffix('.cmd'))
            wrapper = Path(__file__).resolve().parents[2] / 'setup/stage-gufo-runtime.ps1'
            child_env = dict(os.environ, PYTHONPATH='unchanged sentinel')
            result = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(wrapper),
                                     '-PythonExe', str(helper), '-Verify',
                                     '-RuntimeDir', str(Path(temp) / 'space target')],
                                    capture_output=True, text=True, check=False, env=child_env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('space target', result.stdout)
            self.assertIn('PYPATH=unchanged sentinel', result.stdout)
    def test_unknown_nonempty_target_is_not_touched(self):
        with TemporaryDirectory() as temp:
            target = Path(temp) / 'runtime'
            target.mkdir()
            existing = target / 'user.txt'
            existing.write_text('keep', encoding='utf-8')
            with self.assertRaises(ValueError):
                runtime_package.stage_runtime(Path(temp) / 'build', Path(temp) / 'sdk',
                                              Path(temp) / 'vcpkg', target)
            self.assertEqual(existing.read_text(encoding='utf-8'), 'keep')

    def test_cli_requires_explicit_inputs(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                runtime_package.main(['stage', '--runtime-dir', 'C:/missing'])
        self.assertEqual(caught.exception.code, 2)
