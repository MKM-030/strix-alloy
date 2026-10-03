"""Disclosed tool-agent analogue; not Pi or the author's exact ten-task run.

Prepare pinned inputs with --work <ignored-workdir> --prepare. The work directory
also needs the article tokenizer.json/corpus.json/vendor and coding-vendor with
pytest 8.4.2 (dependency pins are recorded in the public dataset manifest).
Measurement requires an already-owned ready 131072-capacity gateway; this runner
never starts an engine. All tests run in the already-installed pinned Docker image.
"""
import argparse
import ast
import hashlib
import io
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import urllib.error
import uuid

ROOT = Path(__file__).resolve().parents[2]
HERE = None
REVISION = '7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f'
EXERCISES = ('affine-cipher', 'beer-song', 'book-store', 'bottle-song', 'bowling',
             'connect', 'dominoes', 'dot-dsl', 'food-chain', 'forth')
DATASET = None
GRADER_IMAGE = 'ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a'
GRADER_DISTRO = None
GRADER_USER = None
PUBLIC_MANIFEST = Path(__file__).with_name('polyglot-coding-manifest.json')
sys.path.insert(0, str(ROOT / 'scripts/benchmarks'))
sys.path.insert(0, str(ROOT / 'server'))
from host_frames import frame


class CaseDeadlineExceeded(TimeoutError):
    pass


class ApiDeadlineExceeded(CaseDeadlineExceeded):
    pass


def configure_work(path):
    global HERE, DATASET, GRADER_DISTRO, GRADER_USER
    HERE = path.resolve()
    HERE.mkdir(parents=True, exist_ok=True)
    DATASET = HERE / 'coding-dataset'
    machine = json.loads((ROOT / 'backends/halogen-wsl2-0.16.2/.local/machine.json').read_text())
    if machine['image'] != GRADER_IMAGE:
        raise ValueError('Installed grading image differs from the pinned digest')
    GRADER_DISTRO, GRADER_USER = machine['distro'], machine['user']


def expected_test_ids(exercise, config):
    ids = []
    for name in config['files']['test']:
        tree = ast.parse((DATASET / exercise / name).read_text(encoding='utf-8'))
        stem = Path(name).with_suffix('').as_posix().replace('/', '.')
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                ids.extend(stem + '.' + node.name + '.' + function.name for function in node.body
                    if isinstance(function, ast.FunctionDef) and function.name.startswith('test_'))
            elif isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                ids.append(stem + '.' + node.name)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Invalid official static test identity list')
    return sorted(ids)


