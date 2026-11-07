"""CPU-only integration tests using saved responses, RAW journals and a scratch Git plan."""
import copy
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from test_export_comparison import exporter, legacy, projected_profile

RULE = 'HALOGEN_MTP_GATE_RULE'
EXPERIMENT = 'mtp_gate_cost'
PLAN_PATH = 'docs/benchmarks/halogen0191-mtp-cost-gate-plan-20261107-v2.json'


class CostEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.ExportTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.campaign = self.fixture.campaign
        self.repository = self.fixture.root / 'registered-repository'
        self.repository.mkdir()
        self.handle = self.fixture.handle
        self.handle.update(experiment=EXPERIMENT,
                           schema='halogen0191.mtp_gate_cost-raw-campaign.v1')
        self.handle['baseline']['profile']['sha256'] = exporter.COST_PROFILE_SHA
        self.handle['final'].update(profile=dict(sha256=exporter.COST_PROFILE_SHA),
            native=dict(context=32768, slots=1, kv_pool_positions=32768,
                        status='ok', version=dict(api='0.19.1', engine='0.19.1', match=True)))
        self.handle['final']['outer']['phase'] = 'ready'
        self.handle['final']['inner']['phase'] = 'ready'

    def sources(self):
        paths = [
            exporter.COST_HERE / 'root_campaign.py',
            exporter.HERE / 'collector/collect_epoch.py',
            exporter.HERE / 'collector/qpc_audit.py',
            exporter.COST_HERE / 'integration/root-bound/transition.json',
            exporter.HERE / 'observer/root-dso-pin.json',
            exporter.COST_HERE / 'mtp_cost_trace.py',
        ]
        files = {str(path): dict(bytes=path.stat().st_size, sha256=exporter.sha(path))
                 for path in paths}
        plan = dict(schema='halogen0191.mtp-cost-gate-plan.v1',
                    experiment=EXPERIMENT,
                    exporter_source_pin=dict(sha256=exporter.sha(Path(exporter.__file__)),
                                             bytes=Path(exporter.__file__).stat().st_size),
                    executed_source_pins={path.name: files[str(path)] for path in paths})
        plan_file = self.repository / PLAN_PATH
        legacy.save(plan_file, plan)
        for arguments in (
                ['init', '-q'],
                ['add', '--', PLAN_PATH],
                ['-c', 'user.name=CPU evidence tests', '-c',
                 'user.email=cpu-evidence@example.invalid', 'commit', '-qm', 'Register synthetic plan']):
            subprocess.run(['git', *arguments], cwd=self.repository, check=True,
                           capture_output=True, text=True)
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.repository,
                                check=True, capture_output=True, text=True).stdout.strip()
        registration = dict(schema='halogen0191.mtp-gate-cost-registration.v1', commit=commit,
                            plan_path=PLAN_PATH, plan_sha256=exporter.sha(plan_file))
        legacy.save(self.campaign / 'executed-source-pins.json',
                    dict(schema='halogen0191.mtp-gate-cost-executed-sources.v1',
                         registration=registration, files=files))

    def cohort(self, arm, name, *, output='fixture result', generated=128, repeat_ids=False):
        native_fixture = legacy.fixture

        def shifted_fixture(*args, **kwargs):
            if name == 'natural16384' and not repeat_ids:
                kwargs['request_id'] += 4
            return native_fixture(*args, **kwargs)

        with patch.object(legacy, 'fixture', side_effect=shifted_fixture):
            result, folder = self.fixture.cohort(
                arm, name, experiment='draft_vocab_q8', output=output,
                generated=generated, lookup_drafted=0, lookup_accepted=0)
        profile_path = self.campaign / (arm + '.profile.json')
        legacy.save(profile_path, projected_profile(arm))
        result['collector']['profile_sha256'] = exporter.sha(profile_path)
        result['collector']['expected_output_tokens'] = 128
        legacy.save(folder / 'handle.json', result['collector'])
        rule = 'cost' if arm == 'candidate' else 'gate'
        environment = {
            RULE: rule, 'HALOGEN_MTP_GATE_P': '0.90',
            'HALOGEN_DRAFT_VOCAB_Q8': '0', 'HALOGEN_SERVE_TRACE': '1',
            'HALOGEN_DECODE_PREFETCH': '0', 'HALOGEN_PLD': '3,3',
            'HGN0191_RAW_ENABLE': '1',
        }
        manifest = dict(checkpoint='v2', context=32768, slots=1, kv_pool_positions=32768,
                        environment=environment,
                        speculation_policy=projected_profile(arm)['engine']['speculation_policy'])
        manifest_path = folder / 'service-manifest.json'
        legacy.save(manifest_path, manifest)
        marker = 'cost rule' if rule == 'cost' else 'confidence gate'
        lines = [
            'flash_serve: listening on 0.0.0.0:8731, 1 slots over ONE 32768-position KV pool, '
            'each request up to 32768 (it reserves prompt + max_tokens), max_tok 2048, '
            'BATCHED greedy or sampled; MTP depth-2 (up to 7, ' + marker + ') enabled'
        ]
        rows = []
        for sample in result['samples']:
            counters = sample['speculation']
            row = dict(id=sample['native_request_id'], rounds=counters['rounds'],
                       legacy_accepted=45, list_tokens=0, list_off=0)
            for scope in ('head', 'lookup', 'grammar'):
                row.update({scope + '_' + key: counters[scope][key]
                            for key in ('rounds', 'drafted', 'accepted')})
            rows.append(row)
            lines.append(f"req {row['id']} spec: {row['rounds']} rounds {row['legacy_accepted']} accepted; " +
                '; '.join(f"{label} {row[scope + '_rounds']} rounds "
                          f"{row[scope + '_drafted']} drafted {row[scope + '_accepted']} accepted"
                          for label, scope in (('chain', 'head'), ('lookup', 'lookup'), ('grammar', 'grammar'))) +
                '; 0 serial; list 0 tokens 0 off;')
        log = folder / 'native-cost-log.txt'
        legacy.save(log, ('\n'.join(lines) + '\n').encode(), raw=True)
        trace = dict(expected_rule=rule, startup_banner=dict(marker=marker, count=1), samples=rows,
            native_rule_activation_observed=True, per_decision_policy_observed=False,
            qualification_scope='Native startup rule with matching per-request MTP head counters',
            log=dict(path='C:/Users/PRIVATEUSER/native-cost-log.txt',
                     sha256=exporter.sha(log), bytes=log.stat().st_size),
            manifest=dict(path='C:/Users/PRIVATEUSER/service-manifest.json',
                          sha256=exporter.sha(manifest_path), bytes=manifest_path.stat().st_size),
            manifest_environment=environment)
        legacy.save(folder / 'mtp-cost-trace.json', trace)
        result['mtp_cost_trace'] = trace
        return result, folder

    def prepare(self, *, complete=True, different_output=False, repeat_ids=False, generated=128):
        self.sources()
        for arm in exporter.ARMS:
            for name in ('natural8192', 'natural16384') if complete else ('natural8192',):
                self.cohort(arm, name,
                    output='different result' if different_output and arm == 'candidate'
                        and name == 'natural16384' else 'fixture result',
                    repeat_ids=repeat_ids, generated=generated)
        return self.fixture.write_handle()

    def report(self):
        with patch.object(exporter, 'ROOT', self.repository):
            return exporter.build_report(self.fixture.write_handle())

    def save_trace(self, arm, name, trace):
        self.handle['results'][arm][name]['mtp_cost_trace'] = trace
        legacy.save(self.campaign / arm / name / 'mtp-cost-trace.json', trace)

    def repin_trace_file(self, arm, name, role, filename):
        folder = self.campaign / arm / name
        trace = copy.deepcopy(self.handle['results'][arm][name]['mtp_cost_trace'])
        path = folder / filename
        trace[role].update(bytes=path.stat().st_size, sha256=exporter.sha(path))
        self.save_trace(arm, name, trace)

    def refresh_cohort(self, arm, name, *, finish_reason=None, remove_qpc_boundaries=False):
        folder = self.campaign / arm / name
        result = self.handle['results'][arm][name]
        request = json.loads((folder / 'request.json').read_bytes())
        responses = []
        for ordinal, sample in enumerate(result['samples']):
            path = folder / ('response-' + str(ordinal) + '.json')
            response = json.loads(path.read_bytes())
            if finish_reason is not None:
                response['choices'][0]['finish_reason'] = finish_reason
            legacy.save(path, response)
            sample.update(legacy.account_response(path.read_bytes(), request, expected_output_tokens=128))
            sample['response_sha256'] = exporter.sha(path)
            if remove_qpc_boundaries:
                del sample['qpc_start_ns']
                del sample['qpc_end_ns']
            legacy.save(folder / ('sample-' + str(ordinal) + '.json'), sample)
            responses.append(path)
        ready = json.loads((folder / 'ready-before.json').read_bytes())
        raw = legacy.validate_cohort(folder / 'journals/capture', responses, folder / 'request.json',
            int(result['collector']['epoch_nonce'], 16),
            Path(ready['inner']['attempt']) / 'raw-phase/arm', require_cold=True)
        audit = legacy.audit_qpc(raw, result['samples'], exporter.sha(folder / 'request.json'))
        legacy.save(folder / 'raw-report.json', raw)
        legacy.save(folder / 'qpc-audit.json', audit)
        result.update(raw_report=raw, qpc_audit=audit)

    def test_complete_cost_evidence_separates_raw_http_and_pooled_head_with_full_vocab_fallback(self):
        self.prepare()
        report = self.report()
        self.assertEqual(report['qualified_cases'], ['natural8192', 'natural16384'])
        self.assertEqual(report['executed_source_pins']['root_campaign.py']['implementation_version'], 8)
        self.assertEqual(len(report['executed_source_pins']), 6)
        self.assertEqual(report['registration']['plan_path'], PLAN_PATH)
        for arm, rule in zip(exporter.ARMS, ('gate', 'cost', 'gate')):
            self.assertEqual(report['profiles'][arm]['mtp_gate_rule'], rule)
            for cohort in report['arms'][arm].values():
                trace = cohort['mtp_cost_trace']
                self.assertIs(trace['native_rule_activation_observed'], True)
                self.assertIs(trace['per_decision_policy_observed'], False)
                self.assertTrue(all(row['list_tokens'] == 0 for row in trace['samples']))
                self.assertTrue(all(row['legacy_accepted'] == 45 for row in trace['samples']))
                summary = cohort['summary']
                self.assertEqual(summary['actual_output_tokens'], [128, 128, 128])
                self.assertEqual(summary['output_caps'], [128, 128, 128])
                self.assertEqual(summary['whole_http_output_tps'], 6400.0)
                self.assertEqual(summary['pooled_scoped_counters']['head'],
                    dict(rounds=6, drafted=12, accepted=6, acceptance_fraction=0.5))
                self.assertIn('mean_raw_tps', summary)
        rendered = exporter.render_markdown(report)
        self.assertIn('Whole-HTTP useful-output t/s', rendered)
        self.assertIn('gate/cost/gate', rendered)
        self.assertNotIn('PRIVATEUSER', json.dumps(report) + rendered)
        self.assertNotIn('NFPU', rendered)
        outputs = exporter.write_outputs(report)
        self.assertIs(outputs['written'], False)
        self.assertEqual([row['file'] for row in outputs['outputs']], [
            'halogen0191-mtp-gate-cost-raw-20261107-v2.json',
            'halogen0191-mtp-gate-cost-raw-20261107-v2.md'])

    def test_prior_counter_failure_render_does_not_claim_preoverlay_failure(self):
        self.prepare()
        report = self.report()
        report['first_preoverlay_attempt'] = dict(terminal=True, completed=False,
            restored=True, no_measurement_requests=False, error_type='ValueError',
            included_in_comparison=False, summary=None)
        rendered = exporter.render_markdown(report)
        self.assertIn('## Earlier failed counter-qualification attempt', rendered)
        self.assertIn('after overlay application and four cohort requests', rendered)
        self.assertIn('None of its timing samples is included', rendered)
        self.assertNotIn('First pre-overlay attempt', rendered)
        self.assertNotIn('No measurement requests were recorded', rendered)

    def test_missing_second_case_withholds_both_case_comparisons(self):
        self.prepare(complete=False)
        report = self.report()
        self.assertEqual(report['qualified_cases'], [])
        self.assertFalse(report['comparison_qualification']['natural8192']['all_cost_case_arm_traces_qualified'])

    def test_one_cross_arm_output_difference_withholds_both_case_comparisons(self):
        self.prepare(different_output=True)
        self.assertEqual(self.report()['qualified_cases'], [])

    def test_native_ids_must_be_unique_across_both_cases_within_each_arm(self):
        self.prepare(repeat_ids=True)
        report = self.report()
        self.assertEqual(report['qualified_cases'], [])
        self.assertFalse(report['comparison_qualification']['natural8192']['all_cost_arm_native_ids_unique'])

    def test_finish_reason_difference_with_matching_output_bytes_withholds_both_cases(self):
        self.prepare()
        self.refresh_cohort('candidate', 'natural16384', finish_reason='length')
        report = self.report()
        self.assertEqual(report['qualified_cases'], [])
        self.assertFalse(report['comparison_qualification']['natural8192']['all_cost_finish_and_cap_semantics_matched'])

    def test_exact_qpc_boundaries_are_required_even_when_duration_only_audit_passes(self):
        self.prepare()
        self.refresh_cohort('candidate', 'natural8192', remove_qpc_boundaries=True)
        with self.assertRaisesRegex(ValueError, 'QPC'):
            self.report()

    def test_missing_trace_for_a_complete_cohort_rejects(self):
        self.prepare()
        (self.campaign / 'candidate/natural16384/mtp-cost-trace.json').unlink()
        with self.assertRaisesRegex(ValueError, 'trace'):
            self.report()

    def test_matching_saved_trace_relabelling_cannot_replace_recomputation(self):
        self.prepare()
        original = self.handle['results']['candidate']['natural8192']['mtp_cost_trace']
        for key, value in (('native_rule_activation_observed', False),
                           ('per_decision_policy_observed', True), ('expected_rule', 'gate')):
            with self.subTest(key=key):
                trace = copy.deepcopy(original)
                trace[key] = value
                self.save_trace('candidate', 'natural8192', trace)
                with self.assertRaisesRegex(ValueError, 'trace'):
                    self.report()

    def test_manifest_environment_is_recomputed_after_a_matching_repin(self):
        self.prepare()
        folder = self.campaign / 'candidate/natural8192'
        original = json.loads((folder / 'service-manifest.json').read_bytes())
        mutations = [(RULE, 'gate'), ('HALOGEN_SERVE_TRACE', '0'),
                     ('HALOGEN_DRAFT_VOCAB_Q8', '1'), ('HALOGEN_PLD', '3,4'),
                     ('HGN0191_RAW_ENABLE', '0'), ('HALOGEN_MTP_GATE_P', '0'),
                     ('HALOGEN_MTP_GATE_LINE', '0.88'), ('HALOGEN_MTP_DEPTH', '3'),
                     ('HALOGEN_MTP_DEPTH_HI', '7')]
        for key, value in mutations:
            with self.subTest(key=key):
                manifest = copy.deepcopy(original)
                manifest['environment'][key] = value
                legacy.save(folder / 'service-manifest.json', manifest)
                self.repin_trace_file('candidate', 'natural8192', 'manifest', 'service-manifest.json')
                with self.assertRaisesRegex(ValueError, 'manifest'):
                    self.report()

    def test_undeclared_manifest_rule_metadata_rejects(self):
        self.prepare()
        folder = self.campaign / 'candidate/natural8192'
        manifest = json.loads((folder / 'service-manifest.json').read_bytes())
        del manifest['speculation_policy'][RULE]
        legacy.save(folder / 'service-manifest.json', manifest)
        self.repin_trace_file('candidate', 'natural8192', 'manifest', 'service-manifest.json')
        with self.assertRaisesRegex(ValueError, 'manifest'):
            self.report()

    def test_wrong_native_startup_mode_rejects_after_log_repin(self):
        self.prepare()
        path = self.campaign / 'candidate/natural8192/native-cost-log.txt'
        path.write_bytes(path.read_bytes().replace(b', cost rule)', b', confidence gate)'))
        self.repin_trace_file('candidate', 'natural8192', 'log', 'native-cost-log.txt')
        with self.assertRaises(ValueError):
            self.report()

    def test_native_request_counter_change_rejects_after_log_repin(self):
        self.prepare()
        path = self.campaign / 'candidate/natural8192/native-cost-log.txt'
        path.write_bytes(path.read_bytes().replace(b'chain 1 rounds', b'chain 9 rounds'))
        self.repin_trace_file('candidate', 'natural8192', 'log', 'native-cost-log.txt')
        with self.assertRaises(ValueError):
            self.report()

    def test_actual_output_count_must_equal_128(self):
        self.prepare(generated=127)
        with self.assertRaises(ValueError):
            self.report()

    def test_explicit_collector_output_count_is_required(self):
        self.prepare()
        result = self.handle['results']['candidate']['natural8192']
        del result['collector']['expected_output_tokens']
        legacy.save(self.campaign / 'candidate/natural8192/handle.json', result['collector'])
        with self.assertRaisesRegex(ValueError, '128'):
            self.report()

    def test_rehashed_request_cannot_change_the_frozen_natural_output_cap(self):
        self.prepare()
        folder = self.campaign / 'candidate/natural8192'
        request = json.loads((folder / 'request.json').read_bytes())
        request['max_tokens'] = 127
        legacy.save(folder / 'request.json', request)
        result = self.handle['results']['candidate']['natural8192']
        result['collector']['request_sha256'] = exporter.sha(folder / 'request.json')
        legacy.save(folder / 'handle.json', result['collector'])
        with self.assertRaisesRegex(ValueError, 'request identity'):
            self.report()

    def test_recorded_source_paths_cannot_select_an_untrusted_root_or_helper(self):
        self.prepare()
        path = self.campaign / 'executed-source-pins.json'
        value = json.loads(path.read_bytes())
        for role in ('root_campaign.py', 'mtp_cost_trace.py'):
            key = next(key for key in value['files'] if Path(key).name == role)
            rogue = self.fixture.root / 'untrusted' / role
            legacy.save(rogue, b'raise RuntimeError("untrusted source executed")\n', raw=True)
            value['files'][str(rogue)] = value['files'].pop(key)
        legacy.save(path, value)
        report = self.report()
        self.assertEqual(report['qualified_cases'], ['natural8192', 'natural16384'])
        self.assertNotIn('untrusted', json.dumps(report))

    def test_unknown_extra_and_missing_executed_roles_reject(self):
        self.prepare()
        path = self.campaign / 'executed-source-pins.json'
        original = json.loads(path.read_bytes())
        for role in ('root_campaign.py', 'transition.json', 'mtp_cost_trace.py'):
            with self.subTest(role=role):
                value = copy.deepcopy(original)
                key = next(key for key in value['files'] if Path(key).name == role)
                value['files'][key]['sha256'] = 'f' * 64
                legacy.save(path, value)
                with self.assertRaises(ValueError):
                    self.report()
        value = copy.deepcopy(original)
        value['files']['C:/unexpected/export_comparison.py'] = dict(bytes=0, sha256='0' * 64)
        legacy.save(path, value)
        with self.assertRaisesRegex(ValueError, 'source role'):
            self.report()
        value = copy.deepcopy(original)
        del value['files'][next(key for key in value['files'] if Path(key).name == 'mtp_cost_trace.py')]
        legacy.save(path, value)
        with self.assertRaisesRegex(ValueError, 'source pins'):
            self.report()

    def test_registration_commit_plan_and_source_pins_are_verified(self):
        self.prepare()
        path = self.campaign / 'executed-source-pins.json'
        original = json.loads(path.read_bytes())
        for key, value in (('commit', '0' * 40), ('plan_sha256', 'f' * 64),
                           ('plan_path', 'docs/benchmarks/unregistered.json')):
            with self.subTest(key=key):
                changed = copy.deepcopy(original)
                changed['registration'][key] = value
                legacy.save(path, changed)
                with self.assertRaises(ValueError):
                    self.report()

    def test_final_restore_must_be_the_selected_ready_one_slot_profile(self):
        self.prepare()
        original = copy.deepcopy(self.handle['final'])
        for group, key, value in (('native', 'slots', 2), ('outer', 'phase', 'stopped'),
                                  ('inner', 'phase', 'failed'),
                                  ('native', 'status', 'error'),
                                  ('native', 'version', dict(api='0.19.0', engine='0.19.1', match=True)),
                                  ('native', 'version', dict(api='0.19.1', engine='0.19.1', match=False)),
                                  ('native', 'version', dict(api='0.19.1', engine='0.19.1', match=1)),
                                  ('native', 'version', dict(api='0.19.1', engine='0.19.1')),
                                  ('profile', 'sha256', 'f' * 64)):
            with self.subTest(group=group, key=key):
                self.handle['final'] = copy.deepcopy(original)
                self.handle['final'][group][key] = value
                with self.assertRaisesRegex(ValueError, 'estor'):
                    self.report()


if __name__ == '__main__':
    unittest.main()
