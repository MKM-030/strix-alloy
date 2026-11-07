"""CPU-only companion policy, preregistration and mocked lifecycle boundaries."""
import argparse
import contextlib
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import root_campaign as campaign

parent_spec = importlib.util.spec_from_file_location('cost_parent_transition_tests',
    campaign.PRIMARY / 'raw-phase-prep/test_root_campaign.py')
parent_tests = importlib.util.module_from_spec(parent_spec)
parent_spec.loader.exec_module(parent_tests)
ProvenTransitionTests = parent_tests.TransitionTests


class CostCampaignTests(unittest.TestCase):
    def test_fixed_profiles_differ_only_by_gate_cost_gate(self):
        baseline = json.loads(campaign.NORMAL.read_bytes())
        before = copy.deepcopy(baseline)
        profiles = [campaign.private_profile(baseline, arm, 'mtp_gate_cost')
                    for arm in ('before', 'candidate', 'after')]
        for profile, rule in zip(profiles, ('gate', 'cost', 'gate')):
            self.assertEqual(profile['engine']['speculation_policy'].pop('HALOGEN_MTP_GATE_RULE'), rule)
            self.assertEqual(profile['engine']['speculation_policy'],
                             dict(HALOGEN_PLD='3,3', HALOGEN_MTP_GATE_P='0.90'))
            self.assertEqual(profile['engine']['kernel_controls'], dict(HALOGEN_DECODE_PREFETCH=0,
                HALOGEN_DRAFT_VOCAB_Q8=0, HALOGEN_SERVE_TRACE=1, HALOGEN_PHASE_RAW=1))
            self.assertEqual((profile['engine']['context'], profile['engine']['slots'],
                profile['engine']['kv_pool_positions'], profile['engine']['prefill_chunk'],
                profile['engine']['max_prefill_tokens'], profile['concurrency']),
                (32768, 1, 32768, 2048, 2048, 1))
            self.assertEqual(profile['engine']['prompt_cache'], 'Off')
        self.assertEqual(profiles[0], profiles[1])
        self.assertEqual(profiles[0], profiles[2])
        self.assertEqual(baseline, before)

    def test_exact_existing_natural_requests_and_128_outputs(self):
        values = campaign.cases('mtp_gate_cost')
        self.assertEqual([row['name'] for row in values], ['natural8192', 'natural16384'])
        for row in values:
            self.assertEqual(row['expected_output_tokens'], 128)
            self.assertEqual(hashlib.sha256(row['request'].read_bytes()).hexdigest(), row['request_sha256'])

    def test_all_six_cohorts_and_eight_unique_ids_are_required(self):
        row = dict(collector=dict(completed=True), samples=[dict(native_request_id=i) for i in range(4)],
                   mtp_cost_trace=dict(native_rule_activation_observed=True))
        results = {arm: {name: copy.deepcopy(row) for name in ('natural8192', 'natural16384')}
                   for arm in ('before', 'candidate', 'after')}
        for entries in results.values():
            entries['natural16384']['samples'] = [dict(native_request_id=i) for i in range(4, 8)]
        self.assertTrue(campaign.all_cohorts_complete(results))
        del results['candidate']['natural16384']
        self.assertFalse(campaign.all_cohorts_complete(results))
        with self.assertRaises(ValueError):
            campaign.qualify_arm_ids({'natural8192': row}, [dict(native_request_id=0)])
        campaign.qualify_arm_ids({'natural8192': row}, [dict(native_request_id=4)])

    def test_registration_checks_committed_blob_working_bytes_and_all_six_roles(self):
        with tempfile.TemporaryDirectory(dir=campaign.HERE) as folder:
            repo = Path(folder)
            plan_path = repo / campaign.PLAN_PATH
            plan_path.parent.mkdir(parents=True)
            rows = campaign.source_rows()
            exporter = repo / 'fixture-exporter.py'
            exporter.write_bytes(b'# CPU registration fixture\n')
            plan = dict(schema='halogen0191.mtp-cost-gate-plan.v1', experiment='mtp_gate_cost',
                        executed_source_pins={Path(name).name: pin for name, pin in rows.items()},
                        exporter_source_pin=dict(bytes=exporter.stat().st_size,
                            sha256=hashlib.sha256(exporter.read_bytes()).hexdigest()))
            payload = (json.dumps(plan) + '\n').encode()
            plan_path.write_bytes(payload)
            registration = dict(schema='halogen0191.mtp-gate-cost-registration.v1', commit='a' * 40,
                plan_path=campaign.PLAN_PATH, plan_sha256=hashlib.sha256(payload).hexdigest())
            result = SimpleNamespace(returncode=0, stdout=payload, stderr=b'')
            with patch.object(campaign, 'EXPORTER_SOURCE', exporter), \
                    patch.object(campaign.subprocess, 'run', return_value=result) as git:
                value = campaign.registered_sources(registration, repository=repo)
            self.assertEqual(value['files'], rows)
            self.assertEqual(git.call_args.args[0], ['git', 'show', 'a' * 40 + ':' + campaign.PLAN_PATH])
            for changed in ({**registration, 'commit': 'not-a-commit'},
                            {**registration, 'plan_path': '../untrusted'},
                            {**registration, 'plan_sha256': 'f' * 64}):
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    campaign.registered_sources(changed, repository=repo)
            plan['executed_source_pins'].pop('mtp_cost_trace.py')
            payload = json.dumps(plan).encode()
            plan_path.write_bytes(payload)
            registration['plan_sha256'] = hashlib.sha256(payload).hexdigest()
            with patch.object(campaign.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=0, stdout=payload, stderr=b'')), self.assertRaises(ValueError):
                campaign.registered_sources(registration, repository=repo)

    def test_missing_registration_rejects_before_runtime_boundary(self):
        with tempfile.TemporaryDirectory(dir=campaign.HERE) as folder, \
                patch.object(campaign, 'REGISTRATION', Path(folder) / 'missing.json'), \
                patch.object(campaign, 'support') as support, \
                patch.object(sys, 'argv', ['root_campaign.py', '--run']):
            with self.assertRaises(ValueError):
                campaign.main()
            support.assert_not_called()

    def test_combined_transition_has_exact_normal_rollback(self):
        plan = json.loads((campaign.BOUND / 'transition.json').read_bytes())
        self.assertEqual(len(plan['candidate']), 53)
        self.assertEqual(len(plan['rollback_restore']), 50)
        self.assertEqual(len(plan['rollback_remove']), 3)
        self.assertEqual(plan['source_member_count_after'], 49)
        campaign.check_files(campaign.BOUND / 'candidate', plan['candidate'])
        campaign.check_files(campaign.BOUND / 'rollback', plan['rollback_restore'])


