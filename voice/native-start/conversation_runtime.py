"""Fail-closed owner of a separately qualified loopback conversation process.

No model is selected by this module. The private selection pins a reviewed
profile, which pins measured quality/coexistence evidence and all model assets.
Only the Desktop coordinator calls this after its main Gemma preflight. There
is no inference, prewarm, business executor, public API or automatic restart.
"""
import contextlib
import base64
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter


MAIN_PROFILE_SHA256 = 'ea335895f0cb8f6ded0698ec940cab808a11162187129822ecd9c010efbdb330'
RESERVED_PORTS = {8731, 8795, 8823, 8826, 8836, 8840, 8841, 8850, 8851, 8852, 8853, 8860, 18808}
SAFE_FLAGS = {'--model', '--alias', '--ctx-size', '--parallel', '--host', '--port',
              '--gpu-layers', '--threads', '--threads-batch', '--predict', '--fit',
              '--ctx-checkpoints', '--cache-ram', '--reasoning', '--reasoning-budget', '--api-key-file'}
VALUELESS_FLAGS = frozenset({'--no-context-shift'})
POSITIVE = frozenset({'status_unique', 'audio_stop_direct', 'current_answer', 'open_dialogue',
                     'prior_correction', 'new_intake_explicit_agent', 'business_cancel_direct', 'question_help_grounded'})
NEGATIVE = frozenset({'ambiguous_status_target', 'ambiguous_change_or_question_binding',
                     'unavailable_or_wrong_domain_agent', 'nonauthorizing_control_context'})
STATUS_STATES = frozenset({'running', 'succeeded', 'failed', 'outcome_unknown'})
CRITICAL = frozenset({'false_business', 'wrong_binding', 'wrong_agent', 'false_cancel', 'false_status_target',
                     'invented_result', 'accepted_text_corruption', 'accepted_stale', 'accepted_invalid',
                     'accepted_late', 'unverified_acceptance', 'unexpected_business_write', 'durable_target_mismatch'})
LIFECYCLE = ('source_freeze_verified', 'assets_verified', 'private_token_verified', 'ready',
             'owned_process_stopped', 'listener_released', 'token_removed', 'within_total_deadline')


def _require(condition):
    if not condition:
        raise ValueError('admission rejected')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def read_json(path, limit=131072):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    _require(len(raw) <= limit)
    return _json(raw)


def _json(raw):
    result = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs,
                        parse_constant=lambda _: _require(False))
    _require(type(result) is dict)
    return result


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _hash(value):
    _require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value))
    return value


def _number(value, minimum=0):
    _require(type(value) in (int, float) and math.isfinite(value) and value >= minimum)
    return value


def _file(value, base=None):
    _require(type(value) is str and bool(value) and len(value) <= 2048)
    path = Path(value)
    if not path.is_absolute():
        _require(base is not None)
        path = base / path
    path = path.resolve(strict=True)
    _require(path.is_file() and not str(path).startswith(('\\\\', '//')))
    return path


def _pin(pin, base):
    _require(type(pin) is dict and set(pin) == {'file', 'sha256'})
    path = _file(pin['file'], base)
    _require(sha256(path) == _hash(pin['sha256']))
    return path


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _pinned_json(pin, base, limit=131072):
    _require(type(pin) is dict and set(pin) == {'file', 'sha256'})
    with _file(pin['file'], base).open('rb') as stream:
        raw = stream.read(limit + 1)
    _require(len(raw) <= limit and hashlib.sha256(raw).hexdigest() == _hash(pin['sha256']))
    return _json(raw)


def _same(left, right):
    # Unlike Python equality, JSON serialization distinguishes true from 1.
    _require(_canonical(left) == _canonical(right))


def _lifecycle(value):
    _require(all(value[key] is True for key in LIFECYCLE) and value['watchdog_failure'] is None)


def _parse_runtime_argv(argv):
    """Parse the existing valued allowlist plus one exact valueless switch."""
    _require(type(argv) is list and 1 <= len(argv) <= 50)
    _require(all(type(arg) is str and 0 < len(arg) <= 2048 for arg in argv))
    options = {}
    index = 1
    while index < len(argv):
        flag = argv[index]
        _require(flag not in options and flag in SAFE_FLAGS | VALUELESS_FLAGS)
        if flag in VALUELESS_FLAGS:
            options[flag] = None
            index += 1
        else:
            _require(index + 1 < len(argv) and not argv[index + 1].startswith('--'))
            options[flag] = argv[index + 1]
            index += 2
    return options


# Future requirements only. These validators are not called by runtime admission:
# final byte verification and Task16/17 evaluator/receipt migration are pending.
_ADMITTED_SOURCE = {
    'stage': 'task17-grounded-closed-choice-reviewed-source',
    'protocol_format': 'closed_choice_v2_grounded', 'admission_protocol': 'pinned_chat_count_v1',
    'reviewed_tasks': [12, 13, 14, 15, 16, 17]}
_ADMITTED_PROFILE = {
    'template_sha256': 'd28d7df94f0fd7e8d0075a22c473333d6e7dd2bc4c36c83e8b975300a0fb94bc',
    'message_path': {'system': 'explicit', 'user': 'plain', 'tools': False, 'deterministic': True},
    'context_tokens': 4096, 'parallel': 1, 'main_context_tokens': 32768, 'main_parallel': 1,
    'minimum_reserve_gib': 18, 'server_predict_ceiling': 128, 'no_context_shift': True,
    'request_budgets': {'route': {'prompt': 3584, 'output': 24}, 'planner': {'prompt': 3072, 'output': 128}}}
_ADMITTED_COUNT = {
    'accounting_protocol': 'pinned_chat_count_v1', 'maximum_count_attempts_per_transaction': 1,
    'maximum_inference_attempts_per_transaction': 1, 'maximum_http_per_transaction': 2,
    'same_payload_required': True, 'order': ['count', 'inference'],
    'bypass': [0, 0, 0], 'count_rejected': [1, 0, 1]}
_ADMITTED_CAMPAIGN = {
    'total_cases': 184,
    'routing': {'cases': 120, 'families': 12, 'per_family': 10, 'minimum_exact': 108, 'minimum_positive_per_family': 8},
    'status': {'cases': 40, 'states': 4, 'per_state': 10, 'minimum_exact': 40},
    'maximum_critical_failures': 0,
    'grounded': {'cases': 24, 'answerable': 16, 'families': 4, 'per_family': 4, 'gaps': 8,
        'minimum_useful': 14, 'minimum_useful_per_family': 3, 'correct_or_safe_gaps': 8,
        'maximum_grounding_failures': 0, 'maximum_authority_failures': 0, 'maximum_freshness_failures': 0},
    'maximum_classifier_inference_attempts': 184, 'maximum_planner_inference_attempts': 24,
    'maximum_inference_attempts': 208, 'maximum_count_attempts': 208, 'maximum_total_http': 416}
_ADMITTED_SEPARATE = {'coexistence_main': 6, 'coexistence_conversation': 24,
    'cancellation_preflight': 'SEPARATE_AUTHORIZATION_AND_CAP', 'task7_acceptance': 'SEPARATE_AUTHORIZATION_AND_CAP'}
_ADMITTED_PENDING = ('actual_source_record', 'actual_source_review', 'actual_dependency_inventory',
    'actual_capability_evidence', 'actual_no_shift_evidence', 'actual_model_runtime_process_evidence',
    'actual_evaluator_receipts', 'actual_corpus')


def validate_admitted_preparation(value):
    """Check inert requirements, never readiness, qualification or authority."""
    expected = {'schema': 'admitted_consumer_preparation_v1', 'status': 'NO_GO', 'inference_authorized': False,
        'source_requirements': _ADMITTED_SOURCE, 'profile_requirements': _ADMITTED_PROFILE,
        'count_requirements': _ADMITTED_COUNT, 'campaign_requirements': _ADMITTED_CAMPAIGN,
        'separate_caps': _ADMITTED_SEPARATE, **{key: None for key in _ADMITTED_PENDING}}
    _same(value, expected)


def validate_admitted_profile_requirements(value, argv):
    """Validate future metadata/argv constraints; no capability is established."""
    _same(value, _ADMITTED_PROFILE)
    options = _parse_runtime_argv(argv)
    _require('--no-context-shift' in options)
    _require(options.get('--ctx-size') == '4096' and options.get('--parallel') == '1')
    _require(options.get('--predict') == '128')
    for budget in value['request_budgets'].values():
        _require(budget['prompt'] + budget['output'] <= value['context_tokens'])
    # Full engine/help/asset/security/ownership validation remains in _validate.


def validate_admitted_source_metadata(source, manifest):
    """Structural future pin contract, NOT verification of final bytes/load mode.

    Finalizer must later verify every actual source/review/dependency pin and
    retained load session. Copying dictionaries grants no runtime admission;
    _provenance deliberately does not support this future stage yet.
    """
    _require(type(source) is dict and type(manifest) is dict)
    _require(source.get('status') == 'REVIEWED_FROZEN' and source.get('inference_authorized') is False)
    for key, expected in _ADMITTED_SOURCE.items():
        _same(source.get(key), expected)
        _same(manifest.get(key), expected)
    commit = source.get('commit')
    _require(type(commit) is str and re.fullmatch('[0-9a-f]{40}', commit))
    _same(commit, manifest.get('commit'))
    _hash(source.get('manifest_sha256'))
    dependency = _hash(source.get('dependency_inventory_sha256'))
    _same(dependency, manifest.get('dependency_inventory_sha256'))
    reviews = manifest.get('task_reviews')
    _require(type(reviews) is dict and set(reviews) == {str(task) for task in _ADMITTED_SOURCE['reviewed_tasks']})
    for review in reviews.values():
        _require(type(review) is dict and review.get('status') == 'PASS')
        _require(type(review.get('commit')) is str and re.fullmatch('[0-9a-f]{40}', review['commit']))
        _require(type(review.get('path')) is str and bool(review['path']))
        _hash(review.get('sha256'))
    _same(reviews['17']['commit'], commit)
    sources, tests = manifest.get('source_sha256'), manifest.get('test_sha256')
    _require(type(sources) is dict and bool(sources) and type(tests) is dict and bool(tests))
    _require(set(sources).isdisjoint(tests))
    for name, pin in {**sources, **tests}.items():
        _require(type(name) is str and (name.startswith('voice/native-bridge/') or name == 'voice/native-start/grounded_readiness.py') and '\\' not in name
                 and '..' not in Path(name).parts)
        _hash(pin)
    _same(source.get('reviewed_inventory'), sorted(set(sources) | set(tests)))


def validate_admitted_transaction(value):
    """Pure versioned accounting contract; no legacy request_count conversion.

    payload_sha256 binds the same counted inference payload, not an HTTP URL.
    Actual canonical-byte capture must follow the later reviewed Task16/17 API.
    Attempts include failures; this function does not infer successful output.
    """
    _require(type(value) is dict and set(value) == {'accounting_protocol', 'state',
        'count_attempts', 'inference_attempts', 'total_http', 'events'})
    _require(value['accounting_protocol'] == 'pinned_chat_count_v1')
    states = {'bypass': (0, 0, 0), 'count_rejected': (1, 0, 1), 'inference_attempted': (1, 1, 2)}
    _require(type(value['state']) is str and value['state'] in states)
    counts = tuple(value[key] for key in ('count_attempts', 'inference_attempts', 'total_http'))
    _require(all(type(number) is int for number in counts) and counts == states[value['state']])
    events = value['events']
    _require(type(events) is list and len(events) == counts[2])
    for index, event in enumerate(events):
        _require(type(event) is dict and set(event) == {'operation', 'payload_sha256'})
        _require(event['operation'] == ('count' if index == 0 else 'inference'))
        _hash(event['payload_sha256'])
    if len(events) == 2:
        _same(events[0]['payload_sha256'], events[1]['payload_sha256'])
    return counts


_CHOICE_STAGE = 'task14-closed-choice-reviewed-source'
_CHOICE_MODULES = ('business_tasks', 'task_store', 'servicenow_executor', 'routing_policy',
                   'route_proposal', 'conversation_router', 'conversation_output', 'task_coordinator')
_ADMITTED_MODULES = _CHOICE_MODULES + ('conversation_admission', 'grounded_conversation', 'grounded_readiness')
_EXPECTED_SOURCES = tuple('voice/native-bridge/' + name + '.py' for name in (
    'route_proposal', 'routing_policy', 'conversation_router', 'conversation_admission',
    'grounded_conversation', 'task_store', 'task_coordinator', 'conversation_output',
    'native_bridge', 'responsive_config')) + ('voice/native-start/grounded_readiness.py',)
_GROUNDED_FAMILIES = ('correction_dispatch', 'current_question', 'queue', 'attributed_backend')
_GROUNDING_FAILURES = ('wrong_source', 'wrong_task', 'invented_business', 'write', 'cancel', 'stale')
_RUNTIME_GEOMETRY = (8192, 2)
_ROLE_SLOTS = {'classifier': 0, 'planner': 1}


def _application_path(name):
    return 'voice/native-start/grounded_readiness.py' if name == 'grounded_readiness' else 'voice/native-bridge/' + name + '.py'


