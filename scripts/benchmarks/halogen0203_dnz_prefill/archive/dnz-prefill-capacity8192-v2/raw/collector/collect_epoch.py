"""Private prefill study collector using the existing RAW phase validators."""
import argparse
import asyncio
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
PREP = HERE.parent
sys.path.insert(0, str(PREP / 'collector'))
sys.path.insert(0, str(PREP / 'observer'))
from validate_capture import (CAPTURE_BYTES, UnsupportedCapture, parse_epoch, read_capture,
                              positive_int, response_counts, validate)
from validate_cohort import validate_cohort
from qpc_audit import audit_qpc

_spec = importlib.util.spec_from_file_location('halogen0203_epoch_measure_helpers', PREP.parent / 'measure_helpers.py')
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
need = m.require
NOT_REQUIRED_ADMISSION = dict(version=1, policy='not_required', ready=None, reason='not_required',
    required_available_bytes=None, required_commit_headroom_bytes=None,
    available_bytes=None, commit_headroom_bytes=None, sample_age_ms=None)


class OracleMismatch(ValueError):
    """Decoded output bytes differ from the frozen exact oracle."""


def absent(path):
    return not path.exists() and not path.is_symlink()


def unlinked(path):
    return not any(item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction())
                   for item in (path, *path.parents))


def session_for_token(token):
    import aiohttp
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=900),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})


def request_value(data, expected_sha, drafter):
    need(type(data) is bytes and m.digest(data) == expected_sha, 'Frozen request SHA256 differs')
    value = json.loads(data)
    need(type(value) is dict and value.get('stream') is False
         and value.get('temperature') == 0 and value.get('drafter') == drafter,
         'Requires one frozen nonstreaming greedy ' + drafter + ' request')
    caps = [value[key] for key in ('max_tokens', 'max_output_tokens', 'max_completion_tokens') if key in value]
    need(len(caps) == 1 and type(caps[0]) is int and 0 < caps[0] <= 0xffffffff,
         'One explicit positive output cap required')
    return value


def bound_identity(value):
    return dict(identities=value['identities'], controller_run=value['outer']['run_id'],
                backend_run=value['inner']['run_id'], profile_sha256=value['outer']['profile_sha256'])


def verify_runtime(runtime, profile, port, expected, observation_path=None):
    current = runtime.verify(profile, port, require_idle=True)
    if observation_path is not None:
        runtime.ops.atomic(observation_path, current)
    need(bound_identity(current) == bound_identity(expected), 'Bound runtime identity changed')
    gateway, native = current['gateway'], current['native']
    config = json.loads(Path(profile).read_bytes())
    slots = config['engine'].get('slots', 1)
    need(type(slots) is int and slots in (1, 2)
         and type(config['concurrency']) is int and config['concurrency'] == slots,
         'Gateway profile slot/concurrency contract differs')
    need(type(native['slots']) is int and native['slots'] in (1, 2)
         and type(expected['native']['slots']) is int
         and native['slots'] == expected['native']['slots'] == slots and not native['busy']
         and native['in_flight'] == native['queued'] == 0,
         'Requires idle native engine with the bound slot count')
    need('request_admission_ready' in gateway, 'Gateway admission readiness field missing')
    admission_ready = gateway['request_admission_ready'] is True
    if slots == 1 and gateway['request_admission_ready'] is None:
        admission = gateway.get('request_admission')
        admission_ready = (type(admission) is dict and admission == NOT_REQUIRED_ADMISSION
                           and type(admission['version']) is int)
    need(gateway['active_requests'] == gateway['queued_requests'] == 0
         and not gateway['draining'] and admission_ready,
         'Gateway is busy, queued, draining or unavailable')
    need(native['version'] == dict(api='0.20.3', engine='0.20.3', match=True),
         'Actual API/engine version differs')
    for key in ('completed', 'cancelled'):
        need(type(gateway[key]) is int and gateway[key] >= 0, 'Invalid gateway counter')
    return current


def gateway_step(before, after):
    need(after['gateway']['completed'] == before['gateway']['completed'] + 1
         and after['gateway']['cancelled'] == before['gateway']['cancelled'],
         'Foreign gateway completion or cancellation observed')


def gateway_counts(value):
    return {key: value['gateway'][key] for key in ('completed', 'cancelled')}


