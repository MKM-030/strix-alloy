"""Three-turn coding/cache benchmark for an already-managed Halogen profile.

No lifecycle or cache-clear API is called. --reps 3 means nine measured calls,
with an identical shared system prefix and identical user/tool-fixture bytes.
Candidate runs should reuse --workload <control-out>/workload. Every assistant
message, including reasoning fields, is preserved in the next request. Length
limits are retained as incomplete outputs, never claimed as completed code.

Run requires explicit profile/run/tokenizer pins and writes only server/.local.
The `compare` subcommand compares existing recordings without live requests.
"""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import time

from reddit_runtime import ManagedClient, ROOT, save_json
from reddit_suite import modes_for_profile

MIN_SYSTEM_TOKENS = 8192
SOURCE_FILES = ('server/controller.py', 'server/gateway.py')
MEMORY_FIELDS = ('available_bytes', 'commit_headroom_bytes')


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(',', ':')) + '\n').encode('utf-8')


def file_identity(info):
    return {key: getattr(info, 'st_' + key) for key in
            ('size', 'dev', 'ino', 'mtime_ns', 'ctime_ns')}


def pinned_bytes(path, limit=1024**2):
    with Path(path).open('rb', buffering=0) as stream:
        before = file_identity(os.fstat(stream.fileno()))
        if before['size'] > limit:
            raise ValueError('Input is too large for a bounded source/tokenizer snapshot')
        raw = stream.read(limit + 1)
        if len(raw) != before['size'] or file_identity(os.fstat(stream.fileno())) != before:
            raise ValueError('Input changed while reading snapshot bytes')
    return raw, before


def load_tokenizer(path, expected_sha256, *, loader=None):
    raw, identity = pinned_bytes(path, limit=64 * 1024**2)
    actual = sha256(raw)
    if actual != expected_sha256:
        raise ValueError('Reviewed tokenizer SHA256 does not match')
    if loader is None:
        from tokenizers import Tokenizer
        loader = lambda data: Tokenizer.from_str(data.decode('utf-8'))
    return loader(raw), {'path': str(Path(path).resolve()), 'sha256': actual,
                         'identity': identity}


def token_count(tokenizer, text):
    return len(tokenizer.encode(text, add_special_tokens=False).ids)


def profile_cache(profile):
    return profile['engine'].get('prompt_cache', 'Off')


