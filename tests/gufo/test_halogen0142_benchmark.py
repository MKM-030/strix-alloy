"""Offline tests for the bounded 0.14.2 benchmark companion."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[2] / 'experimental/halogen0142_benchmark/runner.py'


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('benchmark_runner', SOURCE)
        cls.b = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.b)

    def test_effective_argv_has_only_benchmark_context_and_cache(self):
        b = self.b
        m = {'stage': 'smoke', 'timeout_seconds': 1800, 'artifacts': {
            key: {'path': str(b.base.ARTIFACT_ROOT / (key+'.bin')),
                  'container_path': '/candidate/'+key+'.bin'}
            for key in ('entrypoint', 'bridge', 'private', 'probe')}}
        argv = b.command(m, 'halogen-flash-hybrid-0142-benchmark-fixture')
        env = [argv[i+1] for i, part in enumerate(argv[:-1]) if part == '-e']
        self.assertEqual(len(env), len(set(x.split('=', 1)[0] for x in env)))
        for value in ('HALOGEN_CTX=133888', 'HALOGEN_KV_POOL_POSITIONS=133888',
                      'HALOGEN_PROMPT_CACHE=2', 'HALOGEN_CACHE_ENTRIES=3',
                      'HALOGEN_FLASH_ROUTE_GEMM=0'):
            self.assertIn(value, env)
        self.assertNotIn('HALOGEN_CTX=4096', env)
        self.assertEqual(argv[argv.index('--signal=TERM')+2], '1800')

    def test_prerequisites_reject_changed_success_or_source(self):
        b = self.b
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            source = p/'input.json'; source.write_text('{}')
            fixture = {'path': str(source), 'sha256': b.base.file_sha(source)}
            b.check_file(fixture)
            source.write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError, 'hash'):
                b.check_file(fixture)

    def test_qualified_success_requires_matching_seal_and_outcome(self):
        b = self.b
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempt = root/'attempts'/'trace'; attempt.mkdir(parents=True)
            seal = {'manifest': {'stage':'trace', 'artifacts':{'engine':{'sha256':'a'*64}}},
                    'seal_sha256':'b'*64}
            b.base.save(attempt/'seal.json',seal)
            b.base.save(attempt/'success.json',{'stage':'trace','cleanup':True,
                         'recovery':True,'seal_sha256':'b'*64})
            b.base.save(attempt/'outcome.json',{'passed':True})
            item={'path':str(attempt/'success.json'),
                  'sha256':b.base.file_sha(attempt/'success.json'),
                  'seal_sha256':b.base.file_sha(attempt/'seal.json')}
            with patch.object(b.base,'ARTIFACT_ROOT',root), patch.object(b.base,'make_seal',return_value=seal):
                item['evidence_sha256']=b.evidence_digest(attempt)
                b.check_success(item,'trace',seal['manifest']['artifacts'])
                (attempt/'outcome.json').write_text('{"passed": false}')
                with self.assertRaisesRegex(ValueError,'evidence'):
                    b.check_success(item,'trace',seal['manifest']['artifacts'])

    def test_comparability_failure_preserves_completed_workload(self):
        b = self.b
        record = {'requests': [{'success': True}]*8, 'candidate_success': False,
                  'cells': {'0': {'errors': ['prefill_outside_tolerance']}}}
        summary = b.summarize_replay(record, 1)
        self.assertTrue(summary['http_workload_completed'])
        self.assertFalse(summary['strictly_comparable'])
        self.assertEqual(summary['replay_exit_code'], 1)
        self.assertEqual(summary['raw_candidate_success'], False)

    def test_cleanup_requires_terminal_and_recovery_evidence(self):
        b = self.b
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            terminal = {'State': {'Running': False, 'Pid': 0,
                                  'OOMKilled': False, 'Error': '', 'ExitCode': 0}}
            b.base.save(p/'terminal.json', terminal)
            with self.assertRaisesRegex(ValueError, 'recovery'):
                b.check_cleanup(p)
            b.base.save(p/'recovery.json', {'passed': True, 'frames': [{}]*5})
            b.base.save(p/'release.json', {'cleanup': True, 'recovery': True})
            b.check_cleanup(p)

    def test_default_does_not_run_external_process(self):
        b = self.b
        with tempfile.TemporaryDirectory() as directory:
            fixture=Path(directory)/'fixture.json'; fixture.write_text('{}')
            with patch.object(b, 'run', side_effect=AssertionError('live run')):
                with patch.object(b, 'offline', return_value={'seal_sha256':'a'*64}):
                    with patch('builtins.print'):
                        self.assertEqual(b.main(['--manifest', str(fixture)]), 0)

    def test_smoke_trace_review_path_accepts_same_windows_file(self):
        b=self.b
        path=Path(r'C:\Projects\strix-alloy-research\artifacts\halogen0142\attempts\trace\success.json')
        review={'trace_success_path':path.as_posix(), 'trace_success_sha256':'a'*64}
        b.check_smoke_trace_link(review,path,'a'*64)

    def test_table_sample_uses_allowed_inference_phase(self):
        b=self.b
        with patch.object(b.base,'sample',return_value={'containerId':'a'*64}) as sample:
            with patch.object(b.base,'validate_sample'):
                b.sample_after_table('a'*64,Path('fixture'),1)
        self.assertEqual(sample.call_args.args[2],'inference')

    def test_exit_status_requires_cleanup_and_strict_comparability(self):
        b=self.b
        self.assertEqual(b.exit_status({'strictly_comparable':True,'passed':False}),1)
        self.assertEqual(b.exit_status({'strictly_comparable':True,'passed':True}),0)

    def test_one_sealed_table_per_attempt(self):
        b=self.b
        self.assertEqual(b.selected_table({'table':'mixed'}),'mixed')
        self.assertEqual(b.selected_table({'table':'repetitive'}),'repetitive')
        for value in (None,'both','mixed,repetitive'):
            with self.assertRaises(ValueError): b.selected_table({'table':value})

    def test_health_requires_observed_mtp_default(self):
        b=self.b
        health={'status':'ok','version':{'api':'0.14.2','engine':'0.14.2','match':True},
                'context':133888,'kv_pool_positions':133888,'slots':1,
                'prompt_cache':{'mode':2},'drafter_default':'serial',
                'prompt_lookup':{'ngram':3,'chain':3}}
        with self.assertRaisesRegex(ValueError,'health'):
            b.check_health(health,{'artifacts':{}},'a'*64)

    def test_seal_exposes_only_emitted_benchmark_environment(self):
        b=self.b
        research = Path(__file__).resolve().parents[2].parent / 'strix-alloy-research'
        inputs = {table: (research/path.relative_to(b.ROOT), sha)
                  for table, (path, sha) in b.INPUTS.items()}
        if not (research/'artifacts/halogen0142').is_dir() or any(not path.is_file() for path, _ in inputs.values()):
            self.skipTest('Historical 0.14.2 sibling artifacts and benchmark reports required')
        self.enterContext(patch.object(b.base, 'ARTIFACT_ROOT', research/'artifacts/halogen0142'))
        self.enterContext(patch.object(b, 'INPUTS', inputs))
        config=b.base.read_json(b.HERE/'manifest.json')
        seal=b.offline(config)
        self.assertEqual(seal['launch_environment']['HALOGEN_CTX'],'133888')
        self.assertNotIn('base_seal',seal)
        self.assertNotIn('HALOGEN_CTX=4096',seal['docker_argv'])

    def test_benchmark_admission_uses_reviewed_47_116_gib_floor(self):
        b=self.b
        good={'available_bytes':47*b.base.GIB,
              'commit_headroom_bytes':116*b.base.GIB}
        b.check_benchmark_admission(good,'mixed')
        for key in good:
            with self.assertRaisesRegex(ValueError,'benchmark admission'):
                b.check_benchmark_admission({**good,key:good[key]-1},'mixed')

    def test_repetitive_only_admits_reviewed_45_116_gib_floor(self):
        b=self.b
        good={'available_bytes':45*b.base.GIB,
              'commit_headroom_bytes':116*b.base.GIB}
        b.check_benchmark_admission(good,'repetitive')
        for key in good:
            with self.assertRaisesRegex(ValueError,'benchmark admission'):
                b.check_benchmark_admission({**good,key:good[key]-1},'repetitive')
        with self.assertRaisesRegex(ValueError,'benchmark admission'):
            b.check_benchmark_admission(good,'mixed')

    def test_precreate_rejection_checks_recovery_without_terminal(self):
        b=self.b
        with tempfile.TemporaryDirectory() as directory:
            attempt=Path(directory)
            b.base.save(attempt/'recovery.json',{'passed':True,'frames':[{}]*5})
            b.base.save(attempt/'release.json',{'cleanup':True,'recovery':True})
            b.check_cleanup(attempt,had_container=False)
            (attempt/'release.json').unlink()
            with self.assertRaisesRegex(ValueError,'recovery'):
                b.check_cleanup(attempt,had_container=False)


if __name__ == '__main__':
    unittest.main()
