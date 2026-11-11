"""Default-inert, Root-sealed finite DNZ0/1/0 GPU-only coordinator.

No run occurs on import or without --run and a separately reviewed source seal.
One input size per complete campaign; the normal32K server is restored finally.
"""
import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import time
import traceback

import prepare_source as prep
import counter_reader as counter

HERE = Path(__file__).resolve().parent
ROOT, PRIMARY, PACKAGE, NORMAL = prep.ROOT, prep.PRIMARY, prep.PACKAGE, prep.NORMAL
SCHEMA = prep.SCHEMA
ARMS = prep.ARMS
STATE = ROOT / 'server/.local/optimization9h-20261004/continuation-current.json'
need, pin, read = prep.need, prep.pin, prep.read


def utc():
    return datetime.now(timezone.utc).isoformat()


def load(name, path):
    path = Path(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def require_execution_seal(binding):
    need(binding.get('schema') == SCHEMA and binding.get('root_sealed') is True
         and binding.get('dependency_closure_reviewed') is True,
         'Root must independently review the complete dependency closure and seal execution')
    prep.verify_pins(binding['pins'])


def validate_bindings(path, expected_sha, running=False):
    need(pin(path)['sha256'] == expected_sha, 'Root binding SHA changed')
    value = read(path)
    need(value.get('schema') == SCHEMA, 'Wrong GPU-only cohort binding')
    if not running:
        return value
    require_execution_seal(value)
    needed = {str(p.resolve()) for p in prep.dependencies()}
    sealed = {str(Path(row['path']).resolve()) for row in value['pins']}
    need(needed <= sealed, 'An executed/delegated source role is not sealed')
    need(value['normal_profile'] == pin(NORMAL)
         and value['normal_profile']['sha256'] == prep.NORMAL_SHA
         and value['normal_source_manifest'] == pin(PACKAGE / 'profiles/sources.json')
         and value['normal_source_manifest']['sha256'] == prep.SOURCE_SHA,
         'Normal source/profile identity differs')
    need(value['case'] == prep.request_case(value['case']['actual_input_tokens']),
         'Exact length-specific request identity differs')
    need(value['guards'] == dict(startup_physical=30, startup_commit=131, entry=22, runtime=18)
         and value['NPU_helper'] is False and value['external_stream'] is False,
         'GPU-only unchanged admission contract required')
    for arm, profile in prep.profiles(read(NORMAL)).items():
        need(pin(value['profiles'][arm]['path']) == value['profiles'][arm]
             and read(value['profiles'][arm]['path']) == profile, 'Frozen DNZ arm profile differs')
    need(value['artifact']['target'] == '.local/libhgn0203_raw_side.so'
         and value['artifact']['source']['sha256'] == prep.RAW_SHA,
         'Only the existing RAW observer product is allowed')
    return value


@contextmanager
def counter_bracket(collector, runtime, capture, qualify, publish, clock_ns=time.perf_counter_ns):
    """Replace one call boundary, not the original HTTP/RAW timing code."""
    original = collector.post_once
    async def post(*args, **kwargs):
        record = dict(before_host_started_ns=clock_ns())
        record['before'] = capture()
        record['before_host_finished_ns'] = clock_ns()
        collector.m.check_reserve(runtime, 22)
        result = None
        try:
            result = await original(*args, **kwargs)
            return result
        except BaseException as error:
            record['request_error'] = type(error).__name__ + ': ' + str(error)
            raise
        finally:
            record['after_host_started_ns'] = clock_ns()
            try:
                record['after'] = capture()
                record['after_host_finished_ns'] = clock_ns()
                record['delta'] = qualify(record['before'], record['after'])
                if result is not None:
                    timing = result[2]
                    need(record['before_host_finished_ns'] <= timing['qpc_start_ns']
                         and timing['qpc_end_ns'] <= record['after_host_started_ns'],
                         'Counter reads entered the matching HTTP QPC interval')
                    record['outside_HTTP_QPC_proved'] = True
            except BaseException as error:
                record['counter_error'] = type(error).__name__ + ': ' + str(error)
                raise
            finally:
                publish(record)
    collector.post_once = post
    try:
        yield
    finally:
        collector.post_once = original


def require_parity(reference, current):
    need(reference == current,
         'Exact UTF8/finish/actual-count/scoped-counter comparison differs from BEFORE warmup')


@contextmanager
def restoration_guard(restore):
    try:
        yield
    finally:
        restore()


def restore_online(*, active, baseline, overlay_attempted, current, stop, rollback, launch, verify):
    if (not overlay_attempted and active is baseline and current['phase'] == 'ready'
            and current['run_id'] == baseline['outer']['run_id']):
        restored = verify()
        need(restored['identities'] == baseline['identities'], 'Original online owner changed')
        return restored
    if active is not None and current['phase'] in ('starting', 'ready'):
        stop(active, 'final-private-stop')
    rollback()
    return launch()


def support(output, binding):
    # Only called after every declared input is verified and Root enabled --run.
    module = load('dnz_existing_lifecycle', prep.OLD / 'prefill4096-cohort-prep/root_campaign.py')
    module.OUT, module.PACKAGE, module.NORMAL = output, PACKAGE, NORMAL
    module.NORMAL_SHA256 = prep.NORMAL_SHA
    module.CASE_NAMES = (binding['case']['name'],)
    selected = prep.profiles(read(NORMAL))
    module.policy.normal = lambda: read(NORMAL)
    module.private_profile = lambda baseline, arm, experiment=None: selected[arm]
    module.native_environment = lambda rule='gate', arm='before': dict(
        HALOGEN_DN_Z_STREAM=str(int(arm == 'candidate')), HALOGEN_MTP_GATE_P='0.90',
        HALOGEN_PLD='3,3', HALOGEN_SERVE_TRACE='1', HALOGEN_DECODE_PREFETCH='0',
        HGN0203_RAW_ENABLE='1', HGN0203_API_NATIVE_ID='1',
        HALOGEN_PREFILL_CHUNK='8192', HALOGEN_MAX_TOK='8192')
    # Retain exact original acceptance scope; the MTP gate banner is not DNZ proof.
    module.trace_parser = load('dnz_original_native_trace', prep.OLD / 'prefill8192-cohort-prep-v2/mtp_trace.py')
    reference = load('dnz_existing_artifact_cleanup', prep.OLD / 'oracle-cohort-prep/oracle_campaign.py')
    reference.NORMAL, reference.NORMAL_SHA = NORMAL, prep.NORMAL_SHA
    collector = load('dnz_current_RAW_collector', prep.FROZEN / 'raw/collector/collect_epoch.py')
    return module, reference, collector


def check_native_manifest(manifest, mode):
    env, mounts = manifest['environment'], manifest['mounts']
    need(env.get('HALOGEN_DN_Z_STREAM') == str(mode)
         and env.get('HGN0203_RAW_ENABLE') == env.get('HGN0203_API_NATIVE_ID') == '1',
         'Resolved DNZ/RAW/API native-ID selectors differ')
    forbidden = ('HALOGEN_EXTERNAL_STREAM', 'HGN0203_STREAM_CAPTURE', 'HGN0203_EXTERNAL_STREAM',
                 'HGN0203_STREAM_CONFIG', 'HGN0203_STREAM_CONFIG_SHA256',
                 'HGN0203_STREAM_SOCKET', 'HGN0203_STREAM_STATS')
    need(not any(key in env for key in forbidden)
         and 'streaming_draft' not in manifest
         and not any('libhgn0203-stream.so' in str(value) or 'hdo2-qualified.json' in str(value)
                     for value in (env.get('LD_PRELOAD', ''), *mounts)),
         'GPU-only campaign must have no external stream, consumer or producer mapping')
    need(env.get('HALOGEN_CTX') == env.get('HALOGEN_KV_POOL_POSITIONS') == '32768'
         and env.get('HALOGEN_MAX_TOK') == env.get('HALOGEN_PREFILL_CHUNK') == '8192'
         and env.get('HALOGEN_PROMPT_CACHE') == '0', 'Native capacity/prefill/cache changed')


def summarize(results):
    summaries = {}
    for arm in ARMS:
        report = results[arm]
        need(report['collector']['completed'] is True and len(report['samples']) == 4,
             'Complete four-request arms required')
        rows = report['samples'][1:]
        summary = {}
        for name, get in (
                ('API_prefill_tok_s', lambda row: row['timings']['prompt_per_second']),
                ('API_decode_tok_s', lambda row: row['timings']['predicted_per_second']),
                ('HTTP_seconds', lambda row: row['http_qpc_seconds'])):
            values = [get(row) for row in rows]
            summary[name] = dict(mean=sum(values) / 3, minimum=min(values), maximum=max(values))
        summary['acceptance_scopes'] = {}
        for scope in ('head', 'lookup', 'grammar'):
            accepted = sum(row['scoped'][scope]['accepted'] for row in rows)
            drafted = sum(row['scoped'][scope]['drafted'] for row in rows)
            summary['acceptance_scopes'][scope] = dict(accepted=accepted, drafted=drafted,
                rate=accepted / drafted if drafted else None)
        summary['RAW'] = report['raw_report']['arithmetic_means']
        summary['independent_all_neural_acceptance'] = False
        summaries[arm] = summary
    return dict(arms=summaries, warmup_excluded=True, measured_per_arm=3,
                headline_qualified=False, independent_review_required=True,
                native_token_ID_sequence_parity_observed=False)


def run(binding, output):
    require_execution_seal(binding)
    output = prep.safe(output).resolve()
    need(output.is_relative_to(PRIMARY.resolve()) and not output.exists(),
         'A fresh Root-owned output is required; observe old handles first')
    module, reference, collector = support(output, binding)
    plan = read(binding['transition'])
    bound = Path(binding['transition']).parent
    module.check_files(PACKAGE, plan['baseline']['files'])
    module.check_files(bound / 'candidate', plan['candidate'])
    module.check_files(bound / 'rollback', plan['rollback_restore'])
    previous, runtime = module.support()
    previous.allowed(runtime)
    baseline = runtime.verify(NORMAL, 8840, require_idle=True)
    need(baseline['profile']['sha256'] == prep.NORMAL_SHA, 'Current normal owner/profile differs')
    collector.m.check_reserve(runtime, 22)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 18840))
    output.mkdir()
    runtime.ops.atomic(output / 'executed-bindings.json', binding)
    case = binding['case']
    record = dict(schema='halogen0203.DNZ-GPU-cohort.v1', utc=utc(), terminal=False,
        completed=False, restored=False, identity=runtime.ops.ident.process_identity(os.getpid()),
        baseline=baseline, owned_runs=[], owned_bindings={}, results={}, artifacts=[],
        weights_identity_by_arm={}, startup_allocation_by_arm={}, hardware_owner='root',
        NPU_helper=False, actual_input_tokens=case['actual_input_tokens'], output_tokens=128,
        warmups_excluded=1, measured_per_arm=3, headline_qualified=False)
    def save(phase, **updates):
        record.update(phase=phase, **updates)
        runtime.ops.atomic(output / 'handle.json', record)
        state = runtime.ops.read(STATE)
        state['current_work'] = dict(scope='halogen0203_DNZ_GPU_finite', phase=phase,
            handle=str(output / 'handle.json'), identity=record['identity'], hardware_owner='root',
            server_restore_required=not record['restored'], lifecycle_receipt=record.get('lifecycle_receipt'),
            do_not_duplicate_live_handles=True, goal_achieved=False)
        runtime.ops.atomic(STATE, state)
    def launch(profile, label, port):
        receipt = output / (label + '-launch.json')
        save(label + '_launching', lifecycle_receipt=str(receipt), launch_result=None, launch_observed=False)
        result = runtime.lifecycle.launch(argparse.Namespace(profile=profile, receipt=receipt,
            version='0.20.3', port=port, visible=port == 8840, admission_wait=180))
        save(label + '_launch_returned', launch_result=result)
        need(result == 0, 'Existing startup admission failed')
        ready = runtime.await_ready(profile, port, receipt)
        record['owned_runs'].append(ready['outer']['run_id'])
        record['owned_bindings'][ready['outer']['run_id']] = ready
        save(label + '_ready', active=ready, launch_observed=True)
        return ready
    active, overlay_attempted, reference_output = baseline, False, None
    def restore():
        nonlocal active
        try:
            # Resolve a captured launch before considering any restoration start.
            if active is None and record.get('lifecycle_receipt'):
                receipt_path = Path(record['lifecycle_receipt'])
                current = runtime.ops.read(ROOT / 'server/.local/current.json')
                if receipt_path.exists():
                    receipt = runtime.ops.read(receipt_path)
                    if current['phase'] in ('starting', 'ready'):
                        active = runtime.await_ready(Path(receipt['profile']['path']), receipt['port'], receipt_path)
                        run_id = active['outer']['run_id']
                        if run_id not in record['owned_runs']:
                            record['owned_runs'].append(run_id)
                        record['owned_bindings'][run_id] = active
                    else:
                        need(not runtime.previous.identity_live(receipt['launcher_identity'])
                             or record.get('launch_observed'), 'Unpublished live launcher must be observed')
                        if receipt.get('controller_run'):
                            need(current['run_id'] == receipt['controller_run']
                                 and not runtime.previous.identity_live(receipt['controller_identity']),
                                 'Owned terminal controller differs or remains live')
                            if receipt['controller_run'] not in record['owned_runs']:
                                record['owned_runs'].append(receipt['controller_run'])
                elif record.get('launch_result') != 2:
                    raise RuntimeError('Unresolved launch; inspect actual handles before another start')
            def rollback():
                runtime.ops.atomic(output / 'rollback-terminal.json',
                    module.terminal(runtime, baseline, record['owned_runs'], record['owned_bindings']))
                if overlay_attempted:
                    reference.artifacts_restore(module, record['artifacts'])
                    module.restore_overlay(PACKAGE, bound, plan)
                module.check_files(PACKAGE, plan['baseline']['files'])
                need(pin(PACKAGE / 'profiles/sources.json')['sha256'] == prep.SOURCE_SHA,
                     'Exact47-source normal manifest was not restored')
            restored = restore_online(active=active, baseline=baseline, overlay_attempted=overlay_attempted,
                current=runtime.ops.read(ROOT / 'server/.local/current.json'), stop=runtime.stop_owned,
                rollback=rollback, launch=lambda: launch(NORMAL, 'restore-normal', 8840),
                verify=lambda: runtime.verify(NORMAL, 8840, require_idle=False))
            reference.refresh_consumer(runtime, restored, output)
            runtime.ops.atomic(output / 'ready-left-online.json', restored)
            save('complete_normal_online', restored=True, final=restored, terminal=True, ended_utc=utc())
        except BaseException as error:
            save('restoration_incomplete', restoration_error=dict(type=type(error).__name__, message=str(error)))
            raise
    save('normal_verified')
    with runtime.previous.wsl_stdin_lease(output):
        with restoration_guard(restore):
            try:
                runtime.gpu_receipt('before-stop')
                runtime.stop_owned(active, 'normal-stop')
                active = None
                runtime.ops.atomic(output / 'normal-terminal.json',
                    module.terminal(runtime, baseline, record['owned_runs'], record['owned_bindings']))
                overlay_attempted = True
                module.apply_overlay(PACKAGE, bound, plan)
                artifact = binding['artifact']
                record['artifacts'].append(reference.artifact_install(module, output,
                    PACKAGE / artifact['target'], Path(artifact['source']['path'])))
                save('private_source_applied')
                for index, arm in enumerate(ARMS):
                    profile = Path(binding['profiles'][arm]['path'])
                    active = launch(profile, arm, 18840)
                    module.check_files(PACKAGE, plan['candidate'])
                    arm_dir = output / arm
                    arm_dir.mkdir()
                    manifest = read(Path(active['inner']['attempt']) / 'manifest.json')
                    check_native_manifest(manifest, int(arm == 'candidate'))
                    runtime.ops.atomic(arm_dir / 'initial-service-manifest.json', manifest)
                    weights_before = module.observe_weights_identity()
                    record['startup_allocation_by_arm'][arm] = module.save_startup_allocation(runtime, active, arm)
                    folder = arm_dir / case['name']
                    counters, last = [], None
                    def capture():
                        nonlocal last
                        last = counter.capture(runtime, active, last)
                        return last
                    def publish_counter(value):
                        counters.append(value)
                        runtime.ops.atomic(folder / ('dnz-counter-' + str(len(counters) - 1) + '.json'), value)
                    def after_validated(ordinal, sample, raw_sample, current_folder):
                        nonlocal reference_output
                        response = read(Path(current_folder) / ('response-' + str(ordinal) + '.json'))
                        choice = response['choices'][0]
                        current = dict(text=choice['text'], finish_reason=sample['finish_reason'],
                            actual_input_tokens=sample['actual_input_tokens'], actual_output_tokens=sample['actual_output_tokens'],
                            scoped=sample['scoped'], request_sha256=sample['request_sha256'])
                        need(current['finish_reason'] == 'length' and current['actual_output_tokens'] == 128,
                             'Frozen length128 output required')
                        if reference_output is None:
                            need(arm == 'before' and ordinal == 0, 'Only BEFORE warmup establishes output reference')
                            reference_output = current
                            (output / 'reference-output.utf8').write_bytes(current['text'].encode('utf-8'))
                        require_parity(reference_output, current)
                        need(len(counters) == ordinal + 1
                             and counters[-1].get('outside_HTTP_QPC_proved') is True,
                             'Exactly two successful outside-timing counter reads required')
                        runtime.ops.atomic(Path(current_folder) / ('parity-' + str(ordinal) + '.json'),
                            dict(exact_UTF8_finish_counts_scopes=True, native_token_ID_sequence_parity=False,
                                 native_request_id=sample['native_request_id'], output_sha256=sample['output_sha256']))
                    save('collecting', arm=arm)
                    with counter_bracket(collector, runtime, capture,
                            lambda before, after: counter.qualify_delta(before, after, int(arm == 'candidate')),
                            publish_counter):
                        report = asyncio.run(collector.collect_epoch(runtime=runtime, profile=profile, port=18840,
                            expected=active, request_bytes=Path(case['request']['path']).read_bytes(),
                            request_sha256=case['request']['sha256'], route='/v1/completions',
                            raw_dir=Path(active['inner']['attempt']) / 'raw-phase',
                            epoch=0x020300D200000001 + index, output=folder,
                            expected_prompt_tokens=case['actual_input_tokens'], expected_output_tokens=128,
                            after_validated_sample=after_validated))
                    module.save_cost_trace(runtime, active, profile, folder, report, {}, arm=arm)
                    report['DNZ_counter_samples'] = counters
                    record['results'][arm] = report
                    weights_after = module.observe_weights_identity()
                    record['weights_identity_by_arm'][arm] = module.save_weights_identity(
                        runtime, arm, weights_before, weights_after)
                    runtime.stop_owned(active, arm + '-stop')
                    active = None
                    save('arm_complete', arm=arm)
                record['summary'] = summarize(record['results'])
                record['completed'] = True
                save('all_twelve_requests_qualified')
            except BaseException as error:
                save('error', error=dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bindings', type=Path)
    parser.add_argument('--bindings-sha')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not args.run:
        print(json.dumps(dict(source_only=True, executed=False)))
        return 0
    need(args.bindings is not None and args.bindings_sha is not None and args.output is not None,
         'Explicit Root binding/SHA and fresh output required')
    binding = validate_bindings(args.bindings, args.bindings_sha, running=True)
    result = run(binding, args.output)
    return 0 if result['completed'] and result['restored'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
