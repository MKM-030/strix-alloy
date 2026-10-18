"""Private, finite replay of GUFO's frozen Reddit HTTP rows on Halogen.

This module never starts Halogen. The supervising PowerShell controller owns the
single container and invokes ``replay`` only after both guards have handed off.
``validate`` is strictly offline and cannot contact WSL or an HTTP endpoint.
"""
import argparse
import base64
import hashlib
import http.client
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

from . import reddit_native_run as native

ROOT = Path(r'C:\Projects\strix-alloy-research')
LIMIT = 4 << 20
RESPONSE_LIMIT = 1 << 20
CONTEXT = 133888  # Halogen requires KV pool alignment to 256 positions.
REQUEST_SECONDS = 1800
TABLE_SECONDS = 3600
MODEL = 'qwen38-flash-next-w4b'
HERE = Path(__file__).resolve().parent
FILES = (HERE/'reddit_halogen_client.py', HERE/'reddit_halogen_run.ps1',
         HERE/'reddit_halogen_controller.ps1', HERE/'wait-lookup-runtime-guard.ps1',
         HERE/'reddit_halogen_sample.ps1', HERE/'reddit_halogen_host_guard.py',
         HERE/'reddit_halogen_startup_guard.py',
         Path(r'C:\Projects\strix-alloy-wsl2\scripts\guard-halogen-startup.py'),
         Path(r'C:\Projects\strix-alloy-wsl2\profiles\qualified-profile.json'),
         Path(r'C:\Projects\strix-alloy-wsl2\profiles\environment.json'))
API = Path(r'C:\Users\Marcel\Documents\Codex\2026-08-25\goal-ermittle-und-implementiere-auf-meinem\results\preflight-20260925\dual-decode-serve_api.py')
API_SHA = '97019CC97CDAD6F21F0ABE795527DE740422F94B81324FFEE27F237DD1DCC572'
HISTORICAL = Path(r'C:\Users\Marcel\Documents\Codex\2026-08-25\goal-ermittle-und-implementiere-auf-meinem\results\halogen-performance-20260924\publication-repeat3-inspect.json')


def digest(value):
    return hashlib.sha256(value).hexdigest().upper()


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def load_source(path, table):
    path = Path(path).resolve(strict=True)
    expected = ROOT/'reports'/f'reddit-native-{table}-20260928-v1-runs'
    if path.name != 'result.json' or path.parent.parent != expected:
        raise ValueError('unbound_native_source_path')
    result = json.loads(path.read_text(encoding='utf-8'))
    if result.get('table') != table or result.get('cleanup_confirmed') is not True:
        raise ValueError('native_source_not_clean')
    http = result.get('http')
    if not isinstance(http, dict):
        raise ValueError('native_http_missing')
    rows = http.get('requests')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 15:
        raise ValueError('native_request_count_invalid')
    seen = []
    for row in rows:
        body = base64.b64decode(row['request_body_base64'], validate=True)
        if len(body) > LIMIT or digest(body) != row['request_sha256']:
            raise ValueError('native_wire_hash_invalid')
        source = json.loads(body.decode('utf-8'))
        if source != row['request'] or source.get('model') != native.smoke_http.MODEL:
            raise ValueError('native_decoded_request_disagrees')
        messages = source.get('messages')
        if not isinstance(messages, list) or not 1 <= len(messages) <= 3:
            raise ValueError('native_messages_invalid')
        semantic = digest(packed(messages))
        if row.get('frozen_messages_sha256') and row['frozen_messages_sha256'] != semantic:
            raise ValueError('native_semantic_hash_invalid')
        if source.get('temperature') != 0 or source.get('max_tokens') not in (1, 8, 16, 128):
            raise ValueError('native_sampler_or_budget_changed')
        seen.append((row, source, semantic))
    labels = [r['label'] for r, _, _ in seen]
    if labels != list(dict.fromkeys(labels)) or labels[:min(3,len(labels))] != ['calibration-hi', 'calibration-3000', 'warmup'][:min(3,len(labels))]:
        raise ValueError('native_order_invalid')
    for i, (row, source, _) in enumerate(seen):
        label = row['label']
        if i >= 3 and not re.fullmatch(r'd(?:0|131072)-a[0-3]-(?:prefix|measured)', label):
            raise ValueError('native_label_outside_frozen_workload')
        if label.endswith('-prefix') and (not label.startswith('d131072-') or source['max_tokens'] != 8 or source['stream'] is not False):
            raise ValueError('native_prefix_shape_invalid')
        if label.endswith('-measured') and (source['max_tokens'] != 128 or source['stream'] is not True):
            raise ValueError('native_measured_shape_invalid')
        if label.endswith('-measured') and label.startswith('d131072-'):
            if i == 0 or seen[i-1][0]['label'] != label.replace('-measured', '-prefix'):
                raise ValueError('prefix_not_immediately_before_measurement')
            if source['messages'][1]['content'] != seen[i-1][0]['parsed']['visible_answer']:
                raise ValueError('gufo_prefix_reply_not_frozen')
    cells = http.get('cells') or {}
    accepted = {}
    for depth, cell in cells.items():
        if cell.get('status') == 'accepted':
            index = cell.get('request_index')
            if type(index) is not int or not 0 <= index < len(seen) or not seen[index][0]['label'].endswith('-measured'):
                raise ValueError('native_accepted_cell_index_invalid')
            if seen[index][2] != cell.get('frozen_messages_sha256'):
                raise ValueError('native_accepted_cell_hash_invalid')
            accepted[depth] = index
    return result, seen, path, accepted