def build_workload(root, tokenizer, tokenizer_sha256):
    """Snapshot public repository source plus deterministic virtual tool data."""
    assets, source_snapshots, excerpts = {}, [], []
    for relative in SOURCE_FILES:
        raw, _ = pinned_bytes(Path(root) / relative)
        target = 'snapshots/' + relative.replace('/', '-')
        assets[target] = raw
        source_snapshots.append({'source': relative, 'file': target,
                                 'sha256': sha256(raw), 'bytes': len(raw)})
        excerpts.append('\nRepository file ' + relative + ':\n' + raw.decode('utf-8'))
    config = 'def parse_port(value):\n    return int(value)\n'
    tests = ('import pytest\nfrom config import parse_port\n\n'
             'def test_bool_rejected():\n    with pytest.raises(ValueError):\n        parse_port(True)\n\n'
             'def test_upper_bound():\n    with pytest.raises(ValueError):\n        parse_port(65536)\n')
    assets['fixtures/config.py'] = config.encode()
    assets['fixtures/tests/test_config.py'] = tests.encode()
    report = {'synthetic': True, 'scope': 'baseline virtual fixture; generated code was not executed',
        'read_file': [{'path': 'config.py', 'content': config},
                      {'path': 'tests/test_config.py', 'content': tests}],
        'test_report': {'runner': 'pytest-like synthetic fixture', 'passed': 0, 'failed': 1,
                        'failures': [{'test': 'test_bool_rejected',
                                      'expected': 'ValueError', 'observed': 'returned 1'}]}}
    assets['tool-report.json'] = json_bytes(report)
    lead = ('You are a coding assistant working on a virtual Python project. '
            'Treat repository snapshots and corpus records below as context data. '
            'Return the requested code or tests. Tool reports are explicit synthetic '
            'fixtures; no generated code has been executed.\n')
    base = lead + ''.join(excerpts) + '\nDeterministic corpus records:\n'
    records, count = [], 0
    while True:
        for _ in range(16):
            records.append(json.dumps({'record': count, 'path': f'modules/item_{count:04d}.py',
                'revision': (count * 17 + 23) % 997, 'owner': f'team_{count % 11}',
                'note': f'Port parser fixture {count}: reject bool, check limits, retain stable API.'},
                sort_keys=True, separators=(',', ':')) + '\n')
            count += 1
        corpus = ''.join(records)
        system = base + corpus
        measured = token_count(tokenizer, system)
        if measured >= MIN_SYSTEM_TOKENS:
            break
        if count >= 16384:
            raise ValueError('Cannot construct the required 8192-token common prefix')
    turns = [
        'Edit virtual config.py. Its current contents are `def parse_port(value): return int(value)`. '
        'Return only a complete replacement parse_port(value) function. Accept integers 1..65535; '
        'reject booleans, non-integers and values outside that range with ValueError. No markdown.',
        'Tool-response-like payload from actual synthetic fixture files follows. It describes the '
        'baseline, not execution of your proposed code:\n' + assets['tool-report.json'].decode() +
        '\nReview your proposal against this report. Return only the two test functions for '
        'True and 65536, each asserting ValueError with pytest.raises. No markdown.',
        'Follow-up edit to the same virtual parse_port function: also accept whitespace-trimmed '
        'ASCII decimal strings, retaining the 1..65535 range and rejection of booleans and floats. '
        'Return only the complete updated function. Preserve the earlier checks. No markdown.',
    ]
    assets['corpus.jsonl'] = corpus.encode('utf-8')
    assets['system.txt'] = system.encode('utf-8')
    assets.update({f'turn{index}.txt': text.encode('utf-8')
                   for index, text in enumerate(turns, 1)})
    manifest = {'schema': 1, 'case': 'virtual_port_edit_three_turns',
        'tokenizer_sha256': tokenizer_sha256, 'minimum_system_tokens': MIN_SYSTEM_TOKENS,
        'system_text_tokens': measured, 'corpus_records': count,
        'source_snapshots': source_snapshots,
        'files': {name: {'sha256': sha256(raw), 'bytes': len(raw)}
                  for name, raw in sorted(assets.items())}}
    return {'manifest': manifest, 'assets': assets, 'system': system, 'turns': turns}


def save_workload(directory, workload):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    for name, raw in workload['assets'].items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)
    with (directory / 'manifest.json').open('xb') as stream:
        stream.write(json_bytes(workload['manifest']))


def load_workload(directory, tokenizer, tokenizer_sha256):
    directory = Path(directory).resolve(strict=True)
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    if manifest.get('schema') != 1 or manifest.get('tokenizer_sha256') != tokenizer_sha256:
        raise ValueError('Workload schema or tokenizer pin differs')
    assets = {}
    for name, record in manifest['files'].items():
        path = (directory / name).resolve(strict=True)
        if not path.is_relative_to(directory):
            raise ValueError('Workload file escapes its immutable directory')
        raw, _ = pinned_bytes(path)
        if len(raw) != record['bytes'] or sha256(raw) != record['sha256']:
            raise ValueError('Workload file hash/bytes changed: ' + name)
        assets[name] = raw
    system = assets['system.txt'].decode('utf-8')
    measured = token_count(tokenizer, system)
    if (measured < MIN_SYSTEM_TOKENS or measured != manifest['system_text_tokens'] or
            manifest.get('minimum_system_tokens') != MIN_SYSTEM_TOKENS):
        raise ValueError('Workload common prefix token count changed')
    return {'manifest': manifest, 'assets': assets, 'system': system,
            'turns': [assets[f'turn{turn}.txt'].decode('utf-8') for turn in (1, 2, 3)]}