class RuntimeFixture:
    def __init__(self, directory):
        self.root = Path(directory)
        self.events = []
        self.output = self.root / 'campaign'
        self.normal = campaign.NORMAL
        self.current = dict(phase='ready', run_id='normal-run')
        self.identity = {'fixture': 1}
        self.state = dict(latest_halogen0191_runtime_status=dict(identities=self.identity))
        self.baseline = self.ready(self.normal, 'normal')
        self.counts = {}
        self.collected = 0
        self.ops = SimpleNamespace(read=self.read, atomic=self.atomic, pin=self.pin,
            ident=SimpleNamespace(process_identity=lambda pid: dict(pid=pid)))
        self.previous = SimpleNamespace(wsl_stdin_lease=lambda path: contextlib.nullcontext(),
                                        identity_live=lambda identity: False)
        self.lifecycle = SimpleNamespace(launch=self.launch)
        self.verify = Mock(return_value=self.baseline)
        self.stop_owned = Mock(side_effect=self.stop)
        self.check_reserve = Mock()
        self.collector = SimpleNamespace(m=SimpleNamespace(check_reserve=self.check_reserve),
            collect_epoch=self.collect, OracleMismatch=type('OracleMismatch', (ValueError,), {}))
        self.consumer = SimpleNamespace(token=lambda *args: 'fixture-token',
            request=lambda route, token: dict(status='ok') if route == '/health'
                else dict(data=[dict(id='halogen-v2')]), remember=Mock())

    def pin(self, path):
        path = Path(path)
        data = path.read_bytes()
        return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    def read(self, path):
        path = Path(path)
        if path == campaign.STATE:
            return copy.deepcopy(self.state)
        if path == campaign.ROOT / 'server/.local/current.json':
            return copy.deepcopy(self.current)
        return json.loads(path.read_bytes())

    def atomic(self, path, value):
        path = Path(path)
        if path == campaign.STATE:
            self.state = copy.deepcopy(value)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        self.events.append(('write', path.name))

    def ready(self, profile, label):
        attempt = self.root / ('engine-' + label)
        attempt.mkdir(exist_ok=True)
        return dict(profile=self.pin(profile), identities=self.identity,
            outer=dict(run_id=label + '-run', phase='ready', pid=1),
            inner=dict(run_id=label + '-inner', phase='ready', controller_pid=2, attempt=str(attempt)),
            native=dict(context=32768, slots=1, kv_pool_positions=32768), utc='fixture')

    def launch(self, arguments):
        self.events.append(('launch', str(arguments.profile)))
        self.atomic(arguments.receipt, dict(profile=self.pin(arguments.profile), port=arguments.port,
                                           launcher_identity={}, controller_identity={}))
        return 0

    def await_ready(self, profile, port, receipt):
        label = 'restore-normal' if port == 8840 else Path(profile).name.split('.')[0]
        ready = self.ready(profile, label)
        self.current = dict(phase='ready', run_id=ready['outer']['run_id'])
        if port == 18840:
            from test_mtp_cost_trace import banner
            rule = self.read(profile)['engine']['speculation_policy']['HALOGEN_MTP_GATE_RULE']
            attempt = Path(ready['inner']['attempt'])
            env = campaign.native_environment(rule)
            self.atomic(attempt / 'manifest.json', dict(environment=env,
                speculation_policy=self.read(profile)['engine']['speculation_policy']))
            (attempt / 'engine.log').write_text(banner(rule), encoding='utf-8')
        return ready

    def stop(self, active, label):
        self.events.append(('stop', label))
        self.current = dict(phase='stopped', run_id=active['outer']['run_id'])

    async def collect(self, **arguments):
        from test_mtp_cost_trace import line, sample
        arm = Path(arguments['profile']).name.split('.')[0]
        start = self.counts.get(arm, 0) + 1
        ids = range(start, start + 4)
        self.counts[arm] = start + 3
        self.collected += 4
        self.asserted_output = arguments['expected_output_tokens']
        self.asserted_prompt = arguments['expected_prompt_tokens']
        attempt = Path(arguments['expected']['inner']['attempt'])
        with (attempt / 'engine.log').open('a', encoding='utf-8') as stream:
            stream.write(''.join(line(value) for value in ids))
        arguments['output'].mkdir(parents=True)
        samples = [dict(sample(value), actual_input_tokens=arguments['expected_prompt_tokens'],
            actual_output_tokens=128, output_sha256='a' * 64, ordinal=index,
            phase='warmup_excluded' if index == 0 else 'measured') for index, value in enumerate(ids)]
        return dict(collector=dict(completed=True), samples=samples)


class SavedManifestTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        from test_mtp_cost_trace import banner, line, sample
        with tempfile.TemporaryDirectory(dir=campaign.HERE) as directory:
            runtime = RuntimeFixture(directory)
            profile = Path(directory) / 'candidate.json'
            runtime.atomic(profile, campaign.private_profile(runtime.read(campaign.NORMAL),
                'candidate', 'mtp_gate_cost'))
            active = runtime.ready(profile, 'candidate')
            attempt = Path(active['inner']['attempt'])
            manifest = dict(environment=campaign.native_environment('cost'),
                speculation_policy=dict(HALOGEN_MTP_GATE_RULE='cost'))
            runtime.atomic(attempt / 'manifest.json', manifest)
            (attempt / 'engine.log').write_text(banner('cost') + ''.join(line(i) for i in range(4)),
                encoding='utf-8')
            output = Path(directory) / 'saved-cohort'
            output.mkdir()
            report = dict(samples=[sample(i) for i in range(4)])
            yield runtime, active, profile, output, report, attempt, manifest

    def test_exact_saved_manifest_and_log_bytes_are_preserved(self):
        with self.fixture() as (runtime, active, profile, output, report, attempt, manifest):
            campaign.save_cost_trace(runtime, active, profile, output, report, {})
            self.assertEqual((output / 'service-manifest.json').read_bytes(),
                             (attempt / 'manifest.json').read_bytes())
            self.assertEqual((output / 'native-cost-log.txt').read_bytes(),
                             (attempt / 'engine.log').read_bytes())
            self.assertTrue(report['mtp_cost_trace']['native_rule_activation_observed'])
            self.assertEqual(report['mtp_cost_trace']['manifest_environment'],
                             campaign.native_environment('cost'))

    def test_manifest_environment_and_declared_rule_drift_rejected_before_save(self):
        changes = [('HALOGEN_MTP_GATE_RULE', 'gate'), ('HALOGEN_MTP_GATE_P', '0.9'),
            ('HALOGEN_DRAFT_VOCAB_Q8', '1'), ('HALOGEN_SERVE_TRACE', '0'),
            ('HALOGEN_DECODE_PREFETCH', '1'), ('HALOGEN_PLD', '3,4'),
            ('HGN0191_RAW_ENABLE', '0'), ('HALOGEN_MTP_DEPTH', '3'),
            ('HALOGEN_MTP_DEPTH_HI', '3'), ('HALOGEN_MTP_GATE_LINE', 'cost'),
            ('declared_rule', 'gate')]
        for key, value in changes:
            with self.subTest(key=key), self.fixture() as data:
                runtime, active, profile, output, report, attempt, manifest = data
                if key == 'declared_rule':
                    manifest['speculation_policy']['HALOGEN_MTP_GATE_RULE'] = value
                else:
                    manifest['environment'][key] = value
                runtime.atomic(attempt / 'manifest.json', manifest)
                with self.assertRaisesRegex(ValueError, 'manifest environment'):
                    campaign.save_cost_trace(runtime, active, profile, output, report, {})
                self.assertEqual(list(output.iterdir()), [])
                self.assertNotIn('mtp_cost_trace', report)


class LifecycleBoundaryTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory(dir=campaign.HERE) as folder:
            runtime = RuntimeFixture(folder)
            previous = SimpleNamespace(allowed=Mock(), gpu_gate=Mock())
            registration = dict(schema='fixture', registration={}, files={})
            with patch.object(campaign, 'campaign_output', return_value=runtime.output), \
                    patch.object(campaign, 'registered_sources', return_value=registration), \
                    patch.object(campaign, 'source_rows', return_value={}), \
                    patch.object(campaign, 'support', return_value=(previous, runtime)), \
                    patch.object(campaign, 'terminal', return_value={}), \
                    patch.object(campaign, 'apply_overlay'), \
                    patch.object(campaign, 'restore_overlay') as restore, \
                    patch.object(campaign, 'socket', SimpleNamespace(socket=lambda:
                        contextlib.nullcontext(SimpleNamespace(bind=Mock())))), \
                    patch.dict(sys.modules, collect_epoch=runtime.collector,
                               controller_consumer=runtime.consumer), \
                    patch.object(sys, 'argv', ['root_campaign.py', '--run']):
                yield runtime, restore

    def test_canonical_normal_drift_rejected_before_runtime_boundary(self):
        with self.fixture() as (runtime, restore), \
                patch.object(campaign, 'NORMAL_SHA256', '0' * 64), \
                patch.object(campaign, 'support') as support:
            with self.assertRaisesRegex(ValueError, 'Canonical normal'):
                campaign.main()
            support.assert_not_called()
            self.assertFalse(runtime.output.exists())
            runtime.stop_owned.assert_not_called()

    def test_normal_profile_rechecked_before_output_creation(self):
        with self.fixture() as (runtime, restore), \
                patch.object(campaign, 'verify_normal_profile',
                    side_effect=[None, ValueError('Canonical normal profile differs')]) as verify:
            with self.assertRaisesRegex(ValueError, 'Canonical normal'):
                campaign.main()
            self.assertEqual(verify.call_count, 2)
            self.assertFalse(runtime.output.exists())
            runtime.stop_owned.assert_not_called()
            restore.assert_not_called()

    def test_low_memory_rejects_before_mkdir_stop_or_launch(self):
        with self.fixture() as (runtime, restore):
            runtime.check_reserve.side_effect = RuntimeError('below 22 GiB')
            with self.assertRaisesRegex(RuntimeError, '22'):
                campaign.main()
            self.assertFalse(runtime.output.exists())
            runtime.stop_owned.assert_not_called()
            restore.assert_not_called()
            self.assertFalse(any(event[0] == 'launch' for event in runtime.events))

    def test_full_mocked_workflow_collects_24_and_restores_exact_normal(self):
        with self.fixture() as (runtime, restore):
            campaign.main()
            handle = runtime.read(runtime.output / 'handle.json')
            self.assertTrue(handle['completed'])
            self.assertTrue(handle['restored'])
            self.assertEqual(runtime.collected, 24)
            self.assertEqual(runtime.asserted_output, 128)
            runtime.check_reserve.assert_called_once_with(runtime, 22)
            source_write = runtime.events.index(('write', 'executed-source-pins.json'))
            first_stop = runtime.events.index(('stop', 'normal-stop'))
            self.assertLess(source_write, first_stop)
            restore.assert_called_once()
            self.assertEqual(handle['final']['profile']['sha256'], runtime.baseline['profile']['sha256'])
            runtime.consumer.remember.assert_called_once()
            self.assertEqual(runtime.consumer.remember.call_args.args[1],
                campaign.ROOT / 'server/.local/voice-deployment/controller-selection.local.json')

    def test_partial_apply_failure_restores_and_leaves_terminal_failure(self):
        with self.fixture() as (runtime, restore), \
                patch.object(campaign, 'apply_overlay', side_effect=OSError('partial apply fixture')):
            with self.assertRaisesRegex(OSError, 'partial apply'):
                campaign.main()
            handle = runtime.read(runtime.output / 'handle.json')
            self.assertTrue(handle['terminal'])
            self.assertTrue(handle['restored'])
            self.assertFalse(handle['completed'])
            restore.assert_called_once()


if __name__ == '__main__':
    unittest.main()