def pinned_dependencies():
    public = json.loads(PUBLIC_MANIFEST.read_text(encoding='utf-8'))
    dependencies = {item.metadata['Name']: item.version for item in
                    importlib.metadata.distributions(path=[str(HERE / 'coding-vendor')])}
    if dependencies != public['dependency_pins']:
        raise ValueError('Install the exact public coding-vendor dependency pins before preparation/run')
    save(HERE / 'coding-dependencies.json', dependencies)
    return dependencies


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def prepare():
    pinned_dependencies()
    manifest_path = HERE / 'coding-manifest.json'
    if manifest_path.exists():
        verify_dataset()
        print('Existing pinned dataset verified; no engine requests.')
        return
    url = f'https://codeload.github.com/Aider-AI/polyglot-benchmark/tar.gz/{REVISION}'
    request = urllib.request.Request(url, headers={'User-Agent': 'Strix-Alloy-local-coding-benchmark'})
    with urllib.request.urlopen(request, timeout=60) as response:
        archive = response.read(32 * 1024**2 + 1)
    if len(archive) > 32 * 1024**2:
        raise ValueError('Oversized dataset archive')
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as bundle:
        members = {PurePosixPath(m.name): m for m in bundle if m.isfile()}
        archive_root = next(iter(members)).parts[0]
        for exercise in EXERCISES:
            prefix = PurePosixPath(archive_root, 'python/exercises/practice', exercise)
            config_name = prefix / '.meta/config.json'
            config = json.loads(bundle.extractfile(members[config_name]).read())
            required = set(config['files']['solution'] + config['files']['test'])
            required.add('.meta/config.json')
            required.update(str(path.relative_to(prefix)) for path in members
                            if path.is_relative_to(prefix / '.docs'))
            for relative in sorted(required):
                path = PurePosixPath(relative)
                if path.is_absolute() or '..' in path.parts:
                    raise ValueError('Unsafe dataset path')
                member = members[prefix / path]
                if member.size > 4 * 1024**2:
                    raise ValueError('Oversized exercise file')
                content = bundle.extractfile(member).read()
                destination = DATASET / exercise / Path(*path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open('xb') as output:
                    output.write(content)
                files[f'{exercise}/{relative}'] = sha(content)
    notice_request = urllib.request.Request('https://raw.githubusercontent.com/exercism/python/main/LICENSE',
                         headers={'User-Agent': 'Strix-Alloy-local-coding-benchmark'})
    with urllib.request.urlopen(notice_request, timeout=30) as response:
        license_bytes = response.read()
    (HERE / 'CODING_EXERCISM_LICENSE.txt').write_bytes(license_bytes)
    observed_manifest = {'schema': 1, 'repository': 'Aider-AI/polyglot-benchmark',
        'revision': REVISION, 'archive_url': url, 'archive_sha256': sha(archive),
        'selection': 'First ten Python exercise names in lexical order; author subset unknown',
        'exercises': list(EXERCISES), 'files_sha256': files,
        'license_source': notice_request.full_url, 'license_sha256': sha(license_bytes),
        'runner': 'local read_file/write_file OpenAI tool loop, not pi -p',
        'context_capacity': 131072, 'initial_input_target': 65536,
        'attempts': 2, 'max_agent_calls_per_attempt': 4, 'output_limit_per_call': 4096,
        'grading': 'Pristine official tests and model-edited solution files in a fresh pytest directory',
        'test_visibility': 'Tests and examples withheld from model tools and initial prompt',
        'shell_tool': False, 'pytest': '8.4.2', 'test_timeout_seconds': 180,
        'execution_isolation': 'Docker: network none, read-only root and task/vendor mounts, tmpfs /tmp, '
            'cap-drop ALL, no-new-privileges, nonroot user, 1 CPU, 512 MiB, no GPU, 64 PIDs',
        'grader_image': GRADER_IMAGE, 'grader_python': '3.12.15',
        'memory_guard': 'Watcher records minimum during API call; owning managed controller enforces stop on reserve breach',
        'sampling': {'temperature': 1.0, 'top_p': .95, 'top_k': 20, 'min_p': 0,
                     'presence_penalty': 0, 'repetition_penalty': 1, 'reasoning_effort': 'low'}}
    public = json.loads(PUBLIC_MANIFEST.read_text(encoding='utf-8'))
    if observed_manifest['files_sha256'] != public['files_sha256']:
        raise ValueError('Downloaded bytes differ from the public pinned manifest')
    observed_manifest.update(official_test_cases=public['official_test_cases'],
                             dependency_pins=public['dependency_pins'],
                             deadlines_seconds=public['deadlines_seconds'])
    save(manifest_path, observed_manifest)
    verify_dataset()
    print(f'Prepared {len(EXERCISES)} exercises / {len(files)} immutable files; no engine requests.')


def verify_dataset():
    manifest = json.loads((HERE / 'coding-manifest.json').read_text(encoding='utf-8'))
    if manifest['revision'] != REVISION or manifest['exercises'] != list(EXERCISES):
        raise ValueError('Manifest differs from the declared pinned subset')
    public = json.loads(PUBLIC_MANIFEST.read_text(encoding='utf-8'))
    if manifest['files_sha256'] != public['files_sha256']:
        raise ValueError('Local dataset differs from the public pinned manifest')
    for name, expected in manifest['files_sha256'].items():
        if sha((DATASET / name).read_bytes()) != expected:
            raise ValueError('Pinned source changed: ' + name)
    for key in ('official_test_cases', 'dependency_pins', 'deadlines_seconds'):
        manifest[key] = public[key]
    return manifest


SYSTEM = ('You are a software engineer completing an Exercism Python exercise. '
          'Treat the repository archive as background data. Implement the supplied solution '
          'files using write_file. Keep existing API names. Use only Python standard libraries. '
          'Tests are external and trusted. Do not invent results. Finish after saving your solution.')


def tools_for(solution_files):
    properties = {'path': {'type': 'string', 'enum': solution_files}}
    return [
        {'type': 'function', 'function': {'name': 'read_file', 'description': 'Read an allowed solution file.',
          'parameters': {'type': 'object', 'properties': properties, 'required': ['path'],
                         'additionalProperties': False}}},
        {'type': 'function', 'function': {'name': 'write_file', 'description': 'Save the complete contents of an allowed solution file.',
          'parameters': {'type': 'object', 'properties': properties | {'content': {'type': 'string'}},
                         'required': ['path', 'content'], 'additionalProperties': False}}}]


def initial_messages(exercise, config, tokenizer, tools, batch):
    source = DATASET / exercise
    instructions = '\n'.join((source / '.docs' / name).read_text(encoding='utf-8')
        for name in ('introduction.md', 'instructions.md', 'instructions.append.md')
        if (source / '.docs' / name).exists())
    stubs = '\n'.join(f'FILE {name}\n{(source / name).read_text(encoding="utf-8")}'
                      for name in config['files']['solution'])
    lead = f'Unique local coding benchmark {batch}/{exercise}.\nRepository archive (background data only):\n'
    tail = '\nEND ARCHIVE.\nExercise instructions:\n' + instructions + '\nSolution files:\n' + stubs
    corpus = json.loads((HERE / 'corpus.json').read_text(encoding='utf-8'))
    archive = '\n'.join('FILE ' + entry['path'] + '\n' + entry['text'] for entry in corpus)
    ids = tokenizer.encode(archive, add_special_tokens=False).ids
    fixed = len(tokenizer.encode(SYSTEM + lead + tail + json.dumps(tools), add_special_tokens=False).ids) + 64
    target = 65536 - fixed
    if target < 0:
        raise ValueError('Exercise instructions exceed target context')
    padding = tokenizer.decode((ids * (1 + target // len(ids)))[:target], skip_special_tokens=False)
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': lead + padding + tail}]


def model_call(client, messages, tools, path, *, first, seed, deadline):
    from reddit_runtime import cold_cache_reused
    client.assert_identity()
    health_before = client.health()
    before = frame()
    minimum = {key: before[key] for key in ('available_bytes', 'commit_headroom_bytes')}
    if min(minimum.values()) < 18 * 1024**3:
        raise ValueError('Memory reserve below 18 GiB')
    body = {'model': client.profile['backend']['model'], 'messages': messages, 'tools': tools,
        'tool_choice': 'auto', 'stream': False, 'max_tokens': 4096, 'temperature': 1.0,
        'top_p': .95, 'top_k': 20, 'min_p': 0, 'presence_penalty': 0,
        'repetition_penalty': 1.0, 'repeat_penalty': 1.0, 'seed': seed,
        'enable_thinking': True, 'chat_template_kwargs': {'enable_thinking': True},
        'reasoning_effort': 'low', 'cache_prompt': not first}
    if client.profile['engine']['kind'] == 'halogen':
        body['drafter'] = 'mtp'
    save(path.with_suffix('.request.json'), body)
    done = threading.Event()
    failures = []
    def watch():
        while not done.wait(.2):
            try:
                observation = frame()
                for key in minimum:
                    minimum[key] = min(minimum[key], observation[key])
            except Exception as exc:
                failures.append(str(exc))
                return
    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    started = time.perf_counter()
    budget = min(600, deadline - started)
    if budget <= 0:
        done.set()
        thread.join(timeout=2)
        raise CaseDeadlineExceeded('No time remains for an API call')
    try:
        response = client.request('/v1/chat/completions', body, timeout=budget)
    except (TimeoutError, urllib.error.URLError) as exc:
        if isinstance(exc, urllib.error.URLError) and not isinstance(exc.reason, TimeoutError):
            raise
        save(path.with_suffix('.timeout.json'), {'error': str(exc), 'timeout_seconds': budget})
        raise ApiDeadlineExceeded('API call exceeded its remaining time budget') from exc
    finally:
        wall = time.perf_counter() - started
        done.set()
        thread.join(timeout=2)
        after = frame()
        for key in minimum:
            minimum[key] = min(minimum[key], after[key])
    client.assert_identity()
    if time.perf_counter() > deadline:
        raise CaseDeadlineExceeded('Exercise or suite deadline crossed during API call')
    if failures or min(minimum.values()) < 18 * 1024**3:
        raise ValueError('Memory observation failed or crossed reserve')
    save(path.with_suffix('.response.json'), response)
    usage, timings = response.get('usage', {}), response.get('timings', {})
    count = usage.get('prompt_tokens', timings.get('prompt_n'))
    geometry_ok = type(count) is int and abs(count - 65536) <= 655
    if first and (not geometry_ok or cold_cache_reused(usage, timings)):
        save(path.with_suffix('.invalid.json'), {'prompt_tokens': count, 'geometry_ok': geometry_ok,
                                                'cold_cache_reused': cold_cache_reused(usage, timings)})
        raise ValueError('Initial input geometry/cache is not comparable; results withheld')
    choices = response.get('choices', [])
    finish = choices[0].get('finish_reason') if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
    return response, {'wall_seconds': wall, 'usage': usage, 'timings': timings,
        'requested_output_tokens': 4096, 'finish_reason': finish, 'output_capped': finish == 'length',
        'minimum_memory': minimum, 'health_before': health_before,
        'initial_input_geometry_ok': geometry_ok if first else None}


def require_idle_after_timeout(client):
    deadline = time.perf_counter() + 30
    while time.perf_counter() < deadline:
        client.assert_identity()
        health = client.request('/health', timeout=5)
        if health.get('backend') != client.model:
            raise RuntimeError('Backend changed after a timed-out request')
        if not any(health.get(key, 0) for key in ('active_requests', 'busy', 'in_flight', 'queued')):
            return
        time.sleep(.5)
    raise RuntimeError('Infrastructure error: timed-out API request did not become idle')


def checked_message(response):
    choices = response.get('choices')
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError('Invalid response choices')
    message = choices[0].get('message')
    if not isinstance(message, dict) or message.get('content') is not None and not isinstance(message['content'], str):
        raise ValueError('Invalid assistant message')
    calls = message.get('tool_calls') or []
    if not isinstance(calls, list):
        raise ValueError('Invalid tool-call list')
    ids = []
    for call in calls:
        if (not isinstance(call, dict) or not isinstance(call.get('id'), str) or not call['id']
                or call.get('type', 'function') != 'function' or not isinstance(call.get('function'), dict)
                or not isinstance(call['function'].get('name'), str)
                or not isinstance(call['function'].get('arguments'), str)):
            raise ValueError('Malformed tool-call payload')
        ids.append(call['id'])
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate tool-call identity')
    return dict(message, role='assistant'), calls


def grade(exercise, config, solution_dir, case_dir, attempt, *, deadline=None):
    manifest = verify_dataset()
    source = DATASET / exercise
    grade_dir = case_dir / f'grade-{attempt}'
    grade_dir.mkdir()
    for name in config['files']['test'] + config['files']['solution']:
        destination = grade_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        origin = source / name if name in config['files']['test'] else solution_dir / name
        shutil.copyfile(origin, destination)
    # Import pytest before making model-written code importable. No plugin discovery.
    bootstrap = ('import sys,json,xml.etree.ElementTree as ET;'
                 'sys.path.insert(0,sys.argv[1]);import pytest;sys.path.insert(0,sys.argv[2]);'
                 'code=pytest.main(sys.argv[3:]+["--junitxml=/tmp/grading.xml"]);'
                 'tree=ET.parse("/tmp/grading.xml");'
                 'cases=[{"id":e.get("classname","")+"."+e.get("name",""),'
                 '"bad":any(c.tag in ("failure","error","skipped") for c in e)} '
                 'for e in tree.iter("testcase")];'
                 'print("STRIX_TRUSTED_JUNIT:"+json.dumps(cases));raise SystemExit(code)')
    def wsl_path(path):
        path = path.resolve()
        if not re.fullmatch(r'[a-zA-Z]:', path.drive):
            raise ValueError('Grader requires a local Windows drive path')
        return '/mnt/' + path.drive[0].lower() + '/' + '/'.join(path.parts[1:])
    owned = 'strix-coding-' + uuid.uuid4().hex
    cid_file = case_dir / f'grader-{attempt}.cid'
    docker = ['wsl.exe', '-d', GRADER_DISTRO, '-u', GRADER_USER, '--', 'docker']
    command = docker + ['run', '--rm', '--pull=never', '--name', owned,
        '--label', 'strix.coding-grader=' + owned, '--cidfile', wsl_path(cid_file),
        '--network', 'none', '--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--user', '65534:65534',
        '--cpus', '1', '--memory', '512m', '--memory-swap', '512m', '--pids-limit', '64',
        '--mount', f'type=bind,src={wsl_path(grade_dir)},dst=/task,readonly',
        '--mount', f'type=bind,src={wsl_path(HERE / "coding-vendor")},dst=/vendor,readonly',
        '--workdir', '/task', '--env', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD=1',
        '--entrypoint', '/usr/local/bin/python3', GRADER_IMAGE,
        '-I', '-B', '-c', bootstrap, '/vendor', '/task',
        '-q', '--disable-warnings', '-p', 'no:cacheprovider', *config['files']['test']]
    save(case_dir / f'grader-{attempt}-command.json', {'command': command, 'image': GRADER_IMAGE,
                                                   'expected_nonroot': '65534:65534'})
    started = time.perf_counter()
    budget = min(180, deadline-started) if deadline is not None else 180
    if budget <= 0:
        raise CaseDeadlineExceeded('No time remains to grade this exercise')
    try:
        result = subprocess.run(command, cwd=case_dir, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', timeout=budget)
        code, output = result.returncode, result.stdout
    except subprocess.TimeoutExpired as exc:
        code, output = None, f'Tests timed out after {budget:.1f} seconds.\n' + str(exc.stdout or '')
        if cid_file.exists():
            cid = cid_file.read_text(encoding='ascii').strip()
            if not re.fullmatch(r'[0-9a-f]{64}', cid):
                raise ValueError('Invalid owned grader container id')
            inspection = subprocess.run(docker + ['inspect', '--format', '{{json .Config.Labels}}', cid],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
            if inspection.returncode == 0:
                labels = json.loads(inspection.stdout)
                if labels.get('strix.coding-grader') != owned:
                    raise ValueError('Cannot prove grader container ownership')
                subprocess.run(docker + ['rm', '-f', cid], check=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=15)
            elif 'No such' not in inspection.stderr:
                raise RuntimeError('Cannot verify cleanup of the owned grader container')
        else:
            # Without a cidfile the client may have been interrupted during run
            # creation. Inspect only our retained unique name before cleanup.
            inspection = subprocess.run(docker + ['inspect', '--format', '{{json .Config.Labels}}', owned],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
            if inspection.returncode == 0:
                if json.loads(inspection.stdout).get('strix.coding-grader') != owned:
                    raise ValueError('Cannot prove grader container ownership')
                subprocess.run(docker + ['rm', '-f', owned], check=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=15)
            elif 'No such' not in inspection.stderr:
                raise RuntimeError('Cannot verify cleanup of the owned grader container')
    (case_dir / f'pytest-{attempt}.txt').write_text(output, encoding='utf-8')
    if code in (125, 126, 127):
        raise RuntimeError('Docker grading infrastructure failed; no coding score available')
    expected = expected_test_ids(exercise, config)
    if len(expected) != manifest['official_test_cases'][exercise]:
        raise ValueError('Official static test count differs from public manifest')
    records = re.findall(r'^STRIX_TRUSTED_JUNIT:(.*)$', output, re.MULTILINE)
    try:
        observed = json.loads(records[-1]) if len(records) == 1 else []
        actual = [item['id'] for item in observed]
        all_tests_ran = len(actual) == len(expected) and sorted(actual) == expected
        exceptional_summary = bool(re.search(r'\b[0-9]+ (?:skipped|deselected|xfailed|xpassed|errors?)\b', output))
        passed = code == 0 and all_tests_ran and not exceptional_summary and not any(item['bad'] for item in observed)
    except (ValueError, KeyError, TypeError):
        observed, all_tests_ran, passed = [], False, False
    integrity = all(sha((grade_dir / name).read_bytes()) == manifest['files_sha256'][exercise + '/' + name]
                    for name in config['files']['test'])
    verify_dataset()
    return {'passed': passed and integrity, 'returncode': code, 'test_integrity': integrity,
            'expected_test_count': len(expected), 'observed_test_count': len(observed),
            'all_official_tests_ran': all_tests_ran, 'test_records': observed,
            'wall_seconds': time.perf_counter() - started, 'output': output,
            'solution_sha256': {name: sha((solution_dir / name).read_bytes()) for name in config['files']['solution']}}


def run_case(client, exercise, index, output_dir, tokenizer, suite_deadline):
    case_started = time.perf_counter()
    case_deadline = min(case_started + 1200, suite_deadline)
    case_dir = output_dir / exercise
    solution_dir = case_dir / 'solution'
    solution_dir.mkdir(parents=True)
    config = json.loads((DATASET / exercise / '.meta/config.json').read_text(encoding='utf-8'))
    allowed = config['files']['solution']
    for name in allowed:
        destination = solution_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DATASET / exercise / name, destination)
    tools = tools_for(allowed)
    messages = initial_messages(exercise, config, tokenizer, tools, output_dir.name)
    row = {'exercise': exercise, 'attempts': [], 'calls': [], 'tool_events': [],
           'agent_errors': [], 'first_pass': False, 'passed': False, 'status': 'running'}
    first, writes = True, 0
    try:
        for attempt in range(1, 3):
            malformed = False
            for turn in range(4):
                if time.perf_counter() >= case_deadline:
                    raise CaseDeadlineExceeded('Exercise or suite deadline reached between API calls')
                label = case_dir / f'attempt{attempt}-call{turn}'
                response, metrics = model_call(client, messages, tools, label, first=first,
                                               seed=20261003 + index, deadline=case_deadline)
                row['calls'].append(metrics)
                first = False
                try:
                    message, tool_calls = checked_message(response)
                except ValueError as exc:
                    row['agent_errors'].append({'attempt': attempt, 'turn': turn, 'error': str(exc)})
                    malformed = True
                    break
                messages.append(message)
                if not tool_calls:
                    break
                for call in tool_calls:
                    function = call['function']
                    name = function['name']
                    try:
                        value = json.loads(function['arguments'])
                        path_name = value['path']
                        if path_name not in allowed:
                            raise ValueError('Path is not an allowed solution file')
                        target = (solution_dir / path_name).resolve()
                        if not target.is_relative_to(solution_dir.resolve()):
                            raise ValueError('Path escaped the solution directory')
                        if name == 'read_file':
                            tool_result = target.read_text(encoding='utf-8')
                        elif name == 'write_file':
                            content = value['content']
                            if not isinstance(content, str) or len(content) > 100000:
                                raise ValueError('Invalid or oversized file contents')
                            target.write_text(content, encoding='utf-8')
                            writes += 1
                            tool_result = 'Saved ' + path_name
                        else:
                            raise ValueError('Unknown tool')
                        ok = True
                    except (ValueError, KeyError, TypeError, OSError) as exc:
                        tool_result, ok = 'Tool error: ' + str(exc), False
                    row['tool_events'].append({'attempt': attempt, 'turn': turn, 'name': name,
                        'ok': ok, 'result_sha256': sha(tool_result.encode('utf-8'))})
                    messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': tool_result})
            result = grade(exercise, config, solution_dir, case_dir, attempt, deadline=case_deadline)
            result['passed'] = result['passed'] and writes > 0 and not malformed
            result['write_calls_so_far'], result['malformed_agent_response'] = writes, malformed
            row['attempts'].append(result)
            if attempt == 1:
                row['first_pass'] = result['passed']
            if result['passed']:
                break
            messages.append({'role': 'user', 'content': 'Trusted test results:\n' + result['output'][:12000] +
                '\nTests are correct. Fix only the allowed solution files using write_file.'})
        row.update(passed=row['attempts'][-1]['passed'], status='graded')
    except ApiDeadlineExceeded as exc:
        row.update(status='infrastructure_error', error=str(exc))
        # Closing the timed-out HTTP client is not sufficient proof that every
        # upstream engine has cancelled generation. Do not send another request.
        require_idle_after_timeout(client)
        raise RuntimeError('Infrastructure error: API request timed out; remaining suite cancelled') from exc
    except CaseDeadlineExceeded as exc:
        require_idle_after_timeout(client)
        row.update(status='case_deadline', error=str(exc))
    except Exception as exc:
        row.update(status='infrastructure_error', error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        row['wall_seconds'] = time.perf_counter() - case_started
        save(case_dir / 'result.json', row)
    return row


def run(args):
    from reddit_runtime import ManagedClient
    manifest = verify_dataset()
    dependencies = pinned_dependencies()
    if args.profile is None or not args.run_id or not args.out:
        raise ValueError('--profile, --run-id and --out are required for a measured run')
    client = ManagedClient(args.profile, args.run_id)
    if client.profile['backend']['context'] != 131072:
        raise ValueError('Coding suite requires capacity 131072')
    sys.path.insert(0, str(HERE / 'vendor'))
    from tokenizers import Tokenizer
    tokenizer = Tokenizer.from_file(str(HERE / 'tokenizer.json'))
    output_dir = args.out.resolve()
    if not output_dir.is_relative_to(HERE):
        raise ValueError('Results must be in the ignored article scratch directory')
    output_dir.mkdir(exist_ok=False)
    save(output_dir / 'manifest.json', manifest)
    rows, started = [], time.perf_counter()
    suite_deadline = started + 7200
    summary = {'runner': manifest['runner'], 'exact_author_replication': False,
               'backend': client.model,
               'completed': False, 'profile_sha256': client.profile_sha256, 'run_id': args.run_id,
               'runner_sha256': sha(Path(__file__).read_bytes()),
               'runner_source': 'scripts/benchmarks/polyglot_tool_bench.py', 'suite_revision': 'polyglot-tool-v1',
               'public_manifest_sha256': sha(PUBLIC_MANIFEST.read_bytes()),
               'dataset_manifest_sha256': sha((HERE / 'coding-manifest.json').read_bytes()),
               'tokenizer_sha256': sha((HERE / 'tokenizer.json').read_bytes()),
               'corpus_sha256': sha((HERE / 'corpus.json').read_bytes()),
               'grader_dependencies': dependencies,
               'grading_isolation': manifest['execution_isolation'], 'grader_image': GRADER_IMAGE,
               'deadlines_seconds': {'api_call': 600, 'exercise': 1200, 'suite': 7200},
               'context': 131072, 'target_initial_input': 65536, 'exercises': list(EXERCISES), 'rows': rows}
    try:
        for index, exercise in enumerate(EXERCISES):
            if time.perf_counter() >= suite_deadline:
                raise TimeoutError('Engine suite deadline reached; partial results retained')
            client.assert_identity()
            row = run_case(client, exercise, index, output_dir, tokenizer, suite_deadline)
            rows.append(row)
            save(output_dir / 'summary.json', summary | {'wall_seconds': time.perf_counter()-started})
            print(f"CODING {exercise} first={row['first_pass']} final={row['passed']} seconds={row['wall_seconds']:.1f}", flush=True)
        summary.update(completed=True, first_pass=sum(row['first_pass'] for row in rows),
                       passed=sum(row['passed'] for row in rows), total=len(rows))
    except Exception as exc:
        case_result = output_dir / exercise / 'result.json'
        if case_result.exists() and (not rows or rows[-1]['exercise'] != exercise):
            rows.append(json.loads(case_result.read_text(encoding='utf-8')))
        summary['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        summary['wall_seconds'] = time.perf_counter() - started
        save(output_dir / 'summary.json', summary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--out', type=Path)
    arguments = parser.parse_args()
    configure_work(arguments.work)
    if arguments.prepare:
        prepare()
    else:
        run(arguments)
