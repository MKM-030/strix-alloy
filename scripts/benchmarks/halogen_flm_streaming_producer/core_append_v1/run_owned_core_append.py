"""Root-only finite unused-head component monitor; file validation is the default.

One retained child, no retries or GPU lifecycle, and the same established
entry/post GPU checks. This is a component comparison, never engine tok/s.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
PRIMARY = HERE.parents[1]
ROOT = HERE.parents[5]
OUT = PRIMARY/'stateful1012-core-append-component-v1'
PRIOR_PATH = PRIMARY/'stateful1012-live-prep/producer/run_owned_qualification.py'
SUPPORT = PRIMARY/'prefill4096-cohort-prep/root_campaign.py'
MODULE_MONITOR = PRIMARY/'stateful1012-prep/run_owned_stateful.py'
STATE = ROOT/'server/.local/optimization9h-20261004/continuation-current.json'
POLICY = dict(entry_reserve_gib=22, runtime_reserve_gib=18,
    child_deadline_seconds=120, worker_deadline_seconds=110, automatic_retries=0,
    NPU_children=1, GPU_lifecycle_actions=False)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prior = load('core_append_owned_prior_monitor', PRIOR_PATH)
pin, require, utc = prior.pin, prior.require, prior.utc


def failure(error):
    return dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())


def validate_preparation(path, expected_sha, *, normal_profile, wrapper_sha):
    require(pin(path)['sha256'] == expected_sha, 'Root-sealed preparation changed')
    prep = json.loads(Path(path).read_bytes())
    require(prep.get('schema') == 'halogen0201.stateful1012-core-append-runtime-preparation.v1'
            and prep.get('native_execution_performed') is False, 'Prospective source-only preparation required')
    require(prep['policy'] == POLICY, 'Declared finite 22/18/120-second policy differs')
    require(Path(prep['output_directory']).resolve() == OUT, 'Only one fresh declared output is supported')
    for group in ('source_pins', 'references', 'runtime_pins'):
        for expected in prep[group]:
            require(pin(expected['path']) == expected, 'Pinned file changed: '+expected['path'])
    source_paths = {Path(item['path']).resolve() for item in prep['source_pins']}
    required_sources = {HERE/name for name in ('actor.py', 'service.py', 'request_scoped_backend.py',
        'native_backend.py', 'native_backend.cpp', 'append_head_scope.hpp', 'qualify_core_append.py', 'run_owned_core_append.py')}
    require(required_sources <= source_paths and all(HERE in item.parents for item in source_paths),
            'New private source closure pins are required; no canonical monkeypatch')
    for name in ('host', 'native_wrapper', 'GPU_baseline_seal'):
        require(pin(prep[name]['path']) == prep[name], 'Pinned '+name+' changed')
    require(len(wrapper_sha) == 64 and all(c in '0123456789abcdef' for c in wrapper_sha)
            and wrapper_sha != '8d997e0a9c7566c740ed7a754a59aaa7efed1af174c3a38ba8ad7a5c3e68f91a'
            and prep['native_wrapper']['sha256'] == wrapper_sha,
            'Explicit Root-compiled new unused-head wrapper SHA256 differs')
    require(Path(normal_profile).resolve() == Path(prep['normal_profile']['path']).resolve()
            and pin(normal_profile) == prep['normal_profile'], 'Explicit current normal profile pin differs')
    require(prep['required_loaded_modules']['native_backend.dll'] == prep['native_wrapper'],
            'Actual wrapper module proof must select the new DLL')
    for expected in prep['required_loaded_modules'].values():
        require(pin(expected['path']) == expected, 'Expected loaded module changed')
    require(pin(prep['input'])['sha256'] == prior.INPUT_SHA, 'Frozen qualification input differs')
    prior.validate_prompt_hashes(json.loads(Path(prep['input']).read_bytes()))
    return prep


def execute_child(runtime, item, command, *, cwd, env, log_path, baseline, save,
                  module_probe, spawn=subprocess.Popen, clock=time.monotonic, pause=time.sleep):
    """Cleanup uses this retained Popen handle, never a PID lookup/reopen."""
    child = None; started = clock(); last_paths = None; primary_error = None
    item.update(command=command, started_utc=utc(), memory_samples=[],
                module_observations=[], module_inspection_errors=[], child_deadline_seconds=120)
    with Path(log_path).open('xb') as log:
        try:
            child = spawn(command, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            item['identity'] = runtime.ops.ident.process_identity(child.pid)
            save('child_running')
            while child.poll() is None:
                frame = runtime.ops.host.frame(); item['memory_samples'].append(frame)
                require(min(frame['available_bytes'], frame['commit_headroom_bytes']) >= 18*2**30,
                        '18-GiB physical/commit runtime reserve crossed')
                require(clock()-started <= 120, 'Finite120-second child deadline exceeded')
                prior.same_gpu(runtime, baseline)
                try:
                    paths = module_probe(child)
                    if paths != last_paths:
                        item['module_observations'].append(dict(elapsed_seconds=clock()-started, paths=paths))
                        last_paths = paths
                except OSError as error: item['module_inspection_errors'].append(str(error))
                pause(.1)
            item['exit_code'] = child.wait()
        except BaseException as error:
            primary_error = error; item['execution_error'] = failure(error)
            raise
        finally:
            try:
                if child is not None and child.poll() is None:
                    child.terminate(); item['exit_code'] = child.wait(timeout=20)
                    item['terminated_own_child'] = True
            except BaseException as error:
                item['own_child_cleanup_error'] = failure(error)
                if primary_error is None: raise
            finally:
                terminal = child is None or child.poll() is not None
                item['elapsed_seconds'] = clock()-started; item['ended_utc'] = utc()
                if child is not None and terminal:
                    handle = getattr(child, '_handle', None)
                    if handle is not None:
                        try: handle.Close(); item['retained_handle_closed'] = True
                        except BaseException as error: item['handle_close_error'] = failure(error)
                save('child_closed' if terminal else 'child_cleanup_incomplete')


def validate_outputs(report, comparison):
    require(report.get('schema') == 'halogen0201.stateful1012-core-append-qualification.v1'
            and report.get('complete') is True and report.get('error') is None
            and all(report.get(k) is True for k in ('native_closed', 'native_cleanup_complete',
                'terminal_cancel_completed', 'head_instructions_restored')), 'Complete restored and closed native component required')
    runs = report.get('runs', [])
    require(len(runs) == 8 and report.get('native_engine_constructions') == 1,
            'Eight replays in one native engine construction required')
    for index, row in enumerate(runs):
        require(row.get('complete') is True and row.get('run_index') == index
                and row.get('mode') == ('head_on' if index%2 == 0 else 'head_skip')
                and row.get('excluded_warmup') is (index < 2)
                and row.get('measured_run') == (None if index < 2 else index//2)
                and row.get('actual_committed_T_count') == 128 and len(row.get('states', [])) == 9
                and row.get('committed_event_batches') == 8
                and row.get('head_skip_count_delta') == (0 if index%2 == 0 else 120)
                and row.get('head_instructions_restored') is True
                and len(row.get('commit_segments', [])) == 8,
                'Excluded warmups and paired three-run 128-token/nine-endpoint replays required')
    mixed = report.get('correctness_mixed_batches', {})
    require(mixed.get('run_index') == 8 and mixed.get('mode') == 'correctness_mixed_batches'
            and mixed.get('timed') is False and mixed.get('measured_run') is None
            and mixed.get('complete') is True and mixed.get('actual_committed_T_count') == 128
            and mixed.get('committed_event_batches') == 40 and mixed.get('batch_sizes_per_span') == [1,2,3,4,6]
            and len(mixed.get('states', [])) == 9 and mixed.get('head_skip_count_delta') == 88
            and mixed.get('head_instructions_restored') is True and 'commit_loop_ms' not in mixed,
            'One unmeasured mixed-batch correctness replay required')
    require(comparison.get('schema') == 'halogen0201.stateful1012-core-append-comparison.v1'
            and comparison.get('exact_endpoint_row_parity') is True
            and comparison.get('compared_endpoint_states') == 81
            and comparison.get('timed_compared_endpoint_states') == 72
            and comparison.get('timed_compared_BF16_values') == 17861040
            and comparison.get('endpoint_indices') == list(range(0, 129, 16))
            and comparison.get('tolerance_relaxed') is False
            and comparison.get('criterion') == 'original exact BF16 byte equality'
            and comparison.get('compared_BF16_values') == 20093670
            and len(comparison.get('runs', [])) == 8
            and all(len(row.get('comparisons', [])) == 9
                and all(item.get('passed') is True and item.get('exact_BF16_bytes_equal') is True
                    and item.get('compared_BF16_values') == 248070 for item in row['comparisons'])
                for row in comparison['runs'])
            and len(comparison.get('correctness_mixed_batches', {}).get('comparisons', [])) == 9
            and all(item.get('passed') is True and item.get('exact_BF16_bytes_equal') is True
                and item.get('compared_BF16_values') == 248070
                for item in comparison['correctness_mixed_batches']['comparisons']),
            'Unchanged exact BF16 endpoint parity failed')
    require(all(report.get(k) is None for k in ('native_acceptance','prefill_tok_s','decode_tok_s','engine_benefit')),
            'Component replay cannot claim measured engine metrics')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--preparation', type=Path, required=True)
    parser.add_argument('--preparation-sha', required=True)
    parser.add_argument('--normal-profile', type=Path, required=True)
    parser.add_argument('--native-wrapper-sha', required=True)
    args = parser.parse_args(); prep = validate_preparation(args.preparation, args.preparation_sha,
        normal_profile=args.normal_profile, wrapper_sha=args.native_wrapper_sha)
    if not args.run:
        print(json.dumps(dict(validated=True, native_execution=False, GPU_lifecycle_actions=False))); return 0
    require(not OUT.exists(), 'Observe retained process/session handles; do not duplicate this job')
    support = load('core_append_existing_support', SUPPORT); support.OUT = OUT
    _, runtime = support.support()
    modules = load('core_append_existing_module_monitor', MODULE_MONITOR)
    seal = json.loads(Path(prep['GPU_baseline_seal']['path']).read_bytes())
    baseline = runtime.verify(args.normal_profile, 8840, require_idle=True)
    require(baseline['identities'] == seal['identities']
            and baseline['outer']['run_id'] == seal['outer']['run_id']
            and baseline['inner']['run_id'] == seal['inner']['run_id'], 'Exact normal-server seal changed')
    OUT.mkdir()
    record = dict(schema='halogen0201.stateful1012-owned-core-append-component.v1', terminal=False,
        completed=False, identity=runtime.ops.ident.process_identity(os.getpid()), baseline=baseline,
        preparation=pin(args.preparation), monitor=pin(__file__), child={}, policy=POLICY,
        native_acceptance=None, prefill_tok_s=None, decode_tok_s=None, engine_benefit=None)
    def save(phase):
        record['phase'] = phase; runtime.ops.atomic(OUT/'handle.json', record)
        state = runtime.ops.read(STATE)
        state['current_work'] = dict(scope='stateful1012_core_append_component', phase=phase,
            identity=record['identity'], handle=str(OUT/'handle.json'), hardware_owner='root',
            server_restore_required=False, do_not_duplicate_live_handles=True, goal_achieved=False)
        runtime.ops.atomic(STATE, state)
    save('normal_verified'); failures = []
    try:
        record['entry_GPU'] = support.local_gpu_admission().observe(runtime, OUT, 'core-append-entry',
            wait_for_idle=True, entry_reserve_gib=22)
        fresh = runtime.verify(args.normal_profile, 8840, require_idle=True)
        require(fresh['identities'] == baseline['identities'], 'GPU identities changed during entry check')
        frame = runtime.ops.host.frame(); record['entry_memory'] = frame
        require(min(frame['available_bytes'], frame['commit_headroom_bytes']) >= 22*2**30,
                '22-GiB entry reserve required immediately before native launch')
        output = OUT/'qualification.json'
        command = [prep['host']['path'], '-B', str(HERE/'qualify_core_append.py'), '--enable-native-component',
            '--dll', prep['native_wrapper']['path'], '--model', prep['model_dir'], '--bundle', prep['bundle_root'],
            '--runtime-dir', prep['runtime_dir'], '--input', prep['input'], '--reference', prep['reference'],
            '--output', str(output), '--deadline-seconds', '110']
        env = dict(os.environ); env['PATH'] = prep['runtime_dir']+';C:\\Windows\\System32;C:\\Windows'
        execute_child(runtime, record['child'], command, cwd=prep['runtime_dir'], env=env,
            log_path=OUT/'qualification.log', baseline=baseline, save=save, module_probe=modules.module_paths)
        record['qualified_loaded_modules'] = prior.qualify_loaded_modules(
            record['child']['module_observations'], prep['required_loaded_modules'])
        require(record['child']['exit_code'] == 0, 'Unused-head child failed; preserve without retry')
        require(not any(k in record['child'] for k in ('own_child_cleanup_error','handle_close_error')),
                'Retained child cleanup did not fully succeed')
        comparison_path = Path(str(output)+'.comparison.json')
        report = runtime.ops.read(output); comparison = runtime.ops.read(comparison_path)
        validate_outputs(report, comparison)
        record.update(completed=True, qualification=pin(output), comparison=pin(comparison_path))
    except BaseException as error: failures.append(failure(error))
    finally:
        try:
            record['post_GPU'] = support.local_gpu_admission().observe(runtime, OUT, 'core-append-after',
                wait_for_idle=True, entry_reserve_gib=18)
        except BaseException as error: failures.append(dict(stage='post_GPU', **failure(error)))
        try:
            final = runtime.verify(args.normal_profile, 8840, require_idle=False)
            require(final['identities'] == baseline['identities'], 'Final GPU identities changed')
            runtime.ops.atomic(OUT/'ready-left-online.json', final); record['server_online'] = True
        except BaseException as error:
            record['server_online'] = False; failures.append(dict(stage='final_server', **failure(error)))
        try:
            frame = runtime.ops.host.frame(); record['final_memory'] = frame
            require(min(frame['available_bytes'], frame['commit_headroom_bytes']) >= 18*2**30,
                    '18-GiB final runtime reserve crossed')
        except BaseException as error: failures.append(dict(stage='final_memory', **failure(error)))
        record.update(terminal=True, ended_utc=utc(), errors=failures)
        save('closed_server_online' if record['server_online'] else 'closed_server_verification_failed')
    print(json.dumps(dict(completed=record['completed'], server_online=record['server_online'], errors=len(failures))))
    return 0 if record['completed'] and not failures else 1


if __name__ == '__main__': raise SystemExit(main())