def gateway_unchanged(before, after):
    need(gateway_counts(before) == gateway_counts(after), 'Foreign gateway activity between requests')


def serial_counts(response, request):
    usage, timings = response['usage'], response['timings']
    prompt, generated = usage.get('prompt_tokens'), usage.get('completion_tokens')
    request_id = timings.get('raw_native_request_id')
    cap = next(request[key] for key in ('max_tokens', 'max_output_tokens', 'max_completion_tokens')
               if key in request)
    need(type(prompt) is int and 0 < prompt <= 0xffffffff
         and type(generated) is int and 0 <= generated <= cap
         and type(request_id) is int and 0 < request_id <= 0x7fffffffffffffff,
         'Invalid serial smoke actual counts or native request identity')
    need(type(timings.get('predicted_n')) is int and timings['predicted_n'] == generated
         and type(timings.get('prompt_n')) is int and timings['prompt_n'] == prompt
         and timings.get('cache_n', 0) == 0 and type(usage.get('total_tokens')) is int
         and usage['total_tokens'] == prompt + generated,
         'Serial smoke actual usage/timing counts differ')
    return dict(prompt=prompt, generated=generated, request_id=request_id, output_cap=cap)


def account_response(raw, request, *, oracle_bytes=None, expected_prompt_tokens=None,
                     expected_output_tokens=None, phase_support=True):
    if expected_output_tokens is not None:
        positive_int(expected_output_tokens, 'expected output count', 0xffffffff)
    response = json.loads(raw)
    need(type(response) is dict and type(response.get('choices')) is list
         and len(response['choices']) == 1, 'Expected one OAI choice')
    choice = response['choices'][0]
    message = choice.get('message', {})
    text = choice.get('text', message.get('content'))
    need(type(text) is str and choice.get('finish_reason') in ('stop', 'length'),
         'Expected a completed ordinary text response')
    need(oracle_bytes is None or choice['finish_reason'] == 'stop',
         'Exact oracle requires a natural stop finish reason')
    need('<think>' not in text and '</think>' not in text
         and not message.get('reasoning_content') and not message.get('tool_calls'),
         'Returned reasoning or tool calls outside frozen text scope')
    timings, usage = response['timings'], response['usage']
    generated = usage.get('completion_tokens')
    need(type(generated) is int and 0 <= generated <= 0xffffffff, 'Invalid actual output count')
    need(expected_output_tokens is None or generated == expected_output_tokens,
         'Actual output differs from expected output count')
    counts = (response_counts(response, request, require_cold=True) if phase_support
              else serial_counts(response, request))
    need(expected_prompt_tokens is None or counts['prompt'] == expected_prompt_tokens,
         'Native actual prompt count differs from frozen expectation')
    need(timings.get('disk_restore_n', 0) == 0
         and usage.get('prompt_tokens_details', {}).get('cached_tokens', 0) == 0
         and usage.get('cached_tokens', 0) == 0
         and usage.get('completion_tokens_details', {}).get('reasoning_tokens', 0) == 0
         and not any('clamp' in key for key in timings),
         'Cache reuse, reasoning tokens or output/context clamp observed')
    for key in ('prompt_ms', 'predicted_ms', 'prompt_per_second', 'predicted_per_second'):
        number = timings.get(key)
        need(type(number) in (int, float) and math.isfinite(number) and number >= 0,
             'Invalid native API timing observation')
    scoped = None
    ledger = timings.get('speculation')
    if request['drafter'] == 'mtp' or ledger is not None:
        need(type(ledger) is dict and (request['drafter'] != 'mtp' or ledger.get('drafter') == 'mtp'),
             'Missing or invalid per-request MTP speculation ledger')
        scoped = {name: ledger.get(name) for name in ('head', 'lookup', 'grammar')}
        need(all(type(scope) is dict and all(type(scope.get(key)) is int and scope[key] >= 0
             for key in ('rounds', 'drafted', 'accepted')) and scope['accepted'] <= scope['drafted']
             for scope in scoped.values()), 'Invalid per-request scoped counters')
        need(type(ledger.get('rounds')) is int
             and sum(scope['rounds'] for scope in scoped.values()) == ledger['rounds']
             and sum(scope['drafted'] for scope in scoped.values()) == timings.get('draft_n')
             and sum(scope['accepted'] for scope in scoped.values()) == timings.get('draft_n_accepted'),
             'Per-request scoped and combined draft counters differ')
    output = text.encode('utf-8')
    if oracle_bytes is not None and output != oracle_bytes:
        raise OracleMismatch('Exact output oracle mismatch')
    sample = dict(actual_input_tokens=counts['prompt'], actual_output_tokens=generated,
        output_cap=counts['output_cap'], native_request_id=counts['request_id'],
        output_sha256=m.digest(output), output_utf8_bytes=len(output),
        finish_reason=choice['finish_reason'], usage=usage, timings=timings, scoped=scoped,
        speculation=ledger, exact_oracle_checked=oracle_bytes is not None,
        actual_no_cache_reuse=True, generated_code_executed=False)
    if expected_output_tokens is not None:
        sample['expected_output_tokens'] = expected_output_tokens
    return sample


