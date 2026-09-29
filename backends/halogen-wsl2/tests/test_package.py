import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class PackageTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'scripts/package.py').exists(), 'portable installer is missing')
        self.p = load('package', ROOT / 'scripts/package.py')

    def test_paths_preserve_spaces_refuse_ambiguous_mounts(self):
        self.assertEqual(self.p.linux_path('/home/user/model files'), '/home/user/model files')
        for value in ['/mnt/c/models', '/a:b', '/a,b', '/a\nb', '/a"b', '/a\\b', '/a/../b', 'relative']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.p.linux_path(value, native=True)

    def test_selected_distribution_and_user_are_distinct_arguments(self):
        self.assertEqual(self.p.wsl_command('Other-Distro', 'alice', ['stat', '/models with spaces']),
                         ['wsl.exe', '-d', 'Other-Distro', '-u', 'alice', '--exec', 'stat', '/models with spaces'])

    def test_unknown_profiles_refused(self):
        for mode in ['27B', 'Sessions260k', 'Unpinned256k', 'Pinned32k']:
            with self.assertRaises(ValueError): self.p.profile_mode(mode)
        self.assertEqual(self.p.profile_mode('Serve32k'), 'PreflightServe32k')

    def test_duration_bounds(self):
        for value in [29, 301]:
            with self.assertRaises(ValueError): self.p.serve_seconds(value)
        self.assertEqual(self.p.serve_seconds(300), 300)

    def test_hash_mismatch_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            f = pathlib.Path(directory) / 'artifact'
            f.write_bytes(b'changed')
            with self.assertRaises(ValueError): self.p.check_hash(f, '0' * 64)

    def test_duplicate_environment_refuses(self):
        with self.assertRaises(ValueError): self.p.environment(['A=1', 'A=2'])

    def test_dry_run_never_builds_or_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            with patch.object(self.p, 'preflight', return_value={'distro': 'D', 'user': 'alice'}), patch.object(self.p, 'build_adapters') as build:
                self.p.install(root, 'D', 'alice', '/models', '/dxg.so', None, False, False)
            build.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])

    def test_actual_preflight_dry_run_with_mocked_wsl_has_no_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory)
            for name in ['profiles/build.json','profiles/environment.json'] + [p.relative_to(ROOT).as_posix() for p in (ROOT/'patches').iterdir()]:
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
            before={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
            calls=[]
            def external(distro,user,*args,**kwargs):
                calls.append((distro,user,args))
                if args==('id','-un'): return 'alice'
                if args[0]=='wslpath': return '/mnt/c/package with spaces'
                if args[:3]==('stat','-f','-c'): return 'ext2/ext3'
                if args[:3]==('stat','-c','%s'):
                    return str(next(size for name,size,sha in self.p.MODELS if args[-1].endswith('/'+name)))
                if args[0]=='gcc': return '13.3.0'
                if args==('cat','/etc/os-release'): return 'ID=ubuntu\nVERSION_ID="24.04"'
                if args[0]=='sha256sum':
                    self.assertEqual(args[-1],'/opt/dxg.so')
                    return self.p.DXG_HASH+'  /opt/dxg.so'
                if args[0] in ('docker','test'): return 'ok'
                self.fail('Unexpected external operation: '+repr(args))
            with patch.object(self.p,'wsl',side_effect=external):
                self.p.install(root,'Other-Distro',None,'/home/alice/model files','/opt/dxg.so',None,False,True)
            self.assertTrue(all(distro=='Other-Distro' for distro,user,args in calls))
            self.assertTrue(all(user=='alice' for distro,user,args in calls if args!=('id','-un')))
            self.assertEqual(before,{p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertFalse((root/'.local').exists())

    def test_unknown_existing_install_refuses_before_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / '.local').mkdir()
            (root / '.local/machine.json').write_text('{}')
            with patch.object(self.p, 'preflight') as preflight:
                with self.assertRaises(ValueError): self.p.install(root, 'D', 'alice', '/models', '/dxg', None, True, False)
            preflight.assert_not_called()

    def test_install_manifest_contains_only_created_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            with patch.object(self.p, 'preflight', return_value={'distro': 'D', 'user': 'alice'}), patch.object(self.p, 'build_adapters', return_value=[]):
                self.p.install(root, 'D', 'alice', '/models', '/dxg', None, True, False)
            manifest = json.loads((root / '.local/install-manifest.json').read_text())
            self.assertEqual([item['path'] for item in manifest['files']], ['.local/machine.json'])

    def test_uninstall_preserves_unowned_data_and_rejects_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / '.local').mkdir()
            keep = root / '.local/user-data'; keep.write_text('keep')
            manifest = root / '.local/install-manifest.json'
            manifest.write_text(json.dumps({'schema': 'strix-alloy-install-v1', 'files': [{'path': '../outside', 'sha256': '0'*64}]}))
            with self.assertRaises(ValueError): self.p.uninstall(root)
            self.assertEqual(keep.read_text(), 'keep')

    def test_wsl_config_semantics(self):
        self.p.validate_wsl_config('[wsl2]\nmemory = 56GB\nswap=0\n')
        for value in ['[wsl2]\nmemory=56GB\nmemory=88GB', '[other]\nmemory=56GB', '[wsl2]\nmemory=88GB']:
            with self.assertRaises(ValueError): self.p.validate_wsl_config(value)

    def test_partial_build_failure_removes_only_new_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory)
            manifest={'compilerArguments':['-shared','-o','ignored'], 'adapters':[
                {'binary':'bin/a.so','binarySha256':self.p.hashlib.sha256(b'good').hexdigest()},
                {'binary':'bin/b.so','binarySha256':'0'*64,'source':'patches/private.c'}]}
            def compiler(*args, **kwargs):
                arguments=list(args)
                output=arguments[arguments.index('-o')+1]
                (root/output).write_bytes(b'good')
                return ''
            with patch.object(self.p,'check_sources',return_value=manifest),patch.object(self.p,'wsl',side_effect=compiler):
                with self.assertRaises(ValueError):
                    self.p.build_adapters(root,dict(distro='D',user='alice',workspace='/package'))
            self.assertEqual(list((root/'bin').iterdir()),[])

    def test_safe_uninstall_removes_owned_files_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory);(root/'.local').mkdir()
            machine=root/'.local/machine.json';machine.write_text('{}')
            keep=root/'.local/client-data';keep.write_text('keep')
            self.p.create_json(root/'.local/install-manifest.json',{'schema':'strix-alloy-install-v1','files':[
                {'path':'.local/machine.json','sha256':self.p.digest(machine)}]})
            self.p.uninstall(root)
            self.assertFalse(machine.exists());self.assertTrue(keep.exists())

    def test_uninstall_refuses_empty_manifest_beneath_linked_local(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            root = base / 'package'; root.mkdir()
            outside = base / 'outside'; outside.mkdir()
            manifest = outside / 'install-manifest.json'
            self.p.create_json(manifest, {'schema': 'strix-alloy-install-v1', 'files': []})
            link = root / '.local'
            if sys.platform == 'win32':
                result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            else:
                link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError): self.p.uninstall(root)
            self.assertTrue(manifest.exists())
            self.assertEqual(list(outside.iterdir()), [manifest])

    def test_uninstall_refuses_linked_manifest_even_when_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            root = base / 'package'; (root / '.local').mkdir(parents=True)
            outside = base / 'outside.json'
            self.p.create_json(outside, {'schema': 'strix-alloy-install-v1', 'files': []})
            manifest = root / '.local/install-manifest.json'
            try:
                manifest.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.p.create_json(manifest, {'schema': 'strix-alloy-install-v1', 'files': []})
                original = pathlib.Path.is_symlink
                with patch.object(pathlib.Path, 'is_symlink', autospec=True,
                                  side_effect=lambda path: path == manifest or original(path)):
                    with self.assertRaises(ValueError): self.p.uninstall(root)
                self.assertTrue(manifest.exists())
                self.assertTrue(outside.exists())
                return
            with self.assertRaises(ValueError): self.p.uninstall(root)
            self.assertTrue(outside.exists())
            self.assertEqual(manifest.resolve(), outside)

    def test_uninstall_checks_manifest_junction_metadata_even_without_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory); (root / '.local').mkdir()
            manifest = root / '.local/install-manifest.json'
            self.p.create_json(manifest, {'schema': 'strix-alloy-install-v1', 'files': []})
            original = pathlib.Path.is_junction
            with patch.object(pathlib.Path, 'is_junction', autospec=True,
                              side_effect=lambda path: path == manifest or original(path)):
                with self.assertRaises(ValueError): self.p.uninstall(root)
            self.assertTrue(manifest.exists())

    def test_uninstall_removes_legitimate_empty_failed_install_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory); (root / '.local').mkdir()
            manifest = root / '.local/install-manifest.json'
            self.p.create_json(manifest, {'schema': 'strix-alloy-install-v1', 'files': []})
            self.p.uninstall(root)
            self.assertFalse(manifest.exists())

if __name__ == '__main__': unittest.main()