def translated(source, health_model):
    request = dict(model=health_model, messages=source['messages'],
                   max_tokens=source['max_tokens'], temperature=0,
                   stream=source['stream'], enable_thinking=False)
    if source['stream']:
        request['stream_options'] = {'include_usage': True}
    return request, packed(request)


def binding(source_path, table):
    _, rows, path, accepted = load_source(source_path, table)
    if digest(API.read_bytes()) != API_SHA:
        raise ValueError('pinned_halogen_api_changed')
    reference = json.loads(HISTORICAL.read_text(encoding='utf-8'))[0]
    qualified = json.loads((Path(r'C:\Projects\strix-alloy-wsl2\profiles\qualified-profile.json')).read_text(encoding='utf-8'))
    public_env = json.loads((Path(r'C:\Projects\strix-alloy-wsl2\profiles\environment.json')).read_text(encoding='utf-8'))
    env = reference['Config']['Env']
    pairs = [entry.split('=', 1) for entry in env]
    if any(len(pair) != 2 for pair in pairs) or len(pairs) != len({pair[0] for pair in pairs}):
        raise ValueError('historical_environment_duplicate_or_invalid')
    old = dict(pairs)
    new = dict(entry.split('=', 1) for entry in public_env['environment'])
    if (reference['Config']['Image'] != public_env['image'] or
            old.get('HALOGEN_TOKENIZER') != '/models/tokenizer' or
            old.get('HALOGEN_CHECKPOINT') != '/models/qwen38-flash-next-w4b.hgn' or
            any(old.get(key) != value for key, value in new.items()
                if key not in ('LD_PRELOAD', 'HALOGEN_HYBRID_COPY_BYTES',
                               'HALOGEN_HYBRID_PROFILE', 'HALOGEN_PREFLIGHT_PROFILE',
                               'HALOGEN_PREFLIGHT_TRACE_ONLY')) or
            set(old) - set(new) or
            [(f['name'], f['bytes'], f['sha256']) for f in qualified['modelFiles']] != [
                ('qwen38-flash-next-w4b.hgn', 124068083904,
                 '9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6'),
                ('qwen38-flash-next-w4b.overlay.hgn', 2572466560,
                 '1cdfc3a9f988955bfe9a71bb808d393030abbf9f99d34ffa1ef93815a49b39ab')]):
        raise ValueError('historical_environment_or_model_selection_changed')
    value = dict(schema='reddit-halogen-review-binding-v1', table=table,
                 source=str(path), source_sha256=digest(path.read_bytes()),
                 request_labels=[r['label'] for r, _, _ in rows], accepted_indices=accepted,
                 files={str(file): digest(file.read_bytes()) for file in (*FILES, API, HISTORICAL)},
                 allocation=dict(context=CONTEXT, slots=1, cache_mode=2, cache_entries=3,
                                 cache_snap3=0, cache_full=0, runtime_floor_gib=12,
                                 commit_floor_gib=12, reviewed_min_admission_gib=51.25,
                                 min_planned_commit_growth_gib=86))
    return digest(packed(value)), value