async def post_once(session, runtime, url, body, identities):
    start = time.perf_counter_ns()
    task = asyncio.create_task(m.fetch_http_response(session, url, body))
    minimum = float('inf')
    try:
        while not task.done():
            frame = m.check_reserve(runtime, 18)
            minimum = min(minimum, min(frame['available_bytes'], frame['commit_headroom_bytes']) / 2**30)
            for identity in identities.values():
                need(runtime.ops.ident.process_identity(identity['pid']) == identity,
                     'Bound owner changed during request')
            await asyncio.wait({task}, timeout=0.1)
        raw, status, ended = await task
        return raw, status, dict(qpc_start_ns=start, qpc_end_ns=ended,
            http_qpc_seconds=(ended - start) / 1e9, minimum_reserve_gib=minimum)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def remove_owned(path, identity):
    need(path.is_file() and unlinked(path), 'Owned control file disappeared or became linked')
    stat = path.stat()
    need((stat.st_dev, stat.st_ino) == identity, 'Owned control file identity changed')
    path.unlink()


def save_journals(raw_dir, output, epoch):
    folder = output / 'journals'
    folder.mkdir(exist_ok=True)
    for ordinal in (*range(4), 'fault'):
        source = raw_dir / f'capture-{epoch:016x}-{ordinal}.bin'
        target = folder / source.name
        if source.is_file() and unlinked(source) and not target.exists():
            m.save_new(target, source.read_bytes(), raw=True)