def _main_static(binding, base):
    """Hash immutable Main assets before beginning the five-second live window.

    Current disk hashes transfer under the reviewed trusted-launcher model;
    they are deliberately not called historical executed-image measurements.
    """
    profile_file = _pin(binding['profile'], base)
    _require(binding['profile']['sha256'] == MAIN_PROFILE_SHA256)
    profile = read_json(profile_file)
    _require(profile['concurrency'] == 1 and profile['backend']['context'] == 32768 and
        profile['backend']['identifier'] == 'gemma4-26b-a4b' and
        profile['backend']['checkpoint'] == 'gemma-4-26B-qat-q4_0-it')
    engine = profile['engine']
    _require(engine['kind'] == 'native')
    argv = engine['command']
    _require(type(argv) is list and argv and all(type(v) is str for v in argv))
    # Main has its own reviewed complete argv, not Conversation's allowlist.
    for flag, value in (('--ctx-size', '32768'), ('--parallel', '1'), ('--host', '127.0.0.1'), ('--port', '8823')):
        _require(argv.count(flag) == 1 and argv[argv.index(flag)+1] == value)
    _require(sha256(_file(argv[0])) == _hash(engine['executable_sha256']))
    _require(type(engine['runtime_hashes']) is dict and bool(engine['runtime_hashes']))
    for name, digest in engine['runtime_hashes'].items():
        _require(sha256(_file(name, Path(argv[0]).parent)) == _hash(digest))
    for item in binding['launcher_sources'].values(): _pin(item, base)
    _require(set(binding['launcher_sources']) == {'controller', 'gateway', 'sidecar_launcher'})
    controller_argv = binding['controller_argv']
    _same(controller_argv, [binding['controller_executable'], '-u', '-B',
        str(_file(binding['launcher_sources']['controller']['file'], base)),
        'run', '--config', str(profile_file), '--port', '8840'])
    derived = json.loads(json.dumps(profile))
    for key in ('token_file', 'backend_token_file'):
        if derived.get(key): derived[key] = str(_file(derived[key], profile_file.parent))
    derived.update(demo_no_thinking_model='', queue_limit=8, queue_seconds=120,
                   console_trace=False, native_sdk_proxy=True)
    config_file = _pin(binding['sidecar_config'], base)
    _same(read_json(config_file), derived)
    return {'profile': profile, 'profile_file': str(profile_file), 'profile_sha256': MAIN_PROFILE_SHA256,
        'engine_argv': argv, 'config_file': str(config_file), 'config_sha256': binding['sidecar_config']['sha256'],
        'token_file': derived['token_file'], 'binding': binding}


def _identity_equal(first, second):
    for key in ('pid', 'created', 'exe', 'argv', 'parent_pid'):
        _same(first[key], second[key])
    _require(type(first['created']) in (int, float) and math.isfinite(first['created']) and first['created'] > 0)


def _owned_listener(host, port, pid):
    listeners = host.listeners(port)
    _require(bool(listeners) and all(s['pid'] == pid and s['ip'] == '127.0.0.1' for s in listeners))


def _main_observation(host, static, *, health, deadline):
    """One read-only adapter: files + OS identities + existing8841 health only."""
    _require(time.monotonic() < deadline)
    binding = static['binding']
    _require(sha256(static['profile_file']) == static['profile_sha256'] and
             sha256(static['config_file']) == static['config_sha256'])
    state = read_json(_file(binding['controller_state']))
    _require(state['phase'] == 'ready' and state['port'] == 8840 and state['context'] == 32768 and
             state['profile_sha256'] == static['profile_sha256'] and type(state['run_id']) is str and state['run_id'])
    _require(0 <= time.time() - _number(state['heartbeat']) <= 10)
    controller = host.process(state['pid'])
    _require(controller is not None and controller['argv'] == binding['controller_argv'])
    _require(controller['exe'] == binding['controller_executable'])
    _owned_listener(host, 8840, controller['pid'])
    engines = [p for p in host.children(controller['pid']) if p['argv'] == static['engine_argv']]
    _require(len(engines) == 1)
    engine = engines[0]
    _require(engine['parent_pid'] == controller['pid'] and engine['exe'] == static['engine_argv'][0])
    _owned_listener(host, 8823, engine['pid'])
    saved = read_json(_file(binding['sidecar_state']))
    _require(saved['port'] == 8841 and saved['profile_sha256'] == static['profile_sha256'] and
             _file(saved['profile']) == Path(static['profile_file']) and
             _file(saved['config']) == Path(static['config_file']))
    launcher = host.process(saved['pid'])
    _require(launcher is not None and launcher['created_ticks'] == saved['started_ticks'] and
             launcher['exe'] == saved['python'] and launcher['argv'] == binding['sidecar_launcher_argv'])
    expected_tail = ['-u', saved['gateway'], '--config', saved['config'], '--port', '8841', '--log', binding['sidecar_log']]
    _same(binding['sidecar_launcher_argv'], [saved['python']] + expected_tail)
    _same(binding['sidecar_worker_argv'], [binding['sidecar_worker_executable']] + expected_tail)
    _require(_file(saved['gateway']) == _file(binding['launcher_sources']['gateway']['file']))
    workers = [p for p in host.children(launcher['pid']) if p['argv'] == binding['sidecar_worker_argv']]
    _require(len(workers) == 1)
    worker = workers[0]
    _require(worker['parent_pid'] == launcher['pid'] and worker['exe'] == binding['sidecar_worker_executable'])
    _owned_listener(host, 8841, worker['pid'])
    if health:
        with _file(static['token_file']).open(encoding='utf-8-sig') as stream: token = stream.read(8193).strip()
        _require(0 < len(token) <= 8192)
        response = host.main_health(token, deadline)
        _require(response['status'] == 'ok' and response['draining'] is False and
            response['backend'] == 'gemma4-26b-a4b' and response['checkpoint'] == 'gemma-4-26B-qat-q4_0-it' and response['context'] == 32768)
    _require(time.monotonic() <= deadline)
    return {'run_id': state['run_id'], 'profile_sha256': state['profile_sha256'],
        'controller': controller, 'engine': engine, 'launcher': launcher, 'worker': worker,
        'saved': saved, 'config_sha256': static['config_sha256']}


def _host_dependency(identity):
    """Independently hash the complete pinned OS package without importing it."""
    _require(type(identity) is dict and set(identity) == {'name', 'root', 'files'} and identity['name'] == 'psutil')
    _require(type(identity['root']) is str and not identity['root'].startswith(('\\\\', '//')))
    root = Path(identity['root']).resolve(strict=True)
    _require(root.is_dir())
    files = identity['files']
    _require(type(files) is dict and '__init__.py' in files and any(n.endswith('.pyd') for n in files))
    for name, expected in files.items():
        _require(type(name) is str and not Path(name).is_absolute() and '\\' not in name and '..' not in Path(name).parts)
        path = _file(name, root)
        _require(path.is_relative_to(root) and path.is_file() and sha256(path) == _hash(expected))
    _require(set(files) == {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()})


def _closed_choice_identity(source, manifest, artifacts):
    """Narrow new applicability branch; historical V4 remains historical."""
    admitted = source.get('stage') == _ADMITTED_SOURCE['stage']
    stage = _ADMITTED_SOURCE['stage'] if admitted else _CHOICE_STAGE
    modules = _ADMITTED_MODULES if admitted else _CHOICE_MODULES
    tasks = _ADMITTED_SOURCE['reviewed_tasks'] if admitted else [12, 13, 14, 15]
    protocol = _ADMITTED_SOURCE['protocol_format'] if admitted else 'closed_choice_v1'
    _require(source.get('stage') == manifest.get('stage') == stage)
    _require(source.get('protocol_format') == manifest.get('protocol_format') == protocol)
    _require(source.get('reviewed_tasks') == manifest.get('reviewed_tasks') == tasks)
    if admitted:
        validate_admitted_source_metadata(source, manifest)
        _require(type(source.get('dependency_inventory_path')) is str)
        dependency = _file(source['dependency_inventory_path'])
        _require(sha256(dependency) == source['dependency_inventory_sha256'])
        inventory = read_json(dependency)
        _same(inventory['source_sha256'], manifest['source_sha256'])
        _same(inventory['test_sha256'], manifest['test_sha256'])
        _same(inventory['application_imports'], manifest['application_imports'])
    reviews = manifest.get('task_reviews')
    _require(type(reviews) is dict and set(reviews) == {str(t) for t in tasks})
    for review in reviews.values():
        _require(review['status'] == 'PASS' and re.fullmatch('[0-9a-f]{40}', review['commit']))
        _require(sha256(_file(review['path'])) == _hash(review['sha256']))
    _require(reviews[str(tasks[-1])]['commit'] == source['commit'])
    identity = manifest['execution_identity']
    if admitted: _host_dependency(identity['host_dependency'])
    _require(identity['loader_version'] == 'v4-retained-bytes-1')
    _require(identity['loader_sha256'] == artifacts['v4_pinned_loader.py'])
    _require(identity['application_modules'] == list(modules) and identity['external_imports'] == [])
    support = identity['support_sha256']
    _require(type(support) is dict and {'v4_pinned_loader.py', 'v4_pinned_child.py', 'v4_adapter.py',
              'v4_scoring.py', 'v4_runtime_callbacks.py', 'v4_owned_lifecycle.py',
              'v4_candidate_runner.py', 'v4_coexistence_runner.py'} <= set(support))
    _require(all(artifacts.get(name) == _hash(pin) for name, pin in support.items()))
    interpreter = identity['interpreter']
    _require(sha256(_file(interpreter['executable'])) == _hash(interpreter['sha256']))
    _require(type(interpreter['version']) is str and bool(interpreter['version']) and interpreter['implementation'] == 'cpython')
    _hash(interpreter['stdlib_tree_sha256'])
    _require(type(interpreter['stdlib_files']) is int and interpreter['stdlib_files'] > 0)
    binaries = interpreter['runtime_binary_sha256']
    _require(type(binaries) is dict and bool(binaries))
    _require(all(sha256(_file(name)) == _hash(pin) for name, pin in binaries.items()))
    _require(set(manifest['application_imports']) == set(modules))
    _require(set(manifest['source_sha256']).isdisjoint(manifest['test_sha256']))
    _require(bool(manifest['test_sha256']))
    _require(all(_application_path(name) in manifest['source_sha256'] for name in modules))
    if admitted: _require(set(_EXPECTED_SOURCES) <= set(manifest['source_sha256']))
    root = Path(source['snapshot_root']).resolve(strict=True)
    for name, pin in {**manifest['source_sha256'], **manifest['test_sha256']}.items():
        _require(type(name) is str and (name.startswith('voice/native-bridge/') or
            admitted and name == 'voice/native-start/grounded_readiness.py') and '\\' not in name
                 and '..' not in Path(name).parts)
        path = _file(str(root / name))
        _require(path.is_relative_to(root) and sha256(path) == _hash(pin))


def _executed_choice(evidence, source, manifest):
    """Execution receipt must bind the exact final source and loader closure."""
    admitted = source['stage'] == _ADMITTED_SOURCE['stage']
    _require(type(evidence) is dict and evidence['stage'] == source['stage'])
    _require(evidence['protocol_format'] == ('closed_choice_v2_grounded' if admitted else 'closed_choice_v1') and evidence['source_commit'] == source['commit'])
    _require(evidence['manifest_sha256'] == source['manifest_sha256'])
    _same(evidence['execution_identity'], manifest['execution_identity'])
    expected = {_application_path(name): manifest['source_sha256'][_application_path(name)]
                for name in (_ADMITTED_MODULES if admitted else _CHOICE_MODULES)}
    _same(evidence['application_sha256'], expected)
    root = Path(source['snapshot_root']).resolve(strict=True)
    _same(evidence['application_paths'], {name: str((root / name).resolve(strict=True)) for name in expected})
    _require(evidence['isolated_child'] is True and type(evidence['pid']) is int and evidence['pid'] > 0)
    _require(re.fullmatch('_v4_pinned_[0-9a-f]{32}', evidence['session_id']))