class RecordingClient(ManagedClient):
    """Retain parsed response fields that ManagedClient's metrics do not expose."""
    last_request = last_response = None

    def request(self, path, body=None, timeout=1800):
        if path == '/v1/chat/completions':
            self.last_request = copy.deepcopy(body)
            self.last_response = None
        result = super().request(path, body, timeout)
        if path == '/v1/chat/completions':
            self.last_response = copy.deepcopy(result)
        return result


def cache_observation(usage, timings):
    details = usage.get('prompt_tokens_details') or {}
    count = timings.get('cache_n', usage.get('cached_tokens', details.get('cached_tokens')))
    if type(count) is not int or count < 0:
        return None, 'unknown'
    return count, 'hit' if count else 'miss'


def draft_metrics(usage, timings):
    drafted = timings.get('draft_n', usage.get('draft_tokens'))
    accepted = timings.get('draft_n_accepted', timings.get('draft_accepted',
                        usage.get('draft_tokens_accepted')))
    if type(drafted) is not int or drafted < 0:
        drafted = None
    if type(accepted) is not int or accepted < 0 or (drafted is not None and accepted > drafted):
        accepted = None
    return {'drafted': drafted, 'accepted': accepted,
            'draft_acceptance': accepted / drafted if drafted and accepted is not None else None}