def exchange(method, path, payload=None, timeout=15):
    connection = http.client.HTTPConnection('127.0.0.1', 8731, timeout=timeout)
    began = time.monotonic()
    deadline = began + timeout
    try:
        connection.request(method, path, body=payload,
                           headers={'Content-Type': 'application/json'} if payload is not None else {})
        response = connection.getresponse()
        reader_socket = getattr(getattr(response.fp, 'raw', None), '_sock', None) or connection.sock
        if reader_socket is None:
            raise ValueError('response_socket_unavailable')
        chunks = []
        count = 0
        while not response.isclosed():
            left = deadline-time.monotonic()
            if left <= 0:
                raise TimeoutError('request_deadline')
            # Buffered HTTP readers cannot be reused after a socket timeout.
            # Wait only to the existing absolute deadline; the independent host
            # guard keeps sampling and can stop the owned container meanwhile.
            reader_socket.settimeout(left)
            try:
                part = response.read1(min(65536, RESPONSE_LIMIT+1-count))
            except socket.timeout as error:
                raise TimeoutError('request_deadline') from error
            if not part:
                break
            count += len(part)
            if count > RESPONSE_LIMIT:
                raise ValueError('response_body_limit')
            chunks.append(part)
        raw = b''.join(chunks)
        ended = time.monotonic()
        if len(raw) > RESPONSE_LIMIT:
            raise ValueError('response_body_limit')
        return response.status, dict(response.getheaders()), raw, began, ended
    finally:
        connection.close()


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, entry in items:
            if key in value:
                raise ValueError('duplicate_json_key')
            value[key] = entry
        return value
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)


def decode_completion(raw, streaming):
    if not streaming:
        return strict_json(raw)
    chunks = []
    for line in raw.splitlines():
        if line.startswith(b'data: '):
            data = line[6:]
            if data != b'[DONE]':
                chunks.append(strict_json(data))
    if not chunks:
        raise ValueError('empty_stream')
    usage = next((c['usage'] for c in reversed(chunks) if isinstance(c.get('usage'), dict)), None)
    timings = next((c['timings'] for c in reversed(chunks) if isinstance(c.get('timings'), dict)), None)
    reason = next((c['choices'][0]['finish_reason'] for c in reversed(chunks)
                   if c.get('choices') and c['choices'][0].get('finish_reason')), None)
    answer = ''.join(c['choices'][0].get('delta', {}).get('content') or ''
                     for c in chunks if c.get('choices'))
    return dict(usage=usage, timings=timings, choices=[dict(message=dict(content=answer),
                                                          finish_reason=reason)],
                model=chunks[-1].get('model'))


TOKENIZER_CODE = r'''import hashlib,json,sys
from transformers import AutoTokenizer
msg=json.load(sys.stdin)
tok=AutoTokenizer.from_pretrained('/models/tokenizer',local_files_only=True,use_fast=True)
rendered=tok.apply_chat_template(msg,tokenize=False,add_generation_prompt=True,enable_thinking=False)
ids=tok(rendered,add_special_tokens=False,return_offsets_mapping=True)['input_ids']
print(json.dumps({'tokens':len(ids),'rendered_sha256':hashlib.sha256(rendered.encode('utf-8')).hexdigest().upper()}))'''