def _provenance(inputs, summary, profile, base):
    """Verify the immutable V4 chain without importing qualification code."""
    required = {'summary', 'receipt', 'go', 'artifact_manifest', 'candidate_manifest',
                'source_record', 'source_manifest', 'asset_manifest'}
    source = _pinned_json(inputs['source_record'], base)
    admitted = source.get('stage') == _ADMITTED_SOURCE['stage']
    if admitted: required |= {'admission', 'cancellation'}
    _require(set(inputs) == required)
    records = {key: _pinned_json(inputs[key], base) for key in required - {'summary', 'receipt', 'admission', 'cancellation'}}
    go, artifact, source = (records[key] for key in ('go', 'artifact_manifest', 'source_record'))
    _require(go['status'] == 'GO' and go['authorization'] == ('GO TASK17 184-CASE QUALIFICATION' if admitted else 'GO V4 160-CASE QUALIFICATION'))
    _require(artifact['status'] == source['status'] == records['candidate_manifest']['status'] == 'REVIEWED_FROZEN')
    _require(source['version'] == records['candidate_manifest']['version'] == 'v4')
    _require(type(source['commit']) is str and re.fullmatch('[0-9a-f]{40}', source['commit']))
    _require(go['artifact_manifest_sha256'] == inputs['artifact_manifest']['sha256'])
    _require(go['source_record_sha256'] == artifact['source_record_sha256'] == inputs['source_record']['sha256'])
    corpus = _hash(go['corpus_sha256'])  # Pin only; never open the corpus.
    _require(corpus == artifact['corpus_sha256'] == summary['corpus_sha256'])
    _require(source['manifest_sha256'] == inputs['source_manifest']['sha256'])
    _require(_file(source['manifest_path']) == _file(inputs['source_manifest']['file'], base))
    manifest = records['source_manifest']
    _require(manifest['commit'] == source['commit'])
    if manifest['stage'] == 'task12-reviewed':
        _require(source.get('protocol_format') in (None, 'five_string_v1'))
        _require(manifest.get('protocol_format') in (None, 'five_string_v1'))
        _require(source.get('stage') in (None, 'task12-reviewed'))
        _require(all('execution_evidence' not in item for item in summary.get('candidates', [])))
    else:
        _closed_choice_identity(source, manifest, artifact['artifact_sha256'])
    _require(set(source['reviewed_inventory']) == set(manifest['source_sha256']) | set(manifest['test_sha256']))
    # Bind every evaluated production file, including the final presentation.
    declared = profile['source_hashes']
    _require(len(declared) == len(manifest['source_sha256']))
    for relative, expected in manifest['source_sha256'].items():
        _require(not Path(relative).is_absolute() and '..' not in Path(relative).parts)
        matches = [name for name in declared if Path(name).as_posix().endswith('/' + Path(relative).as_posix())]
        _require(len(matches) == 1 and declared[matches[0]] == _hash(expected))
    artifacts = artifact['artifact_sha256']
    if admitted:
        for kind in ('admission', 'cancellation'):
            _require(artifacts.get(Path(inputs[kind]['file']).name) == inputs[kind]['sha256'])
    _require({'v4_candidate_runner.py', 'v4_scoring.py', 'v4_coexistence_runner.py',
              'v4-source-record.json', 'v4-owned-candidates.json'} <= set(artifacts))
    artifact_root = _file(inputs['artifact_manifest']['file'], base).parent
    for name, expected in artifacts.items():
        _require(type(name) is str and (Path(name).name == name or
                 admitted and name == 'native-start-consumer/conversation_runtime.py'))
        _require(sha256(_file(name, artifact_root)) == _hash(expected))
    _require(artifacts['v4-source-record.json'] == inputs['source_record']['sha256'])
    _require(artifacts['v4-owned-candidates.json'] == inputs['candidate_manifest']['sha256'])
    provenance = {'go_record_sha256': inputs['go']['sha256'],
                  'artifact_manifest_sha256': inputs['artifact_manifest']['sha256'], 'corpus_sha256': corpus,
                  'source_record_sha256': inputs['source_record']['sha256'], 'source_commit': source['commit'],
                  'source_manifest_sha256': inputs['source_manifest']['sha256'], 'artifact_sha256': artifacts}
    _same(summary['provenance'], provenance)
    _require(artifact['main_profile_sha256'] == profile['main_profile_sha256'] == MAIN_PROFILE_SHA256)
    candidates = records['candidate_manifest']['candidates']
    _require(type(candidates) is list and len({c['id'] for c in candidates}) == len(candidates))
    selected = [c for c in candidates if c['id'] == profile['candidate_id']]
    _require(len(selected) == 1)
    candidate = selected[0]
    engine, model = profile['engine'], profile['model']
    _require(_file(candidate['engine']) == _file(engine['executable']) and _file(candidate['gguf']) == _file(model['file']))
    _require(candidate.get('engine_sha256', candidate.get('engine_prior_sha256')) == engine['sha256'])
    _require(candidate.get('gguf_sha256', candidate.get('gguf_prior_sha256')) == model['sha256'])
    _require(candidate['resident_budget_gib'] == profile['resident_budget_gib'])
    argv = list(candidate['recommended_argv'])
    _require(argv.count('--api-key-file') == 1 and argv[argv.index('--api-key-file') + 1] == '__FRESH_OWNED_TOKEN__')
    argv[argv.index('--api-key-file') + 1] = '{token_file}'
    _same(argv, engine['argv'])
    assets = artifact['asset_manifests'][candidate['id']]
    _require(assets['manifest_sha256'] == candidate['local_asset_hash_manifest_sha256'] == inputs['asset_manifest']['sha256'])
    _require(_file(assets['manifest_path']) == _file(inputs['asset_manifest']['file'], base))
    files = records['asset_manifest']['files']
    _require(type(files) is list and len(files) == candidate['asset_file_count'])
    expected_files = {str(_file(k)): v for k, v in engine['runtime_hashes'].items()}
    expected_files.update({str(_file(engine['executable'])): engine['sha256'], str(_file(model['file'])): model['sha256']})
    actual_files = {}
    for item in files:
        path = _file(item['path'])
        _require(str(path) not in actual_files and type(item['bytes']) is int and path.stat().st_size == item['bytes'])
        actual_files[str(path)] = _hash(item['sha256'])
    _same(actual_files, expected_files)
    _require(_file(model['file']).stat().st_size == candidate['gguf_bytes'])
    listed_dlls = {Path(p) for p in actual_files if Path(p).suffix.lower() == '.dll'}
    _require(listed_dlls == {p.resolve() for p in _file(engine['executable']).parent.glob('*.dll')})
    return provenance


def _derive_admitted_transactions(rows, *, require_classifier=True, allow_context_rejection=False, allow_drained=False):
    """Startup-independent replay of captured dispatch/body/accounting facts."""
    _require(type(rows) is list and 1 <= len(rows) <= 2)
    _require([r['role'] for r in rows] in ((['classifier'], ['classifier', 'planner']) if require_classifier else
                                         (['classifier'], ['planner'], ['classifier', 'planner'])))
    totals = dict(classifier_inference=0, planner_inference=0, count=0, inference=0, http=0)
    seen = set()
    for row in rows:
        snapshot, attempts = row['snapshot'], row['attempts']
        _require(row['schema'] == 'admitted_transaction_v2' and snapshot['protocol'] == 'pinned_chat_count_v1')
        _require(row['request_id'] == snapshot['request_id'] and row['request_id'] not in seen)
        seen.add(row['request_id'])
        role = row['role']
        budget = (3584, 24) if role == 'classifier' else (3072, 128)
        _same([snapshot['input_limit'], snapshot['completion_limit']], list(budget))
        counts = [snapshot[k] for k in ('count_attempts', 'inference_attempts', 'total_attempts')]
        _require(all(type(n) is int for n in counts) and counts in ([0, 0, 0], [1, 0, 1], [1, 1, 2]))
        _require(type(attempts) is list and len(attempts) == counts[2])
        _same([a['operation'] for a in attempts], ['count', 'inference'][:counts[2]])
        for key, number in zip(('count', 'inference', 'http'), counts): totals[key] += number
        totals[role + '_inference'] += counts[1]
        _require(snapshot['connection_closed'] is True and snapshot['worker_outstanding'] is False)
        drained = (allow_drained and row['role'] == 'planner' and snapshot.get('drain_started_at') is not None and
                   snapshot.get('publication_revoked_at') is not None and snapshot.get('cancelled_at') is None and
                   snapshot.get('full_terminal_at') is not None and snapshot.get('release_basis') == 'full_terminal_then_idle')
        _require(row['late_worker'] is False and (snapshot['reason'] not in ('timeout', 'cancelled') or drained))
        if snapshot['stage'] == 'bypass':
            _require(counts == [0, 0, 0] and row['prepared'] is None)
            continue
        _require(0 < _number(row['deadline']) - _number(row['started']) <= 2.000001)
        rejected = (allow_context_rejection and counts == [1, 0, 1] and snapshot['reason'] == 'context_budget')
        _require(_number(row['worker_terminal']) >= row['started'] and (row['worker_error'] is None or
                 rejected and row['worker_error'] == 'ContextBudgetExceeded'))
        if not attempts: continue
        payload = base64.b64decode(row['prepared']['payload_base64'], validate=True)
        payload_hash = hashlib.sha256(payload).hexdigest()
        _require(payload_hash == snapshot['payload_sha256'] and len(payload) <= 16384)
        request = _json(payload)
        _same(request['id_slot'], _ROLE_SLOTS[role])
        _require(request.get('stream', False) is False and type(request.get('n', 1)) is int and request.get('n', 1) == 1)
        _same(request['max_tokens'], budget[1])
        _same(request['temperature'], 0)
        _same([m['role'] for m in request['messages']], ['system', 'user'])
        _require(all(type(m['content']) is str for m in request['messages']) and 'tools' not in request)
        previous = row['started']
        decoded = []
        for event in attempts:
            _require(event['payload_sha256'] == payload_hash and 0 < _number(event['request_bytes']) <= 16384)
            _require(previous <= _number(event['dispatch_at']) <= _number(event['send_started'])
                <= _number(event['send_finished']) <= _number(event['response_finished']))
            previous = event['response_finished']
            _require(event['error'] is None)
            raw = base64.b64decode(event['response_base64'], validate=True)
            _require(len(raw) == event['response_bytes'] <= 8192 and len(raw) <= event['response_wire_bytes'] <= 16384)
            decoded.append(_json(raw))
        count = decoded[0]
        _require(count['object'] == 'response.input_tokens' and type(count['input_tokens']) is int and count['input_tokens'] >= 1)
        _same(snapshot['input_tokens'], count['input_tokens'])
        if rejected: _require(count['input_tokens'] > budget[0] and snapshot['count_valid'] is True)
        if counts[1]:
            _require(count['input_tokens'] <= budget[0] and snapshot['count_valid'] is True and snapshot['payload_bound'] is True)
            usage = decoded[1]['usage']
            _same(usage['prompt_tokens'], count['input_tokens'])
            _require(type(usage['completion_tokens']) is int and 0 <= usage['completion_tokens'] <= budget[1])
            _require(snapshot['usage_count_match'] is True and decoded[1]['choices'][0]['finish_reason'] == 'stop')
        _require(_number(snapshot['elapsed_ms']) <= 2000)
    return {**totals, 'terminal': True}


def _grounded_case(case, review_contract, base):
    """Read-only independent replay of authored sources, finite plan and review."""
    author, expected, actual = case['frozen_author_label'], case['materialized_expected'], case['actual']
    label, observed = expected['grounding'], actual['grounded']
    aliases, setup = case['adapter_audit']['task_aliases'], case['adapter_audit']['setup_sources']
    authored = dict(author['grounding'])
    authored['allowed_sources'] = [{**s, 'task_id': aliases[s['task_alias']],
        'setup_binding': setup[s['step']] if isinstance(setup, list) or s['step'] in setup else setup[str(s['step'])]}
        for s in author['grounding']['allowed_sources']]
    _same(label, authored)
    _same(expected['exact_route']['task_id'], aliases[author['exact_route']['task_alias']])
    result, text = observed['result'] or {}, actual['rendered_output']
    evidence = {e['ref']: e for e in observed['evidence']}
    selected, wrong_source = [], False
    for ref in result.get('refs', []):
        source, local = evidence.get(ref), observed['reference_map'].get(ref, {})
        matches = []
        for index, allowed in enumerate(label['allowed_sources']):
            binding = allowed['setup_binding']
            bound = binding.get('task_id') == allowed['task_id']
            if allowed['kind'] == 'question': bound &= binding.get('question_id') is not None and binding['question_id'] == local.get('question_id')
            if allowed['kind'] in ('caller_statement', 'backend_message'): bound &= binding.get('operation_id') is not None and binding['operation_id'] == local.get('operation_id')
            if (source is not None and bound and source.get('complete') is True and source.get('task_ref') == 't1' and
                    allowed['task_id'] == observed['task_id'] and
                    all(source.get(k) == allowed.get(k) for k in ('kind', 'source', 'text', 'fact_code'))):
                matches.append(index)
        if len(matches) != 1: wrong_source = True
        else: selected.append(matches[0])
    plan = {'outcome': result.get('outcome'), 'form': result.get('form'), 'gap': result.get('gap'), 'sources': sorted(selected)}
    reference = plan in label['reference_plans'] and not wrong_source
    facts = bool(label['required_facts']) and all(f in text for f in label['required_facts'])
    output = (len(actual['emitted']) == 1 and actual['emitted'][0]['text'] == text and
        actual['emitted'][0]['task_id'] == observed['task_id'] and
        actual['emitted'][0]['utterance_id'] == actual['accept_call']['call_id'])
    flags = {'wrong_source': wrong_source, 'wrong_task': observed['task_id'] != expected['exact_route']['task_id'],
        'invented_business': any(f in text for f in label['forbidden_claims']),
        'write': list(actual['write_delta'][:2]) != [0, 0], 'cancel': actual['write_delta'][2] != 0,
        'stale': result.get('disposition') == 'stale' or observed['enqueue_at'] is None}
    semantic = True
    if label['semantic_review_required']:
        _require(type(review_contract) is dict)
        _pin(review_contract['rubric'], base)
        review = _pinned_json(actual['semantic_judgment'], base, 16384)
        def utf8_hash(value):
            return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        _require(review['source'] == 'independent_review' and review['reviewer'] == review_contract['reviewer'] and
            review['rubric_sha256'] == review_contract['rubric']['sha256'] and
            review['label_sha256'] == utf8_hash(label) and
            review['observation_sha256'] == utf8_hash({'grounded': observed, 'output': text}))
        semantic = review['judgment'] == 'entailed_and_relevant'
    correct = reference and facts and output and semantic and not any(flags.values())
    useful = expected['category'] in _GROUNDED_FAMILIES and correct and result.get('outcome') == 'answer' and result.get('disposition') == 'published'
    enqueue, planner, started = (observed[k] for k in ('enqueue_at', 'planner_started', 'accept_started'))
    replay = {'correct': bool(correct), 'useful': bool(useful), 'semantic_review_satisfied': semantic,
        'reference_match': reference, 'facts_present': facts,
        'planner_enqueue_ms': None if enqueue is None or planner is None else (enqueue - planner) * 1000,
        'accept_enqueue_ms': None if enqueue is None or started is None else (enqueue - started) * 1000, **flags}
    _same(case['score']['grounding'], replay)
    return replay


