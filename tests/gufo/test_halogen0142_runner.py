"""Offline policy tests; these never invoke Docker, WSL or a GPU."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json
import subprocess
import sys
import time

SOURCE = Path(__file__).resolve().parents[2] / 'experimental/halogen0142/runner.py'


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SOURCE.exists():
            spec = importlib.util.spec_from_file_location('candidate_runner', SOURCE)
            cls.runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.runner)
        else:
            cls.runner = None

    def test_runner_exists(self):
        self.assertIsNotNone(self.runner, 'candidate runner missing')

    def test_admission_requires_fresh_physical_and_commit(self):
        r = self.runner
        if r is None: self.fail('candidate runner missing')
        good = dict(available_bytes=24*r.GIB, commit_headroom_bytes=98*r.GIB)
        r.check_frame(good, admission=True)
        for key in good:
            with self.assertRaises(ValueError): r.check_frame({**good, key: good[key]-1}, admission=True)
        with self.assertRaises(ValueError): r.check_frame(good, admission=True, age=3)
        with self.assertRaises(ValueError): r.check_frame({}, admission=False)

    def test_review_is_bound_to_stage_allocation_and_digest(self):
        r = self.runner
        if r is None: self.fail('candidate runner missing')
        review = dict(approved=True, stage='trace', seal_sha256='a'*64,
                      reviewer='independent', allocation_reason='reviewed 48GiB layout')
        r.check_review(review, 'a'*64, 'trace')
        for key, value in [('stage','smoke'), ('seal_sha256','b'*64),
                           ('approved',False), ('allocation_reason','')]:
            with self.assertRaises(ValueError): r.check_review({**review,key:value},'a'*64,'trace')

    def test_trace_requires_exact_vector_and_exit_before_registration(self):
        r = self.runner
        if r is None: self.fail('candidate runner missing')
        log = ('[preflight-bridge] active sha256='+r.ENGINE_SHA+' rva=0xdf7db0 trace=1\n'
               '[preflight] plan phase=1 ranges=2 aggregate=30 copy=10 host=20\n'
               '[preflight-bridge] demand aggregate=30 host=20 mapping=40 count=2 floor=17179869184\n'
               '[preflight-bridge] range[0]=100:110\n[preflight-bridge] range[1]=200:220\n')
        r.validate_trace(log,1,[10,20])
        r.validate_trace('[hybrid] device-copy cap=51539607552 bytes\n'+
                         '[private-rw] private file mapping bytes=40 path=model.hgn\n'+log,1,[10,20])
        for bad, code in [(log,0),(log.replace('200:220','200:221'),77),
                          (log+'[hybrid] device-copy bytes=10 result=0 copied=10\n',77),
                          (log+'[private-rw] register bytes=10 flags=10 result=0\n',77),
                          (log.replace('trace=1','trace=0'),77)]:
            with self.assertRaises(ValueError): r.validate_trace(bad,code,[10,20])

    def test_frozen_sequence_has_overlay_but_trace_only_trunk(self):
        r=self.runner
        self.assertTrue(hasattr(r,'trace_vector'),'frozen vector validation missing')
        path=Path(r'C:\Projects\strix-alloy-wsl2\tests\preflight-sequences.json')
        self.assertEqual(len(r.trace_vector(path)),252)
        self.assertEqual(sum(r.trace_vector(path)),70434994368)

    def test_terminal_validation_rejects_oom_and_driver_error(self):
        r=self.runner
        self.assertTrue(hasattr(r,'validate_terminal'),'terminal validation missing')
        good={'Running':False,'Pid':0,'OOMKilled':False,'Error':'','ExitCode':1}
        r.validate_terminal(good,trace=True)
        for key,value in [('OOMKilled',True),('Error','driver error'),('Running',True),('ExitCode',137)]:
            with self.assertRaises(ValueError): r.validate_terminal({**good,key:value},trace=True)

    def test_recovery_requires_five_consecutive_fresh_frames(self):
        r = self.runner
        if r is None: self.fail('candidate runner missing')
        frame = dict(available_bytes=28*r.GIB,commit_headroom_bytes=98*r.GIB)
        self.assertFalse(r.recovered([frame]*4,30*r.GIB))
        self.assertTrue(r.recovered([frame]*5,30*r.GIB))
        self.assertFalse(r.recovered([frame]*4+[{**frame,'available_bytes':27*r.GIB}],30*r.GIB))

    def test_artifact_changes_invalidate_seal(self):
        r = self.runner
        if r is None: self.fail('candidate runner missing')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'artifact'; path.write_bytes(b'a')
            manifest={'artifacts':{'fixture':{'path':str(path),'sha256':r.file_sha(path)}}}
            first=r.make_seal(manifest)
            path.write_bytes(b'b')
            with self.assertRaises(ValueError): r.make_seal(manifest)
            manifest['artifacts']['fixture']['sha256']=r.file_sha(path)
            self.assertNotEqual(first['seal_sha256'],r.make_seal(manifest)['seal_sha256'])

    def test_environment_has_both_exact_bridge_optins_and_no_download(self):
        r=self.runner
        env=r.environment({'stage':'trace','artifacts':{
            'bridge':{'container_path':'/candidate/bridge.so'},
            'private':{'container_path':'/candidate/private.so'}}})
        self.assertEqual(env['HALOGEN_PREFLIGHT_PROFILE'],'flash0142-copy48-v1')
        self.assertEqual(env['HALOGEN_HYBRID_PROFILE'],'vgm64-copy48-v1')
        self.assertNotIn('HALOGEN_DOWNLOAD',env)
        self.assertEqual(env['HALOGEN_CTX'],'4096')

    def test_owned_stop_rejects_foreign_identity(self):
        r=self.runner; cid='a'*64; name='halogen-flash-hybrid-0142-trace-test'
        info={'Id':cid,'Name':'/'+name,'Config':{'Image':r.IMAGE,'Labels':{
            'strix-alloy.run':name,'strix-alloy.owner':'strix-alloy-wsl2'}}}
        r.owned(info,cid,name,{})
        with self.assertRaises(ValueError): r.owned(info,'b'*64,name,{})
        info['Config']['Image']='old-image'
        with self.assertRaises(ValueError): r.owned(info,cid,name,{})

    def test_container_command_is_pinned_bounded_and_readonly(self):
        r=self.runner
        artifacts={k:{'path':str(r.ARTIFACT_ROOT/(k+'.bin')),'container_path':'/candidate/'+k+'.bin'}
                   for k in ('entrypoint','bridge','private','probe')}
        command=r.command({'stage':'trace','timeout_seconds':360,'artifacts':artifacts},'name')
        self.assertIn(r.IMAGE,command)
        self.assertIn(str(44*r.GIB),command)
        self.assertIn('/usr/bin/timeout',command)
        self.assertEqual(command[-1],'engine')
        self.assertNotIn('--privileged',command)
        self.assertTrue(all('readonly' in command[i+1] for i,v in enumerate(command) if v=='--mount'))

    def test_telemetry_guard_never_accepts_missing_guest_or_gpu(self):
        r=self.runner
        good={'containerId':'a'*64,'gpuInstances':[{'name':'gpu','dedicatedBytes':0,
              'sharedBytes':0,'totalCommittedBytes':0}],
              'guest':{'memory.current':1,'memory.peak':1,'memory.swap.current':0}}
        self.assertTrue(hasattr(r,'validate_sample'),'independent guest telemetry validation missing')
        r.validate_sample(good,'a'*64)
        for key in ('guest','gpuInstances'):
            with self.assertRaises(ValueError): r.validate_sample({**good,key:None},'a'*64)

    def test_smoke_requires_current_successful_trace(self):
        r=self.runner
        self.assertTrue(hasattr(r,'require_trace'),'trace-before-smoke gate missing')
        with self.assertRaises(ValueError): r.require_trace({'stage':'smoke'}, {})

    def test_default_command_never_contacts_gpu(self):
        r=self.runner
        m={'stage':'trace','timeout_seconds':360,'artifacts':{
            key:{'path':str(r.ARTIFACT_ROOT/(key+'.bin')),'container_path':'/candidate/'+key+'.bin'}
            for key in ('entrypoint','bridge','private','probe')}}
        with (patch.object(r,'read_json',return_value=m), patch.object(r,'validate_manifest'),
             patch.object(r,'make_seal',return_value={}), patch.object(r,'invoke',side_effect=AssertionError('external command')),
             patch('builtins.print')):
            self.assertEqual(r.main(['--manifest','offline.json']),0)

    def test_sampler_uses_powershell_core_for_owned_tree_cleanup(self):
        r=self.runner
        with patch.object(r,'invoke',return_value='') as invoke, patch.object(r,'read_json',return_value={}):
            r.sample('a'*64,Path('fixture'),'inference',0)
            self.assertTrue(invoke.call_args.args[0][0].endswith('pwsh.exe'))

    def test_trace_wrapper_retains_child_status_until_exact_ack(self):
        r=self.runner
        self.assertTrue(hasattr(r,'TRACE_WRAPPER'),'bounded trace wrapper missing')
        with tempfile.TemporaryDirectory() as directory:
            status=Path(directory)/'status.json'; release=Path(directory)/'release.json'
            process=subprocess.Popen([sys.executable,'-c',r.TRACE_WRAPPER,str(status),str(release),
                '3',sys.executable,'-c','raise SystemExit(1)'],
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                deadline=time.monotonic()+2
                while not status.exists() and time.monotonic()<deadline: time.sleep(.01)
                state=json.loads(status.read_text())
                self.assertEqual(state['child_exit'],1)
                self.assertIsNone(process.poll(),'container supervisor must outlive fast engine')
                release.write_text(json.dumps(state))
                self.assertEqual(process.wait(timeout=2),1,'original wrapper status must survive')
            finally:
                if process.poll() is None: process.kill(); process.wait()

    def test_trace_wrapper_missing_ack_fails_with_finite_deadline(self):
        r=self.runner
        self.assertTrue(hasattr(r,'TRACE_WRAPPER'),'bounded trace wrapper missing')
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run([sys.executable,'-c',r.TRACE_WRAPPER,
                str(Path(directory)/'status.json'),str(Path(directory)/'release.json'),
                '.1',sys.executable,'-c','raise SystemExit(1)'],timeout=3,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertEqual(result.returncode,124)

    def test_trace_ack_requires_real_scoped_measurement_first(self):
        r=self.runner
        self.assertTrue(hasattr(r,'complete_trace_telemetry'),'trace telemetry handshake missing')
        with tempfile.TemporaryDirectory() as directory:
            attempt=Path(directory)
            with (patch.object(r,'sample',side_effect=ValueError('missing GPU')),
                  patch.object(r,'docker') as docker):
                with self.assertRaises(ValueError):
                    r.complete_trace_telemetry('a'*64,attempt,dict(schema=1,child_exit=1,
                        child_pid=42,child_finished_ns=time.time_ns()))
                docker.assert_not_called()

    def test_trace_sample_is_saved_with_honest_scope_before_ack(self):
        r=self.runner; cid='a'*64
        raw={'containerId':cid,'gpuInstances':[{'name':'gpu','dedicatedBytes':0,
             'sharedBytes':0,'totalCommittedBytes':0}],
             'guest':{'memory.current':10,'memory.peak':100,'memory.swap.current':0}}
        status=dict(schema=1,child_exit=1,child_pid=42,child_finished_ns=time.time_ns())
        with tempfile.TemporaryDirectory() as directory:
            attempt=Path(directory)
            def acknowledge(*args,**kwargs):
                evidence=json.loads((attempt/'trace-telemetry.json').read_text())
                self.assertEqual(evidence['telemetry'],raw)
                self.assertEqual(evidence['child_status'],status)
                self.assertFalse(evidence['transient_engine_gpu_peak_observed'])
                self.assertIn('post-engine-exit',evidence['scope'])
                self.assertIn('telemetry',evidence['cgroup_peak_scope'])
            with patch.object(r,'sample',return_value=raw), patch.object(r,'docker',side_effect=acknowledge) as docker:
                r.complete_trace_telemetry(cid,attempt,status)
                docker.assert_called_once()

    def test_trace_wrapper_rejects_wrong_child_ack(self):
        r=self.runner
        with tempfile.TemporaryDirectory() as directory:
            status=Path(directory)/'status.json'; release=Path(directory)/'release.json'
            release.write_text('{}')
            result=subprocess.run([sys.executable,'-c',r.TRACE_WRAPPER,str(status),str(release),
                '1',sys.executable,'-c','raise SystemExit(1)'],timeout=3,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertEqual(result.returncode,125)


if __name__ == '__main__': unittest.main()