async def collect_epoch(*, runtime, profile, port, expected, request_bytes, request_sha256,
                        route, raw_dir, epoch, output, oracle_bytes=None,
                        expected_prompt_tokens=None, expected_output_tokens=None, oracle_request_bytes=None,
                        oracle_request_sha256=None, after_validated_sample=None):
    profile, raw_dir, output = Path(profile), Path(raw_dir), Path(output)
    need(type(port) is int and 1 <= port <= 65535, 'Invalid controller port')
    need(route in ('/v1/chat/completions', '/v1/completions'), 'Unsupported OAI route')
    need(type(epoch) is int and 0 < epoch <= 0xffffffffffffffff, 'Invalid epoch nonce')
    if expected_output_tokens is not None:
        positive_int(expected_output_tokens, 'expected output count', 0xffffffff)
    need(oracle_bytes is None or type(oracle_bytes) is bytes, 'Oracle must be exact UTF8 bytes')
    request = request_value(request_bytes, request_sha256, 'mtp')
    serial = None
    if oracle_request_bytes is not None:
        need(oracle_bytes is not None, 'Serial oracle request requires exact expected output bytes')
        serial = request_value(oracle_request_bytes, oracle_request_sha256, 'serial')
        need({**serial, 'drafter': 'mtp'} == request, 'Serial smoke differs beyond drafter')
    config = json.loads(profile.read_bytes())
    slots = config['engine'].get('slots', 1)
    need(type(slots) is int and slots in (1, 2)
         and type(config['concurrency']) is int and config['concurrency'] == slots
         and expected['native']['slots'] == slots
         and config['engine']['prompt_cache'] == 'Off', 'Requires exact cold one-slot or two-slot profile')
    need(m.digest(profile.read_bytes()) == expected['outer']['profile_sha256'], 'Expected profile SHA256 differs')
    need(raw_dir.is_dir() and unlinked(raw_dir)
         and raw_dir.resolve() == (Path(expected['inner']['attempt']) / 'raw-phase').resolve(),
         'RAW directory differs from bound native attempt')
    need(output.is_absolute() and absent(output) and unlinked(output)
         and not output.resolve().is_relative_to(raw_dir.resolve()), 'Fresh separate output directory required')
    arm, lock, state_path = raw_dir / 'arm', raw_dir / 'collector.lock', raw_dir / 'collector-epoch.json'
    need(absent(arm), 'Epoch already armed, inspect true state before continuing')
    output.mkdir(parents=True)
    m.save_new(output / 'request.json', request_bytes, raw=True)
    if oracle_bytes is not None:
        m.save_new(output / 'expected-output.utf8', oracle_bytes, raw=True)
    if serial is not None:
        m.save_new(output / 'serial-request.json', oracle_request_bytes, raw=True)
    record = dict(schema='halogen0203.raw-epoch.collector.v1', utc=m.utc(), terminal=False,
        completed=False, epoch_nonce=f'{epoch:016x}', profile_sha256=expected['outer']['profile_sha256'],
        request_sha256=request_sha256, route=route, port=port, runtime=bound_identity(expected),
        lifecycle_actions=False, completed_requests=0, serial_smoke_completed=False,
        restart_required=False, unsupported=False, no_retries=True)
    if expected_output_tokens is not None:
        record['expected_output_tokens'] = expected_output_tokens
    arm_identity = lock_identity = None
    armed = False
    samples, response_files = [], []
    runtime.ops.atomic(output / 'handle.json', record)
    try:
        with lock.open('xb') as stream:
            stat = os.fstat(stream.fileno())
            lock_identity = (stat.st_dev, stat.st_ino)
            stream.write((f'{os.getpid()}\n').encode())
        need(unlinked(state_path), 'Epoch ledger is linked')
        expected_gateway = gateway_counts(expected)
        previous_epoch = 0
        if state_path.exists():
            previous = json.loads(state_path.read_bytes())
            need(previous['runtime'] == record['runtime'] and previous['completed'] is True
                 and not previous['restart_required'] and int(previous['epoch_nonce'], 16) < epoch,
                 'Previous epoch incomplete, reused, regressed or owned by another engine')
            expected_gateway = previous['gateway_final']
            previous_epoch = int(previous['epoch_nonce'], 16)
        else:
            need(not list(raw_dir.glob('capture-*.bin')), 'Untracked prior epoch captures require inspection')
        current = verify_runtime(runtime, profile, port, expected, output / 'ready-before.json')
        need(gateway_counts(current) == expected_gateway, 'Foreign gateway activity between epochs')
        token = Path(config['token_file']).read_text(encoding='utf-8').strip()
        need(bool(token), 'Empty gateway token')
        async with session_for_token(token) as session:
            if serial is not None:
                m.check_reserve(runtime, 22)
                runtime.ops.atomic(output / 'serial-gpu-before.json', runtime.gpu_receipt('epoch-serial-before'))
                before = verify_runtime(runtime, profile, port, expected, output / 'serial-ready-before.json')
                gateway_unchanged(current, before)
                raw, status, qpc = await post_once(session, runtime,
                    f'http://127.0.0.1:{port}' + route, oracle_request_bytes, expected['identities'])
                m.save_new(output / 'serial.response.json', raw, raw=True)
                m.save_new(output / 'serial.transport.json', dict(http_status=status, **qpc))
                need(qpc['qpc_end_ns'] > qpc['qpc_start_ns'], 'Invalid QPC endpoints')
                need(status == 200, 'Serial smoke failed HTTP ' + str(status))
                current = verify_runtime(runtime, profile, port, expected, output / 'serial-ready-after.json')
                gateway_step(before, current)
                # A verified unarmed response advances the owned gateway count,
                # while the last armed nonce remains unchanged. Root may skip
                # an exact-oracle mismatch before any RAW epoch is started.
                runtime.ops.atomic(state_path, dict(schema='halogen0203.raw-epoch.gateway-checkpoint.v1',
                    runtime=record['runtime'], epoch_nonce=f'{previous_epoch:016x}', completed=True,
                    restart_required=False, gateway_final=gateway_counts(current)))
                sample = account_response(raw, serial, oracle_bytes=oracle_bytes,
                    expected_prompt_tokens=expected_prompt_tokens,
                    expected_output_tokens=expected_output_tokens, phase_support=False)
                m.save_new(output / 'serial.sample.json', dict(**sample, **qpc, phase='serial_oracle',
                    response_sha256=m.digest(raw), request_sha256=oracle_request_sha256))
                runtime.ops.atomic(output / 'serial-gpu-after.json', runtime.gpu_receipt('epoch-serial-after'))
                record['serial_smoke_completed'] = True
            m.check_reserve(runtime, 22)
            ready_to_arm = verify_runtime(runtime, profile, port, expected, output / 'ready-to-arm.json')
            gateway_unchanged(current, ready_to_arm)
            current = ready_to_arm
            for ordinal in (*range(4), 'fault'):
                need(absent(raw_dir / f'capture-{epoch:016x}-{ordinal}.bin'), 'Epoch output already exists')
            runtime.ops.atomic(state_path, record)
            with arm.open('xb') as stream:
                stat = os.fstat(stream.fileno())
                arm_identity = (stat.st_dev, stat.st_ino)
                armed = True
                stream.write(f'{epoch:016x}\n'.encode('ascii'))
                stream.flush()
                os.fsync(stream.fileno())
            m.save_new(output / 'arm-created.json', dict(epoch_nonce=f'{epoch:016x}',
                path=str(arm), content=f'{epoch:016x}\n', utc=m.utc()))
            for ordinal in range(4):
                m.check_reserve(runtime, 22)
                runtime.ops.atomic(output / f'gpu-before-{ordinal}.json', runtime.gpu_receipt(f'epoch-{epoch:016x}-{ordinal}-before'))
                before = verify_runtime(runtime, profile, port, expected, output / f'ready-before-{ordinal}.json')
                gateway_unchanged(current, before)
                record.update(phase='request_running', ordinal=ordinal, request_started_utc=m.utc())
                runtime.ops.atomic(output / 'handle.json', record)
                raw, status, qpc = await post_once(session, runtime,
                    f'http://127.0.0.1:{port}' + route, request_bytes, expected['identities'])
                response_file = output / f'response-{ordinal}.json'
                m.save_new(response_file, raw, raw=True)
                m.save_new(output / f'transport-{ordinal}.json', dict(http_status=status, **qpc))
                need(qpc['qpc_end_ns'] > qpc['qpc_start_ns'], 'Invalid QPC endpoints')
                need(status == 200, 'Request failed HTTP ' + str(status))
                sample = account_response(raw, request, oracle_bytes=oracle_bytes,
                    expected_prompt_tokens=expected_prompt_tokens, expected_output_tokens=expected_output_tokens)
                sample.update(ordinal=ordinal, case=output.name, phase='warmup_excluded' if ordinal == 0 else 'measured',
                    response_sha256=m.digest(raw), request_sha256=request_sha256, **qpc)
                m.save_new(output / f'sample-{ordinal}.json', sample)
                samples.append(sample)
                response_files.append(response_file)
                need(len({row['output_sha256'] for row in samples}) == 1,
                     'Deterministic output hash changed within the frozen epoch')
                current = verify_runtime(runtime, profile, port, expected, output / f'ready-after-{ordinal}.json')
                gateway_step(before, current)
                runtime.ops.atomic(output / f'gpu-after-{ordinal}.json', runtime.gpu_receipt(f'epoch-{epoch:016x}-{ordinal}-after'))
                journal = raw_dir / f'capture-{epoch:016x}-{ordinal}.bin'
                need(journal.is_file() and unlinked(journal) and journal.stat().st_size == CAPTURE_BYTES,
                     'Missing or incomplete RAW journal after API response')
                journal_data = journal.read_bytes()
                raw_sample = validate(read_capture(journal_data, ordinal, epoch), json.loads(raw),
                                      request=request, require_cold=True)
                need(raw_sample['native_slot'] < slots, 'Observed native slot exceeds bound profile')
                m.save_new(output / f'raw-sample-{ordinal}.json', dict(**raw_sample,
                    journal_sha256=m.digest(journal_data), response_sha256=m.digest(raw)))
                need(raw_sample['prefill_raw_upper_ns'] + raw_sample['decode_raw_upper_ns']
                     <= qpc['qpc_end_ns'] - qpc['qpc_start_ns'],
                     'Unadjusted RAW upper bound exceeds matching whole-HTTP QPC interval')
                need(absent(raw_dir / f'capture-{epoch:016x}-fault.bin'), 'Epoch fault marker observed')
                need(arm.read_bytes() == f'{epoch:016x}\n'.encode('ascii'), 'Immutable arm content changed')
                record.update(phase='request_complete', completed_requests=ordinal + 1)
                runtime.ops.atomic(output / 'handle.json', record)
                if after_validated_sample is not None:
                    after_validated_sample(ordinal, sample, raw_sample, output)
            remove_owned(arm, arm_identity)
            arm_identity = None
            m.save_new(output / 'arm-disarmed.json', dict(utc=m.utc(), after_responses=4))
        save_journals(raw_dir, output, epoch)
        report = validate_cohort(raw_dir / 'capture', response_files, output / 'request.json', epoch, arm,
                                 require_cold=True)
        m.save_new(output / 'raw-report.json', report)
        audit = audit_qpc(report, samples, request_sha256)
        m.save_new(output / 'qpc-audit.json', audit)
        need(audit['valid'] is True, 'Unadjusted RAW bounds exceed matching whole-HTTP QPC interval')
        ready_after = verify_runtime(runtime, profile, port, expected, output / 'ready-after.json')
        gateway_unchanged(current, ready_after)
        record.update(completed=True, phase='complete', RAW_validated=True, QPC_audit_passed=True,
                      gateway_final=gateway_counts(ready_after))
        return dict(collector=record, raw_report=report, qpc_audit=audit, samples=samples)
    except BaseException as error:
        record.update(error=dict(type=type(error).__name__, message=str(error)),
            unsupported=isinstance(error, UnsupportedCapture), restart_required=armed)
        raise
    finally:
        if arm_identity is not None:
            try:
                remove_owned(arm, arm_identity)
                record['disarmed_after_error'] = True
            except BaseException as error:
                record['disarm_error'] = dict(type=type(error).__name__, message=str(error))
        save_journals(raw_dir, output, epoch)
        record.update(terminal=True, ended_utc=m.utc())
        runtime.ops.atomic(output / 'handle.json', record)
        if armed:
            runtime.ops.atomic(state_path, record)
        if lock_identity is not None:
            remove_owned(lock, lock_identity)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--expected-ready', type=Path, required=True)
    parser.add_argument('--request-file', type=Path, required=True)
    parser.add_argument('--request-sha256', required=True)
    parser.add_argument('--route', required=True, choices=('/v1/chat/completions', '/v1/completions'))
    parser.add_argument('--raw-dir', type=Path, required=True)
    parser.add_argument('--epoch', type=parse_epoch, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--oracle-file', type=Path)
    parser.add_argument('--expected-prompt-tokens', type=int)
    parser.add_argument('--expected-output-tokens', type=int)
    parser.add_argument('--serial-request-file', type=Path)
    parser.add_argument('--serial-request-sha256')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    request_bytes = args.request_file.read_bytes()
    request_value(request_bytes, args.request_sha256, 'mtp')
    if args.expected_output_tokens is not None:
        positive_int(args.expected_output_tokens, 'expected output count', 0xffffffff)
    if not args.run:
        print(json.dumps(dict(prepared=True, request_sha256=args.request_sha256,
            epoch_nonce=f'{args.epoch:016x}', lifecycle_actions=False, HTTP_requests_sent=0)))
        return
    runtime = m.load_runtime()
    runtime.OUT = args.output
    result = asyncio.run(collect_epoch(runtime=runtime, profile=args.profile, port=args.port,
        expected=json.loads(args.expected_ready.read_bytes()), request_bytes=request_bytes,
        request_sha256=args.request_sha256, route=args.route, raw_dir=args.raw_dir,
        epoch=args.epoch, output=args.output,
        oracle_bytes=args.oracle_file.read_bytes() if args.oracle_file else None,
        expected_prompt_tokens=args.expected_prompt_tokens,
        expected_output_tokens=args.expected_output_tokens,
        oracle_request_bytes=args.serial_request_file.read_bytes() if args.serial_request_file else None,
        oracle_request_sha256=args.serial_request_sha256))
    print(json.dumps(dict(completed=result['collector']['completed'], epoch_nonce=f'{args.epoch:016x}',
        RAW_validated=True, QPC_audit_passed=True)))


if __name__ == '__main__':
    main()