def _grounded_rows(rows):
    _require(len(rows) == 24)
    _same(dict(Counter(r['category'] for r in rows)), {**{f: 4 for f in _GROUNDED_FAMILIES}, 'gap_ambiguity_adversarial': 8})
    for row in rows:
        value = row['grounding']
        for field in ('correct', 'useful', 'semantic_review_satisfied', 'reference_match', 'facts_present', *_GROUNDING_FAILURES):
            _require(type(value[field]) is bool)
        _require(not any(value[k] for k in _GROUNDING_FAILURES))
        if value['useful'] or value['correct']:
            _require(all(value[k] is True for k in ('semantic_review_satisfied', 'reference_match', 'facts_present')))
        _require(_number(value['planner_enqueue_ms']) <= 2200 and _number(value['accept_enqueue_ms']) <= 4400)
    useful = {f: sum(r['grounding']['useful'] for r in rows if r['category'] == f) for f in _GROUNDED_FAMILIES}
    gaps = sum(r['grounding']['correct'] for r in rows if r['category'] == 'gap_ambiguity_adversarial')
    _require(sum(useful.values()) >= 14 and min(useful.values()) >= 3 and gaps == 8)
    durations = sorted(_number(r['accept_elapsed_ms']) for r in rows)
    _require(durations[int(.95 * (len(rows)-1))] < 2000 and durations[-1] <= 2200)
    return {'grounded_useful': useful, 'grounded_useful_total': sum(useful.values()), 'grounded_correct_gaps': gaps,
        'grounded_failures': {k: 0 for k in _GROUNDING_FAILURES},
        'grounded_classifier_p95_ms': durations[int(.95 * (len(rows)-1))],
        'grounded_classifier_max_ms': durations[-1],
        'grounded_planner_max_ms': max(r['grounding']['planner_enqueue_ms'] for r in rows),
        'grounded_accept_enqueue_max_ms': max(r['grounding']['accept_enqueue_ms'] for r in rows),
        'grounded_latency_pass': True}


def _measured_configuration(receipt, profile, source, manifest):
    _require(receipt['status'] == 'measured' and receipt['source_commit'] == source['commit'])
    _executed_choice(receipt['execution_evidence'], source, manifest)
    expected = {'engine_sha256': profile['engine']['sha256'], 'model_sha256': profile['model']['sha256'],
        'runtime_hashes': profile['engine']['runtime_hashes'], 'source_manifest_sha256': source['manifest_sha256'],
        'effective_argv': profile['engine']['argv'], 'context_parallel': list(_RUNTIME_GEOMETRY),
        'role_slots': _ROLE_SLOTS, 'slot_context': 4096, 'template_sha256': _ADMITTED_PROFILE['template_sha256'],
        'protocol': 'pinned_chat_count_v1', 'transport': 'ordinary_nonstream_nonresumable'}
    _same(receipt['configuration'], expected)
    options = _parse_runtime_argv(expected['effective_argv'])
    _require(options.get('--ctx-size') == '8192' and options.get('--parallel') == '2' and
             options.get('--predict') == '128' and '--no-context-shift' in options)
    _require(type(receipt['owner']['pid']) is int and receipt['owner']['pid'] > 0)
    _require(_number(receipt['owner']['created']) > 0)
    return expected


def _slots(rows, owner, maximum, *, require_initial=True):
    _require(type(rows) is list and 1 <= len(rows) <= maximum)
    ids = set()
    for row in rows:
        _require(type(row['observation_id']) is str and row['observation_id'] and row['observation_id'] not in ids)
        ids.add(row['observation_id'])
        _same(row['owner'], owner)
        _require(row['method'] == 'GET' and row['path'] == '/slots' and row['http_status'] == 200)
        _require(0 < _number(row['request_bytes']) <= 16384 and
                 _number(row['send_started']) <= _number(row['response_finished']) <= _number(row['deadline']))
        _require(row['worker_terminal'] is True and row['connection_closed'] is True and row['error'] is None)
        raw = base64.b64decode(row['response_base64'], validate=True)
        _require(len(raw) <= 8192 and len(raw) <= _number(row['response_wire_bytes']) <= 16384)
        slots = json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda _: _require(False))
        _require(type(slots) is list and len(slots) == 2 and {s['id'] for s in slots} == {0, 1})
        for slot in slots:
            _require(type(slot['id']) is int and type(slot['n_ctx']) is int and slot['n_ctx'] == 4096 and
                type(slot['is_processing']) is bool)
            if slot['is_processing']:
                _require(type(slot.get('id_task')) is int and slot['id_task'] >= 0)
            elif 'id_task' in slot:
                _require(type(slot['id_task']) is int and slot['id_task'] >= -1)
        _same(row['slots'], slots)
    if require_initial:
        _require(rows[0]['purpose'] == 'baseline' and all(s['is_processing'] is False for s in rows[0]['slots']))
        _require(sum(row['purpose'] == 'baseline' for row in rows) == 1)
    return len(rows)


def _session_slots(snapshot, observations, transactions, maximum, *, allow_witness=False):
    """Independently replay every retained lease and GET, beyond the128-entry diagnostics."""
    _require(snapshot['initialized'] is True and snapshot['invalid'] is False)
    owner_id = snapshot['owner_id']
    _require(type(owner_id) is str and bool(owner_id))
    owner = {'pid': snapshot['owner_pid'], 'created': snapshot['owner_created']}
    _require(type(owner['pid']) is int and owner['pid'] > 0 and _number(owner['created']) > 0)
    _slots(observations, owner, maximum + 1 + int(allow_witness))
    by_request, by_lease = {}, {}
    totals = {'count_attempts': 0, 'inference_attempts': 0, 'total_attempts': 0,
              'slot_get_attempts': len(observations), 'all_http_attempts': len(observations)}
    for transaction in transactions:
        request_id, receipt = transaction['request_id'], transaction['snapshot']
        _require(request_id == receipt['request_id'] and request_id not in by_request)
        by_request[request_id] = transaction
        for key in ('count_attempts', 'inference_attempts', 'total_attempts'):
            _require(type(receipt[key]) is int and receipt[key] >= 0)
            totals[key] += receipt[key]
        if receipt['stage'] == 'bypass':
            _require(not receipt['lease_id'] and not receipt['total_attempts'])
            continue
        lease = receipt['lease_id']
        _require(type(lease) is str and bool(lease) and lease not in by_lease)
        by_lease[lease] = transaction
        role = transaction['role']
        _require(receipt['owner_id'] == owner_id and receipt['role'] == role and receipt['slot_id'] == _ROLE_SLOTS[role])
        _require(receipt['worker_outstanding'] is False and receipt['cleanup_outstanding'] is False and
                 receipt['connection_closed'] is True and not receipt['unresolved_reason'])
        _require(transaction['started'] == receipt['started_at'] and transaction['deadline'] == receipt['deadline'])
        _require(receipt['started_at'] <= _number(receipt['acquired_at']) <= _number(receipt['released_at']) <= receipt['deadline'])
        _require(receipt['cancelled_at'] is None)
        probes = [r for r in observations if r['request_id'] == request_id]
        _require(receipt['slot_get_attempts'] == len(probes) and receipt['all_http_attempts'] == receipt['total_attempts'] + len(probes))
        _require(receipt['cleanup_get_attempts'] == sum(r['kind'] == 'cleanup' for r in probes) and
                 receipt['witness_get_attempts'] == sum(r['kind'] == 'witness' for r in probes))
        if receipt['inference_attempts']:
            _require(receipt['release_basis'] == 'full_terminal_then_idle' and receipt['cleanup_get_attempts'] == 1)
            release = next(r for r in probes if r['kind'] == 'cleanup')
            _require(transaction['release_observation_id'] == release['observation_id'] and release['purpose'] == 'full_terminal')
            _require(transaction['attempts'][-1]['response_finished'] <= _number(receipt['full_terminal_at']) <=
                     release['attempt_at'] <= release['send_started'] <= release['response_finished'] <=
                     release['observer_received_at'] <= receipt['released_at'] <= receipt['deadline'])
            _require(next(s for s in release['slots'] if s['id'] == receipt['slot_id'])['is_processing'] is False)
        else:
            _require(receipt['release_basis'] == 'sealed_zero_inference' and not probes and
                     receipt['full_terminal_at'] is None and _number(receipt['sealed_at']) <= receipt['released_at'])
    for observation in observations:
        probe = observation['production_probe']
        _require(observation['owner_id'] == owner_id and observation['probe_reason'] == 'observed' and
                 observation['probe_error_type'] is None and observation['send_completed'] is True)
        for key, mapped in (('owner_id', 'owner_id'), ('lease_id', 'lease_id'), ('request_id', 'request_id'),
                ('probe_request_id', 'observation_id'), ('kind', 'kind'), ('deadline', 'deadline'),
                ('sent_at', 'attempt_at'), ('received_at', 'observer_received_at'), ('terminal_at', 'observer_terminal_at')):
            _same(probe[key], observation[mapped])
        _require(probe['connection_closed'] is True and probe['worker_outstanding'] is False and probe['reason'] == 'observed')
        _require(observation['attempt_at'] <= observation['send_started'] <= observation['send_finished'] <=
                 observation['response_finished'] <= observation['observer_received_at'] <= observation['observer_terminal_at'] <= observation['deadline'])
        if observation['kind'] == 'startup':
            _require(observation['purpose'] == 'baseline' and not observation['lease_id'] and not observation['request_id'])
        else:
            _require(observation['kind'] == 'cleanup' or allow_witness and observation['kind'] == 'witness')
            receipt = by_request[observation['request_id']]['snapshot']
            _require(observation['lease_id'] == receipt['lease_id'] and observation['deadline'] == receipt['deadline'])
    _require(set(snapshot['roles']) == set(_ROLE_SLOTS))
    for role in _ROLE_SLOTS:
        leases = sorted((t['snapshot'] for t in by_lease.values() if t['role'] == role), key=lambda r: r['acquired_at'])
        previous = None
        for receipt in leases:
            _require(receipt['predecessor'] == (previous['lease_id'] if previous else ''))
            if previous: _require(previous['released_at'] <= receipt['acquired_at'])
            previous = receipt
        terminal = snapshot['roles'][role]
        _require((terminal is None) == (previous is None))
        if previous:
            for key in ('request_id', 'owner_id', 'lease_id', 'predecessor', 'release_basis', 'released_at',
                        'count_attempts', 'inference_attempts', 'slot_get_attempts', 'all_http_attempts'):
                _same(terminal[key], previous[key])
            _require(terminal['worker_outstanding'] is False and terminal['cleanup_outstanding'] is False)
    for retained in snapshot['history']:
        receipt = by_lease[retained['lease_id']]['snapshot']
        for key in ('request_id', 'owner_id', 'predecessor', 'release_basis', 'released_at'):
            _same(retained[key], receipt[key])
    totals['all_http_attempts'] += totals['total_attempts']
    _require(totals['count_attempts'] <= maximum and totals['inference_attempts'] <= maximum and
             totals['total_attempts'] == totals['count_attempts'] + totals['inference_attempts'] and
             totals['slot_get_attempts'] == totals['inference_attempts'] + 1 + sum(r['kind'] == 'witness' for r in observations))
    for key, value in totals.items():
        _require(type(snapshot[key]) is int and snapshot[key] == value)
    return totals


def _capability_count(row):
    """Independent replay of one public count-only exchange; never inference."""
    role = row['role']
    _require(role in _ROLE_SLOTS and row['count_attempts'] == 1 and row['inference_attempts'] == 0)
    raw = base64.b64decode(row['payload_base64'], validate=True)
    _require(hashlib.sha256(raw).hexdigest() == row['payload_sha256'] and len(raw) <= 16384)
    payload = _json(raw)
    _require(payload['id_slot'] == _ROLE_SLOTS[role] and payload['temperature'] == 0 and
        payload['max_tokens'] == (24 if role == 'classifier' else 128) and payload.get('stream', False) is False and
        payload.get('n', 1) == 1 and 'tools' not in payload)
    _same([m['role'] for m in payload['messages']], ['system', 'user'])
    _require(all(type(m['content']) is str for m in payload['messages']))
    _require(row['send_completed'] is True and row['connection_closed'] is True and row['error'] is None)
    _require(_number(row['started']) <= _number(row['send_started']) <= _number(row['send_finished']) <=
        _number(row['response_finished']) <= _number(row['worker_terminal_at']) <= _number(row['deadline']) and
        0 < row['deadline'] - row['started'] <= 2.000001 and 0 < _number(row['request_bytes']) <= 16384)
    response = base64.b64decode(row['response_base64'], validate=True)
    _require(len(response) == row['response_bytes'] <= 8192 and len(response) <= row['response_wire_bytes'] <= 16384)
    count = _json(response)
    _require(count['object'] == 'response.input_tokens' and type(count['input_tokens']) is int and count['input_tokens'] > 0)
    _same(count['input_tokens'], row['input_tokens'])
    _same(row['within_role_cap'], count['input_tokens'] <= (3584 if role == 'classifier' else 3072))
    _require(type(row['characters']) is int and 1 <= row['characters'] <= 4000)
    return count['input_tokens']


