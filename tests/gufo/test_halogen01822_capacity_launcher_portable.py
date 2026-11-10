"""Portable PS5.1 PrintOnly regressions; tracked sources plus synthetic temporary metadata."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv
from copy import deepcopy

REPO=Path(__file__).resolve().parents[2]
PS=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'


@unittest.skipUnless(os.name=='nt' and PS.is_file(),'Windows PowerShell 5.1 required')
class CapacityLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='alloy-capacity-portable-')
        cls.root=Path(cls.temporary.name)/'project'
        # Only finite tracked source files are copied; never walk ignored models,
        # installed environments, worktrees or sibling audit bundles.
        for source in (REPO/'server').glob('*.py'):
            dest=cls.root/'server'/source.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
        for version in ('0.18.22','0.19.1','0.20.0','0.20.1'):
            source_package=REPO/('backends/halogen-wsl2-'+version)
            pins=json.loads((source_package/'profiles/sources.json').read_text())
            for name in [*pins['files'],'profiles/sources.json']:
                relative=Path(name)
                if relative.is_absolute() or '..' in relative.parts or '.local' in relative.parts:
                    raise AssertionError('Tracked fixture source path is not finite')
                source=source_package/relative
                dest=cls.root/('backends/halogen-wsl2-'+version)/relative
                dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
        cls.script=cls.root/'scripts/Start-Halogen-ServiceNow.ps1'
        cls.script.parent.mkdir(parents=True);shutil.copy2(REPO/'scripts/Start-Halogen-ServiceNow.ps1',cls.script)
        cls.expected_text=json.loads((REPO/'server/tests/fixtures/halogen0201-capacity-text32k-profile.json').read_text())
        fixture_venv=cls.root/'server/.local/venv'
        venv.EnvBuilder(with_pip=False).create(fixture_venv)
        (cls.root/'server/.local/servicenow-api-token.txt').write_text('synthetic-public-token-for-cpu-tests-only')
        for version in ('0.20.1','0.20.0','0.19.1','0.18.22','0.18.16','0.18.15','0.18.10'):
            package=cls.root/('backends/halogen-wsl2-'+version)
            (package/'.local').mkdir(parents=True)
            (package/'profiles').mkdir(exist_ok=True)
            release_path=package/'profiles/release.json'
            release=json.loads(release_path.read_text()) if release_path.exists() else dict(version=version,image='synthetic-image')
            release_path.write_text(json.dumps(release))
            (package/'.local/machine.json').write_text(json.dumps(dict(version=version,image=release['image'],pwsh=str(PS))))
            (package/'.local/api-token.txt').write_text('synthetic-backend-token-for-cpu-tests-only')
        cls.env=os.environ.copy()
        packages=[str(Path(p)) for p in sys.path if (Path(p)/'aiohttp').is_dir()]
        cls.env['PYTHONPATH']=os.pathsep.join(packages)
        cls.env['PATH']=str(fixture_venv/'Scripts')+os.pathsep+cls.env['PATH']
        cls.env['PYTHONDONTWRITEBYTECODE']='1'

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def invoke(self,*args,script=None,profile='CurrentText32K'):
        return subprocess.run([str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script or self.script),
            '-Profile',profile,'-PrintOnly',*args],cwd=self.root,env=self.env,
            text=True,capture_output=True,encoding='utf-8',errors='replace',timeout=30)

    def normalize(self,value):
        if isinstance(value,dict):return {key:self.normalize(item) for key,item in value.items()}
        if isinstance(value,list):return [self.normalize(item) for item in value]
        if isinstance(value,str):
            if os.path.normcase(value)==os.path.normcase(str(PS)):return '<POWERSHELL>'
            if value.startswith(str(self.root)):
                return '<REPO>/'+Path(value).relative_to(self.root).as_posix()
        return value

    def decoded(self,result):
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertGreaterEqual(result.stdout.find('{'),0,result.stdout)
        return json.JSONDecoder().raw_decode(result.stdout[result.stdout.find('{'):])[0]

    def test_current_text_default_matches_explicit_tracked_fixture(self):
        result=self.invoke()
        self.assertEqual(self.normalize(self.decoded(result)),self.expected_text)
        self.assertIn('Halogen 0.20.1 v2; MTP policy Confidence90; PLD 3,3; cache Off; one request.',result.stdout)
        self.assertFalse((self.root/'server/.local/servicenow-sessions').exists())

    def test_opt_in_control_and_candidate_print_exact_capacity_without_session_write(self):
        for slots in (1,2):
            for pool in (32768,65536):
                with self.subTest(slots=slots,pool=pool):
                    actual=self.normalize(self.decoded(self.invoke('-Slots',str(slots),'-KvPoolPositions',str(pool),'-Concurrency','2')))
                    expected=deepcopy(self.expected_text)
                    expected['concurrency']=2
                    expected['engine'].update(slots=slots,kv_pool_positions=pool)
                    expected['backend']['expected'].update(slots=slots,kv_pool_positions=pool,capability_probe='ok')
                    self.assertEqual(actual,expected)
        self.assertFalse((self.root/'server/.local/servicenow-sessions').exists())

    def test_rejects_unsafe_selectors_before_any_launch(self):
        for args in (('-Slots','3'),('-KvPoolPositions','33024'),('-Concurrency','3'),
                     ('-Slots','2','-Concurrency','1'),('-HalogenVersion','0.18.16','-Concurrency','2')):
            with self.subTest(args=args):
                self.assertNotEqual(self.invoke(*args).returncode,0)
        self.assertFalse((self.root/'server/.local/servicenow-sessions').exists())

    def test_capacity_selectors_require_current_text_even_for_default_values(self):
        for profile in ('Current8K','Current4K','Measured32K','MeasuredText32K','FollowupText32K','CurrentCachedText32K'):
            for selector,value in (('-Slots','1'),('-Concurrency','1'),('-KvPoolPositions','32768')):
                with self.subTest(profile=profile,selector=selector):
                    result=self.invoke(selector,value,profile=profile)
                    self.assertNotEqual(result.returncode,0,result.stdout)
                    self.assertIn('Capacity selectors require CurrentText32K',result.stderr+result.stdout)
        self.assertFalse((self.root/'server/.local/servicenow-sessions').exists())

    def test_backend_start_forwards_capacity_and_rejects_legacy_controls(self):
        for version in ('0.18.22','0.19.1','0.20.0','0.20.1'):
            with self.subTest(version=version):
                script=self.root/('backends/halogen-wsl2-'+version)/'Start.ps1'
                result=subprocess.run([str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),
                    '-ContextSize','32768','-Slots','2','-KvPoolPositions','65536','-DisableVision','-PrintOnly'],
                    cwd=self.root,env=self.env,text=True,capture_output=True,encoding='utf-8',errors='replace',timeout=30)
                actual=self.decoded(result)
                self.assertEqual(actual['context'],32768);self.assertEqual(actual['slots'],2)
                self.assertEqual(actual['kv_pool_positions'],65536)
                self.assertGreaterEqual(actual['admission_gib'][0],30);self.assertGreaterEqual(actual['admission_gib'][1],131)
                result=subprocess.run([str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),
                    '-Profile','Trace4k','-Checkpoint','w4b','-Slots','2','-PrintOnly'],cwd=self.root,env=self.env,
                    text=True,capture_output=True,encoding='utf-8',errors='replace',timeout=30)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('Legacy 4K qualification profiles do not accept',result.stderr+result.stdout)


if __name__=='__main__':unittest.main()