def grade_output(turn, content, finish_reason):
    """Grade completed outputs; execute only a small reviewed Python AST subset."""
    if finish_reason != 'stop':
        return {'passed': False, 'kind': 'incomplete', 'reason': 'finish_' + str(finish_reason)}
    if not isinstance(content, str) or len(content) > 4000:
        return {'passed': False, 'kind': 'syntax', 'reason': 'output_not_bounded_code'}
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {'passed': False, 'kind': 'syntax', 'reason': 'invalid_python_or_markdown'}
    if turn == 2:
        values = set()
        functions = tree.body
        if len(functions) != 2:
            return {'passed': False, 'kind': 'test_assertion_ast', 'reason': 'expected_two_tests'}
        names = set()
        for function in functions:
            if (not isinstance(function, ast.FunctionDef) or not function.name.startswith('test_') or
                    function.name in names or function.decorator_list or function.returns or
                    function.args.posonlyargs or function.args.args or function.args.kwonlyargs or
                    function.args.vararg or function.args.kwarg or
                    len(function.body) != 1 or not isinstance(function.body[0], ast.With)):
                return {'passed': False, 'kind': 'test_assertion_ast',
                        'reason': 'expected_straight_line_pytest_assertion'}
            names.add(function.name)
            assertion = function.body[0]
            if (len(assertion.items) != 1 or assertion.items[0].optional_vars is not None or
                    len(assertion.body) != 1 or not isinstance(assertion.body[0], ast.Expr)):
                return {'passed': False, 'kind': 'test_assertion_ast',
                        'reason': 'expected_straight_line_pytest_assertion'}
            context = assertion.items[0].context_expr
            call = assertion.body[0].value
            if (not isinstance(context, ast.Call) or not isinstance(context.func, ast.Attribute) or
                    not isinstance(context.func.value, ast.Name) or context.func.value.id != 'pytest' or
                    context.func.attr != 'raises' or context.keywords or len(context.args) != 1 or
                    not isinstance(context.args[0], ast.Name) or context.args[0].id != 'ValueError' or
                    not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or
                    call.func.id != 'parse_port' or call.keywords or len(call.args) != 1 or
                    not isinstance(call.args[0], ast.Constant)):
                return {'passed': False, 'kind': 'test_assertion_ast',
                        'reason': 'expected_straight_line_pytest_assertion'}
            value = call.args[0].value
            if type(value) is bool and value is True:
                values.add('bool')
            elif type(value) is int and value == 65536:
                values.add('upper')
        return {'passed': values == {'bool', 'upper'},
                'kind': 'test_assertion_ast', 'reason': 'pytest_ValueError_assertions_not_executed'}
    if turn not in (1, 3):
        raise ValueError('Unknown benchmark turn')
    allowed = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.If, ast.Return,
        ast.Raise, ast.Assign, ast.Name, ast.Load, ast.Store, ast.Constant, ast.Call,
        ast.Attribute, ast.BoolOp, ast.UnaryOp, ast.Compare, ast.And, ast.Or, ast.Not,
        ast.Eq, ast.NotEq, ast.Is, ast.IsNot, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
        ast.Tuple, ast.List, ast.Expr, ast.Try, ast.ExceptHandler, ast.Pass, ast.USub)
    calls = {'type', 'isinstance', 'int', 'str', 'len', 'ValueError'}
    methods = {'strip', 'isascii', 'isdecimal', 'isdigit'}
    function = tree.body[0] if len(tree.body) == 1 else None
    nodes = list(ast.walk(tree))
    safe = (isinstance(function, ast.FunctionDef) and function.name == 'parse_port' and
        not function.decorator_list and not function.returns and
        len(function.args.args) == 1 and function.args.args[0].arg == 'value' and
        not function.args.defaults and not function.args.kwonlyargs and
        not function.args.vararg and not function.args.kwarg and len(nodes) <= 200 and
        all(isinstance(node, allowed) and
            (not isinstance(node, ast.Name) or not node.id.startswith('__')) and
            (not isinstance(node, ast.Attribute) or node.attr in methods) and
            (not isinstance(node, ast.Call) or
                (isinstance(node.func, ast.Name) and node.func.id in calls) or
                (isinstance(node.func, ast.Attribute) and node.func.attr in methods))
            for node in nodes))
    if not safe:
        return {'passed': False, 'kind': 'safe_function_cases', 'reason': 'unsafe_or_unreviewed_ast'}
    valid = [(1, 1), (8080, 8080), (65535, 65535)]
    invalid = [True, False, 0, 65536, 8.0, None]
    if turn == 1:
        invalid.append('8080')
    else:
        valid += [(' 8080 ', 8080), ('0012', 12)]
        invalid += ['', '１２', '+80', '-1', '0', '65536', '8.0']
    program = ("scope={'__builtins__': {name: getattr(__import__('builtins'), name) for name in "
        "('type','isinstance','int','str','bool','float','len','ValueError')}}\n"
        "exec(compile(" + repr(content) + ", '<graded-port-fixture>', 'exec'), scope)\n"
        "function=scope['parse_port']\n"
        "for value, expected in " + repr(valid) + ":\n    assert function(value)==expected\n"
        "for value in " + repr(invalid) + ":\n"
        "    try: function(value)\n    except ValueError: pass\n"
        "    else: raise AssertionError('invalid input accepted')\n")
    try:
        result = subprocess.run([sys.executable, '-I', '-S', '-c', program],
                                capture_output=True, timeout=3, check=False)
        return {'passed': result.returncode == 0, 'kind': 'safe_function_cases',
                'reason': 'case_exit_' + str(result.returncode), 'valid_cases': len(valid),
                'invalid_cases': len(invalid)}
    except subprocess.TimeoutExpired:
        return {'passed': False, 'kind': 'safe_function_cases', 'reason': 'case_timeout'}