def _capability_facts(receipt):
    searches, rejections, pairs = (receipt[k] for k in ('count_only_preparations', 'overlimit_rejections', 'conversation_requests'))
    _require(type(searches) is list and 4 <= len(searches) <= 62 and len(rejections) == 2 and len(pairs) == 4)
    ids = [r['request_id'] for r in searches]
    _require(len(set(ids)) == len(ids))
    for row in searches: _capability_count(row)
    _same([r['role'] for r in rejections], ['classifier', 'planner'])
    _same([r['role'] for r in pairs], ['classifier', 'planner', 'classifier', 'planner'])
    actual_transactions = []
    for row in rejections + pairs:
        captured = row['admissions']
        _require(len(captured) == 1 and captured[0]['role'] == row['role'])
        rejected = row in rejections
        count = _derive_admitted_transactions(captured, require_classifier=False, allow_context_rejection=rejected)
        _require(count['count'] == 1 and count['inference'] == (0 if rejected else 1) and
            row['valid'] is (not rejected) and _number(row['wall_ms']) <= 2200)
        if rejected: _require(captured[0]['snapshot']['reason'] == 'context_budget')
        actual_transactions.extend(captured)
    _same(receipt['transactions'], actual_transactions)
    all_ids = ids + [r['request_id'] for r in actual_transactions]
    _require(len(set(all_ids)) == len(all_ids))
    for role, cap in (('classifier', 3584), ('planner', 3072)):
        boundary = receipt['boundary'][role]
        inside, outside = boundary['inside'], boundary['outside']
        _require(inside in searches and outside in searches and inside['role'] == outside['role'] == role and
            inside['input_tokens'] <= cap < outside['input_tokens'])
        reject = next(r for r in rejections if r['role'] == role)['admissions'][0]
        admitted_pair = next(r for r in pairs[2:] if r['role'] == role)['admissions'][0]
        _require(reject['snapshot']['input_tokens'] > cap >= admitted_pair['snapshot']['input_tokens'])
        for transaction, search in ((reject, outside), (admitted_pair, inside)):
            measured = _json(base64.b64decode(transaction['prepared']['payload_base64']))
            searched = _json(base64.b64decode(search['payload_base64']))
            # Fresh local identities differ; the exact public utterance must not.
            _same(_json(measured['messages'][1]['content'].encode())['utterance'],
                  _json(searched['messages'][1]['content'].encode())['utterance'])
    return actual_transactions, len(searches) + 2


def _preflight_attempts(receipt):
    """The attempted HTTP ledger must be complete and contain no unrelated send."""
    expected = [{'attempt_id': t['request_id']+':'+e['operation'], 'kind': e['operation'],
                 'request_id': t['request_id'], 'dispatch_at': e['dispatch_at']}
                for t in receipt['transactions'] for e in t['attempts']]
    expected += [{'attempt_id': r['observation_id'], 'kind': 'slots', 'request_id': r['request_id'],
                  'dispatch_at': r['attempt_at']} for r in receipt['slot_observations']]
    expected += receipt.get('negative_auth', [])
    expected += [{'attempt_id': r['request_id'], 'kind': 'count_only', 'dispatch_at': r['send_started']}
                 for r in receipt.get('count_only_preparations', []) if r['count_attempts']]
    actual = receipt['attempts']
    _require(type(actual) is list and len({r['attempt_id'] for r in actual}) == len(actual))
    _same(actual, expected)
    return len(actual)


def derive_admission(pin, profile, base, source, manifest):
    receipt = _pinned_json(pin, base, 16 * 1024 * 1024)
    _require(receipt['schema'] == 'role_slot_admission_v2')
    _measured_configuration(receipt, profile, source, manifest)
    transactions, count_only = _capability_facts(receipt)
    _session_slots(receipt['slot_owner'], receipt['slot_observations'], transactions, 6)
    _same(receipt['owner'], {'pid': receipt['slot_owner']['owner_pid'], 'created': receipt['slot_owner']['owner_created']})
    _require(_preflight_attempts(receipt) == count_only + 8 + 5)
    transactions = [t for t in transactions if t['snapshot']['inference_attempts'] == 1]
    observations = receipt['slot_observations']
    _require(_slots(observations, receipt['owner'], 5) == 5)
    by_id = {r['observation_id']: r for r in observations}
    for transaction in transactions:
        release = by_id[transaction['release_observation_id']]
        slot = _ROLE_SLOTS[transaction['role']]
        _require(release['purpose'] == 'full_terminal' and release['send_started'] >= transaction['attempts'][1]['response_finished'])
        _require(next(s for s in release['slots'] if s['id'] == slot)['is_processing'] is False)
        _require(transaction['started'] >= observations[0]['response_finished'])
    template_file = _pin(receipt['template'], base)
    _require(sha256(template_file) == _ADMITTED_PROFILE['template_sha256'])
    transfer = receipt['transfer']
    _require(transfer['model'] == 'reviewed_trusted_launcher_immutable_configuration_v1')
    review = _pinned_json(transfer['review'], base)
    _require(review['decision'] == 'APPROVED' and type(review['reviewer']) is str and review['reviewer'])
    _require(review['configuration_sha256'] == hashlib.sha256(_canonical(receipt['configuration'])).hexdigest())
    _require(review['main_binding_sha256'] == hashlib.sha256(_canonical(transfer['main_binding'])).hexdigest())
    _lifecycle(receipt['cleanup'])
    _require(_number(receipt['minimum_available_gib']) >= 18)
    _require(type(receipt['lifecycle_attempts']) is list)
    total = count_only + 8 + len(observations)
    _require(count_only <= 64 and total <= 77)
    return {'count_only_attempts': count_only, 'count_attempts': count_only + 4, 'inference_attempts': 4,
            'slot_get_attempts': 5, 'all_http_attempts': total,
            'context_parallel': list(_RUNTIME_GEOMETRY), 'role_slots': _ROLE_SLOTS, 'slot_context': 4096,
            'template_sha256': _ADMITTED_PROFILE['template_sha256'], 'transfer_model': transfer['model']}


def _drain_trials(receipt):
    """Independent successful default-drain replay; hard latches never pass."""
    trials, observations = receipt['trials'], receipt['slot_observations']
    _require(type(trials) is list and [t['phase'] for t in trials] ==
             ['early_after_inference_send', 'active_slot_observed'])
    _require(receipt.get('requires_fresh_generation') is False)
    _require(_slots(observations, receipt['owner'], 7) == 6)
    auth = receipt['negative_auth']
    _require(len(auth) == 2 and {r['credential_case'] for r in auth} == {'missing', 'wrong'} and
        len({r['attempt_id'] for r in auth}) == 2 and all(r['http_status'] in (401, 403) and
        r['error'] is None and r['method'] == 'GET' and r['path'] == '/slots' for r in auth))
    by_id = {r['observation_id']: r for r in observations}
    captured, durations, releases = [], [], []
    for index, trial in enumerate(trials):
        _same(trial['owner'], receipt['owner'])
        _require(trial['status'] == 'measured' and trial['window_observed'] is True and
            trial['job_active_after_revocation'] is False and trial['planner_slot'] == 1 and trial['classifier_slot'] == 0)
        planner, route_row = trial['planner_transaction'], trial['next_route']
        route = route_row['admissions'][0]
        _require(len(route_row['admissions']) == 1 and route_row['valid'] is True and not route_row['timeout'])
        for transaction, role in ((planner, 'planner'), (route, 'classifier')):
            _require(transaction['role'] == role)
            facts = _derive_admitted_transactions([transaction], require_classifier=False, allow_drained=role == 'planner')
            _require(facts['count'] == facts['inference'] == 1 and facts['http'] == 2)
            snap = transaction['snapshot']
            _require(snap['owner_id'] == trial['owner_id'] and snap['release_basis'] == 'full_terminal_then_idle' and
                     snap['cleanup_get_attempts'] == 1 and snap['cleanup_outstanding'] is False)
            release = by_id[transaction['release_observation_id']]
            _require(release['request_id'] == transaction['request_id'] and release['lease_id'] == snap['lease_id'] and
                release['owner_id'] == snap['owner_id'] and release['kind'] == 'cleanup' and release['purpose'] == 'full_terminal')
            _require(transaction['attempts'][1]['response_finished'] <= snap['full_terminal_at'] <= release['attempt_at'] <=
                release['send_started'] <= release['response_finished'] <= snap['released_at'] <= transaction['deadline'])
            _require(next(s for s in release['slots'] if s['id'] == _ROLE_SLOTS[role])['is_processing'] is False)
            captured.append(transaction)
        snap, revoked = planner['snapshot'], trial['after_revocation']
        _require(planner['request_id'] == trial['planner_request_id'] and planner['deadline'] == trial['original_deadline'])
        _require(trial['before_window']['full_terminal_at'] is None and revoked['full_terminal_at'] is None and
            revoked['cancelled_at'] is None and revoked['connection_closed'] is False and revoked['drain_started_at'] is not None)
        _require(trial['revocation_at'] == revoked['publication_revoked_at'] == snap['publication_revoked_at'])
        _require(planner['attempts'][1]['send_completed'] is True and
            planner['attempts'][1]['send_finished'] <= trial['revocation_at'] <= snap['full_terminal_at'])
        _require(snap['cancelled_at'] is None and snap['witness_get_attempts'] == index and
            snap['slot_get_attempts'] == index + 1 and route['snapshot']['witness_get_attempts'] == 0)
        _require(route['started'] >= trial['revocation_at'] and route_row['classifier_finished'] <= route['deadline'] and
                 _number(route_row['wall_ms']) <= 2200)
        _require(trial['published'] == [] and trial['grounded_result']['disposition'] == 'stale')
        _same(trial['store_before'], trial['store_after'])
        _require(len(trial['output_invalidations']) == 1 and
                 trial['output_invalidations'][0]['job_id'] == trial['grounded_result']['job_id'])
        if index:
            witnesses = [r for r in observations if r['request_id'] == planner['request_id'] and r['kind'] == 'witness']
            _require(len(witnesses) == 1)
            witness, seen = witnesses[0], trial['active_witness']
            active = next(s for s in witness['slots'] if s['id'] == 1)
            _require(active['is_processing'] is True and active['id_task'] == seen['active_task'] == snap['active_task'] and
                seen['full_terminal_at'] is None and witness['response_finished'] <= seen['active_observed_at'] <= trial['revocation_at'])
        durations.append(route_row['wall_ms'])
        releases.append((snap['released_at']-trial['revocation_at'])*1000)
    _require(len({t['request_id'] for t in captured}) == 4)
    _same({t['request_id']: t for t in captured}, {t['request_id']: t for t in receipt['transactions']})
    _require(len(receipt['transactions']) == 4)
    _session_slots(receipt['slot_owner'], observations, receipt['transactions'], 4, allow_witness=True)
    _require(_preflight_attempts(receipt) == 16)
    return {'trials': 2, 'next_route_max_ms': max(durations), 'next_route_p95_ms': None,
        'p95_population': 'separate_24_conversation_coexistence', 'release_diagnostic_ms': releases,
        'attempts_by_kind': {'count': 4, 'inference': 4, 'slots': 6, 'negative_auth': 2},
        'all_http_attempts': 16, 'planner_uncertainty_isolated': True, 'cleanup_complete': True}


def derive_cancellation(pin, profile, base, source, manifest):
    receipt = _pinned_json(pin, base, 4 * 1024 * 1024)
    _require(receipt['schema'] == 'role_slot_cancellation_v2')
    _measured_configuration(receipt, profile, source, manifest)
    facts = _drain_trials(receipt)
    _lifecycle(receipt['cleanup'])
    _require(_number(receipt['minimum_available_gib']) >= 18 and type(receipt['lifecycle_attempts']) is list)
    return facts


def _reviewed_execution(summary, receipt, contract, base):
    """Final scoring adds judgments/scores to one immutable unscored execution."""
    raw_summary = _pinned_json(summary['raw_execution_summary'], base, 262144)
    raw = _pinned_json(receipt['raw_execution'], base, 64 * 1024 * 1024)
    index = _pinned_json(receipt['independent_review_index'], base, 262144)
    _same(summary['independent_review_index'], receipt['independent_review_index'])
    _same(raw_summary['provenance'], summary['provenance'])
    _same(raw_summary['semantic_review_contract'], contract)
    _require(raw_summary['status'] == 'SCORE_PENDING_REVIEW' and len(raw_summary['candidates']) == 1)
    item = raw_summary['candidates'][0]
    _require(item['score'] is None and item['completed_cases'] == 184 and item['error'] is None and
        item['receipt_sha256'] == receipt['raw_execution']['sha256'] and
        _file(item['receipt_file']) == _file(receipt['raw_execution']['file'], base))
    _same(index['reviewer'], contract['reviewer'])
    _same(index['rubric_sha256'], contract['rubric']['sha256'])
    _pin(contract['rubric'], base)
    needed = {c['case_id'] for c in raw['cases'] if c['frozen_author_label'].get('grounding', {}).get('semantic_review_required') is True}
    _require(set(index['judgments']) == needed and len(raw['cases']) == len(receipt['cases']) == 184)
    for before, after in zip(raw['cases'], receipt['cases']):
        _require(before['status'] == 'captured_pending_review' and 'score' not in before)
        retained = json.loads(json.dumps(after))
        retained.pop('score')
        retained['status'], retained['phase'] = before['status'], before['phase']
        if before['case_id'] in needed:
            _same(retained['actual'].pop('semantic_judgment'), index['judgments'][before['case_id']])
        _same(retained, before)
    retained = {k: v for k, v in receipt.items() if k not in ('cases', 'raw_execution', 'independent_review_index')}
    _same(retained, {k: v for k, v in raw.items() if k != 'cases'})


