"""Portable update contract tests: no real model or container is started."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import portable as p
import runner as r
import entrypoint_adapter as entry
import bridge_adapter as bridge

class UpdateTests(unittest.TestCase):
    def test_release_source_integrity_and_pinned_version(self):
        p.verify_sources()
        self.assertEqual(p.RELEASE['version'],'0.16.1')
        self.assertTrue(p.IMAGE.endswith('089701309a7ed9f70c91daca6a66080828e032788d4e6d0da4d427587387ede5'))
        self.assertEqual(p.RELEASE['engine_sha256'],bridge.ENGINE_SHA)
    def test_fixed_profile_and_no_automatic_download(self):
        with patch.object(r,'MACHINE',{'distro':'Fixture','user':'tester'}):
            for stage in ['trace','smoke','serve']:
                m=r.manifest_for(stage)
                env=r.environment(m)
                self.assertEqual(env['HALOGEN_CTX'],'4096')
                self.assertEqual(env['HALOGEN_KV_POOL_POSITIONS'],'4096')
                self.assertEqual(env['HALOGEN_KV_SLOTS'],'1')
                self.assertEqual(env['HALOGEN_PROMPT_CACHE'],'0')
                self.assertNotIn('HALOGEN_DOWNLOAD',env)
                self.assertEqual(env['HALOGEN_PREFLIGHT_PROFILE'],'flash0161-copy48-v1')
    def test_unqualified_profiles_and_durations_refused(self):
        for stage in ['Single32k','Single256k','Sessions32k','27B','persistent']:
            with self.assertRaises(ValueError): r.manifest_for(stage)
        for seconds in [0,29,301,3600,True,30.0]:
            with self.assertRaises(ValueError): r.manifest_for('serve',seconds)
    def test_container_has_private_port_finite_lifetime_and_exact_readonly_mounts(self):
        with patch.object(r,'MACHINE',{}),patch.object(r,'FIXED_MOUNTS',{'/models':'/fixture/models'}),             patch.object(r,'linux_path',side_effect=lambda v:'/fixture/'+Path(v).name):
            args=r.command(r.manifest_for('serve',30),'halogen-flash-hybrid-0151-test')
        self.assertIn('127.0.0.1:8731:8731',args)
        self.assertIn('--restart=no',args)
        self.assertIn('--kill-after=5',args)
        self.assertEqual(args[args.index('--memory')+1],str(44*r.GIB))
        self.assertEqual(args[args.index('--memory-swap')+1],str(44*r.GIB))
        self.assertTrue(all(args[i+1].endswith(',readonly') for i,v in enumerate(args) if v=='--mount'))
        self.assertNotIn('--privileged',args)
    def test_fresh_memory_admission_and_runtime_floors(self):
        good={'available_bytes':45*r.GIB,'commit_headroom_bytes':117*r.GIB}
        r.check_frame(good,admission=True)
        for key in good:
            with self.assertRaises(ValueError): r.check_frame({**good,key:good[key]-1},admission=True)
        with self.assertRaises(ValueError): r.check_frame(good,age=3)
        with self.assertRaises(ValueError): r.check_frame({'available_bytes':True,'commit_headroom_bytes':117*r.GIB})
        r.check_frame({'available_bytes':12*r.GIB,'commit_headroom_bytes':12*r.GIB})
    def test_serve_requires_both_exact_trace_and_smoke(self):
        with patch.object(r,'successful_stage') as success:
            r.require_trace({'stage':'serve'})
        self.assertEqual([c.args[1] for c in success.call_args_list],['trace','smoke'])
        with patch.object(r,'successful_stage',side_effect=ValueError('missing')):
            with self.assertRaises(ValueError): r.require_trace({'stage':'smoke'})
    def test_qualification_success_from_changed_sources_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); attempt=root/'attempts/halogen-flash-hybrid-0151-trace-fixture'; attempt.mkdir(parents=True)
            (attempt/'success.json').write_text(json.dumps({'seal_sha256':'old','cleanup':True,'recovery':True}))
            (attempt/'outcome.json').write_text('{"passed":true}')
            (attempt/'release.json').write_text('{}')
            with patch.object(r,'ARTIFACT_ROOT',root),patch.object(r,'manifest_for',return_value={}),                 patch.object(r,'make_seal',return_value={'seal_sha256':'new'}):
                with self.assertRaises(ValueError): r.successful_stage({},'trace')
    def test_uninstall_cannot_escape_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); local=root/'.local'; local.mkdir()
            keep=root/'README.md'; keep.write_text('keep')
            (local/'install-manifest.json').write_text(json.dumps({'schema':1,'version':'0.16.1',
                'files':{'../README.md':p.digest(keep)}}))
            with patch.object(p,'ROOT',root),patch.object(p,'LOCAL',local):
                with self.assertRaises(ValueError): p.uninstall()
            self.assertEqual(keep.read_text(),'keep')
    def test_uninstall_refuses_unresolved_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); local=root/'.local';local.mkdir();(local/'runner.lock').touch()
            with patch.object(p,'ROOT',root),patch.object(p,'LOCAL',local):
                with self.assertRaises(ValueError): p.uninstall()
    def test_check_only_does_not_write_or_extract(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(p,'ROOT',root),patch.object(p,'LOCAL',root/'.local'),                 patch.object(p,'preflight',return_value={'version':'0.16.1'}),patch.object(p,'wsl') as ws:
                self.assertEqual(p.install('D','u','/models','/dxg',explicit=False),{'version':'0.16.1'})
            ws.assert_not_called();self.assertEqual(list(root.iterdir()),[])
    def test_existing_install_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);local=root/'.local';local.mkdir();(local/'machine.json').write_text('keep')
            with patch.object(p,'ROOT',root),patch.object(p,'LOCAL',local),patch.object(p,'preflight') as check:
                with self.assertRaises(ValueError):p.install('D','u','/models','/dxg',explicit=True)
            check.assert_not_called();self.assertEqual((local/'machine.json').read_text(),'keep')
    def test_linux_paths_and_identity_reject_shell_and_mount_ambiguity(self):
        self.assertEqual(p.linux_path('/srv/model files',native=True),'/srv/model files')
        for value in ['/mnt/c/models','/a,b','/a:b','relative','/a/../b']:
            with self.assertRaises(ValueError):p.linux_path(value,native=True)
        with self.assertRaises(ValueError):p.identity('x;touch','distribution')
    def test_transform_and_bridge_reject_changed_inputs(self):
        with self.assertRaises(ValueError):entry.transform(b'not pinned upstream')
        with self.assertRaises(ValueError):bridge.verify_engine(b'not pinned engine')
    def test_new_bridge_uses_exact_engine_rva_and_profile(self):
        text=(ROOT/'patches/halogen-preflight-bridge.c').read_text(encoding='utf-8')
        self.assertIn(bridge.ENGINE_SHA,text);self.assertIn('0x1876e70',text)
        self.assertIn('flash0161-copy48-v1',text);self.assertNotIn('flash0138-copy48-v1',text)
    def test_german_smoke_answer_is_unicode_not_mojibake(self):
        text=(ROOT/'scripts/runner.py').read_text(encoding='utf-8')
        self.assertIn("'gr\u00fcn'",text)
        self.assertNotIn('gr\u00c3\u00bcn',text)
    def test_loopback_http_redirect_is_refused(self):
        self.assertIsNone(r.NoRedirect().redirect_request(None,None,302,'redirect',{},'https://example.invalid'))

class InstalledArtifactTests(unittest.TestCase):
    def setUp(self):
        if not (ROOT/'.local/machine.json').is_file(): self.skipTest('Explicit local installation required; no downloads in tests')
    def test_rebuilt_artifacts_match_reviewed_hashes(self):
        for name,key in [('flash_serve','engine_sha256'),('libhalogen0161-preflight.so','bridge_sha256'),
                         ('hip-register-private-rw.so','private_sha256'),('halogen0161_hip_probe','probe_sha256'),
                         ('entrypoint-wsl.sh','adapted_entrypoint_sha256')]:
            p.check_hash(ROOT/'.local'/name,p.RELEASE[key])
    def test_upstream_transform_and_elf_abi(self):
        original=(ROOT/'.local/entrypoint-upstream.sh').read_bytes()
        changed=entry.transform(original)
        self.assertEqual(changed,(ROOT/'.local/entrypoint-wsl.sh').read_bytes())
        self.assertEqual(changed[changed.index(b"# THE DOWNLOAD'S SIZE"):],original[original.index(b"# THE DOWNLOAD'S SIZE"):])
        bridge.verify_engine((ROOT/'.local/flash_serve').read_bytes())

if __name__=='__main__':unittest.main()