def run_conversations(client, workload, output, tokenizer, *, mode, reps=3, max_tokens=128):
    """All calls are measured; observed cache misses/hits are retained equally."""
    if mode not in ('serial', 'speculative') or not 1 <= reps <= 3 or not 32 <= max_tokens <= 512:
        raise ValueError('Use serial/speculative, 1..3 repetitions and 32..512 output tokens')
    output = Path(output)
    rows = []
    summary = {'passed_execution': False, 'started_at': time.time(),
        'expected_calls': reps * 3, 'cache_observations': {'hit': 0, 'miss': 0, 'unknown': 0},
        'measurement_scope': 'Every call; observed cache hits and misses retained. '
            'Host RAM/commit sampled by ManagedClient; not VRAM peak.',
        'code_completion_scope': 'Length outputs are incomplete. Stop outputs are graded using '
            'bounded AST/function cases; turn2 pytest assertion structure is checked without execution.'}
    try:
        for rep in range(reps):
            messages = [{'role': 'system', 'content': workload['system']}]
            for turn, instruction in enumerate(workload['turns'], 1):
                messages.append({'role': 'user', 'content': instruction})
                prefix = copy.deepcopy(messages)
                prefix_raw = json_bytes(prefix)
                local_tokens = token_count(tokenizer, ''.join(
                    (message.get('content') or '') + (message.get('reasoning_content') or '')
                    for message in prefix))
                if local_tokens + max_tokens + 1024 > client.profile['backend']['context']:
                    raise ValueError('Conversation exceeds context with framing reserve')
                label = f'agent_rep{rep}_turn{turn}'
                client.last_request = client.last_response = None
                row = {'name': label, 'mode': mode, 'rep': rep, 'turn': turn,
                    'messages_sha256': sha256(prefix_raw), 'local_text_tokens': local_tokens}
                failure = None
                try:
                    row.update(client.call(prefix, max_tokens, mode, label, cold=False))
                except Exception as error:
                    failure = error
                    row['error'] = type(error).__name__ + ': ' + str(error)
                finally:
                    with (output / (label + '.messages.json')).open('xb') as stream:
                        stream.write(prefix_raw)
                    row['messages_file'] = label + '.messages.json'
                    for kind in ('request', 'response'):
                        value = getattr(client, 'last_' + kind, None)
                        if value is not None:
                            raw = json_bytes(value)
                            filename = label + '.' + kind + '.json'
                            with (output / filename).open('xb') as stream:
                                stream.write(raw)
                            row[kind + '_file'] = filename
                            row[kind + '_json_sha256'] = sha256(raw)
                    response = getattr(client, 'last_response', None)
                    if response and response.get('choices'):
                        choice = response['choices'][0]
                        assistant = copy.deepcopy(choice['message'])
                        if assistant.get('role') != 'assistant':
                            raise ValueError('Response has no actual assistant message role')
                        row['assistant_message_sha256'] = sha256(json_bytes(assistant))
                        row['assistant_content_sha256'] = sha256((assistant.get('content') or '').encode('utf-8'))
                        row['finish_reason'] = choice.get('finish_reason')
                        row['output_complete'] = choice.get('finish_reason') == 'stop'
                        row['grading'] = grade_output(turn, assistant.get('content'), choice.get('finish_reason'))
                    usage = row.get('usage', response.get('usage', {}) if response else {})
                    timings = row.get('timings', response.get('timings', {}) if response else {})
                    row['prompt_tokens'] = usage.get('prompt_tokens', timings.get('prompt_n'))
                    row['output_tokens'] = usage.get('completion_tokens', timings.get('predicted_n'))
                    row['cache_n'], row['cache_observation'] = cache_observation(usage, timings)
                    row.update(draft_metrics(usage, timings))
                    rows.append(row)
                    with (output / 'samples.jsonl').open('a', encoding='utf-8') as stream:
                        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                if failure is not None:
                    raise failure
                if (type(row['prompt_tokens']) is not int or type(row['output_tokens']) is not int or
                        row['prompt_tokens'] < MIN_SYSTEM_TOKENS):
                    raise ValueError('Comparable actual token accounting is absent or prefix is too short')
                messages.append(assistant)
                print(label, mode, 'cache_n=', row['cache_n'], 'finish=', row['finish_reason'],
                      'wall=', round(row['wall_seconds'], 3), flush=True)
        summary['passed_execution'] = True
    except Exception as error:
        summary['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        summary['finished_at'] = time.time()
        summary['calls'] = len(rows)
        summary['length_limited_calls'] = sum(row.get('finish_reason') == 'length' for row in rows)
        summary['complete_outputs'] = sum(bool(row.get('output_complete')) for row in rows)
        summary['passed_quality'] = (len(rows) == reps * 3 and
                                     all(row.get('grading', {}).get('passed') for row in rows))
        summary['wall_seconds'] = sum(row.get('wall_seconds', 0) for row in rows)
        for row in rows:
            summary['cache_observations'][row['cache_observation']] += 1
        memories = [row['minimum_memory'] for row in rows if row.get('minimum_memory')]
        summary['calls_with_memory_measurements'] = len(memories)
        summary['minimum_memory'] = {key: min(memory[key] for memory in memories)
                                     for key in MEMORY_FIELDS} if memories else None
        summary['turn_hash_counts'] = {str(turn): len({row.get('assistant_message_sha256')
            for row in rows if row['turn'] == turn}) for turn in (1, 2, 3)}
        known = [row for row in rows if row.get('drafted') is not None and row.get('accepted') is not None]
        drafted = sum(row['drafted'] for row in known)
        accepted = sum(row['accepted'] for row in known)
        summary['draft_accounting'] = {'calls_with_counters': len(known),
            'calls_without_counters': len(rows) - len(known),
            'observed_drafted_tokens': drafted if known else None,
            'observed_accepted_tokens': accepted if known else None,
            'acceptance': accepted / drafted if drafted else None}
        summary['samples_sha256'] = sha256((output / 'samples.jsonl').read_bytes()) if rows else None
        save_json(output / 'summary.json', summary)
    return rows, summary


def compare_recordings(control_identity, control_rows, candidate_identity, candidate_rows):
    fields = ('backend', 'context_capacity', 'harness_sha256', 'workload_sha256',
              'tokenizer_sha256', 'reps', 'max_tokens')
    if any(control_identity.get(key) != candidate_identity.get(key) for key in fields):
        raise ValueError('Recording identity/backend/workload/tokenizer differs')
    def indexed(rows):
        index = {(row['rep'], row['turn']): row for row in rows}
        wanted = {(rep, turn) for rep in range(control_identity['reps']) for turn in (1, 2, 3)}
        if len(index) != len(rows) or index.keys() != wanted or any(row.get('error') for row in rows):
            raise ValueError('A complete three-turn recording is required')
        if any(not row.get('assistant_message_sha256') or not row.get('messages_sha256')
               for row in rows):
            raise ValueError('Complete input/output hashes are required')
        return index
    previous, current = indexed(control_rows), indexed(candidate_rows)
    drifts = {'input_drift': [], 'output_drift': [], 'token_count_drift': [], 'finish_reason_drift': []}
    for key in sorted(previous):
        left, right = previous[key], current[key]
        label = f'rep{key[0]}/turn{key[1]}'
        for field, kind in (('messages_sha256', 'input_drift'),
                            ('assistant_message_sha256', 'output_drift'),
                            ('finish_reason', 'finish_reason_drift')):
            if left.get(field) != right.get(field):
                drifts[kind].append(label)
        if any(left.get(field) != right.get(field) for field in ('prompt_tokens', 'output_tokens')):
            drifts['token_count_drift'].append(label)
    grades = [row.get('grading') for row in control_rows + candidate_rows]
    graded = all(isinstance(grade, dict) for grade in grades)
    quality = all(grade.get('passed') for grade in grades) if graded else None
    return {'passed': not any(drifts.values()) and quality is not False,
            'passed_output_match': not any(drifts.values()), 'passed_quality': quality,
            'grading_available': graded, 'samples': len(previous), **drifts,
            'comparison_kind': 'actual_assistant_messages_and_prefixes_by_turn_not_full_logits',
            'control_profile_sha256': control_identity.get('profile_sha256'),
            'candidate_profile_sha256': candidate_identity.get('profile_sha256')}


def local_path(path):
    resolved = Path(path).resolve()
    local = (ROOT / 'server/.local').resolve()
    if resolved == local or not resolved.is_relative_to(local):
        raise ValueError('Raw benchmark artifacts must be under server/.local')
    return resolved


def read_recording(path):
    path = local_path(path)
    identity = json.loads((path / 'identity.json').read_bytes())
    summary = json.loads((path / 'summary.json').read_bytes())
    raw = (path / 'samples.jsonl').read_bytes()
    if not summary.get('passed_execution') or sha256(raw) != summary.get('samples_sha256'):
        raise ValueError('Recording did not complete or samples changed')
    return identity, [json.loads(line) for line in raw.decode().splitlines()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    run = subparsers.add_parser('run')
    run.add_argument('--profile', type=Path, required=True)
    run.add_argument('--profile-sha256', required=True)
    run.add_argument('--run-id', required=True)
    run.add_argument('--tokenizer', type=Path, required=True)
    run.add_argument('--tokenizer-sha256', required=True)
    run.add_argument('--mode', choices=('serial', 'speculative'), required=True)
    run.add_argument('--reps', type=int, default=3)
    run.add_argument('--max-tokens', type=int, default=256)
    run.add_argument('--workload', type=Path)
    run.add_argument('--control', type=Path, help='Compare candidate with an existing matched recording')
    run.add_argument('--out', type=Path, required=True)
    compare = subparsers.add_parser('compare')
    compare.add_argument('--control', type=Path, required=True)
    compare.add_argument('--candidate', type=Path, required=True)
    compare.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    output = local_path(args.out)
    if args.command == 'compare':
        control_identity, control_rows = read_recording(args.control)
        candidate_identity, candidate_rows = read_recording(args.candidate)
        result = compare_recordings(control_identity, control_rows, candidate_identity, candidate_rows)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as stream:
            stream.write(json_bytes(result))
        print(json.dumps(result), flush=True)
        return 0 if result['passed'] else 2
    if not 1 <= args.reps <= 3 or not 32 <= args.max_tokens <= 512:
        parser.error('Use 1..3 repetitions and 32..512 output tokens')
    profile_raw, _ = pinned_bytes(args.profile)
    if sha256(profile_raw) != args.profile_sha256:
        raise ValueError('Reviewed profile SHA256 does not match')
    tokenizer, tokenizer_receipt = load_tokenizer(args.tokenizer, args.tokenizer_sha256)
    workload = (load_workload(local_path(args.workload), tokenizer, args.tokenizer_sha256)
                if args.workload else build_workload(ROOT, tokenizer, args.tokenizer_sha256))
    client = RecordingClient(args.profile, args.run_id)
    if client.profile_sha256 != args.profile_sha256 or client.profile['engine']['kind'] != 'halogen':
        raise ValueError('The exact reviewed managed Halogen profile is required')
    if args.mode not in modes_for_profile(client.profile):
        raise ValueError('Selected mode is unavailable in this profile')
    output.mkdir(parents=True, exist_ok=False)
    save_workload(output / 'workload', workload)
    identity = {'schema': 1, 'backend': client.model, 'run_id': args.run_id,
        'profile_sha256': client.profile_sha256, 'profile': client.profile,
        'prompt_cache': profile_cache(client.profile),
        'context_capacity': client.profile['backend']['context'],
        'tokenizer_sha256': args.tokenizer_sha256, 'tokenizer_file': tokenizer_receipt,
        'workload_sha256': sha256(json_bytes(workload['manifest'])),
        'harness_sha256': sha256(Path(__file__).read_bytes() +
            Path(__file__).with_name('reddit_runtime.py').read_bytes() +
            Path(__file__).with_name('reddit_suite.py').read_bytes()),
        'mode': args.mode, 'reps': args.reps, 'max_tokens': args.max_tokens,
        'system_text_tokens': workload['manifest']['system_text_tokens'],
        'route': 'managed gateway /v1/chat/completions',
        'note': 'Root manages cache profiles. Nine measured calls at reps3; no warmup requests.'}
    save_json(output / 'identity.json', identity)
    rows, summary = run_conversations(client, workload, output, tokenizer,
        mode=args.mode, reps=args.reps, max_tokens=args.max_tokens)
    if args.control and summary['passed_execution']:
        control_identity, control_rows = read_recording(args.control)
        summary['comparison'] = compare_recordings(control_identity, control_rows, identity, rows)
        summary['control'] = str(local_path(args.control))
        save_json(output / 'comparison.json', summary['comparison'])
        save_json(output / 'summary.json', summary)
    print('AGENT_BENCH_SUMMARY', json.dumps(summary), flush=True)
    return 0 if summary['passed_execution'] and summary.get('comparison', {}).get('passed', True) else 2


if __name__ == '__main__':
    raise SystemExit(main())