def derive_quality(inputs, profile, base):
    """Read pinned score rows only; return facts, never raw cases or model text."""
    summary = _pinned_json(inputs['summary'], base, 262144)
    provenance = _provenance(inputs, summary, profile, base)
    _require(summary['status'] == 'QUALIFICATION_RUN_COMPLETE')
    candidates = summary['candidates']
    _require(type(candidates) is list and len({r['candidate_id'] for r in candidates}) == len(candidates))
    selected = [r for r in candidates if r['candidate_id'] == profile['candidate_id']]
    _require(len(selected) == 1)
    selected = selected[0]
    receipt = _pinned_json(inputs['receipt'], base, 64 * 1024 * 1024)
    source = _pinned_json(inputs['source_record'], base)
    manifest = _pinned_json(inputs['source_manifest'], base, 262144)
    admitted = manifest['stage'] == _ADMITTED_SOURCE['stage']
    is_choice = manifest['stage'] == _CHOICE_STAGE or admitted
    if is_choice:
        _executed_choice(selected.get('execution_evidence'), source, manifest)
        _same(selected['execution_evidence'], receipt.get('execution_evidence'))
    else:
        _require('execution_evidence' not in receipt)
    _require(_file(selected['receipt_file']) == _file(inputs['receipt']['file'], base))
    if admitted:
        _same(selected['receipt_sha256'], inputs['receipt']['sha256'])
        if any(c.get('frozen_author_label', {}).get('grounding', {}).get('semantic_review_required') is True for c in receipt['cases']):
            go = _pinned_json(inputs['go'], base)
            _reviewed_execution(summary, receipt, go['semantic_review_contract'], base)
    for item in (selected, receipt):
        _require(item['candidate_id'] == profile['candidate_id'] and type(item['completed_cases']) is int and item['completed_cases'] == (184 if admitted else 160))
        _require(item['error'] is None and item['owner_close_succeeded'] is True)
        _lifecycle(item['lifecycle'])
    _same(selected['lifecycle'], receipt['lifecycle'])
    cases = receipt['cases']
    _require(type(cases) is list and len(cases) == (184 if admitted else 160))
    rows, seen, calls = [], set(), set()
    for case in cases:
        if is_choice:
            _same(case['actual']['execution_evidence'], receipt['execution_evidence'])
        else:
            _require('execution_evidence' not in case.get('actual', {}))
        _require(case['phase'] == case['status'] == 'complete' and case.get('error_type') is None)
        _require(case['candidate_id'] == profile['candidate_id'])
        row = case['score']
        if admitted:
            _same(row['admission'], _derive_admitted_transactions(case['actual']['admissions']))
            if row['family'] == 'grounded':
                go = _pinned_json(inputs['go'], base)
                _grounded_case(case, go.get('semantic_review_contract'), base)
        case_id = row['case_id']
        _require(type(case_id) is str and case_id and case_id == case['case_id'] and case_id not in seen)
        seen.add(case_id)
        call = row['accept_call']
        _require(call['api'] == 'Attachment.accept' and type(call['count']) is int and call['count'] == 1)
        _require(call['candidate_id'] == profile['candidate_id'] and type(call['call_id']) is str and call['call_id'] and call['call_id'] not in calls)
        calls.add(call['call_id'])
        _require(type(row['exact']) is bool and all(type(row[k]) is bool for k in CRITICAL))
        _number(row['accept_elapsed_ms'])
        rows.append(row)
    routing, status = ([r for r in rows if r['family'] == name] for name in ('routing', 'status'))
    _require(len(routing) == 120 and len(status) == 40)
    categories = dict(Counter(r['category'] for r in routing))
    states = dict(Counter(r['status_state'] for r in status))
    _same(categories, {k: 10 for k in POSITIVE | NEGATIVE})
    _same(states, {k: 10 for k in STATUS_STATES})
    positives = {k: sum(r['exact'] for r in routing if r['category'] == k) for k in POSITIVE}
    critical = {k: sum(r[k] for r in rows) for k in CRITICAL}
    routing_exact, status_exact = sum(r['exact'] for r in routing), sum(r['exact'] for r in status)
    durations = sorted(r['accept_elapsed_ms'] for r in routing + status)
    p95, maximum = durations[int(.95 * (len(durations) - 1))], durations[-1]
    _require(routing_exact >= 108 and status_exact == 40 and min(positives.values()) >= 8 and not any(critical.values()))
    _require(0 <= p95 < 2000 and p95 <= maximum <= 2200)
    expected_score = {'routing_exact': routing_exact, 'status_exact': status_exact, 'positive_family_exact': positives,
                      'critical_counts': critical, 'p95_ms': p95, 'max_ms': maximum,
                      'quality_pass': True, 'latency_pass': True, 'qualification_pass': True}
    if admitted:
        grounding = _grounded_rows([r for r in rows if r['family'] == 'grounded'])
        attempts = {k: sum(r['admission'][k] for r in rows) for k in ('classifier_inference', 'planner_inference', 'count', 'inference', 'http')}
        _require(all(attempts[k] <= maximum for k, maximum in dict(classifier_inference=184, planner_inference=24, count=208, inference=208, http=416).items()))
        session = _session_slots(receipt['slot_owner'], receipt['slot_observations'],
            [t for case in cases for t in case['actual']['admissions']], 208)
        expected_score.update(**grounding, admission_attempts=attempts, session_attempts=session)
    _same(selected['score'], expected_score)
    facts = {'route_cases': len(routing), 'formulation_cases': len(status), 'routing_exact': routing_exact,
             'status_exact': status_exact, 'category_counts': categories, 'status_counts': states,
             'positive_family_exact': positives, 'critical_counts': critical, 'route_p95_seconds': p95 / 1000,
             'max_route_seconds': maximum / 1000, 'model_timeout_seconds': 2.0, 'all_mandatory_gates_passed': True}
    if admitted:
        facts.update(grounded_cases=24, **grounding, admission_attempts=attempts)
        facts['admission'] = derive_admission(inputs['admission'], profile, base, source, manifest)
        facts['cancellation'] = derive_cancellation(inputs['cancellation'], profile, base, source, manifest)
    return facts, provenance


def _timing(rows):
    values = sorted(_number(r['wall_ms']) for r in rows)
    middle = len(values) // 2
    return {'count': len(rows), 'timed_count': len(values),
            'p50_ms': round((values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2), 1) if values else None,
            'p95_ms': values[math.ceil(.95 * len(values)) - 1] if values else None,
            'max_ms': max(values) if values else None,
            'valid': sum(r['valid'] is True for r in rows), 'timeouts': sum(r['timeout'] for r in rows),
            'invalid': sum(r.get('invalid', False) for r in rows)}


def derive_coexistence(inputs, profile, base, quality_inputs, quality, provenance):
    _require(set(inputs) == {'result', 'go'})
    result = _pinned_json(inputs['result'], base, 2 * 1024 * 1024)
    source = _pinned_json(quality_inputs['source_record'], base)
    manifest = _pinned_json(quality_inputs['source_manifest'], base, 262144)
    admitted = manifest['stage'] == _ADMITTED_SOURCE['stage']
    if manifest['stage'] == _CHOICE_STAGE or admitted:
        _executed_choice(result.get('execution_evidence'), source, manifest)
    else:
        _require('execution_evidence' not in result)
    go = _pinned_json(inputs['go'], base)
    _require(go['status'] == 'ROOT_GO_V4_COEXISTENCE' and go['review_status'] == 'APPROVED_BY_ROOT')
    _require(go['candidate_id'] == result['candidate_id'] == profile['candidate_id'])
    _require(type(go['main_requests_max']) is int and go['main_requests_max'] == 6)
    _require(type(go['conversation_requests_max']) is int and go['conversation_requests_max'] == 24)
    _require(go['main_profile_sha256'] == profile['main_profile_sha256'])
    for field, expected in {'qualification_result_sha256': quality_inputs['summary']['sha256'],
                            'qualification_go_record_sha256': provenance['go_record_sha256'],
                            'qualification_corpus_sha256': provenance['corpus_sha256'],
                            'candidate_manifest_sha256': quality_inputs['candidate_manifest']['sha256'],
                            'artifact_manifest_sha256': provenance['artifact_manifest_sha256'],
                            'runner_sha256': provenance['artifact_sha256']['v4_coexistence_runner.py']}.items():
        _require(go[field] == expected)
    _same(result['qualification'], {'sha256': quality_inputs['summary']['sha256'], 'candidate_id': profile['candidate_id'],
          'routing_exact': quality['routing_exact'], 'status_exact': quality['status_exact'],
          'corpus_sha256': provenance['corpus_sha256'], 'provenance': provenance})
    _require(result['status'] == 'measured' and result.get('abort_error_type') is None and result.get('receipt_error') is None)
    _require(result['post_idle'] is True and result['terminal_cleanup'] is True and result['business_calls'] == 0)
    _require(0 < _number(result['elapsed_seconds']) <= 600)
    _require(result['lifecycle_start_attempted'] is True and result['owned_process_spawned'] is True and result['owned_token_created'] is True)
    _lifecycle(result['owned_cleanup'])
    mains, rows = result['main_requests'], result['conversation_requests']
    _require(type(mains) is list and len(mains) == 6 and type(rows) is list and len(rows) == 24)
    _require({r['index'] for r in mains} == set(range(6)) and {r['index'] for r in rows} == set(range(24)))
    for row in mains + rows:
        _require(row['valid'] is True and row['timeout'] is False and row.get('error_type') is None)
        calls = 2 if admitted and row in rows else 1
        _require(type(row['actual_http_calls']) is int and row['actual_http_calls'] == calls
                 and type(row['http_send_attempts']) is int and row['http_send_attempts'] == calls and row['http_send_confirmed'] is True)
        _require(_number(row['http_started']) <= _number(row['http_finished']))
        _number(row['wall_ms'])
    for row in mains:
        _require(row['worker_completed'] is True and row['worker_unfinished'] is False and row['client_cancelled'] is False)
        _require(row['late_completion'] is False and row['observed_active'] is True and row['wall_ms'] <= 55000)
    for row in rows:
        _require(row['invalid'] is False and row['policy_contract_verified'] is True
                 and row['http_worker_unfinished'] is False and row['http_error_type'] is None)
        if admitted:
            _require(row['role'] in _ROLE_SLOTS)
            _same(_derive_admitted_transactions(row['admissions'], require_classifier=False),
                {'classifier_inference': int(row['role'] == 'classifier'), 'planner_inference': int(row['role'] == 'planner'),
                 'count': 1, 'inference': 1, 'http': 2, 'terminal': True})
            transaction = row['admissions'][0]
            _same(transaction['role'], row['role'])
            inference = transaction['attempts'][1]
            _same(row['http_started'], inference['send_started'])
            _same(row['http_finished'], inference['response_finished'])
            _require(row['classifier_started'] <= transaction['started'] <= inference['send_started'])
            _require(row['classifier_finished'] >= inference['response_finished'])
            resolution = row['clock_resolution_seconds']
            _require(0 < _number(resolution['monotonic']) <= .02 and 0 < _number(resolution['perf_counter']) <= .001)
            _require(abs(row['wall_ms'] - (_number(row['wall_finished']) - _number(row['wall_started'])) * 1000) < .0001)
            _require(abs(row['wall_ms'] - (row['classifier_finished'] - row['classifier_started']) * 1000) <=
                     (2 * resolution['monotonic'] + 2 * resolution['perf_counter']) * 1000)
    references = [r for r in rows if r['phase'] == 'serial_reference']
    scheduled = [r for r in rows if r['phase'] == 'overlap']
    _require(len(references) == 6 and len(scheduled) == 18)
    _same(dict(Counter(r['main_index'] for r in scheduled)), {i: 3 for i in range(6)})
    by_index = {r['index']: r for r in mains}
    verified, unverified = [], []
    for row in scheduled:
        main = by_index[row['main_index']]
        overlap = (row['main_active_at_probe'] is True and _number(row['main_probe_at']) <= row['http_started']
                   and main['http_started'] <= row['http_started'] < main['http_finished']
                   and row['http_finished'] > main['http_started'])
        _require(row['verified_overlap'] is overlap)
        (verified if overlap else unverified).append(row)
    _require(len(verified) >= 6)
    for name, subset in [('main_timing', mains), ('serial_timing', references),
                         ('verified_overlap_timing', verified), ('scheduled_unverified_timing', unverified)]:
        _same(result[name], _timing(subset))
    overlap = _timing(verified)
    _require(overlap['p95_ms'] < 2000 and overlap['max_ms'] <= 2200)
    for name, expected in {'scheduled_overlap_count': 18, 'verified_overlap_count': len(verified),
                            'scheduled_unverified_count': len(unverified), 'main_worker_unfinished_count': 0,
                            'classifier_worker_unfinished_count': 0}.items():
        _require(type(result[name]) is int and result[name] == expected)
    _require(result['main_latency_gate_passed'] is True and result['conversation_overlap_latency_gate_passed'] is True)
    health = result['health_samples']
    _require(type(health['count']) is int and health['count'] > 0 and type(health['main_active_one_count']) is int
             and 0 < health['main_active_one_count'] <= health['count'])
    _require(type(health['max_main_active']) is int and health['max_main_active'] == 1 and health['max_main_queued'] == 0)
    minimum = _number(health['minimum_free_gib'], profile['minimum_reserve_gib'])
    if admitted:
        population = _timing(rows)
        _require(population['p95_ms'] < 2000 and population['max_ms'] <= 2200)
        _same(result['all_conversation_timing'], population)
        _same(dict(Counter(r['role'] for r in rows)), {'classifier': 15, 'planner': 9})
        _same(dict(Counter(r['role'] for r in references)), {'classifier': 3, 'planner': 3})
        _same(result['role_counts'], {'classifier': 15, 'planner': 9})
        classifiers = [r for r in verified if r['role'] == 'classifier']
        _require(len(classifiers) >= 6)
        _same(result['classifier_verified_timing'], _timing(classifiers))
        _require(_timing(classifiers)['p95_ms'] < 2000 and _timing(classifiers)['max_ms'] <= 2200)
        _same(result['classifier_main_verified_count'], len(classifiers))
        _same(result['classifier_main_unverified_count'], sum(r['role'] == 'classifier' for r in unverified))
        _same(result['planner_main_verified_count'], sum(r['role'] == 'planner' for r in verified))
        _same(result['planner_main_unverified_count'], sum(r['role'] == 'planner' for r in unverified))
        waves = []
        for index in range(6):
            group = [r for r in scheduled if r['main_index'] == index]
            _same(dict(Counter(r['role'] for r in group)), {'classifier': 2, 'planner': 1})
            routes = sorted((r for r in group if r['role'] == 'classifier'), key=lambda r: r['classifier_started'])
            _require(routes[0]['classifier_finished'] <= routes[1]['classifier_started'])
            planner = next(r for r in group if r['role'] == 'planner')
            pairs = [[planner['index'], route['index']] for route in routes if
                max(planner['http_started'], route['http_started']) < min(planner['http_finished'], route['http_finished'])]
            _require(bool(pairs))
            waves.append({'main_index': index, 'pairs': pairs, 'verified': True})
        _same(result['role_overlap_waves'], waves)
        _require(result['role_contention_gate_passed'] is True)
        session = _session_slots(result['slot_owner'], result['slot_observations'],
            [t for row in rows for t in row['admissions']], 24)
        _same(result['session_attempts'], session)
        _same(result['conversation_owner'], {'pid': result['slot_owner']['owner_pid'], 'created': result['slot_owner']['owner_created']})
        slot_count = session['slot_get_attempts']
        _same(result['conversation_http_attempts'], {'count': 24, 'inference': 24, 'slots': slot_count, 'all_http': 48 + slot_count})
        _require(type(result['lifecycle_attempts']) is list)
    return {'minimum_available_gib': minimum, 'main_context': 32768, 'main_parallel': 1, 'bounded_load': True,
            'main_latency_gate_passed': True, 'main_count': len(mains), 'conversation_count': len(rows),
            'main_max_seconds': max(r['wall_ms'] for r in mains) / 1000,
            'verified_overlap_count': len(verified), 'scheduled_unverified_count': len(unverified),
            'overlap_p95_seconds': overlap['p95_ms'] / 1000, 'overlap_max_seconds': overlap['max_ms'] / 1000,
            'main_worker_unfinished_count': 0, 'classifier_worker_unfinished_count': 0}