def count_prompt(container, messages):
    # Only the pinned tokenizer/template is loaded; no checkpoint or second engine.
    command = ['wsl.exe', '-d', 'Ubuntu-24.04', '-u', 'revn', '--exec',
               'docker', 'exec', '-i', container, 'timeout', '--signal=TERM',
               '--kill-after=5s', '75s', 'python', '-c', TOKENIZER_CODE]
    proc = subprocess.run(command, input=packed(messages), capture_output=True,
                          timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
    if proc.returncode or len(proc.stdout) > 4096 or len(proc.stderr) > 8192:
        raise ValueError('bounded_tokenizer_failed')
    value = strict_json(proc.stdout)
    if type(value.get('tokens')) is not int or value['tokens'] < 1 or not isinstance(value.get('rendered_sha256'), str):
        raise ValueError('tokenizer_count_invalid')
    return value


def replay(source_path, table, container, output):
    result, rows, path, accepted = load_source(source_path, table)
    output = Path(output)
    if output.exists():
        raise ValueError('attempt_output_exists')
    record = dict(schema='reddit-halogen-replay-v1', table=table, source=str(path),
                  source_sha256=digest(path.read_bytes()), success=False,
                  requests=[], cells={}, health=None, cache_before=None,
                  cache_after=None, health_after=None, candidate_success=False,
                  ledger_audit='pending', error=None)
    started = time.monotonic()
    pair_before = {}
    try:
        status, _, raw, _, _ = exchange('GET', '/health')
        health = strict_json(raw)
        record['health'] = health
        model = health.get('model')
        if status != 200 or health.get('status') != 'ok' or health.get('capability_probe') != 'ok' or not model:
            raise ValueError('health_not_ready')
        template = health.get('chat_template') or {}
        if (health.get('context') != CONTEXT or health.get('slots') != 1 or
                health.get('slot_ctx') != CONTEXT or health.get('kv_pool_positions') != CONTEXT or
                health.get('max_tokens_cap', 0) < 128 or health.get('checkpoint_format') != 'hgn' or
                template.get('probe') != 'passed' or template.get('thinking_control') is not True or
                not template.get('sha256') or health.get('prompt_cache', {}).get('mode') != 2):
            raise ValueError('effective_capacity_or_cache_mode_invalid')
        status, _, raw, _, _ = exchange('GET', '/cache')
        cache = strict_json(raw)
        record['cache_before'] = cache
        if status != 200 or cache.get('max_entries') != 3:
            raise ValueError('cache_entry_count_invalid')
        for source_index, (original, source, semantic) in enumerate(rows):
            if time.monotonic()-started >= TABLE_SECONDS:
                raise TimeoutError('table_deadline')
            label = original['label']
            request, body = translated(source, model)
            if len(body) > LIMIT:
                raise ValueError('translated_request_limit')
            row = dict(label=label, native_request_sha256=original['request_sha256'],
                       source_index=source_index,
                       semantic_messages_sha256=semantic, request=request,
                       request_body_base64=base64.b64encode(body).decode('ascii'),
                       wire_request_sha256=digest(body), response_status=None,
                       raw_response_base64=None, response_sha256=None, parsed=None,
                       token_count=None, error=None, success=False)
            record['requests'].append(row)
            if label.endswith('-prefix') or label.startswith('d0-') and label.endswith('-measured'):
                c_status, _, c_raw, _, _ = exchange('GET', '/cache')
                if c_status != 200:
                    raise ValueError('pair_cache_before_unavailable')
                pair_before[label.replace('-prefix', '-measured')] = strict_json(c_raw)
            if label.startswith('d131072-') and label.endswith('-measured'):
                count = count_prompt(container, source['messages'])
                row['token_count'] = count
                if count['tokens']+source['max_tokens'] > CONTEXT:
                    row['error'] = 'actual_hgn_capacity_exceeded'
                    raise ValueError(row['error'])
            try:
                status, headers, raw, began, ended = exchange('POST', '/v1/chat/completions',
                    body, timeout=min(REQUEST_SECONDS, max(1, TABLE_SECONDS-(time.monotonic()-started))))
                row.update(response_status=status, response_headers=headers,
                           raw_response_base64=base64.b64encode(raw).decode('ascii'),
                           response_sha256=digest(raw), wall_ms=(ended-began)*1000)
                if status != 200:
                    raise ValueError('http_status_'+str(status))
                parsed = decode_completion(raw, source['stream'])
                row['parsed'] = parsed
                if parsed.get('model') not in (None, model) or parsed['choices'][0].get('finish_reason') not in ('stop', 'length'):
                    raise ValueError('completion_identity_or_finish_invalid')
                usage, timings = parsed.get('usage'), parsed.get('timings')
                if not isinstance(usage, dict) or not isinstance(timings, dict):
                    raise ValueError('missing_usage_or_timings')
                cached = usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)
                fresh = timings.get('prompt_n')
                if cached != timings.get('cache_n') or usage.get('prompt_tokens') != cached+fresh:
                    raise ValueError('cache_ledger_disagrees')
                if timings.get('predicted_n') != usage.get('completion_tokens'):
                    raise ValueError('output_ledger_disagrees')
                row['counts'] = dict(cache_n=cached, prompt_n=fresh,
                                     predicted_n=timings['predicted_n'])
                row['pp_tps'] = fresh*1000/timings['prompt_ms'] if timings.get('prompt_ms', 0) > 0 else None
                row['tg_tps'] = timings['predicted_n']*1000/timings['predicted_ms'] if timings.get('predicted_ms', 0) > 0 else None
                if label.endswith('-measured'):
                    depth = 131072 if label.startswith('d131072-') else 0
                    errors = []
                    if (cached != 0 if depth == 0 else abs(cached-depth) > max(32, int(depth*.005))):
                        errors.append('cache_outside_tolerance')
                    if abs(fresh-2048) > max(32, int(2048*.005)):
                        errors.append('prefill_outside_tolerance')
                    if timings['predicted_n'] != 128:
                        errors.append('output_count_invalid')
                    if row['pp_tps'] is None or row['tg_tps'] is None:
                        errors.append('engine_timing_invalid')
                    row['cell_validation_errors'] = errors
                    row['native_accepted_cell'] = accepted.get(str(depth)) == source_index
                    before = pair_before.get(label)
                    c_status, _, c_raw, _, _ = exchange('GET', '/cache')
                    if before is None or c_status != 200:
                        raise ValueError('pair_cache_evidence_missing')
                    after = strict_json(c_raw)
                    row['cache_pair'] = dict(before=before, after=after,
                        evicted_delta=after.get('evicted', 0)-before.get('evicted', 0),
                        bytes_after=after.get('bytes'))
                    if after.get('max_entries') != 3 or row['cache_pair']['evicted_delta'] < 0:
                        errors.append('cache_pair_counters_invalid')
                    if row['native_accepted_cell']:
                        record['cells'][str(depth)] = dict(label=label, source_index=source_index,
                            errors=errors, candidate=not errors, comparable=False,
                            ledger_audit='pending')
                row['success'] = True
            except Exception as error:
                row['error'] = type(error).__name__+':'+str(error)
                if row['raw_response_base64'] is None:
                    row['raw_response_omission_reason'] = 'transport_failed_before_complete_body'
                raise
        status, _, raw, _, _ = exchange('GET', '/cache')
        record['cache_after'] = strict_json(raw)
        if status != 200 or record['cache_after'].get('max_entries') != 3:
            raise ValueError('terminal_cache_invalid')
        record['candidate_success'] = all(c['candidate'] for c in record['cells'].values()) and set(record['cells']) == {'0', '131072'}
    except BaseException as error:
        record['error'] = type(error).__name__+':'+str(error)
    finally:
        if record['cache_after'] is None:
            try:
                status, _, raw, _, _ = exchange('GET', '/cache', timeout=15)
                if status == 200:
                    record['cache_after'] = strict_json(raw)
            except Exception as error:
                record['cache_after_error'] = type(error).__name__+':'+str(error)
        try:
            status, _, raw, _, _ = exchange('GET', '/health', timeout=15)
            if status == 200:
                record['health_after'] = strict_json(raw)
        except Exception as error:
            record['health_after_error'] = type(error).__name__+':'+str(error)
        record['elapsed_seconds'] = time.monotonic()-started
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return 0 if record['candidate_success'] else 1


