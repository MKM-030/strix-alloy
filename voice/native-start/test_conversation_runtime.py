"""Synthetic ownership/admission tests. Never launch a model or business request."""
import contextlib
import copy
import hashlib
import importlib.util
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import urllib.error


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('conversation_runtime', HERE / 'conversation_runtime.py')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


POSITIVE = ('status_unique', 'audio_stop_direct', 'current_answer', 'open_dialogue',
            'prior_correction', 'new_intake_explicit_agent', 'business_cancel_direct', 'question_help_grounded')
NEGATIVE = ('ambiguous_status_target', 'ambiguous_change_or_question_binding',
            'unavailable_or_wrong_domain_agent', 'nonauthorizing_control_context')
CRITICAL = ('false_business', 'wrong_binding', 'wrong_agent', 'false_cancel', 'false_status_target',
            'invented_result', 'accepted_text_corruption', 'accepted_stale', 'accepted_invalid',
            'accepted_late', 'unverified_acceptance', 'unexpected_business_write', 'durable_target_mismatch')
STATES = ('running', 'succeeded', 'failed', 'outcome_unknown')


class FakeHost:
    def __init__(self):
        self.free = 40.0
        self.after_launch_free = 30.0
        self.sockets = []
        self.processes = {}
        self.launches = 0
        self.stops = []
        self.probes = 0
        self.identity = {'healthy': True, 'alias': 'synthetic-conversation', 'auth_required': True}

    def memory_gib(self):
        return self.free

    def listeners(self, port):
        return self.sockets

    def process(self, pid):
        return self.processes.get(pid)

    def launch(self, argv):
        self.launches += 1
        self.free = self.after_launch_free
        self.processes[41] = {'pid': 41, 'created': 1.5, 'exe': argv[0], 'argv': argv}
        self.sockets = [{'pid': 41, 'ip': '127.0.0.1'}]
        return 41

    def probe(self, port, token):
        self.probes += 1
        return self.identity

    def stop_new(self, identity):
        self.stops.append(identity['pid'])

    @contextlib.contextmanager
    def lock(self, owner):
        yield


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This assertion supplies an intentional RED before the new module exists.
        assert Path(SPEC.origin).is_file(), 'qualified runtime owner has not been implemented'
        cls.mod = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(cls.mod)

    def setUp(self):
        workspace = HERE / 'fake-test-workspace'
        workspace.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='task6-synthetic-', dir=workspace)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exe = self.root / 'fake-engine.exe'
        self.dll = self.root / 'fake-runtime.dll'
        self.model = self.root / 'fake-model.gguf'
        self.source = self.root / 'fake-router.py'
        for path in (self.exe, self.dll, self.model, self.source):
            path.write_bytes(b'synthetic asset ' + path.name.encode())
        self.token = self.root / 'conversation.token'
        self.token.write_text('synthetic-test-credential-only-1234567890')
        self.argv = [str(self.exe), '--model', str(self.model), '--alias', 'synthetic-conversation',
                     '--ctx-size', '4096', '--parallel', '1', '--host', '127.0.0.1',
                     '--port', '52744', '--gpu-layers', '99', '--reasoning', 'off',
                     '--reasoning-budget', '0', '--api-key-file', '{token_file}']
        help_file = self.root / 'help.txt'
        help_file.write_text('\n'.join(self.argv[1::2]))
        self.profile = {
            'schema': 1, 'qualified': True, 'candidate_id': 'synthetic-only',
            'engine': {'executable': str(self.exe), 'sha256': digest(self.exe.read_bytes()),
                       'runtime_hashes': {str(self.dll): digest(self.dll.read_bytes())},
                       'argv': self.argv, 'help': self.pin(help_file)},
            'model': {'file': str(self.model), 'sha256': digest(self.model.read_bytes())},
            'source_hashes': {str(self.source): digest(self.source.read_bytes())},
            'main_profile_sha256': 'ea335895f0cb8f6ded0698ec940cab808a11162187129822ecd9c010efbdb330',
            'minimum_reserve_gib': 18.0, 'resident_budget_gib': 8.0,
            'token_file': self.token.name,
        }
        self.profile_file = self.root / 'conversation-runtime.local.json'
        self.owner = self.root / 'conversation-owner.json'
        self.host = FakeHost()
        self.write_profile()

    def pin(self, path):
        return {'file': str(path), 'sha256': digest(path.read_bytes())}

    def write_profile(self, quality_changes=None, coexist_changes=None):
        new = getattr(self, 'new_source', False)
        if new:
            source_pins = {}
            for name in self.mod._CHOICE_MODULES:
                target = self.root / 'voice/native-bridge' / (name + '.py')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('# synthetic source; no product certification')
                source_pins['voice/native-bridge/' + name + '.py'] = digest(target.read_bytes())
            self.profile['source_hashes'] = {str(self.root / k): v for k, v in source_pins.items()}
        binding = {k: v for k, v in self.profile.items() if k not in ('quality', 'coexistence', 'token_file')}
        bound = digest(canonical(binding))
        quality = {'route_cases': 120,
                   'formulation_cases': 40, 'route_p95_seconds': 1.8, 'max_route_seconds': 1.9,
                   'model_timeout_seconds': 2.0, 'all_mandatory_gates_passed': True,
                   'routing_exact': 120, 'status_exact': 40,
                   'category_counts': {k: 10 for k in POSITIVE + NEGATIVE},
                   'status_counts': {k: 10 for k in STATES},
                   'positive_family_exact': {k: 10 for k in POSITIVE},
                   'critical_counts': {k: 0 for k in CRITICAL}}
        coexist = {'minimum_available_gib': 20.0,
                   'main_context': 32768, 'main_parallel': 1, 'bounded_load': True,
                   'main_latency_gate_passed': True, 'main_count': 6, 'conversation_count': 24,
                   'main_max_seconds': 10.0, 'verified_overlap_count': 18, 'scheduled_unverified_count': 0,
                   'overlap_p95_seconds': 1.0, 'overlap_max_seconds': 1.0,
                   'main_worker_unfinished_count': 0, 'classifier_worker_unfinished_count': 0}
        quality.update(quality_changes or {})
        coexist.update(coexist_changes or {})
        def save(name, value):
            path = self.root / name
            path.write_bytes(canonical(value))
            return self.pin(path)
        life = {k: True for k in ('source_freeze_verified', 'assets_verified', 'private_token_verified',
                                  'ready', 'owned_process_stopped', 'listener_released', 'token_removed', 'within_total_deadline')}
        life['watchdog_failure'] = None
        inputs = {}
        inputs['asset_manifest'] = save('assets.json', {'files': [
            {'path': str(p), 'sha256': digest(p.read_bytes()), 'bytes': p.stat().st_size}
            for p in (self.exe, self.model, self.dll)]})
        candidate = {'id': self.profile['candidate_id'], 'engine': str(self.exe),
                     'engine_sha256': self.profile['engine']['sha256'], 'gguf': str(self.model),
                     'gguf_sha256': self.profile['model'].get('sha256'), 'gguf_bytes': self.model.stat().st_size,
                     'asset_file_count': 3, 'resident_budget_gib': self.profile['resident_budget_gib'],
                     'local_asset_hash_manifest_sha256': inputs['asset_manifest']['sha256'],
                     'recommended_argv': [a if a != '{token_file}' else '__FRESH_OWNED_TOKEN__' for a in self.profile['engine']['argv']]}
        inputs['candidate_manifest'] = save('v4-owned-candidates.json', {'version': 'v4', 'status': 'REVIEWED_FROZEN', 'candidates': [candidate]})
        artifacts = {Path(inputs['candidate_manifest']['file']).name: inputs['candidate_manifest']['sha256']}
        helpers = ('v4_candidate_runner.py', 'v4_scoring.py', 'v4_coexistence_runner.py')
        if new:
            helpers += ('v4_pinned_loader.py', 'v4_pinned_child.py', 'v4_adapter.py', 'v4_runtime_callbacks.py', 'v4_owned_lifecycle.py')
        for name in helpers:
            p = self.root / name
            p.write_text('# synthetic public contract fixture only')
            artifacts[name] = digest(p.read_bytes())
        manifest = {'stage': 'task12-reviewed', 'commit': 'a' * 40,
            'source_sha256': {self.source.name: digest(self.source.read_bytes())}, 'test_sha256': {}}
        extra = {}
        execution = None
        if new:
            reviews = {}
            for task in (12, 13, 14, 15):
                review = save(f'fake-task-{task}-review.json', {'synthetic_only': True})
                reviews[str(task)] = {'path': review['file'], 'sha256': review['sha256'], 'commit': 'a' * 40, 'status': 'PASS'}
            identity = {'loader_version': 'v4-retained-bytes-1', 'loader_sha256': artifacts['v4_pinned_loader.py'],
                'support_sha256': {name: artifacts[name] for name in helpers},
                'application_modules': list(self.mod._CHOICE_MODULES), 'external_imports': [],
                'interpreter': {'executable': str(self.source), 'sha256': digest(self.source.read_bytes()), 'version': 'synthetic-only', 'implementation': 'cpython', 'stdlib_tree_sha256': 'c' * 64, 'stdlib_files': 1, 'runtime_binary_sha256': {str(self.source): digest(self.source.read_bytes())}}}
            extra = {'stage': self.mod._CHOICE_STAGE, 'protocol_format': 'closed_choice_v1', 'reviewed_tasks': [12, 13, 14, 15], 'snapshot_root': str(self.root)}
            test_file = self.root / 'voice/native-bridge/test_public_fake.py'
            test_file.write_text('# synthetic test inventory only')
            manifest.update(extra, source_sha256=source_pins, test_sha256={'voice/native-bridge/test_public_fake.py': digest(test_file.read_bytes())}, task_reviews=reviews, execution_identity=identity,
                application_imports={name: [] for name in self.mod._CHOICE_MODULES})
        inputs['source_manifest'] = save('source-manifest.json', manifest)
        inputs['source_record'] = save('v4-source-record.json', {'version': 'v4', 'status': 'REVIEWED_FROZEN',
            'commit': 'a' * 40, 'manifest_path': inputs['source_manifest']['file'], **extra,
            'manifest_sha256': inputs['source_manifest']['sha256'], 'reviewed_inventory': list(manifest['source_sha256']) + list(manifest['test_sha256'])})
        artifacts['v4-source-record.json'] = inputs['source_record']['sha256']
        if new:
            execution = {'stage': self.mod._CHOICE_STAGE, 'protocol_format': 'closed_choice_v1', 'source_commit': 'a' * 40,
                'manifest_sha256': inputs['source_manifest']['sha256'], 'execution_identity': identity,
                'application_sha256': source_pins, 'application_paths': {name: str((self.root / name).resolve()) for name in source_pins},
                'session_id': '_v4_pinned_' + '1' * 32, 'pid': 1234, 'isolated_child': True}
        inputs['artifact_manifest'] = save('v4-adapter-preflight.json', {'status': 'REVIEWED_FROZEN',
            'source_record_sha256': inputs['source_record']['sha256'], 'corpus_sha256': 'b' * 64,
            'main_profile_sha256': self.profile['main_profile_sha256'], 'artifact_sha256': artifacts,
            'asset_manifests': {candidate['id']: {'manifest_path': inputs['asset_manifest']['file'],
                                                'manifest_sha256': inputs['asset_manifest']['sha256']}}})
        inputs['go'] = save('v4-qualification-go.json', {'status': 'GO', 'authorization': 'GO V4 160-CASE QUALIFICATION',
            'corpus_sha256': 'b' * 64, 'artifact_manifest_sha256': inputs['artifact_manifest']['sha256'],
            'source_record_sha256': inputs['source_record']['sha256']})
        provenance = {'go_record_sha256': inputs['go']['sha256'],
                      'artifact_manifest_sha256': inputs['artifact_manifest']['sha256'], 'corpus_sha256': 'b' * 64,
                      'source_record_sha256': inputs['source_record']['sha256'], 'source_commit': 'a' * 40,
                      'source_manifest_sha256': inputs['source_manifest']['sha256'], 'artifact_sha256': artifacts}
        cases = []
        for index in range(160):
            score = {'case_id': f'case-{index}', 'family': 'routing' if index < 120 else 'status',
                     'category': (POSITIVE + NEGATIVE)[index // 10] if index < 120 else 'dedicated_status',
                     'status_state': '' if index < 120 else STATES[(index - 120) // 10],
                     'exact': True, 'accept_elapsed_ms': quality['max_route_seconds'] * 1000 if index == 159 else quality['route_p95_seconds'] * 1000,
                     'accept_call': {'api': 'Attachment.accept', 'count': 1, 'call_id': f'call-{index}', 'candidate_id': candidate['id']},
                     **{k: False for k in CRITICAL}}
            cases.append({'case_id': score['case_id'], 'candidate_id': candidate['id'], 'phase': 'complete', 'status': 'complete', 'score': score, **({'actual': {'execution_evidence': execution}} if new else {})})
        inputs['receipt'] = save('synthetic-receipts.json', {'candidate_id': candidate['id'], 'completed_cases': 160,
            'error': None, 'lifecycle': life, 'owner_close_succeeded': True, 'cases': cases, **({'execution_evidence': execution} if new else {})})
        aggregate = {'routing_exact': 120, 'status_exact': 40, 'positive_family_exact': {k: 10 for k in POSITIVE},
                     'critical_counts': {k: 0 for k in CRITICAL}, 'p95_ms': quality['route_p95_seconds'] * 1000,
                     'max_ms': quality['max_route_seconds'] * 1000, 'quality_pass': True, 'latency_pass': True, 'qualification_pass': True}
        inputs['summary'] = save('v4-qualification-results.json', {'status': 'QUALIFICATION_RUN_COMPLETE', 'corpus_sha256': 'b' * 64,
            'provenance': provenance, 'candidates': [{'candidate_id': candidate['id'], 'completed_cases': 160, 'error': None,
            'owner_close_succeeded': True, 'lifecycle': life, 'score': aggregate, 'receipt_file': inputs['receipt']['file'], **({'execution_evidence': execution} if new else {})}]})
        self.quality_inputs = inputs
        main_rows, conversation_rows = [], []
        for i in range(6):
            main_rows.append({'index': i, 'worker_completed': True, 'worker_unfinished': False, 'client_cancelled': False,
                'timeout': False, 'late_completion': False, 'error_type': None, 'actual_http_calls': 1, 'http_send_attempts': 1,
                'http_send_confirmed': True, 'http_started': 100 + 100 * i, 'http_finished': 110 + 100 * i,
                'valid': True, 'observed_active': True, 'wall_ms': 10000.0})
        for i in range(24):
            overlap, main_index = i >= 6, (i - 6) // 3 if i >= 6 else None
            begin = (101 + 100 * main_index + (i - 6) % 3) if overlap else i * 2
            conversation_rows.append({'index': i, 'phase': 'overlap' if overlap else 'serial_reference', 'main_index': main_index,
                'valid': True, 'timeout': False, 'invalid': False, 'policy_contract_verified': True,
                'actual_http_calls': 1, 'http_send_attempts': 1, 'http_send_confirmed': True,
                'http_started': begin, 'http_finished': begin + 1, 'http_worker_unfinished': False,
                'http_error_type': None, 'main_active_at_probe': overlap, 'main_probe_at': begin - .1 if overlap else None,
                'verified_overlap': overlap, 'wall_ms': 1000.0})
        def timing(count, ms):
            return {'count': count, 'timed_count': count, 'p50_ms': ms if count else None,
                    'p95_ms': ms if count else None, 'max_ms': ms if count else None,
                    'valid': count, 'timeouts': 0, 'invalid': 0}
        result = {'status': 'measured', 'candidate_id': candidate['id'],
            'qualification': {'sha256': inputs['summary']['sha256'], 'candidate_id': candidate['id'], 'routing_exact': 120,
                'status_exact': 40, 'corpus_sha256': 'b' * 64, 'provenance': provenance},
            'main_requests': main_rows, 'conversation_requests': conversation_rows, 'business_calls': 0,
            'post_idle': True, 'elapsed_seconds': 100.0, 'terminal_cleanup': True, 'owned_cleanup': life,
            'lifecycle_start_attempted': True, 'owned_process_spawned': True, 'owned_token_created': True,
            'main_worker_unfinished_count': 0, 'classifier_worker_unfinished_count': 0,
            'main_latency_gate_passed': True, 'conversation_overlap_latency_gate_passed': True,
            'scheduled_overlap_count': 18, 'verified_overlap_count': 18, 'scheduled_unverified_count': 0,
            'serial_timing': timing(6, 1000.0), 'verified_overlap_timing': timing(18, 1000.0),
            'scheduled_unverified_timing': timing(0, 0), 'main_timing': timing(6, 10000.0),
            'health_samples': {'count': 10, 'main_active_one_count': 6, 'max_main_active': 1,
                'max_main_queued': 0, 'minimum_free_gib': 20.0}}
        if new:
            result['execution_evidence'] = dict(execution, session_id='_v4_pinned_' + '2' * 32)
        coex_inputs = {'result': save('synthetic-coexistence.json', result)}
        coex_inputs['go'] = save('coexistence-go.json', {'status': 'ROOT_GO_V4_COEXISTENCE', 'review_status': 'APPROVED_BY_ROOT',
            'candidate_id': candidate['id'], 'main_requests_max': 6, 'conversation_requests_max': 24,
            'qualification_result_sha256': inputs['summary']['sha256'], 'qualification_go_record_sha256': inputs['go']['sha256'],
            'qualification_corpus_sha256': 'b' * 64, 'candidate_manifest_sha256': inputs['candidate_manifest']['sha256'],
            'artifact_manifest_sha256': inputs['artifact_manifest']['sha256'], 'runner_sha256': artifacts['v4_coexistence_runner.py'],
            'main_profile_sha256': self.profile['main_profile_sha256']})
        self.coex_inputs = coex_inputs
        for key, data, pins in [('quality', quality, inputs), ('coexistence', coexist, coex_inputs)]:
            evidence = {'schema': 2, 'binding_sha256': bound, 'inputs': pins, 'measurements': data}
            review = {'schema': 1, 'decision': 'APPROVED', 'reviewer': 'synthetic-review-only',
                'reviewed_at': '2026-10-23T00:00:00Z', 'normalizer_sha256': digest(Path(self.mod.__file__).read_bytes()),
                'normalization_sha256': digest(canonical(evidence)), 'model_timeout_seconds': 2,
                'main_context': 32768, 'main_parallel': 1}
            evidence['review'] = save(key + '-review.json', review)
            self.profile[key] = save(key + '.json', evidence)
        self.profile_file.write_bytes(canonical(self.profile))
        self.profile_sha = digest(self.profile_file.read_bytes())

    def runtime(self):
        return self.mod.ConversationRuntime(self.profile_file, self.profile_sha, self.owner, self.host)

    def rewrite_evidence(self, kind, edit):
        path = Path(self.profile[kind]['file'])
        evidence = json.loads(path.read_bytes())
        edit(evidence)
        review_path = Path(evidence['review']['file'])
        review = json.loads(review_path.read_bytes())
        review['normalization_sha256'] = digest(canonical({k: v for k, v in evidence.items() if k != 'review'}))
        review_path.write_bytes(canonical(review))
        evidence['review'] = self.pin(review_path)
        path.write_bytes(canonical(evidence))
        self.profile[kind] = self.pin(path)
        self.profile_file.write_bytes(canonical(self.profile))
        self.profile_sha = digest(self.profile_file.read_bytes())

    def mutate_receipt(self, kind, key, edit):
        def mutate(evidence):
            path = Path(evidence['inputs'][key]['file'])
            data = json.loads(path.read_bytes())
            edit(data)
            path.write_bytes(canonical(data))
            evidence['inputs'][key] = self.pin(path)
        self.rewrite_evidence(kind, mutate)

    def test_receipt_backed_v4_normalization_accepts_only_measured_complete_pass(self):
        self.assertEqual(self.runtime().run(check_only=True), 'prepared')

    def test_declaration_only_v1_cannot_admit_even_with_true_flags(self):
        binding = digest(canonical({k: v for k, v in self.profile.items()
                                    if k not in ('quality', 'coexistence', 'token_file')}))
        declarations = {
            'quality': {'route_cases': 120, 'formulation_cases': 40, 'route_p95_seconds': 1.8,
                        'max_route_seconds': 1.9, 'model_timeout_seconds': 2,
                        'all_mandatory_gates_passed': True},
            'coexistence': {'minimum_available_gib': 20, 'main_context': 32768, 'main_parallel': 1,
                            'bounded_load': True, 'main_latency_gate_passed': True}}
        for key, values in declarations.items():
            path = self.root / (key + '-legacy-declaration.json')
            path.write_bytes(canonical({'schema': 1, 'passed': True, 'binding_sha256': binding, **values}))
            self.profile[key] = self.pin(path)
        self.profile_file.write_bytes(canonical(self.profile))
        self.profile_sha = digest(self.profile_file.read_bytes())
        with self.assertRaises(RuntimeError):
            self.runtime().run(check_only=True)

    def test_missing_provenance_and_review_rejected(self):
        for kind, field in [('quality', 'go'), ('quality', 'receipt'), ('quality', 'source_record'),
                            ('quality', 'source_manifest'), ('quality', 'asset_manifest'),
                            ('quality', 'candidate_manifest'), ('quality', 'artifact_manifest'), ('coexistence', 'go')]:
            with self.subTest(kind=kind, field=field):
                self.write_profile()
                self.rewrite_evidence(kind, lambda e: e['inputs'].pop(field))
                with self.assertRaises(RuntimeError):
                    self.runtime().run(check_only=True)
        self.write_profile()
        evidence = json.loads(Path(self.profile['quality']['file']).read_bytes())
        Path(evidence['review']['file']).unlink()
        with self.assertRaises(RuntimeError):
            self.runtime().run(check_only=True)

    def test_any_critical_score_rejected_despite_aggregate_pass(self):
        for critical in CRITICAL:
            with self.subTest(critical=critical):
                self.write_profile()
                self.mutate_receipt('quality', 'receipt', lambda r: r['cases'][0]['score'].update({critical: True}))
                with self.assertRaises(RuntimeError):
                    self.runtime().run(check_only=True)

    def test_case_coverage_partial_duplicate_or_incomplete_rejected(self):
        edits = [lambda r: r['cases'].pop(),
                 lambda r: r['cases'].__setitem__(1, copy.deepcopy(r['cases'][0])),
                 lambda r: r['cases'][0].update(phase='scoring'),
                 lambda r: r['cases'][0]['score'].update(category='unknown'),
                 lambda r: r['cases'][120]['score'].update(status_state='running-other'),
                 lambda r: r.update(owner_close_succeeded=False)]
        for edit in edits:
            self.write_profile()
            self.mutate_receipt('quality', 'receipt', edit)
            with self.assertRaises(RuntimeError):
                self.runtime().run(check_only=True)

    def test_raw_success_counters_must_match_aggregate_and_thresholds(self):
        for indices in (range(13), range(3), [120]):
            self.write_profile()
            def edit(data):
                for i in indices:
                    data['cases'][i]['score']['exact'] = False
            self.mutate_receipt('quality', 'receipt', edit)
            with self.assertRaises(RuntimeError):
                self.runtime().run(check_only=True)

    def test_failed_quality_thresholds_rejected_even_when_all_claims_agree(self):
        cases = [(list(range(80, 93)), {'routing_exact': 107}),
                 ([0, 1, 2], {'routing_exact': 117, 'positive_family_exact': {**{k: 10 for k in POSITIVE}, POSITIVE[0]: 7}}),
                 ([120], {'status_exact': 39})]
        for indices, counters in cases:
            with self.subTest(counters=counters):
                self.write_profile()
                def receipt_edit(data):
                    for i in indices:
                        data['cases'][i]['score']['exact'] = False
                self.mutate_receipt('quality', 'receipt', receipt_edit)
                self.mutate_receipt('quality', 'summary', lambda s: s['candidates'][0]['score'].update(counters))
                self.rewrite_evidence('quality', lambda e: e['measurements'].update(counters))
                with self.assertRaises(RuntimeError):
                    self.runtime().run(check_only=True)

    def test_pinned_receipt_bytes_and_reviewed_normalizer_cannot_drift(self):
        path = Path(self.quality_inputs['receipt']['file'])
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaises(RuntimeError):
            self.runtime().run(check_only=True)
        self.write_profile()
        evidence = json.loads(Path(self.profile['quality']['file']).read_bytes())
        review_path = Path(evidence['review']['file'])
        review = json.loads(review_path.read_bytes())
        review['normalizer_sha256'] = '0' * 64
        review_path.write_bytes(canonical(review))
        self.rewrite_evidence('quality', lambda e: e.update(review=self.pin(review_path)))
        with self.assertRaises(RuntimeError):
            self.runtime().run(check_only=True)

    def test_coexistence_requires_actual_complete_workers_and_overlap(self):
        edits = [lambda r: r['main_requests'].pop(), lambda r: r['conversation_requests'].pop(),
                 lambda r: r['main_requests'][0].update(wall_ms=55001),
                 lambda r: r['main_requests'][0].update(worker_unfinished=True),
                 lambda r: r['main_requests'][0].update(timeout=True),
                 lambda r: r['conversation_requests'][0].update(http_worker_unfinished=True),
                 lambda r: r['conversation_requests'][6].update(main_active_at_probe=False),
                 lambda r: r['conversation_requests'][6].update(wall_ms=2201),
                 lambda r: r['health_samples'].update(minimum_free_gib=17.9),
                 lambda r: r.update(terminal_cleanup=False)]
        for edit in edits:
            self.write_profile()
            self.mutate_receipt('coexistence', 'result', edit)
            with self.assertRaises(RuntimeError):
                self.runtime().run(check_only=True)

    def test_unverified_scheduled_overlap_is_disclosed_separately(self):
        def change(result):
            result['conversation_requests'][6].update(main_active_at_probe=False, verified_overlap=False)
            result['verified_overlap_count'] = 17
            result['scheduled_unverified_count'] = 1
            result['verified_overlap_timing'].update(count=17, timed_count=17, valid=17)
            result['scheduled_unverified_timing'].update(count=1, timed_count=1, valid=1,
                                                        p50_ms=1000.0, p95_ms=1000.0, max_ms=1000.0)
        self.mutate_receipt('coexistence', 'result', change)
        self.rewrite_evidence('coexistence', lambda e: e['measurements'].update(
            verified_overlap_count=17, scheduled_unverified_count=1))
        self.assertEqual(self.runtime().run(check_only=True), 'prepared')

    def test_repeated_start_reuses_exact_owned_process(self):
        self.assertEqual(self.runtime().run(), 'started')
        self.assertEqual(self.runtime().run(), 'reused')
        self.assertEqual(self.host.launches, 1)
        owner = json.loads(self.owner.read_text())
        self.assertEqual(owner['pid'], 41)
        self.assertEqual(owner['created'], 1.5)
        self.assertEqual(owner['port'], 52744)
        self.assertEqual(owner['model_sha256'], digest(self.model.read_bytes()))
        self.assertEqual(owner['profile_sha256'], self.profile_sha)
        self.assertNotIn('argv', owner)
        self.assertNotIn('token', self.owner.read_text())
        self.assertNotIn(self.token.read_text(), self.owner.read_text())

    def test_foreign_owner_refused_before_auth_probe(self):
        self.host.sockets = [{'pid': 99, 'ip': '127.0.0.1'}]
        with self.assertRaises(RuntimeError):
            self.runtime().run()
        self.assertEqual((self.host.launches, self.host.probes, self.host.stops), (0, 0, []))

    def test_reused_pid_creation_time_refused(self):
        self.runtime().run()
        self.host.processes[41]['created'] = 5.5
        with self.assertRaises(RuntimeError):
            self.runtime().run()
        self.assertEqual(self.host.launches, 1)
        self.assertEqual(self.host.stops, [])

    def test_changed_args_refused_without_disclosing_them(self):
        self.runtime().run()
        self.host.processes[41]['argv'] += ['--api-key', 'MUST-NOT-LEAK']
        with self.assertRaises(RuntimeError) as error:
            self.runtime().run()
        self.assertNotIn('MUST-NOT-LEAK', str(error.exception))
        self.assertEqual(self.host.stops, [])

    def test_stale_owner_without_listener_does_not_restart(self):
        self.runtime().run()
        self.host.sockets = []
        self.host.processes = {}
        with self.assertRaises(RuntimeError):
            self.runtime().run()
        self.assertEqual(self.host.launches, 1)

    def test_identity_read_failure_preserves_barrier_and_prevents_second_launch(self):
        original_launch = self.host.launch
        def loading(argv):
            pid = original_launch(argv)
            self.host.sockets = []
            return pid
        self.host.launch = loading
        def denied(pid):
            raise PermissionError('synthetic private process details')
        self.host.process = denied
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                self.runtime().run()
        self.assertEqual(self.host.launches, 1)
        self.assertEqual(self.host.stops, [])
        barrier = json.loads(self.owner.read_text())
        self.assertEqual(barrier['state'], 'launch_unresolved')
        self.assertEqual(barrier['pid'], 41)
        self.assertNotIn('argv', barrier)
        self.assertNotIn(self.token.read_text(), self.owner.read_text())

    def test_launch_exception_keeps_prelaunch_barrier_without_signaling_any_pid(self):
        def launch(argv):
            self.host.launches += 1
            raise PermissionError('process launch disposition unknown')
        self.host.launch = launch
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                self.runtime().run()
        self.assertEqual(self.host.launches, 1)
        self.assertEqual(self.host.stops, [])
        self.assertEqual(json.loads(self.owner.read_text())['state'], 'launch_unresolved')

    def test_cleanup_identity_failure_keeps_failed_barrier(self):
        original = self.host.process
        calls = 0
        def process(pid):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise PermissionError('synthetic inaccessible process')
            return original(pid)
        self.host.process = process
        with self.assertRaises(RuntimeError):
            self.runtime().run()
        self.assertEqual(json.loads(self.owner.read_text())['state'], 'failed')
        with self.assertRaises(RuntimeError):
            self.runtime().run()
        self.assertEqual(self.host.launches, 1)
        self.assertEqual(self.host.stops, [])

    def test_nonloopback_listener_refused(self):
        self.runtime().run()
        self.host.sockets[0]['ip'] = '0.0.0.0'
        with self.assertRaises(RuntimeError):
            self.runtime().run()

    def test_check_only_no_files_or_process_mutation(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(self.runtime().run(check_only=True), 'prepared')
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertEqual((self.host.launches, self.host.probes), (0, 0))

    def test_check_only_verifies_existing_owner_without_rewriting(self):
        self.runtime().run()
        before = self.owner.read_bytes()
        self.assertEqual(self.runtime().run(check_only=True), 'reused')
        self.assertEqual(before, self.owner.read_bytes())
        self.assertEqual(self.host.launches, 1)

    def test_missing_hash_fails_closed(self):
        del self.profile['model']['sha256']
        self.write_profile()
        with self.assertRaises(RuntimeError):
            self.runtime().run()
        self.assertEqual(self.host.launches, 0)

    def test_asset_drift_fails_closed(self):
        for path in (self.exe, self.dll, self.model, self.source):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(b'changed')
                with self.assertRaises(RuntimeError):
                    self.runtime().run()
                path.write_bytes(original)
        self.assertEqual(self.host.launches, 0)

    def test_unqualified_or_insufficient_evidence_fails_closed(self):
        for quality, coexist in [({'passed': False}, {}), ({'route_cases': 119}, {}),
                                 ({'formulation_cases': 39}, {}), ({'max_route_seconds': 2.21}, {}),
                                 ({'route_p95_seconds': 2.0}, {}), ({'model_timeout_seconds': 2.1}, {}),
                                 ({'all_mandatory_gates_passed': False}, {}),
                                 ({'binding_sha256': '0' * 64}, {}), ({}, {'passed': False}),
                                 ({}, {'minimum_available_gib': 17.9}),
                                 ({}, {'main_parallel': 2}), ({}, {'bounded_load': False})]:
            with self.subTest(quality=quality, coexist=coexist):
                self.write_profile(quality, coexist)
                with self.assertRaises(RuntimeError):
                    self.runtime().run(check_only=True)
        self.assertEqual(self.host.launches, 0)

    def test_route_overhead_is_not_mislabeled_model_timeout(self):
        self.write_profile({'max_route_seconds': 2.1, 'route_p95_seconds': 1.99, 'model_timeout_seconds': 2.0})
        self.assertEqual(self.runtime().run(check_only=True), 'prepared')

    def test_prelaunch_budget_is_reserved(self):
        self.host.free = 25.99
        with self.assertRaises(RuntimeError):
            self.runtime().run()
        self.assertEqual(self.host.launches, 0)

    def test_reserve_breach_cleans_only_new_exact_owned_child(self):
        self.host.after_launch_free = 17.9
        with self.assertRaises(RuntimeError):
            self.runtime().run()
        self.assertEqual(self.host.stops, [41])
        self.assertEqual(json.loads(self.owner.read_text())['state'], 'failed')

    def test_bad_health_alias_or_auth_fails_closed(self):
        for key, value in [('healthy', False), ('alias', 'wrong'), ('auth_required', False)]:
            with self.subTest(key=key):
                self.host = FakeHost()
                self.owner.unlink(missing_ok=True)
                self.host.identity[key] = value
                with self.assertRaises(RuntimeError):
                    self.runtime().run()
                self.assertEqual(self.host.stops, [41])

    def test_unsafe_argv_fails_closed_even_with_matching_evidence(self):
        original = list(self.argv)
        for flag, value in [('--host', '0.0.0.0'), ('--parallel', '2'), ('--ctx-size', '32768'),
                            ('--gpu-layers', '0'), ('--reasoning', 'on'), ('--api-key-file', 'other')]:
            with self.subTest(flag=flag):
                self.profile['engine']['argv'] = list(original)
                self.profile['engine']['argv'][original.index(flag) + 1] = value
                self.write_profile()
                with self.assertRaises(RuntimeError):
                    self.runtime().run()

    def test_valueless_no_context_shift_preserves_receipt_and_owner_checks(self):
        self.argv.append('--no-context-shift')
        help_file = self.root / 'help.txt'
        help_file.write_text(help_file.read_text() + '\n--no-context-shift\n')
        self.profile['engine']['help'] = self.pin(help_file)
        self.write_profile()
        self.runtime().run(check_only=True)
        self.assertEqual(self.host.launches, 0)

    def test_new_admitted_profile_cannot_use_old_qualified_chain(self):
        self.profile['admitted_contract'] = {'stage': 'task17-grounded-closed-choice-reviewed-source'}
        self.write_profile()
        with self.assertRaises(RuntimeError):
            self.runtime().run(check_only=True)

    def select(self, changes=None):
        responsive = {'enabled': True, 'mode': 'assist', 'store_file': 'tasks.sqlite',
                      'model_url': 'http://127.0.0.1:52744/v1/chat/completions',
                      'model_name': 'synthetic-conversation', 'model_token_file': self.token.name,
                      'model_timeout_seconds': 2.0}
        responsive.update(changes or {})
        self.responsive = self.root / 'responsive.local.json'
        self.responsive.write_bytes(canonical(responsive))
        native = self.root / 'native.local.json'
        native.write_bytes(canonical({'responsive_config_file': self.responsive.name}))
        selection = self.root / 'conversation-selection.local.json'
        selection.write_bytes(canonical({'schema': 1, 'profile_file': self.profile_file.name,
                                         'profile_sha256': self.profile_sha,
                                         'responsive_profile_sha256': digest(self.responsive.read_bytes())}))
        return selection, native

    def test_selection_binds_exact_responsive_deployment(self):
        selected = self.mod.selected_runtime(*self.select(), host=self.host)
        self.assertEqual(selected.run(check_only=True), 'prepared')

    def test_absent_selection_does_not_activate_or_create_files(self):
        native = self.root / 'native.local.json'
        native.write_text('{}')
        self.assertIsNone(self.mod.selected_runtime(self.root / 'missing-selection.json', native, host=self.host))
        self.assertFalse(self.owner.exists())

    def test_enabled_responsive_cannot_bypass_missing_selection(self):
        selection, native = self.select()
        selection.unlink()
        with self.assertRaises(RuntimeError):
            self.mod.selected_runtime(selection, native, host=self.host)

    def test_selection_refuses_full_mode_or_mismatched_model(self):
        for changes in [{'mode': 'full'}, {'enabled': False}, {'model_name': 'foreign'},
                        {'model_url': 'http://127.0.0.1:8823/v1/chat/completions'},
                        {'model_timeout_seconds': 3}, {'store_file': '../public-tasks.sqlite'}]:
            with self.subTest(changes=changes):
                with self.assertRaises(RuntimeError):
                    self.mod.selected_runtime(*self.select(changes), host=self.host)

    def test_responsive_profile_drift_fails_closed(self):
        selection, native = self.select()
        self.responsive.write_text('{}')
        with self.assertRaises(RuntimeError):
            self.mod.selected_runtime(selection, native, host=self.host)

    def test_existing_owner_reserve_failure_never_stops_it(self):
        self.runtime().run()
        self.host.free = 17.9
        with self.assertRaises(RuntimeError):
            self.runtime().run()
        self.assertEqual(self.host.stops, [])
        self.assertEqual(self.host.launches, 1)

    def test_duplicate_profile_keys_and_unpinned_profile_fail(self):
        self.profile_file.write_text('{"schema":1,"schema":1}')
        self.profile_sha = digest(self.profile_file.read_bytes())
        with self.assertRaises(RuntimeError):
            self.runtime().run()
        self.assertEqual(self.host.launches, 0)

    def test_http_probe_requires_wrong_bearer_to_be_rejected(self):
        class Response(io.BytesIO):
            status = 200
        class Opener:
            def open(inner, request, timeout):
                if not request.has_header('Authorization'):
                    raise urllib.error.HTTPError(request.full_url, 401, 'synthetic', {}, None)
                body = {'status': 'ok'} if request.full_url.endswith('/health') else {'data': [{'id': 'synthetic-conversation'}]}
                return Response(canonical(body))
        with patch.object(self.mod.urllib.request, 'build_opener', return_value=Opener()):
            proof = self.mod.WindowsHost().probe(52744, 'synthetic-credential')
        self.assertFalse(proof['auth_required'])

    def test_http_probe_accepts_enforced_auth_and_model_identity(self):
        class Response(io.BytesIO):
            status = 200
        class Opener:
            def open(inner, request, timeout):
                if request.get_header('Authorization') != 'Bearer synthetic-credential':
                    raise urllib.error.HTTPError(request.full_url, 401, 'synthetic', {}, None)
                body = {'status': 'ok'} if request.full_url.endswith('/health') else {'data': [{'id': 'synthetic-conversation'}]}
                return Response(canonical(body))
        with patch.object(self.mod.urllib.request, 'build_opener', return_value=Opener()):
            proof = self.mod.WindowsHost().probe(52744, 'synthetic-credential')
        self.assertEqual(proof, {'healthy': True, 'alias': 'synthetic-conversation', 'auth_required': True})

    def test_cleanup_uses_the_same_pid_creation_checked_process_handle(self):
        class Process:
            def __init__(inner):
                inner.terminated = False
            def create_time(inner):
                return 1.5
            def exe(inner):
                return str(self.exe)
            def cmdline(inner):
                return ['synthetic-command']
            def terminate(inner):
                inner.terminated = True
        original, replacement = Process(), Process()
        host = self.mod.WindowsHost()
        with patch.object(host.psutil, 'Process', side_effect=[original, replacement]):
            host.stop_new({'pid': 41, 'created': 1.5, 'exe': str(self.exe), 'argv': ['synthetic-command']})
        self.assertTrue(original.terminated)
        self.assertFalse(replacement.terminated)

    def test_atomic_write_does_not_delete_a_preexisting_pending_file(self):
        pending = self.owner.with_name(self.owner.name + '.' + str(self.mod.os.getpid()) + '.pending')
        pending.write_text('other pending evidence')
        with self.assertRaises(FileExistsError):
            self.mod._atomic(self.owner, {'synthetic': True})
        self.assertEqual(pending.read_text(), 'other pending evidence')


class DesktopSeamTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('current_voice_task6', HERE / 'start_current_voice.py')
        self.start = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.start)
        self.events = []
        @contextlib.contextmanager
        def lock():
            self.events.append('lock')
            yield
        self.start.services = SimpleNamespace(startup_lock=lock, voice_start=lambda *a, **k: self.events.append('voice'))
        self.start.speech_services = SimpleNamespace(startup_lock=lock, speech_start=lambda *a: self.events.append('speech'))
        for name in ('preflight', 'model_start', 'gateway_start', 'funnel_check'):
            setattr(self.start, name, lambda *a, n=name: self.events.append(n))
        self.start.validate_profile = lambda: {}

    def test_desktop_check_only_checks_selected_runtime_without_start(self):
        self.start.conversation_stage = lambda check_only: self.events.append(('conversation', check_only))
        self.start.run(check_only=True)
        self.assertEqual(self.events, ['preflight', ('conversation', True)])

    def test_desktop_preflights_addition_before_any_start_and_starts_after_gemma(self):
        self.start.conversation_stage = lambda check_only: self.events.append(('conversation', check_only))
        self.start.run()
        self.assertEqual(self.events, ['lock', 'lock', 'preflight', ('conversation', True), 'speech',
                                       'model_start', 'gateway_start', ('conversation', False), 'voice', 'funnel_check'])


if __name__ == '__main__':
    unittest.main()


class ClosedChoiceRuntimeTests(RuntimeTests):
    """Same synthetic chain/gates with explicit final protocol evidence only."""
    new_source = True

    def test_receipt_link_must_resolve_to_exact_pinned_receipt(self):
        other = self.root / 'other-receipt.json'
        other.write_bytes(Path(self.quality_inputs['receipt']['file']).read_bytes())
        self.mutate_receipt('quality', 'summary', lambda d: d['candidates'][0].update(receipt_file=str(other)))
        with self.assertRaises(RuntimeError): self.runtime().run(check_only=True)

    def test_historical_source_cannot_carry_closed_choice_execution(self):
        # A same-threshold historical chain cannot qualify this new source.
        self.mutate_receipt('quality', 'summary', lambda d: d['candidates'][0]['execution_evidence'].update(stage='task12-reviewed'))
        with self.assertRaises(RuntimeError): self.runtime().run(check_only=True)

    def test_new_execution_loader_mismatch_rejected(self):
        self.mutate_receipt('quality', 'summary', lambda d: d['candidates'][0]['execution_evidence']['execution_identity'].update(loader_sha256='0' * 64))
        with self.assertRaises(RuntimeError): self.runtime().run(check_only=True)

    def test_new_case_execution_cross_wiring_rejected(self):
        self.mutate_receipt('quality', 'receipt', lambda d: d['cases'][0]['actual']['execution_evidence'].update(source_commit='b' * 40))
        with self.assertRaises(RuntimeError): self.runtime().run(check_only=True)

    def test_new_coexistence_execution_required(self):
        self.mutate_receipt('coexistence', 'result', lambda d: d.pop('execution_evidence'))
        with self.assertRaises(RuntimeError): self.runtime().run(check_only=True)

    def test_final_review_tasks_and_provisional_rejected(self):
        source = json.loads(Path(self.quality_inputs['source_record']['file']).read_bytes())
        manifest = json.loads(Path(self.quality_inputs['source_manifest']['file']).read_bytes())
        artifacts = json.loads(Path(self.quality_inputs['artifact_manifest']['file']).read_bytes())['artifact_sha256']
        for change in ({'reviewed_tasks': [12, 13, 14]}, {'stage': 'task14-provisional-closed-choice'}, {'protocol_format': 'five_string_v1'}):
            wrong = dict(manifest, **change)
            with self.assertRaises(ValueError): self.mod._closed_choice_identity(source, wrong, artifacts)
        wrong = copy.deepcopy(manifest)
        wrong['task_reviews']['15']['commit'] = 'b' * 40
        with self.assertRaises(ValueError): self.mod._closed_choice_identity(source, wrong, artifacts)


class Task18ConsumerTests(unittest.TestCase):
    def test_main_read_only_adapter_replays_launcher_profile_child_and_health(self):
        import time
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def save(name, value, raw=False):
                path = root/name
                path.write_bytes(value if raw else canonical(value))
                return {'file': str(path), 'sha256': digest(path.read_bytes())}
            engine = save('main-engine.exe', b'fake executable', True)
            dll = save('main-runtime.dll', b'fake dll', True)
            token = save('main.token', b'fake test credential', True)
            launchers = {name: save(name+'.py', b'# fake immutable launcher', True)
                         for name in ('controller', 'gateway', 'sidecar_launcher')}
            argv = [engine['file'], '--ctx-size', '32768', '--parallel', '1', '--host', '127.0.0.1', '--port', '8823']
            profile = {'concurrency': 1, 'backend': {'context': 32768, 'identifier': 'gemma4-26b-a4b',
                'checkpoint': 'gemma-4-26B-qat-q4_0-it'}, 'engine': {'kind': 'native', 'command': argv,
                'executable_sha256': engine['sha256'], 'runtime_hashes': {dll['file']: dll['sha256']}},
                'token_file': token['file']}
            profile_pin = save('main-profile.json', profile)
            derived = dict(profile, demo_no_thinking_model='', queue_limit=8, queue_seconds=120,
                           console_trace=False, native_sdk_proxy=True)
            config = save('sidecar-config.json', derived)
            binding = {'profile': profile_pin, 'launcher_sources': launchers, 'sidecar_config': config,
                'controller_executable': engine['file'], 'sidecar_worker_executable': engine['file'],
                'sidecar_log': str(root/'fake.log')}
            controller_argv = [engine['file'], '-u', '-B', launchers['controller']['file'], 'run', '--config', profile_pin['file'], '--port', '8840']
            tail = ['-u', launchers['gateway']['file'], '--config', config['file'], '--port', '8841', '--log', binding['sidecar_log']]
            binding.update(controller_argv=controller_argv, sidecar_launcher_argv=[engine['file']]+tail,
                           sidecar_worker_argv=[engine['file']]+tail)
            state = save('controller-state.json', {'phase': 'ready', 'port': 8840, 'context': 32768,
                'profile_sha256': profile_pin['sha256'], 'run_id': 'fake-main-1', 'heartbeat': time.time(), 'pid': 10})
            saved = save('sidecar-state.json', {'port': 8841, 'profile_sha256': profile_pin['sha256'],
                'profile': profile_pin['file'], 'config': config['file'], 'pid': 12, 'started_ticks': 123,
                'python': engine['file'], 'gateway': launchers['gateway']['file']})
            binding.update(controller_state=state['file'], sidecar_state=saved['file'])
            processes = {pid: {'pid': pid, 'created': 1.23456789 + pid, 'created_ticks': 123,
                'exe': engine['file'], 'argv': args, 'parent_pid': parent} for pid, args, parent in
                [(10, controller_argv, 1), (11, argv, 10), (12, [engine['file']]+tail, 1), (13, [engine['file']]+tail, 12)]}
            health = []
            class Host:
                def process(self, pid): return processes.get(pid)
                def children(self, pid): return [p for p in processes.values() if p['parent_pid'] == pid]
                def listeners(self, port): return [{'pid': {8840: 10, 8823: 11, 8841: 13}[port], 'ip': '127.0.0.1'}]
                def main_health(self, credential, deadline):
                    health.append(deadline)
                    return {'status': 'ok', 'draining': False, 'backend': 'gemma4-26b-a4b',
                            'checkpoint': 'gemma-4-26B-qat-q4_0-it', 'context': 32768}
            before = {p.name: digest(p.read_bytes()) for p in root.iterdir()}
            with patch.object(self.mod, 'MAIN_PROFILE_SHA256', profile_pin['sha256']):
                static = self.mod._main_static(binding, root)
                observed = self.mod._main_observation(Host(), static, health=True, deadline=time.monotonic()+5)
                self.assertEqual(observed['engine']['argv'], argv)
                self.assertEqual(len(health), 1)
                processes[13]['parent_pid'] = 99
                with self.assertRaises(ValueError): self.mod._main_observation(Host(), static, health=True, deadline=time.monotonic()+5)
                processes[13]['parent_pid'] = 12
                processes[12]['created_ticks'] = 124
                with self.assertRaises(ValueError): self.mod._main_observation(Host(), static, health=True, deadline=time.monotonic()+5)
            self.assertEqual(before, {p.name: digest(p.read_bytes()) for p in root.iterdir()})

    def test_host_distribution_inventory_rejects_changed_extra_and_escaped_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'__init__.py').write_bytes(b'fake installed distribution')
            (root/'_psutil_windows.pyd').write_bytes(b'fake binary, never imported')
            identity = {'name': 'psutil', 'root': str(root), 'files': {
                p.name: digest(p.read_bytes()) for p in root.iterdir()}}
            self.mod._host_dependency(identity)
            (root/'extra.py').write_bytes(b'extra')
            with self.assertRaises(ValueError): self.mod._host_dependency(identity)
            (root/'extra.py').unlink()
            (root/'__init__.py').write_bytes(b'changed')
            with self.assertRaises(ValueError): self.mod._host_dependency(identity)
            escaped = copy.deepcopy(identity)
            escaped['files']['../outside.py'] = 'a'*64
            with self.assertRaises(ValueError): self.mod._host_dependency(escaped)

    def test_virgin_idle_slots_allow_absent_task_but_active_requires_identity(self):
        import base64
        spec = importlib.util.spec_from_file_location('task18_slot_consumer', HERE / 'conversation_runtime.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        owner = {'pid': 77, 'created': 1.12345}
        def row(slots):
            raw = json.dumps(slots).encode()
            return {'observation_id': 'virgin', 'owner': owner, 'method': 'GET', 'path': '/slots',
                'http_status': 200, 'request_bytes': 100, 'send_started': 10, 'response_finished': 10.01,
                'deadline': 10.1, 'worker_terminal': True, 'connection_closed': True, 'error': None,
                'response_base64': base64.b64encode(raw).decode(), 'response_wire_bytes': len(raw) + 100,
                'slots': slots, 'purpose': 'baseline'}
        slots = [{'id': i, 'n_ctx': 4096, 'is_processing': False} for i in (0, 1)]
        self.assertEqual(module._slots([row(slots)], owner, 1), 1)
        for value in (None, True, -1, '42'):
            active = copy.deepcopy(slots); active[0].update(is_processing=True, id_task=value)
            with self.assertRaises(ValueError): module._slots([row(active)], owner, 1, require_initial=False)
        active = copy.deepcopy(slots); active[0].update(is_processing=True, id_task=42)
        self.assertEqual(module._slots([row(active)], owner, 1, require_initial=False), 1)

    def setUp(self):
        self.mod = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(self.mod)
    def test_canonical_finalizer_is_present_and_rejects_foreign_expected(self):
        self.assertTrue(callable(getattr(self.mod.ConversationRuntime, 'verify_grounded_stage', None)),
                        'canonical read-only finalizer missing')

    def test_measured_admission_and_cancellation_derivers_are_present(self):
        self.assertTrue(callable(getattr(self.mod, 'derive_admission', None)), 'measured admission path missing')
        self.assertTrue(callable(getattr(self.mod, 'derive_cancellation', None)), 'measured cancellation path missing')

    def test_canonical_proof_preserves_creation_and_rechecks_drift_without_mutation(self):
        import sys
        canonical_path = HERE/'grounded_readiness.py'
        spec = importlib.util.spec_from_file_location('grounded_readiness', canonical_path)
        module = importlib.util.module_from_spec(spec)
        previous = sys.modules.get('grounded_readiness')
        sys.modules['grounded_readiness'] = module
        spec.loader.exec_module(module)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                def write(name, value):
                    path = root/name
                    path.write_bytes(canonical(value))
                    return {'file': str(path), 'sha256': digest(path.read_bytes())}
                sources = {name: '1'*64 for name in self.mod._EXPECTED_SOURCES}
                sources[self.mod._EXPECTED_SOURCES[-1]] = digest(canonical_path.read_bytes())
                manifest = write('manifest.json', {'source_sha256': sources})
                admission = write('admission.json', {'transfer': {'main_binding': {}}})
                profile = {'engine': {'sha256': '2'*64}, 'model': {'sha256': '3'*64}}
                profile_pin = write('profile.json', profile)
                selection = [write(name, {}) for name in ('selection.json', 'native.json', 'responsive.json')]
                token = root/'token'
                token.write_text('x'*48)
                created = 1712345678.1234567
                owner = {'schema': 1, 'pid': 777, 'created': created, 'exe': 'fake-engine',
                    'executable_sha256': '2'*64, 'model_sha256': '3'*64,
                    'profile_sha256': profile_pin['sha256'], 'port': 59999, 'alias': 'fake', 'state': 'ready'}
                owner_pin = write('owner.json', owner)
                process = {'pid': 777, 'created': created, 'exe': 'fake-engine', 'argv': ['fake-engine'], 'parent_pid': 1}
                main_process = {**process, 'pid': 888}
                main = {'run_id': 'fake-run', **{k: main_process for k in ('controller', 'engine', 'launcher', 'worker')}}
                class Host:
                    drift = False
                    calls = 0
                    def process(self, pid):
                        self.calls += 1
                        return {**process, 'created': created + 1 if self.drift and self.calls > 2 else created}
                    def listeners(self, port): return [{'pid': 777, 'ip': '127.0.0.1'}]
                    def memory_gib(self): return 24
                    def probe_bounded(self, *args): return {'healthy': True, 'alias': 'fake', 'auth_required': True}
                    def observe_main(self, *args, **kwargs): return main
                host = Host()
                runtime = self.mod.ConversationRuntime(profile_pin['file'], profile_pin['sha256'], owner_pin['file'], host)
                runtime.selection_binding = tuple((p['file'], p['sha256']) for p in selection)
                def verified_fake_chain():
                    runtime.argv, runtime.alias, runtime.port = ['fake-engine'], 'fake', 59999
                    runtime.profile, runtime.reserve, runtime.token_file, runtime.token = profile, 18, token, 'x'*48
                    return {'source': {'stage': self.mod._ADMITTED_SOURCE['stage']}, 'profile': profile,
                        'quality': {'inputs': {'source_manifest': manifest, 'admission': admission,
                            'receipt': {'sha256': '4'*64}, 'cancellation': {'sha256': '5'*64}}},
                        'coexistence': {'inputs': {'result': {'sha256': '6'*64}}}}
                expected = module.GroundedExpected('http://127.0.0.1:59999/v1/chat/completions', 'fake',
                    tuple(sources.items()), context_parallel=(8192, 2))
                before = {p.name: digest(p.read_bytes()) for p in root.iterdir()}
                with patch.object(runtime, '_validate', side_effect=verified_fake_chain), patch.object(self.mod, '_main_static', return_value={}):
                    proof = runtime.verify_grounded_stage(expected)
                    self.assertIs(type(proof), module.GroundedReadinessProof)
                    self.assertIs(proof.expected, expected)
                    self.assertEqual(proof.owner_created, created)
                    self.assertEqual([p[0] for p in proof.measured_evidence_sha256], ['admission', 'grounding', 'cancellation', 'coexistence'])
                    # This real canonical function is not invoked by finalization;
                    # rejection must come from the live-code identity boundary.
                    target = module.expected_grounded
                    original_code = target.__code__
                    self.assertIn('native-bridge', original_code.co_consts)
                    changed_constants = tuple('changed-native-bridge' if value == 'native-bridge' else value
                                              for value in original_code.co_consts)
                    for mutation, changed_code in (
                            ('source location', original_code.replace(co_firstlineno=original_code.co_firstlineno + 1)),
                            ('executable constant', original_code.replace(co_consts=changed_constants))):
                        with self.subTest(canonical_code_mutation=mutation):
                            calls_before = host.calls
                            try:
                                target.__code__ = changed_code
                                with self.assertRaises(RuntimeError): runtime.verify_grounded_stage(expected)
                                self.assertEqual(host.calls, calls_before)
                            finally:
                                target.__code__ = original_code
                            self.assertIs(target.__code__, original_code)
                            restored_proof = runtime.verify_grounded_stage(expected)
                            self.assertIs(type(restored_proof), module.GroundedReadinessProof)
                            self.assertIs(restored_proof.expected, expected)
                            self.assertEqual(restored_proof.owner_created, created)
                            self.assertEqual(before, {p.name: digest(p.read_bytes()) for p in root.iterdir()})
                            print(f'Canonical live-code {mutation}: rejected; code restored; positive proof accepted.')
                    with self.assertRaises(RuntimeError): runtime.verify_grounded_stage(SimpleNamespace(**vars(expected)))
                    host.calls, host.drift = 0, True
                    with self.assertRaises(RuntimeError): runtime.verify_grounded_stage(expected)
                    host.calls, host.drift = 0, False
                    with patch.object(self.mod.time, 'monotonic', side_effect=[1., 7.]):
                        with self.assertRaises(RuntimeError): runtime.verify_grounded_stage(expected)
                self.assertEqual(before, {p.name: digest(p.read_bytes()) for p in root.iterdir()})
        finally:
            if previous is None: sys.modules.pop('grounded_readiness', None)
            else: sys.modules['grounded_readiness'] = previous


class AdmittedContractTests(unittest.TestCase):
    """Pure FAKE metadata/accounting examples; never final evaluator receipts."""
    @classmethod
    def setUpClass(cls):
        cls.mod = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(cls.mod)


    def source_metadata(self):
        # Synthetic metadata only in memory, no Task16/17 freeze/review files.
        source = {'status': 'REVIEWED_FROZEN', 'inference_authorized': False,
            'stage': 'task17-grounded-closed-choice-reviewed-source',
            'protocol_format': 'closed_choice_v2_grounded', 'admission_protocol': 'pinned_chat_count_v1',
            'reviewed_tasks': [12, 13, 14, 15, 16, 17], 'commit': 'a' * 40,
            'manifest_sha256': 'b' * 64, 'dependency_inventory_sha256': 'c' * 64,
            'reviewed_inventory': ['voice/native-bridge/fake.py', 'voice/native-bridge/test_fake.py']}
        manifest = {key: copy.deepcopy(source[key]) for key in
            ('stage', 'protocol_format', 'admission_protocol', 'reviewed_tasks', 'commit', 'dependency_inventory_sha256')}
        manifest.update(source_sha256={'voice/native-bridge/fake.py': 'd' * 64},
            test_sha256={'voice/native-bridge/test_fake.py': 'e' * 64},
            task_reviews={str(task): {'status': 'PASS', 'commit': 'a' * 40,
                'path': 'FAKE_TEST_ONLY_NO_FINAL_REVIEW', 'sha256': 'f' * 64} for task in range(12, 18)})
        return source, manifest

    def transaction(self, state='inference_attempted'):
        events = [] if state == 'bypass' else [{'operation': 'count', 'payload_sha256': 'a' * 64}]
        if state == 'inference_attempted': events.append({'operation': 'inference', 'payload_sha256': 'a' * 64})
        return {'accounting_protocol': 'pinned_chat_count_v1', 'state': state,
            'count_attempts': int(state != 'bypass'), 'inference_attempts': int(state == 'inference_attempted'),
            'total_http': len(events), 'events': events}

    def test_only_exact_valueless_switch_and_valued_options_parse(self):
        parse = self.mod._parse_runtime_argv
        self.assertEqual(parse(['fake.exe', '--alias', 'fake', '--no-context-shift', '--predict', '128']),
            {'--alias': 'fake', '--no-context-shift': None, '--predict': '128'})
        for tail in (['--no-context-shift', '--no-context-shift'], ['--no-context-shift', 'false'],
                     ['--no-context-shift=false'], ['--context-shift'], ['--unknown'],
                     ['--alias'], ['--alias', '--predict', '128'], ['--alias', 'one', '--alias', 'two']):
            with self.subTest(tail=tail), self.assertRaises(ValueError): parse(['fake.exe'] + tail)



    def test_final_source_metadata_requires_exact_stage_tasks_and_pins(self):
        source, manifest = self.source_metadata()
        self.assertIsNone(self.mod.validate_admitted_source_metadata(source, manifest))
        for key, replacement in [('stage', 'task12-reviewed'), ('stage', 'task14-closed-choice-reviewed-source'),
                ('stage', 'task14-provisional-closed-choice'), ('protocol_format', 'closed_choice_v1'),
                ('protocol_format', 'five_string_v1'), ('admission_protocol', 'legacy_count'),
                ('reviewed_tasks', [12, 13, 14, 15, 16]), ('reviewed_tasks', [12, 13, 14, 15, 16, 17, 18]),
                ('commit', None), ('dependency_inventory_sha256', None)]:
            bad_source, bad_manifest = copy.deepcopy(source), copy.deepcopy(manifest)
            bad_source[key] = bad_manifest[key] = replacement
            with self.subTest(key=key, value=replacement), self.assertRaises(ValueError):
                self.mod.validate_admitted_source_metadata(bad_source, bad_manifest)
        for change in ('missing_review', 'wrong_final_commit', 'missing_source_pin'):
            wrong = copy.deepcopy(manifest)
            if change == 'missing_review': wrong['task_reviews'].pop('16')
            elif change == 'wrong_final_commit': wrong['task_reviews']['17']['commit'] = 'b' * 40
            else: wrong['source_sha256']['voice/native-bridge/fake.py'] = None
            with self.subTest(change=change), self.assertRaises(ValueError): self.mod.validate_admitted_source_metadata(source, wrong)
        with self.assertRaises(ValueError): self.mod._closed_choice_identity(source, manifest, {})

    def test_transaction_attempts_order_payload_and_version_are_distinct(self):
        for state, expected in [('bypass', (0, 0, 0)), ('count_rejected', (1, 0, 1)), ('inference_attempted', (1, 1, 2))]:
            self.assertEqual(self.mod.validate_admitted_transaction(self.transaction(state)), expected)
        edits = [lambda d: d.update(accounting_protocol='old_request_count'),
            lambda d: d.update(request_count=1), lambda d: d.update(count_attempts=0),
            lambda d: d.update(inference_attempts=2), lambda d: d.update(total_http=1),
            lambda d: d.update(count_attempts=True), lambda d: d['events'].reverse(),
            lambda d: d['events'][1].update(payload_sha256='b' * 64), lambda d: d['events'].append(d['events'][1]),
            lambda d: d.update(state='bypass')]
        for edit in edits:
            wrong = self.transaction(); edit(wrong)
            with self.subTest(edit=edits.index(edit)), self.assertRaises(ValueError): self.mod.validate_admitted_transaction(wrong)