def _reviewed_normalization(evidence, facts, base, binding):
    _require(set(evidence) == {'schema', 'binding_sha256', 'inputs', 'measurements', 'review'})
    _require(evidence['schema'] == 2 and evidence['binding_sha256'] == binding)
    _same(evidence['measurements'], facts)
    review = _pinned_json(evidence['review'], base)
    _require(review['schema'] == 1 and review['decision'] == 'APPROVED')
    _require(type(review['reviewer']) is str and 0 < len(review['reviewer']) <= 128)
    _require(type(review['reviewed_at']) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', review['reviewed_at']))
    _require(review['normalizer_sha256'] == sha256(__file__))
    _require(review['normalization_sha256'] == hashlib.sha256(_canonical({k: v for k, v in evidence.items() if k != 'review'})).hexdigest())
    _require(type(review['model_timeout_seconds']) in (int, float) and review['model_timeout_seconds'] == 2)
    _require(type(review['main_context']) is int and review['main_context'] == 32768
             and type(review['main_parallel']) is int and review['main_parallel'] == 1)


def _atomic(path, value):
    # Owner directory is the existing private deployment directory. No secrets.
    temporary = path.with_name(path.name + '.' + str(os.getpid()) + '.pending')
    created = False
    try:
        with temporary.open('xb') as stream:
            created = True
            stream.write(_canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if created:
            temporary.unlink(missing_ok=True)


def selected_runtime(selection_file, native_config_file, host=None):
    """Read private activation and bind it to the exact bridge configuration."""
    try:
        selection_file, native_config_file = Path(selection_file), Path(native_config_file)
        base = native_config_file.parent.resolve(strict=True)
        _require(selection_file.parent.resolve(strict=True) == base)
        native = read_json(native_config_file)
        reference = native.get('responsive_config_file')
        responsive = None
        if reference is not None:
            responsive_file = _file(reference, base)
            _require(responsive_file.parent == base)
            responsive = read_json(responsive_file)
        if not selection_file.exists():
            _require(responsive is None or responsive.get('enabled', False) is False)
            return None
        selection = read_json(selection_file)
        _require(set(selection) == {'schema', 'profile_file', 'profile_sha256', 'responsive_profile_sha256'})
        _require(selection['schema'] == 1 and responsive is not None)
        _require(sha256(responsive_file) == _hash(selection['responsive_profile_sha256']))
        _require(responsive.get('enabled') is True and responsive.get('mode') == 'assist')
        profile = _file(selection['profile_file'], base)
        _require(profile.parent == base)
        runtime = ConversationRuntime(profile, selection['profile_sha256'], base / 'conversation-owner.json', host)
        runtime._validate()
        _require(responsive.get('model_name') == runtime.alias)
        _require(responsive.get('model_url') == f'http://127.0.0.1:{runtime.port}/v1/chat/completions')
        _require(_file(responsive['model_token_file'], base) == runtime.token_file)
        _require(0 < _number(responsive.get('model_timeout_seconds', 2)) <= 2)
        store = Path(responsive['store_file'])
        if not store.is_absolute():
            store = base / store
        _require(store.resolve().parent == base and store.suffix in ('.sqlite', '.sqlite3', '.db'))
        _require(store.resolve() not in (runtime.token_file, profile, responsive_file, native_config_file.resolve(), selection_file.resolve()))
        runtime.selection_binding = tuple((str(path.resolve()), sha256(path)) for path in
            (selection_file, native_config_file, responsive_file))
        return runtime
    except Exception:
        raise RuntimeError('Conversation selection is missing, changed or not qualified for this native configuration.') from None


class ConversationRuntime:
    def __init__(self, profile_file, profile_sha256, owner_file, host=None):
        self.profile_file = Path(profile_file)
        self.profile_sha256 = profile_sha256
        self.owner_file = Path(owner_file)
        self.host = host if host is not None else WindowsHost()

    def verify_grounded_stage(self, expected):
        """Read-only point-in-time proof; no lock, launch, stop or inference.

        Immutable chain/asset hashing precedes the bounded live observation
        window. This proof is consumed immediately by the canonical adapter.
        """
        try:
            import types
            canonical = sys.modules.get('grounded_readiness')
            _require(canonical is not None and canonical.__name__ == 'grounded_readiness')
            Expected, Proof = canonical.GroundedExpected, canonical.GroundedReadinessProof
            _require(type(expected) is Expected and Expected.__module__ == Proof.__module__ == 'grounded_readiness')
            _require(type(expected.source_sha256) is tuple and len(expected.source_sha256) == 11)
            _require(all(type(p) is tuple and len(p) == 2 for p in expected.source_sha256))
            _same([p[0] for p in expected.source_sha256], list(_EXPECTED_SOURCES))
            for _, digest in expected.source_sha256: _hash(digest)
            _require(expected.protocol == 'pinned_chat_count_v1' and expected.route_limits == (3584, 24) and
                expected.planner_limits == (3072, 128) and expected.context_parallel == _RUNTIME_GEOMETRY and
                expected.main_context_parallel == (32768, 1) and type(expected.reserve_gib) is int and expected.reserve_gib == 18)
            selected = getattr(self, 'selection_binding', None)
            _require(type(selected) is tuple and len(selected) == 3)
            for path, digest in selected: _require(sha256(_file(path)) == _hash(digest))
            validated = self._validate()  # Independently rerun the entire chain.
            source, profile = validated['source'], validated['profile']
            _require(source['stage'] == _ADMITTED_SOURCE['stage'])
            manifest = _pinned_json(validated['quality']['inputs']['source_manifest'], self.profile_file.parent, 262144)
            _require(expected.source_sha256 == tuple((name, manifest['source_sha256'][name]) for name in _EXPECTED_SOURCES))
            _require(expected.endpoint == f'http://127.0.0.1:{self.port}/v1/chat/completions' and expected.model == self.alias)
            module_file = _file(canonical.__file__)
            _require(sha256(module_file) == expected.source_sha256[-1][1])
            # Verify the already-executed source functions against retained
            # canonical bytes without executing a second module/class universe.
            code = compile(module_file.read_bytes(), str(module_file), 'exec', dont_inherit=True)
            functions = {c.co_name: c for c in code.co_consts if isinstance(c, types.CodeType)}
            def code_identity(value):
                # marshal encodes object sharing/interned-string references,
                # which may differ between equal retained and fresh CodeTypes.
                # Compare every executable/source-location attribute and typed
                # recursive constants instead of serialization allocation state.
                if isinstance(value, types.CodeType):
                    fields = ('co_argcount', 'co_posonlyargcount', 'co_kwonlyargcount', 'co_nlocals',
                        'co_stacksize', 'co_flags', 'co_code', 'co_names', 'co_varnames', 'co_freevars',
                        'co_cellvars', 'co_filename', 'co_name', 'co_qualname', 'co_firstlineno',
                        'co_linetable', 'co_lnotab', 'co_exceptiontable')
                    return ('code', tuple((key, getattr(value, key)) for key in fields), code_identity(value.co_consts))
                if type(value) is tuple: return ('tuple', tuple(code_identity(v) for v in value))
                if type(value) is frozenset: return ('frozenset', tuple(sorted((code_identity(v) for v in value), key=repr)))
                return (type(value).__name__, repr(value))
            for name in ('expected_grounded', '_selected_runtime', 'validate_proof', 'verify_grounded_readiness'):
                actual = getattr(canonical, name)
                _require(type(actual) is types.FunctionType and actual.__globals__ is vars(canonical) and
                         code_identity(actual.__code__) == code_identity(functions[name]))
            admission_pin = validated['quality']['inputs']['admission']
            admission = _pinned_json(admission_pin, self.profile_file.parent, 16 * 1024 * 1024)
            main = _main_static(admission['transfer']['main_binding'], self.profile_file.parent)
            token_hash = sha256(self.token_file)
            profile_hash = sha256(self.profile_file)
            _require(profile_hash == self.profile_sha256)
            # Everything above may hash large immutable assets. Everything below
            # is a current bounded observation, repeated before proof creation.
            started = time.monotonic()
            deadline = started + 5
            owner = read_json(self.owner_file)
            _require(owner['state'] == 'ready' and _number(owner['created']) > 0)
            self._owned(owner, self.host.listeners(self.port))
            process = self.host.process(owner['pid'])
            _require(_number(self.host.memory_gib()) >= self.reserve)
            identity = self.host.probe_bounded(self.port, self.token, deadline)
            _require(identity['healthy'] is True and identity['alias'] == self.alias and identity['auth_required'] is True)
            main_before = self.host.observe_main(main, health=True, deadline=deadline)
            main_after = self.host.observe_main(main, health=False, deadline=deadline)
            _same(main_before, main_after)
            for name in ('controller', 'engine', 'launcher', 'worker'):
                _identity_equal(main_before[name], main_after[name])
            _same(read_json(self.owner_file), owner)
            self._owned(owner, self.host.listeners(self.port))
            _same(self.host.process(owner['pid']), process)
            _require(sha256(self.profile_file) == profile_hash and sha256(self.token_file) == token_hash)
            for path, digest in selected: _require(sha256(_file(path)) == digest)
            _require(_number(self.host.memory_gib()) >= self.reserve and time.monotonic() <= deadline)
            measured = (('admission', admission_pin['sha256']),
                ('grounding', validated['quality']['inputs']['receipt']['sha256']),
                ('cancellation', validated['quality']['inputs']['cancellation']['sha256']),
                ('coexistence', validated['coexistence']['inputs']['result']['sha256']))
            for _, digest in measured: _hash(digest)
            proof = Proof(expected, profile_hash, owner['pid'], process['created'], measured)
            _require(type(proof) is Proof and proof.expected is expected and proof.owner_created == owner['created'])
            return proof
        except Exception:
            raise RuntimeError('Grounded readiness is unavailable: verified evidence or current ownership changed.') from None

    def _validate(self):
        _require(sha256(self.profile_file) == _hash(self.profile_sha256))
        profile = read_json(self.profile_file)
        _require(set(profile) == {'schema', 'qualified', 'candidate_id', 'engine', 'model',
                                  'source_hashes', 'main_profile_sha256', 'minimum_reserve_gib',
                                  'resident_budget_gib', 'token_file', 'quality', 'coexistence'})
        _require(profile['schema'] == 1 and profile['qualified'] is True)
        _require(type(profile['candidate_id']) is str and re.fullmatch(r'[a-zA-Z0-9._-]{1,100}', profile['candidate_id']))
        _require(profile['main_profile_sha256'] == MAIN_PROFILE_SHA256)
        base = self.profile_file.parent.resolve(strict=True)
        _require(self.owner_file.parent.resolve(strict=True) == base)
        self.reserve = _number(profile['minimum_reserve_gib'], 18)
        self.budget = _number(profile['resident_budget_gib'], 0.1)
        engine, model = profile['engine'], profile['model']
        exe = _file(engine['executable'])
        model_file = _file(model['file'])
        _require(sha256(exe) == _hash(engine['sha256']))
        _require(sha256(model_file) == _hash(model['sha256']))
        for pins in (engine['runtime_hashes'], profile['source_hashes']):
            _require(type(pins) is dict and bool(pins))
            for name, expected in pins.items():
                _require(sha256(_file(name)) == _hash(expected))
        help_file = _pin(engine['help'], base)
        help_text = help_file.read_text(encoding='utf-8-sig')
        argv = engine['argv']
        options = _parse_runtime_argv(argv)
        quality = _pinned_json(profile['quality'], base)
        selected_source = _pinned_json(quality['inputs']['source_record'], base)
        admitted = selected_source.get('stage') == _ADMITTED_SOURCE['stage']
        _require(15 <= len(argv) <= 50)
        _require(argv[0] == str(exe))
        _require(all(re.search(re.escape(flag) + r'(?![\w-])', help_text) for flag in options))
        _require(options['--model'] == str(model_file))
        _require(options['--host'] == '127.0.0.1' and options['--parallel'] == ('2' if admitted else '1'))
        if admitted:
            _require(options['--ctx-size'] == '8192' and options.get('--predict') == '128' and '--no-context-shift' in options)
        else:
            _require(options['--ctx-size'].isdigit() and 1 <= int(options['--ctx-size']) <= 4096)
        _require(options['--gpu-layers'] == '99')  # No rejected CPU fallback.
        _require(options['--reasoning'] == 'off' and options['--reasoning-budget'] == '0')
        _require(options['--api-key-file'] == '{token_file}')
        _require(options['--port'].isdigit())
        self.port = int(options['--port'])
        _require(1024 <= self.port <= 65535 and self.port not in RESERVED_PORTS)
        self.alias = options['--alias']
        _require(re.fullmatch(r'[a-zA-Z0-9._-]{1,100}', self.alias))
        for flag, allowed in {'--predict': {'128'}, '--fit': {'off'}, '--cache-ram': {'0'},
                              '--ctx-checkpoints': {'0'}, '--threads': {'6'}, '--threads-batch': {'6'}}.items():
            _require(flag not in options or options[flag] in allowed)
        binding = {k: v for k, v in profile.items() if k not in ('quality', 'coexistence', 'token_file')}
        bound = hashlib.sha256(_canonical(binding)).hexdigest()
        coexist = _pinned_json(profile['coexistence'], base)
        facts, provenance = derive_quality(quality['inputs'], profile, base)
        _reviewed_normalization(quality, facts, base, bound)
        coex_facts = derive_coexistence(coexist['inputs'], profile, base, quality['inputs'], facts, provenance)
        _reviewed_normalization(coexist, coex_facts, base, bound)
        self.token_file = _file(profile['token_file'], base)
        _require(self.token_file.parent == base)
        self.token = self.token_file.read_text(encoding='utf-8-sig').strip()
        _require(32 <= len(self.token) <= 4096 and all(33 <= ord(c) <= 126 for c in self.token))
        self.argv = [str(self.token_file) if arg == '{token_file}' else arg for arg in argv]
        self.profile = profile
        return {'profile': profile, 'source': selected_source, 'quality': quality, 'coexistence': coexist,
                'quality_facts': facts, 'coexistence_facts': coex_facts}

    def _matches(self, process, owner):
        return (process is not None and process['pid'] == owner['pid']
                and process['created'] == owner['created']
                and os.path.normcase(process['exe']) == os.path.normcase(self.argv[0])
                and process['argv'] == self.argv)

    def _identity(self, pid):
        process = self.host.process(pid)
        _require(process is not None and type(process['created']) in (int, float))
        owner = {'schema': 1, 'pid': pid, 'created': process['created'], 'exe': self.argv[0],
                 'executable_sha256': self.profile['engine']['sha256'],
                 'model_sha256': self.profile['model']['sha256'],
                 'profile_sha256': self.profile_sha256, 'port': self.port,
                 'alias': self.alias, 'state': 'starting'}
        _require(self._matches(process, owner))
        return owner

    def _owned(self, owner, sockets):
        expected = {'schema': 1, 'exe': self.argv[0], 'executable_sha256': self.profile['engine']['sha256'],
                    'model_sha256': self.profile['model']['sha256'], 'profile_sha256': self.profile_sha256,
                    'port': self.port, 'alias': self.alias}
        _require(all(owner.get(key) == value for key, value in expected.items()))
        _require(type(owner['pid']) is int and owner['state'] in ('starting', 'ready'))
        _require(self._matches(self.host.process(owner['pid']), owner))
        _require(sockets and all(s['pid'] == owner['pid'] and s['ip'] == '127.0.0.1' for s in sockets))

    def _health(self):
        identity = self.host.probe(self.port, self.token)
        _require(identity['healthy'] is True and identity['alias'] == self.alias
                 and identity['auth_required'] is True)

    def _run(self, check_only):
        self._validate()
        sockets = self.host.listeners(self.port)
        if self.owner_file.exists():
            owner = read_json(self.owner_file)
            _require(owner.get('state') == 'ready')
            self._owned(owner, sockets)
            _require(self.host.memory_gib() >= self.reserve)
            self._health()
            return 'reused'
        _require(not sockets)
        _require(self.host.memory_gib() >= self.reserve + self.budget)
        if check_only:
            return 'prepared'
        # Persist before crossing the process boundary: even an exception from
        # launch() can mean the child exists. No automatic retry of uncertainty.
        barrier = {'schema': 1, 'state': 'launch_unresolved', 'pid': None,
                   'profile_sha256': self.profile_sha256, 'port': self.port}
        _atomic(self.owner_file, barrier)
        owner = None
        try:
            pid = self.host.launch(self.argv)
            _require(type(pid) is int and pid > 0)
            barrier['pid'] = pid
            _atomic(self.owner_file, barrier)
            owner = self._identity(pid)
            _atomic(self.owner_file, owner)
            deadline = time.monotonic() + 300
            while True:
                _require(self.host.memory_gib() >= self.reserve)
                _require(self._matches(self.host.process(pid), owner))
                sockets = self.host.listeners(self.port)
                if sockets:
                    self._owned(owner, sockets)
                    # The engine can expose /health=503 while loading. Retry
                    # only that explicit loading state; wrong auth/alias fails.
                    try:
                        self._health()
                        break
                    except Loading:
                        pass
                _require(time.monotonic() < deadline)
                time.sleep(.25)
            owner['state'] = 'ready'
            _atomic(self.owner_file, owner)
            return 'started'
        except Exception:
            # Never touch an existing process. Only this invocation's newly
            # created PID, creation time, executable and in-memory argv match.
            if owner is not None:
                try:
                    if self._matches(self.host.process(pid), owner):
                        self.host.stop_new({**owner, 'argv': self.argv})
                finally:
                    owner['state'] = 'failed'
                    _atomic(self.owner_file, owner)
            # Without a verified identity the unresolved barrier remains. Never
            # kill by PID alone, including when identity inspection itself fails.
            raise

    def run(self, check_only=False):
        try:
            if check_only:
                return self._run(True)
            with self.host.lock(self.owner_file):
                return self._run(False)
        except Exception:
            # No arbitrary exception/config/HTTP text or command line escapes.
            raise RuntimeError('Conversation runtime admission or ownership failed; no existing owner was changed.') from None


class Loading(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class WindowsHost:
    """OS boundary; instantiated only for an explicitly selected profile."""
    def __init__(self):
        import psutil
        self.psutil = psutil

    def memory_gib(self):
        class PerformanceInfo(ctypes.Structure):
            _fields_ = [('cb', ctypes.c_ulong)] + [(name, ctypes.c_size_t) for name in (
                'CommitTotal', 'CommitLimit', 'CommitPeak', 'PhysicalTotal', 'PhysicalAvailable',
                'SystemCache', 'KernelTotal', 'KernelPaged', 'KernelNonpaged', 'PageSize')] + [
                ('HandleCount', ctypes.c_ulong), ('ProcessCount', ctypes.c_ulong), ('ThreadCount', ctypes.c_ulong)]
        info = PerformanceInfo()
        info.cb = ctypes.sizeof(info)
        _require(ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(info), info.cb))
        commit_free = (info.CommitLimit - info.CommitTotal) * info.PageSize
        return min(self.psutil.virtual_memory().available, commit_free) / (1024 ** 3)

    def listeners(self, port):
        return [{'pid': conn.pid, 'ip': conn.laddr.ip} for conn in self.psutil.net_connections(kind='tcp')
                if conn.status == self.psutil.CONN_LISTEN and conn.laddr.port == port]

    def process(self, pid):
        try:
            process = self.psutil.Process(pid)
            return {'pid': pid, 'created': process.create_time(), 'exe': process.exe(), 'argv': process.cmdline(),
                    'parent_pid': process.ppid(), 'created_ticks': self.creation_ticks(pid)}
        except self.psutil.NoSuchProcess:
            return None

    @staticmethod
    def creation_ticks(pid):
        # Lossless .NET tick comparison for the existing saved sidecar launcher;
        # Conversation's canonical proof still uses unrounded psutil create_time.
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        _require(bool(handle))
        try:
            created, ended, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
            _require(kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in (created, ended, kernel_time, user_time))))
            return str((created.dwHighDateTime << 32) + created.dwLowDateTime + 504911232000000000)
        finally:
            kernel.CloseHandle(handle)

    def children(self, pid):
        return [self.process(child.pid) for child in self.psutil.Process(pid).children(recursive=False)]

    def observe_main(self, static, *, health, deadline):
        return _main_observation(self, static, health=health, deadline=deadline)

    def main_health(self, token, deadline):
        status, result = self._bounded_get(8841, '/health', token, deadline)
        _require(status == 200)
        return result

    @staticmethod
    def _bounded_get(port, path, credential, deadline):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        headers = {'Authorization': 'Bearer ' + credential} if credential else {}
        request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', headers=headers)
        remaining = deadline - time.monotonic()
        _require(remaining > 0)
        try:
            with opener.open(request, timeout=min(.5, remaining)) as response:
                raw = bytearray()
                while True:
                    _require(time.monotonic() < deadline)
                    part = response.read1(4096)
                    if not part: break
                    raw.extend(part)
                    _require(len(raw) <= 65536)
                _require(time.monotonic() <= deadline)
                return response.status, _json(bytes(raw))
        except urllib.error.HTTPError as error:
            return error.code, {}

    def probe_bounded(self, port, token, deadline):
        status, health = self._bounded_get(port, '/health', token, deadline)
        _require(status == 200 and health.get('status') == 'ok')
        status, models = self._bounded_get(port, '/v1/models', token, deadline)
        _require(status == 200 and type(models.get('data')) is list and len(models['data']) == 1)
        denied, _ = self._bounded_get(port, '/v1/models', None, deadline)
        wrong, _ = self._bounded_get(port, '/v1/models', token + '-invalid', deadline)
        return {'healthy': True, 'alias': models['data'][0]['id'], 'auth_required': denied in (401, 403) and wrong in (401, 403)}

    def launch(self, argv):
        # Engines can print configuration and credentials. Discard both streams;
        # persisted owner state is the diagnostic boundary, not engine output.
        return subprocess.Popen(argv, cwd=Path(argv[0]).parent, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=0x08000000 | 0x00000200).pid

    def stop_new(self, identity):
        try:
            # Retain the checked psutil Process object: terminate() then checks
            # its cached creation identity against PID reuse before signaling.
            process = self.psutil.Process(identity['pid'])
            if (process.create_time() == identity['created'] and process.exe() == identity['exe']
                    and process.cmdline() == identity['argv']):
                process.terminate()
        except self.psutil.NoSuchProcess:
            pass

    @contextlib.contextmanager
    def lock(self, owner):
        import msvcrt
        with owner.with_suffix('.lock').open('a+b') as handle:
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    def probe(self, port, token):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

        def get(path, credential):
            headers = {'Authorization': 'Bearer ' + credential} if credential else {}
            request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', headers=headers)
            try:
                with opener.open(request, timeout=2) as response:
                    raw = response.read(65537)
                    _require(len(raw) <= 65536 and response.status == 200)
                    return 200, json.loads(raw, object_pairs_hook=_pairs)
            except urllib.error.HTTPError as error:
                return error.code, {}

        status, health = get('/health', token)
        if status == 503:
            raise Loading()
        _require(status == 200 and health.get('status') == 'ok')
        status, models = get('/v1/models', token)
        _require(status == 200 and type(models.get('data')) is list and len(models['data']) == 1)
        denied, _ = get('/v1/models', None)
        wrong, _ = get('/v1/models', token + '-invalid')
        return {'healthy': True, 'alias': models['data'][0]['id'],
                'auth_required': denied in (401, 403) and wrong in (401, 403)}