LEDGER = re.compile(r'serve_api: .*? (\d+) tok in .*?\| .*?prompt (\d+)'
                    r'(?: \((\d+) cached(?:, [^)]*)?\))?, prefill ([\d.]+)s')


def audit(source_path, table, replay_path, log_path, output):
    _, _, source, accepted = load_source(source_path, table)
    run = json.loads(Path(replay_path).read_text(encoding='utf-8'))
    verdict = dict(schema='reddit-halogen-ledger-audit-v1', table=table,
                   source=str(source), replay=str(replay_path), log=str(log_path),
                   success=False, rows=[], errors=[])
    if (run.get('source_sha256') != digest(source.read_bytes()) or
            run.get('candidate_success') is not True or
            len(run.get('requests', [])) == 0):
        verdict['errors'].append('replay_candidate_or_source_invalid')
    ledger = []
    with Path(log_path).open(encoding='utf-8', errors='replace') as stream:
        for line in stream:
            if len(line) > 16384:
                verdict['errors'].append('oversized_ledger_line')
                continue
            match = LEDGER.search(line)
            if match:
                ledger.append(dict(output=int(match[1]), prompt=int(match[2]),
                                   cached=int(match[3] or 0), prefill_seconds=float(match[4])))
                if len(ledger) > 15:
                    verdict['errors'].append('too_many_ledger_rows')
                    break
    completed = [r for r in run.get('requests', []) if r.get('success')]
    if len(ledger) != len(completed) or len(completed) != len(run.get('requests', [])):
        verdict['errors'].append('ledger_request_count_mismatch')
    for index, (row, entry) in enumerate(zip(completed, ledger)):
        timing = row['parsed']['timings']
        usage = row['parsed']['usage']
        errors = []
        if (entry['output'] != timing.get('predicted_n') or
                entry['prompt'] != usage.get('prompt_tokens') or
                entry['cached'] != timing.get('cache_n') or
                entry['prompt']-entry['cached'] != timing.get('prompt_n')):
            errors.append('serving_ledger_counts_disagree')
        if abs(entry['prefill_seconds']*1000-timing.get('prompt_ms', -1)) > 15:
            errors.append('serving_ledger_prefill_time_disagrees')
        verdict['rows'].append(dict(index=index, label=row['label'], ledger=entry,
                                    counts=row.get('counts'), errors=errors))
        verdict['errors'].extend(f'{row["label"]}:{error}' for error in errors)
    for depth, index in accepted.items():
        cell = run.get('cells', {}).get(depth)
        if (cell is None or cell.get('source_index') != index or
                cell.get('candidate') is not True or index >= len(verdict['rows']) or
                verdict['rows'][index]['errors']):
            verdict['errors'].append(f'accepted_cell_not_audited:{depth}')
    verdict['success'] = not verdict['errors']
    verdict['cells'] = {depth: dict(source_index=index, comparable=verdict['success'])
                        for depth, index in accepted.items()}
    Path(output).write_text(json.dumps(verdict, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return 0 if verdict['success'] else 1


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=('validate', 'replay', 'audit'))
    p.add_argument('--table', required=True, choices=tuple(native.TABLES))
    p.add_argument('--source', required=True)
    p.add_argument('--container')
    p.add_argument('--output')
    p.add_argument('--replay')
    p.add_argument('--log')
    a = p.parse_args(argv)
    if a.action == 'validate':
        result, rows, path, accepted = load_source(a.source, a.table)
        binding_sha256, bound = binding(a.source, a.table)
        print(json.dumps(dict(table=a.table, source=str(path), source_sha256=digest(path.read_bytes()),
                              request_count=len(rows), labels=[r['label'] for r, _, _ in rows],
                              accepted_indices=accepted,
                              binding_sha256=binding_sha256, binding=bound)))
        return 0
    if a.action == 'audit':
        if not a.replay or not a.log or not a.output or Path(a.output).exists():
            p.error('new audit output and replay/log paths required')
        return audit(a.source, a.table, a.replay, a.log, a.output)
    if not a.container or not a.output or len(a.container) != 64 or any(c not in '0123456789abcdef' for c in a.container):
        p.error('exact container and output required')
    return replay(a.source, a.table, a.container, a.output)


if __name__ == '__main__':
    sys.exit(main())
