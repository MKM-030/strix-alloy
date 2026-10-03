"""Format existing article/coding summaries and sanitize recorded evidence.

No engine actions, request/key reads, grading, or phase/time-metric recomputation.
Recorded integer counters and host-memory minima are aggregated for display.
Existing phase/time rows are unchanged. Writes only to stdout.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path, PureWindowsPath

GEOMETRIES = ((65536, 32768), (131072, 65536), (131072, 98304), (262144, 131072))
BACKENDS = ('halogen-v2', 'gufo', 'projfix')
MODEL_IDS = {'halogen-v2': 'halogen-v2', 'gufo': 'gufo-flash-next', 'projfix': 'projfix-flash-next'}
LABELS = {
    'halogen-v2': ('Halogen 0.16.2 / WSL2', 'v2 HGN + lookup source'),
    'gufo': ('GUFO / native Windows', 'UD-IQ4_XS + Q8_0 MTP'),
    'projfix': ('PROJFIX / native Windows', 'IQ4_NL-PROJFIX + Q8_0 MTP'),
}
SUMMARY_FIELDS = (
    'backend', 'context', 'target_input', 'passed_execution',
    'three_turn_seconds', 'three_turn_repetitions', 'prefill_tps', 'decode_tps',
    'mtp_acceptance', 'retrieval_correct', 'retrieval_total', 'retrieval_details',
    'actual_initial_tokens', 'initial_cached_tokens', 'initial_cache_observations',
    'followup_cache_observations', 'observed_wall_seconds', 'requests',
    'completed_requests', 'capped_outputs', 'generated_tokens', 'output_limit',
    'eos_outputs', 'clamped_outputs', 'prompt_cache', 'host_memory_floor_bytes',
    'memory_scope', 'profile_sha256', 'client_sha256', 'corpus_sha256', 'measured_at',
)
SAMPLE_FIELDS = (
    'backend', 'context', 'target_input', 'rep', 'turn', 'prompt_tokens',
    'output_tokens', 'ttft_seconds', 'visible_ttft_seconds', 'wall_seconds',
    'last_delivery_seconds', 'stream_events', 'pp_tps', 'decode_tps',
    'normalized_1000_seconds', 'drafted', 'accepted', 'finish_reason',
    'requested_output_tokens', 'output_capped', 'eos', 'max_tokens_clamped_from',
    'cache_n', 'expected_cache_state', 'observed_cache_state',
    'cache_prompt_requested', 'reasoning_tokens_included',
)
TIMING_FIELDS = (
    'prompt_n', 'prompt_ms', 'prompt_per_second', 'predicted_n', 'predicted_ms',
    'predicted_per_second', 'draft_n', 'draft_n_accepted', 'draft_accepted',
    'cache_n', 'max_tokens_clamped_from',
)
COMMAND_OPTIONS = (
    '--draft-tokens', '--mtp-draft-vocab', '--mtp-policy', '--prefill-chunk',
    '--sessions', '--context', '--speculative', '--think', '--temperature',
    '--max-tokens', '--load-mode', '--lazy-mode', '-b', '-ub', '-ctk', '-ctv',
    '-c', '--parallel', '--spec-type', '--spec-draft-n-max', '--tensor-split',
    '-ot', '--reasoning', '--reasoning-effort', '--ctx-checkpoints', '--cache-ram',
)
SAFE_ENV = (
    'HALOGEN_MTP_DEPTH', 'HALOGEN_PREFILL_CHUNK', 'HALOGEN_TOKEN_ARENA',
    'HALOGEN_ADMIT_TICKS', 'HALOGEN_PREFILL_KEEP_TRUNK', 'HALOGEN_CTX',
    'HALOGEN_KV_POOL_POSITIONS', 'HALOGEN_KV_SLOTS', 'HALOGEN_HOST_RESERVE_GIB',
    'HALOGEN_PROMPT_CACHE', 'HALOGEN_CHECKPOINT_VARIANT', 'HALOGEN_ROUTE_GEMM',
    'HSA_OVERRIDE_GFX_VERSION',
)
HEX64 = re.compile(r'[0-9a-fA-F]{64}\Z')
EXERCISES = ('affine-cipher', 'beer-song', 'book-store', 'bottle-song', 'bowling',
             'connect', 'dominoes', 'dot-dsl', 'food-chain', 'forth')
RETRIEVAL_KEYS = (
    'SERVICE_LABEL', 'RPC_TIMEOUT_MS', 'MAX_ACTIVE_JOBS', 'CACHE_NAMESPACE',
    'RETRY_SCHEDULE', 'HEALTH_ROUTE', 'UNICODE_SPINNER', 'AUDIT_EVENT',
)


def subset(value, fields):
    return {key: value[key] for key in fields if key in value}


def number(value, digits=2):
    if type(value) not in (int, float) or not math.isfinite(value):
        return '—'
    return f'{value:.{digits}f}'


def hash_map(value):
    return {name: digest for name, digest in value.items()
            if isinstance(name, str) and not Path(name).is_absolute()
            and not PureWindowsPath(name).drive and not PureWindowsPath(name).root
            and '..' not in PureWindowsPath(name).parts
            and isinstance(digest, str) and HEX64.fullmatch(digest)}


def retrieval(value):
    result = subset(value, ('correct', 'total'))
    if isinstance(value.get('missing'), list):
        result['missing'] = [key for key in value['missing'] if key in RETRIEVAL_KEYS]
    return result


def identity(value):
    profile = value.get('profile') or {}
    backend = profile.get('backend') or {}
    engine = profile.get('engine') or {}
    qualification = profile.get('qualification') or {}
    command = engine.get('command') or []
    settings = {}
    for flag in COMMAND_OPTIONS:
        if command.count(flag) == 1 and command.index(flag) + 1 < len(command):
            settings[flag] = command[command.index(flag) + 1]
    result = {
        'profile_sha256': value.get('profile_sha256'),
        'client_sha256': value.get('client_sha256'),
        'corpus_sha256': value.get('corpus_sha256'),
        'checkpoint_label': backend.get('checkpoint'),
        'model_alias': backend.get('model'),
        'engine_kind': engine.get('kind'),
        'context': backend.get('context'),
        'minimum_reserve_gib': profile.get('minimum_reserve_gib'),
        'expected_versions': subset(backend.get('expected') or {}, (
            'version.api', 'version.engine', 'version.match')),
        'native_settings': settings,
        'prompt_lookup': '--prompt-lookup' in command,
        'disk_cache_configured': '--cache-disk' in command,
        'profile_settings': subset(engine, (
            'checkpoint', 'context', 'prompt_cache', 'draft_tokens',
            'prefill_chunk', 'prefill_keep_trunk', 'admit_ticks', 'kernel_controls')),
        'qualification': subset(qualification, (
            'source_commit', 'sdk', 'sdk_runtime', 'compiler_sha256',
            'source_patch_sha256', 'operator_proof_sha256', 'manifest_sha256',
            'decoding_mode', 'draft_tokens', 'draft_vocab', 'mtp_policy',
            'placement', 'weight_placement', 'experimental')),
        'runtime_hashes': hash_map(engine.get('runtime_hashes') or {}),
    }
    if engine.get('executable_sha256'):
        result['executable_sha256'] = engine['executable_sha256']
    if command:
        result['executable_name'] = PureWindowsPath(command[0]).name
    weights = {}
    for flag in ('--model', '--mtp-model', '-m', '-md'):
        if command.count(flag) == 1 and command.index(flag) + 1 < len(command):
            weights[flag] = PureWindowsPath(command[command.index(flag) + 1]).name
    result['weight_filenames'] = weights
    manifest = value.get('engine_manifest') or {}
    result['halogen_manifest'] = subset(manifest, (
        'schema', 'version', 'image', 'checkpoint', 'context', 'slots',
        'entrypoint_sha256'))
    result['halogen_manifest']['environment'] = subset(manifest.get('environment') or {}, SAFE_ENV)
    result['halogen_manifest']['source_hashes'] = hash_map(manifest.get('sources') or {})
    if value.get('engine_manifest_sha256'):
        result['engine_manifest_sha256'] = value['engine_manifest_sha256']
    return result


def sample(value):
    result = subset(value, SAMPLE_FIELDS)
    result['turn_kind'] = 'exact-value retrieval' if value.get('turn') == 0 else 'sampled code / review (ungraded)'
    result['raw_phase_timings'] = subset(value.get('timings') or {}, TIMING_FIELDS)
    calibration = value.get('clock') or {}
    result['clock'] = subset(calibration, (
        'monotonic_per_raw', 'raw_per_qpc', 'mono_per_qpc',
        'windows_seconds', 'guest_raw_seconds', 'guest_monotonic_seconds',
        'qpc_seconds', 'uncertainty_seconds', 'raw_seconds', 'mono_seconds',
        'window_seconds', 'handshake_uncertainty_seconds'))
    native = value.get('native_cache_counters') or {}
    result['native_cache_counters'] = {
        key: item for key, item in native.items()
        if isinstance(key, str) and re.fullmatch(r'[a-zA-Z0-9_]{1,80}', key)
        and ('cache' in key or 'reuse' in key)
        and type(item) in (int, float, bool) and (type(item) is bool or math.isfinite(item))
    }
    memory = value.get('host_memory') or {}
    result['host_memory'] = {
        key: subset(memory.get(key) or {}, ('available_bytes', 'commit_headroom_bytes'))
        for key in ('before', 'after', 'observed_minimum', 'controller_before', 'controller_after')
    }
    return result


def failure_details(error, default='recorded failure'):
    """Classify an error without publishing its text or arbitrary exception name."""
    result = {'failure_category': default}
    if not isinstance(error, str):
        return result
    error_type = error.split(':', 1)[0]
    if error_type in ('RuntimeError', 'ValueError', 'FileNotFoundError', 'TimeoutError',
                      'OSError', 'ConnectionError', 'URLError', 'HTTPError',
                      'ApiDeadlineExceeded', 'CaseDeadlineExceeded'):
        result['failure_type'] = error_type
    http = re.search(r'\bHTTP(?: Error)? ([1-5][0-9]{2})\b', error)
    if http:
        result['failure_http_status'] = int(http.group(1))
    categories = (
        (('Memory reserve', 'Memory headroom', 'memory below', 'crossed reserve',
          'physical reserve crossed', 'physical/commit reserve crossed'), 'memory reserve'),
        (('Initial conversation reused', 'geometry/cache'), 'initial input/cache validation'),
        (('Incomplete streamed',), 'incomplete stream'),
        (('Readiness', 'readiness', 'startup', 'Startup', 'before ready'), 'startup/readiness'),
        (('Controller terminal', 'Runtime ended'), 'controller terminal state'),
        (('runtime changed', 'Backend changed'), 'runtime identity changed'),
        (('profile bytes changed', 'source/profile changed'), 'source/profile identity changed'),
        (('Initial prompt exceeds',), 'input token geometry'),
        (('draft-token acceptance',), 'draft accounting'),
        (('completion-token count',), 'output token accounting'),
        (('timed out', 'time budget', 'deadline', 'TimeoutExpired'), 'deadline/timeout'),
        (('Docker grading', 'grader container'), 'grading infrastructure'),
        (('cleanup', 'recovery'), 'lifecycle cleanup/recovery'),
    )
    for needles, category in categories:
        if any(needle in error for needle in needles):
            result['failure_category'] = category
            break
    return result


def lifecycle(directory):
    """Return only public status/memory/identity fields from a root-owned group."""
    result = {}
    result_path = directory / 'result.json'
    if result_path.is_file():
        raw = result_path.read_bytes()
        value = json.loads(raw)
        result.update(subset(value, ('passed', 'cleanup', 'finished_at')))
        result['result_sha256'] = hashlib.sha256(raw).hexdigest()
        if value.get('error') or value.get('passed') is False:
            result.update(failure_details(value.get('error'), 'group startup/lifecycle failure'))
    terminal_path = directory / 'terminal.json'
    if terminal_path.is_file():
        raw = terminal_path.read_bytes()
        terminal = json.loads(raw)
        result['terminal_sha256'] = hashlib.sha256(raw).hexdigest()
        controller = terminal.get('controller') or {}
        result['terminal_controller'] = subset(controller, (
            'phase', 'backend', 'checkpoint', 'context', 'minimum_reserve_gib',
            'profile_sha256', 'minimum_available_gib'))
        controller_memory = controller.get('memory') or {}
        result['terminal_controller']['memory'] = subset(controller_memory, (
            'available_bytes', 'commit_headroom_bytes'))
        controller_failure = failure_details(controller.get('error'), 'controller terminal state')
        if controller.get('phase') == 'failed' and controller_failure['failure_category'] == 'memory reserve':
            result['failure_category'] = 'memory reserve'
            result['failure_evidence'] = 'controller terminal error'
        inner = terminal.get('backend') or {}
        result['terminal_backend'] = subset(inner, (
            'phase', 'checkpoint', 'context', 'slots', 'prompt_cache'))
        result['terminal_backend']['outcome'] = subset(inner.get('outcome') or {}, (
            'ready', 'cleanup', 'recovery', 'context'))
    return result


def group_for(work, backend, context, tag, coding=False):
    prefix = f'coding-run-{backend}' if coding else f'{backend}-c{context}'
    if tag:
        directory = work / (prefix + '-' + tag)
        return directory if directory.is_dir() else None, False
    pattern = re.compile(re.escape(prefix) + r'-[A-Za-z0-9_-]{1,48}\Z')
    directories = [p for p in work.iterdir() if p.is_dir() and pattern.fullmatch(p.name)
                   and (coding or not re.match(r'-p[0-9]+(?:-|$)', p.name[len(prefix):]))]
    return (directories[0] if len(directories) == 1 else None), len(directories) > 1


def read_cell(work, backend, context, fill, tag):
    prefix = f'{backend}-c{context}-p{fill}'
    paths = [work / (prefix + '-' + tag)] if tag else [p for p in work.iterdir()
             if p.is_dir() and (p.name == prefix or p.name.startswith(prefix + '-'))]
    if len(paths) > 1:
        return {'backend': backend, 'context': context, 'target_input': fill,
                'status': 'ambiguous reruns; select --tag'}
    if not paths or not (paths[0] / 'summary.json').is_file():
        result = {'backend': backend, 'context': context, 'target_input': fill, 'status': 'pending'}
        selected_tag = tag
        if paths and paths[0].name.startswith(prefix + '-'):
            selected_tag = paths[0].name[len(prefix) + 1:]
        group, ambiguous = group_for(work, backend, context, selected_tag)
        if ambiguous:
            result['status'] = 'ambiguous reruns; select --tag'
        elif group is not None:
            try:
                result['lifecycle'] = lifecycle(group)
                if 'failure_category' in result['lifecycle']:
                    result['status'] = 'failed before measurement'
                    result.update(subset(result['lifecycle'], (
                        'failure_category', 'failure_type', 'failure_http_status')))
            except (OSError, ValueError, TypeError, KeyError):
                result['status'] = 'invalid or incomplete lifecycle artifact; review locally'
        return result
    directory = paths[0]
    try:
        source = (directory / 'summary.json').read_bytes()
        summary = json.loads(source)
        if any(summary.get(key) != expected for key, expected in (
                ('backend', backend), ('context', context), ('target_input', fill))):
            raise ValueError('Geometry mismatch')
        result = subset(summary, SUMMARY_FIELDS)
        result['status'] = 'completed' if summary.get('passed_execution') is True else 'failed or partial'
        result['summary_sha256'] = hashlib.sha256(source).hexdigest()
        result['retrieval_details'] = [retrieval(item) for item in summary.get('retrieval_details', [])]
        if summary.get('error'):
            result.update(failure_details(summary['error']))
        rows = []
        samples_path = directory / 'samples.jsonl'
        if samples_path.is_file():
            for line in samples_path.read_text(encoding='utf-8').splitlines():
                if line.strip():
                    value = json.loads(line)
                    if any(value.get(key) != expected for key, expected in (
                            ('backend', backend), ('context', context), ('target_input', fill))):
                        raise ValueError('Sample geometry mismatch')
                    rows.append(sample(value))
        result['turns'] = rows
        valid = all(type(row.get('drafted')) is int and type(row.get('accepted')) is int
                    and 0 <= row['accepted'] <= row['drafted'] for row in rows)
        result['draft_counters_complete_for_recorded_turns'] = bool(rows) and valid
        result['recorded_drafted_total'] = sum(row['drafted'] for row in rows) if rows and valid else None
        result['recorded_accepted_total'] = sum(row['accepted'] for row in rows) if rows and valid else None
        for row in rows:
            rep = row.get('rep')
            if row.get('turn') == 0 and type(rep) is int and 0 <= rep < len(result['retrieval_details']):
                row['retrieval'] = result['retrieval_details'][rep]
        identity_path = directory / 'identity.json'
        if identity_path.is_file():
            result['identity'] = identity(json.loads(identity_path.read_text(encoding='utf-8')))
        selected_tag = paths[0].name[len(prefix) + 1:] if paths[0].name.startswith(prefix + '-') else tag
        group, _ = group_for(work, backend, context, selected_tag)
        if group is not None:
            result['lifecycle'] = lifecycle(group)
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {'backend': backend, 'context': context, 'target_input': fill,
                'status': 'invalid or incomplete artifact; review locally'}


def numeric_metrics(value):
    return {key: item for key, item in value.items()
            if isinstance(key, str) and re.fullmatch(r'[a-zA-Z0-9_]{1,80}', key)
            and type(item) in (int, float, bool)
            and (type(item) is bool or math.isfinite(item))}


def coding_manifest(value):
    result = subset(value, (
        'schema', 'repository', 'revision', 'archive_sha256', 'selection',
        'context_capacity', 'initial_input_target', 'attempts',
        'max_agent_calls_per_attempt', 'output_limit_per_call', 'grading',
        'test_visibility', 'shell_tool', 'pytest', 'test_timeout_seconds',
        'execution_isolation', 'grader_image', 'grader_python', 'memory_guard',
        'suite_revision', 'api_timeout_policy'))
    result['exercises'] = [name for name in value.get('exercises', []) if name in EXERCISES]
    result['files_sha256'] = hash_map(value.get('files_sha256') or {})
    result['official_test_cases'] = subset(value.get('official_test_cases') or {}, EXERCISES)
    result['sampling'] = subset(value.get('sampling') or {}, (
        'temperature', 'top_p', 'top_k', 'min_p', 'presence_penalty',
        'repetition_penalty', 'reasoning_effort'))
    result['dependency_pins'] = subset(value.get('dependency_pins') or {}, (
        'colorama', 'iniconfig', 'packaging', 'pluggy', 'Pygments', 'pytest'))
    result['deadlines_seconds'] = subset(value.get('deadlines_seconds') or {}, (
        'api_call', 'exercise', 'suite'))
    return result


def coding_call(value):
    result = subset(value, (
        'wall_seconds', 'initial_input_geometry_ok', 'finish_reason',
        'requested_output_tokens', 'output_tokens', 'output_capped', 'eos',
        'max_tokens_clamped_from', 'cache_prompt_requested'))
    usage = value.get('usage') or {}
    timings = value.get('timings') or {}
    result['usage'] = subset(usage, (
        'prompt_tokens', 'completion_tokens', 'total_tokens', 'cached_tokens',
        'draft_tokens', 'draft_tokens_accepted', 'prompt_tokens_per_second',
        'completion_tokens_per_second'))
    result['usage']['prompt_tokens_details'] = subset(usage.get('prompt_tokens_details') or {}, ('cached_tokens',))
    result['usage']['completion_tokens_details'] = subset(usage.get('completion_tokens_details') or {}, ('reasoning_tokens',))
    result['usage']['gufo'] = numeric_metrics(usage.get('gufo') or {})
    result['raw_phase_timings'] = subset(timings, TIMING_FIELDS)
    result['native_cache_counters'] = {key: item for key, item in
        numeric_metrics((usage.get('gufo') or {}) | timings).items()
        if 'cache' in key or 'reuse' in key}
    result['minimum_memory'] = subset(value.get('minimum_memory') or {}, (
        'available_bytes', 'commit_headroom_bytes'))
    result['recorded_drafted'] = timings.get('draft_n', usage.get('draft_tokens'))
    result['recorded_accepted'] = timings.get('draft_n_accepted',
        timings.get('draft_accepted', usage.get('draft_tokens_accepted')))
    return result


def coding_task(value):
    if value.get('exercise') not in EXERCISES:
        raise ValueError('Unknown exercise')
    result = subset(value, ('exercise', 'first_pass', 'passed', 'wall_seconds'))
    status = value.get('status')
    result['status'] = status if status in ('running', 'graded', 'case_deadline', 'infrastructure_error') else 'unknown'
    if value.get('error'):
        result.update(failure_details(value['error'], 'coding task failure'))
    result['attempts'] = []
    for attempt in value.get('attempts', []):
        safe = subset(attempt, (
            'passed', 'returncode', 'test_integrity', 'expected_test_count',
            'observed_test_count', 'all_official_tests_ran', 'write_calls_so_far',
            'malformed_agent_response', 'wall_seconds'))
        safe['solution_sha256'] = hash_map(attempt.get('solution_sha256') or {})
        records = attempt.get('test_records')
        if isinstance(records, list) and all(isinstance(record, dict)
                and type(record.get('bad')) is bool for record in records):
            safe['recorded_nonpassing_test_count'] = sum(record['bad'] for record in records)
            safe['recorded_passing_test_count'] = len(records) - safe['recorded_nonpassing_test_count']
        result['attempts'].append(safe)
    if not result['attempts']:
        result.pop('first_pass', None)
        result.pop('passed', None)
    result['calls'] = [coding_call(call) for call in value.get('calls', [])]
    result['recorded_call_count'] = len(result['calls'])
    result['recorded_attempt_count'] = len(result['attempts'])
    result['tool_events'] = [subset(event, ('attempt', 'turn', 'name', 'ok', 'result_sha256'))
                            for event in value.get('tool_events', [])
                            if event.get('name') in ('read_file', 'write_file')]
    result['agent_error_count'] = len(value.get('agent_errors', []))
    return result


def read_coding(work, backend, tag):
    prefix = f'coding-{backend}'
    paths = [work / (prefix + '-' + tag)] if tag else [p for p in work.iterdir()
             if p.is_dir() and re.fullmatch(re.escape(prefix) + r'-[A-Za-z0-9_-]{1,48}', p.name)]
    result = {'backend': backend, 'context': 131072, 'target_initial_input': 65536, 'status': 'pending'}
    if len(paths) > 1:
        result['status'] = 'ambiguous reruns; select --tag'
        return result
    selected_tag = tag
    if paths and paths[0].name.startswith(prefix + '-'):
        selected_tag = paths[0].name[len(prefix) + 1:]
    group, ambiguous = group_for(work, backend, 131072, selected_tag, coding=True)
    if ambiguous:
        result['status'] = 'ambiguous reruns; select --tag'
        return result
    try:
        if group is not None:
            result['lifecycle'] = lifecycle(group)
        if not paths or not (paths[0] / 'summary.json').is_file():
            if 'failure_category' in result.get('lifecycle', {}):
                result['status'] = 'failed before measurement'
                result.update(subset(result['lifecycle'], (
                    'failure_category', 'failure_type', 'failure_http_status')))
            return result
        directory = paths[0]
        raw = (directory / 'summary.json').read_bytes()
        summary = json.loads(raw)
        if summary.get('backend', backend) not in (backend, MODEL_IDS[backend]) or summary.get('context') != 131072:
            raise ValueError('Coding identity mismatch')
        if summary.get('target_initial_input') != 65536:
            raise ValueError('Coding input geometry mismatch')
        result.update(subset(summary, (
            'completed', 'exact_author_replication', 'first_pass', 'passed', 'total',
            'wall_seconds', 'context', 'target_initial_input', 'runner_sha256',
            'suite_revision', 'public_manifest_sha256', 'dataset_manifest_sha256',
            'tokenizer_sha256', 'corpus_sha256', 'profile_sha256',
            'grading_isolation', 'grader_image')))
        result['status'] = 'completed' if summary.get('completed') is True else 'in progress or partial'
        if summary.get('error'):
            result['status'] = 'failed or partial'
            result.update(failure_details(summary['error'], 'coding suite failure'))
        elif summary.get('completed') is not True and 'failure_category' in result.get('lifecycle', {}):
            result['status'] = 'failed or partial'
            result.update(subset(result['lifecycle'], (
                'failure_category', 'failure_type', 'failure_http_status')))
        if summary.get('completed') is not True and result.get('lifecycle', {}).get('failure_category') == 'memory reserve':
            result['failure_category'] = 'memory reserve'
            result['failure_evidence'] = 'owning controller lifecycle'
        result['summary_sha256'] = hashlib.sha256(raw).hexdigest()
        if summary.get('runner_source') == 'scripts/benchmarks/polyglot_tool_bench.py':
            result['runner_source'] = summary['runner_source']
        result['grader_dependencies'] = subset(summary.get('grader_dependencies') or {}, (
            'colorama', 'iniconfig', 'packaging', 'pluggy', 'Pygments', 'pytest'))
        result['deadlines_seconds'] = subset(summary.get('deadlines_seconds') or {}, (
            'api_call', 'exercise', 'suite'))
        result['exercises'] = [name for name in summary.get('exercises', []) if name in EXERCISES]
        result['rows'] = [coding_task(row) for row in summary.get('rows', [])]
        # Partial suites never acquire invented 0/10 scores or elapsed-time sums.
        if summary.get('completed') is not True:
            for key in ('first_pass', 'passed', 'total'):
                result.pop(key, None)
        manifest_path = directory / 'manifest.json'
        if manifest_path.is_file():
            manifest_raw = manifest_path.read_bytes()
            result['manifest_sha256'] = hashlib.sha256(manifest_raw).hexdigest()
            result['manifest'] = coding_manifest(json.loads(manifest_raw))
        calls = [call for row in result['rows'] for call in row['calls']]
        counters_complete = bool(calls) and all(
            type(call['recorded_drafted']) is int and type(call['recorded_accepted']) is int
            and 0 <= call['recorded_accepted'] <= call['recorded_drafted'] for call in calls)
        result['draft_counters_complete_for_recorded_calls'] = counters_complete
        result['recorded_drafted_total'] = sum(call['recorded_drafted'] for call in calls) if counters_complete else None
        result['recorded_accepted_total'] = sum(call['recorded_accepted'] for call in calls) if counters_complete else None
        drafted = result['recorded_drafted_total']
        result['recorded_mtp_acceptance'] = result['recorded_accepted_total'] / drafted if drafted else None
        result['recorded_host_memory_floor_bytes'] = {
            key: min(call['minimum_memory'][key] for call in calls)
            for key in ('available_bytes', 'commit_headroom_bytes')
            if calls and all(type(call['minimum_memory'].get(key)) is int for call in calls)}
        profile_paths = [work / f'{backend}-c131072.json'] + sorted(work.glob(f'{backend}-*-c131072.json'))
        for profile_path in profile_paths:
            if not profile_path.is_file():
                continue
            profile_raw = profile_path.read_bytes()
            if hashlib.sha256(profile_raw).hexdigest() == summary.get('profile_sha256'):
                identity_value = {'profile': json.loads(profile_raw), 'profile_sha256': summary['profile_sha256']}
                if group is not None and (group / 'engine-manifest.json').is_file():
                    manifest_raw = (group / 'engine-manifest.json').read_bytes()
                    identity_value['engine_manifest'] = json.loads(manifest_raw)
                    identity_value['engine_manifest_sha256'] = hashlib.sha256(manifest_raw).hexdigest()
                result['identity'] = identity(identity_value)
                break
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {'backend': backend, 'context': 131072, 'target_initial_input': 65536,
                'status': 'invalid or incomplete coding artifact; review locally'}


def prior_attempts(work, selected_tags):
    """Keep nonselected recorded attempts separate; never use them in tables."""
    result = []
    directories = [path for path in work.iterdir() if path.is_dir()]
    for context, fill in GEOMETRIES:
        for backend in BACKENDS:
            tags = set()
            cell_prefix = f'{backend}-c{context}-p{fill}-'
            group_prefix = f'{backend}-c{context}-'
            for directory in directories:
                if directory.name.startswith(cell_prefix):
                    tags.add(directory.name[len(cell_prefix):])
                elif directory.name.startswith(group_prefix):
                    suffix = directory.name[len(group_prefix):]
                    if not re.match(r'p[0-9]+(?:-|$)', suffix):
                        tags.add(suffix)
            for tag in sorted(tags):
                if tag == selected_tags[backend] or not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', tag):
                    continue
                attempt = read_cell(work, backend, context, fill, tag)
                if attempt['status'] != 'pending':
                    attempt['run_tag'] = tag
                    result.append(attempt)
    return result


def prior_coding_attempts(work, selected_tags):
    """Sanitize nonselected coding receipts without adding them to scores."""
    result = []
    directories = [path for path in work.iterdir() if path.is_dir()]
    for backend in BACKENDS:
        tags = set()
        prefixes = (f'coding-{backend}-', f'coding-run-{backend}-')
        for directory in directories:
            for prefix in prefixes:
                if directory.name.startswith(prefix):
                    tags.add(directory.name[len(prefix):])
        for tag in sorted(tags):
            if tag == selected_tags[backend] or not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', tag):
                continue
            attempt = read_coding(work, backend, tag)
            if attempt['status'] != 'pending':
                attempt['run_tag'] = tag
                result.append(attempt)
    return result


def markdown(cells, coding=None, prior=None, prior_coding=None):
    lines = [
        'Existing article-cell summaries; no old result substitution.', '',
        'Method reference: [deepu105\'s comparison](https://www.reddit.com/r/LocalLLM/comments/1wu0m53/benchmarks_best_engine_for_qwen_38flashnext_on/).', '',
        '3-turn time is the existing normalized summary, displayed in minutes. WSL-adjusted phase estimates and independent client times remain in the JSON. Article follow-up code is ungraded; optional tool-coding results below are separately graded.', '',
    ]
    for context, fill in GEOMETRIES:
        lines.extend([f'## {context:,} capacity / {fill:,} initial tokens', '',
            '| Engine | Weights | 3-turn time | Prefill t/s | Decode t/s | MTP accept | Retrieval |',
            '|---|---|---:|---:|---:|---:|---:|'])
        for cell in (c for c in cells if c['context'] == context and c['target_input'] == fill):
            label, weights = LABELS[cell['backend']]
            if cell['status'] != 'completed':
                lines.append(f'| {label} | {weights} | {cell["status"]} | — | — | — | — |')
                continue
            normalized = cell.get('three_turn_seconds')
            minutes = number(normalized / 60) + ' min' if type(normalized) in (int, float) else '—'
            fraction = cell.get('mtp_acceptance')
            accept = number(fraction * 100, 1) + '%' if type(fraction) in (int, float) else 'unavailable'
            correct, total = cell.get('retrieval_correct'), cell.get('retrieval_total')
            grade = f'{correct}/{total}' if type(correct) is int and type(total) is int else '—'
            lines.append(f'| {label} | {weights} | {minutes} | {number(cell.get("prefill_tps"), 1)} | {number(cell.get("decode_tps"))} | {accept} | {grade} |')
        lines.append('')
    lines.extend(['## Counts and telemetry', '',
        '| Engine / capacity / input | Accepted / drafted | Initial counts | Cache: first / follow-ups | Caps / EOS / clamps | Observed wall s | Min RAM / commit GiB |',
        '|---|---:|---|---|---:|---:|---:|'])
    for cell in cells:
        if cell['status'] not in ('completed', 'failed or partial'):
            continue
        name = f'{cell["backend"]} / {cell["context"]} / {cell["target_input"]}'
        accepted, drafted = cell.get('recorded_accepted_total'), cell.get('recorded_drafted_total')
        counters = f'{accepted}/{drafted}' if type(accepted) is int and type(drafted) is int else 'unavailable'
        counts = json.dumps(cell.get('actual_initial_tokens', []))
        cache = json.dumps(cell.get('initial_cache_observations', [])) + ' / ' + json.dumps(cell.get('followup_cache_observations', []))
        limits = ' / '.join(str(cell.get(key, '—')) for key in ('capped_outputs', 'eos_outputs', 'clamped_outputs'))
        floor = cell.get('host_memory_floor_bytes') or {}
        memory = ' / '.join(number(floor[key] / 1024**3) if type(floor.get(key)) is int else '—'
                            for key in ('available_bytes', 'commit_headroom_bytes'))
        lines.append(f'| {name} | {counters} | {counts} | {cache} | {limits} | {number(cell.get("observed_wall_seconds"))} | {memory} |')
    groups = [cell for cell in cells if cell.get('lifecycle')]
    if groups:
        lines.extend(['', '## Recorded lifecycle', '',
            '| Engine / capacity / input | Group passed | Cleanup | Controller / backend terminal | Failure category |',
            '|---|---|---|---|---|'])
        for cell in groups:
            life = cell['lifecycle']
            terminal = str(life.get('terminal_controller', {}).get('phase', 'unavailable')) + ' / ' + str(life.get('terminal_backend', {}).get('phase', 'unavailable'))
            lines.append(f'| {cell["backend"]} / {cell["context"]} / {cell["target_input"]} | {life.get("passed", "unavailable")} | {life.get("cleanup", "unavailable")} | {terminal} | {life.get("failure_category", "—")} |')
    if coding is not None:
        lines.extend(['', '## Optional disclosed tool-coding analogue', '',
            'Different agent loop and disclosed first-ten lexical subset; not the author\'s exact Pi run. Elapsed time comes directly from the coding summary and excludes engine startup. Pending/partial suites have no invented pass score.', '',
            '| Engine | Status | First pass | Final pass | Actual suite elapsed | Accepted / drafted |',
            '|---|---|---:|---:|---:|---:|'])
        for cell in coding:
            label = LABELS[cell['backend']][0]
            complete = cell.get('completed') is True
            first = f'{cell["first_pass"]}/{cell["total"]}' if complete and type(cell.get('first_pass')) is int and type(cell.get('total')) is int else '—'
            final = f'{cell["passed"]}/{cell["total"]}' if complete and type(cell.get('passed')) is int and type(cell.get('total')) is int else '—'
            elapsed = number(cell.get('wall_seconds')) + ' s' if type(cell.get('wall_seconds')) in (int, float) else '—'
            accepted, drafted = cell.get('recorded_accepted_total'), cell.get('recorded_drafted_total')
            counters = f'{accepted}/{drafted}' if type(accepted) is int and type(drafted) is int else 'unavailable'
            lines.append(f'| {label} | {cell["status"]} | {first} | {final} | {elapsed} | {counters} |')
        rows = [(cell, row) for cell in coding for row in cell.get('rows', [])]
        if rows:
            lines.extend(['', '| Engine / task | Status | First / final pass | Attempts / calls | Expected / observed final tests | All official tests ran | Actual task elapsed s |',
                '|---|---|---|---:|---:|---|---:|'])
            for cell, row in rows:
                attempt = row['attempts'][-1] if row['attempts'] else {}
                tests = str(attempt.get('expected_test_count', '—')) + ' / ' + str(attempt.get('observed_test_count', '—'))
                passes = str(row.get('first_pass', 'unavailable')) + ' / ' + str(row.get('passed', 'unavailable'))
                counts = str(row.get('recorded_attempt_count', 0)) + ' / ' + str(row.get('recorded_call_count', 0))
                lines.append(f'| {cell["backend"]} / {row["exercise"]} | {row["status"]} | {passes} | {counts} | {tests} | {attempt.get("all_official_tests_ran", "unavailable")} | {number(row.get("wall_seconds"))} |')
        lines.extend(['', '| Coding engine | Group passed | Cleanup | Terminal controller / backend | Failure category |',
            '|---|---|---|---|---|'])
        for cell in coding:
            life = cell.get('lifecycle') or {}
            terminal = str(life.get('terminal_controller', {}).get('phase', 'unavailable')) + ' / ' + str(life.get('terminal_backend', {}).get('phase', 'unavailable'))
            lines.append(f'| {cell["backend"]} | {life.get("passed", "unavailable")} | {life.get("cleanup", "unavailable")} | {terminal} | {life.get("failure_category", cell.get("failure_category", "—"))} |')
    if prior is not None:
        lines.extend(['', '## Prior attempts retained separately', '',
            'These attempts do not contribute to the selected comparison tables.', '',
            '| Engine / capacity / input | Tag | Status | Completed requests | Failure category | Cleanup |',
            '|---|---|---|---:|---|---|'])
        for cell in prior:
            name = f'{cell["backend"]} / {cell["context"]} / {cell["target_input"]}'
            count = cell.get('requests', cell.get('completed_requests', 'unavailable'))
            life = cell.get('lifecycle') or {}
            lines.append(f'| {name} | {cell["run_tag"]} | {cell["status"]} | {count} | {cell.get("failure_category", life.get("failure_category", "—"))} | {life.get("cleanup", "unavailable")} |')
    if prior_coding is not None:
        lines.extend(['', '## Prior coding attempts retained separately', '',
            'These attempts do not contribute to the selected coding scores. Incomplete suites remain unscored.', '',
            '| Engine | Tag | Status | Recorded calls / graded attempts | Actual elapsed s | Failure category / HTTP | Cleanup |',
            '|---|---|---|---:|---:|---|---|'])
        for cell in prior_coding:
            rows = cell.get('rows') or []
            counts = str(sum(row.get('recorded_call_count', 0) for row in rows)) + ' / ' + str(sum(row.get('recorded_attempt_count', 0) for row in rows))
            life = cell.get('lifecycle') or {}
            failure = str(cell.get('failure_category', life.get('failure_category', '—')))
            if type(cell.get('failure_http_status')) is int:
                failure += ' / ' + str(cell['failure_http_status'])
            lines.append(f'| {cell["backend"]} | {cell["run_tag"]} | {cell["status"]} | {counts} | {number(cell.get("wall_seconds"))} | {failure} | {life.get("cleanup", "unavailable")} |')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--tag', default='', help='Exact run tag; required if there are multiple matching reruns')
    parser.add_argument('--projfix-tag', default='',
                        help='Explicit PROJFIX article replacement tag; other article engines keep --tag')
    parser.add_argument('--projfix-coding-tag', default='',
                        help='Explicit PROJFIX coding replacement tag; other coding engines keep --tag')
    parser.add_argument('--format', choices=('markdown', 'json'), default='markdown')
    parser.add_argument('--include-coding', action='store_true',
                        help='Include only coding-<engine>-<tag> summaries and coding-run lifecycle records')
    parser.add_argument('--include-prior-attempts', action='store_true',
                        help='Retain sanitized nonselected article attempts and optional coding attempts separately')
    args = parser.parse_args()
    if any(tag and not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', tag)
           for tag in (args.tag, args.projfix_tag, args.projfix_coding_tag)):
        parser.error('Use a short alphanumeric run tag')
    work = args.work.resolve(strict=True)
    selected_tags = {backend: args.projfix_tag if backend == 'projfix' and args.projfix_tag else args.tag
                     for backend in BACKENDS}
    selected_coding_tags = {backend: args.projfix_coding_tag if backend == 'projfix' and args.projfix_coding_tag else args.tag
                            for backend in BACKENDS}
    cells = [read_cell(work, backend, context, fill, selected_tags[backend])
             for context, fill in GEOMETRIES for backend in BACKENDS]
    coding = [read_coding(work, backend, selected_coding_tags[backend]) for backend in BACKENDS] if args.include_coding else None
    prior = prior_attempts(work, selected_tags) if args.include_prior_attempts else None
    prior_coding = prior_coding_attempts(work, selected_coding_tags) if args.include_prior_attempts and args.include_coding else None
    if args.format == 'json':
        result = {'schema': 2, 'scope': 'Sanitized existing article/coding summaries and recorded fields; article code is ungraded and optional coding outcomes use the recorded official-test grader.',
            'reference': 'https://www.reddit.com/r/LocalLLM/comments/1wu0m53/benchmarks_best_engine_for_qwen_38flashnext_on/',
            'metric_source': 'Summary phase/time/retrieval fields preserved. Article acceptance preserved. Recorded coding acceptance and memory floor derive only from recorded calls; actual coding elapsed comes from its summary.',
            'selected_article_tags': selected_tags, 'coding_tag': args.tag,
            'cells': cells}
        if coding is not None:
            result['selected_coding_tags'] = selected_coding_tags
            result['coding'] = coding
        if prior is not None:
            result['prior_attempts'] = prior
        if prior_coding is not None:
            result['prior_coding_attempts'] = prior_coding
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    else:
        print(markdown(cells, coding, prior, prior_coding), end='')


if __name__ == '__main__':
    main()
