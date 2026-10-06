"""Root-only finite prepared-W comparison with the user server stopped.

The reviewed normal lifecycle coordinator stops/restores the exact user run.
This worker owns only its UUID-labelled no-model container and Windows job.
No timeout permits a second launch. Serving metrics remain unmeasured.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'server/.local/optimization9h-20261004'
HERE = Path(__file__).resolve().parent
SOURCE, WRAPPER = HERE / 'replay.c', HERE / 'image_wrapper.py'
BACKEND = ROOT / 'backends/halogen-wsl2-0.16.2'
FIXTURES = BASE / 'prefill-ht-capture-9ac79c0cb8c4479189d101c12e6f588f/trace'
HSACO = BASE / 'mtp-route-static-20261004/engine-gfx1151.hsaco'
BINARY = '/home/revn/halogen-re/prefill-deq-replay-20261006-v1'
BINARY_SHA = '69142bb40b6434df6abeb9388c2c0bc4ec8dfaaadf221cce2a8ea94b6329bf4b'
SOURCE_SHA = '0fe60be21173d1f2395725da4ea83aa1210b5d492f3e871927b4e00941d89e5b'
IMAGE = 'ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a'
LABEL = 'strix-alloy.prefill-deq'
INPUTS = {
    'packed.bin': (13107200, 'd27fc76fab0646ba5b675f9dd9137c342a39f70aa980acf62f6959f5fdf0245d'),
    'signs-u16.bin': (5120, '0866b9d9d28380f5f6ea3fdc0fa78a5643db9629c8a3e0094eb01f5b3e33cd7c'),
    'scales-u16.bin': (20480, 'dad8e70f72ce13f67692a184cac608e71986d740d43f72201ee52acc4146061e'),
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scope = load('prefill_deq_guard_helpers', ROOT / 'scripts/benchmarks/halogen_gpu_hidden_q8_fused/owned_run.py')
require, capture, backend = scope.require, scope.capture, scope.backend
frame, OwnedProcess = scope.frame, scope.OwnedProcess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(report):
    require(report.get('schema') == 'halogen.prefill-deq.replay.v1' and report.get('passed') is True,
            'Native exactness/timing qualification failed')
    required = dict(engine_sha256=scope.ENGINE_SHA, codeobject_sha256=scope.CODE_SHA,
        runtime_sha256=scope.HIP_SHA, original_code_from_engine_verified=True,
        N=10240, K=2560, descriptor_mode=4, PRE=1, KFAST=1,
        grid=[20, 80, 1], original_block=[512, 1, 1], candidate_block=[256, 1, 1],
        original_W16=1, candidate_W16=0, default_stream=True, dynamic_shared_bytes=0,
        public_argument_count=6, W_bytes=52428800, W_words=26214400,
        qualification_exact=2, qualification_W_files_written=2, timed_output_files_written=0,
        warmup_pairs=4, measured_pairs=16, qualification_before_timing=True,
        original_poison_byte=255, candidate_poison_byte=165, primer_launches=0,
        run_count=42, pairs_completed=20, launch_attempts=42, launches_ok=42,
        poison_ok=42, pre_sync_ok=42, full_sync_ok=42, copies_ok=45,
        allocations_ok=4, free_ok=4, module_loads=1, module_unloads=1,
        event_creates=2, event_records=80, event_waits=40, event_elapsed=40, event_destroys=2,
        cleanup_sync_attempts=1, cleanup_sync_ok=1, cleanup_errors=0, file_close_errors=0,
        immutable_files_rechecked=True, gemm_qualified=False, prefill_gain_claim=False,
        decode_gain_claim=False, acceptance_claim=False, tolerance_adjustment=False, error='', error_code=0)
    scope.matching(report, required, 'Native ABI/finite-count/cleanup/claim receipt differs')
    require(re.fullmatch('[0-9a-f]{64}', report['oracle_sha256']), 'Missing original oracle hash')
    pairs = report['timing_pairs']
    require(len(pairs) == 20 and report['pairs_completed'] == 20, 'Finite 4+16 pair budget differs')
    for index, row in enumerate(pairs):
        require(row['sequence'] == index and row['measured'] is (index >= 4) and
                row['first_arm'] == ('candidate' if index & 1 else 'original'), 'Pair order differs')
        require(row['outputs_byte_equal'] is True, 'Prepared weights differ')
        require(row['original_output_sha256'] == row['candidate_output_sha256'] == report['oracle_sha256'],
                'Timed output hash differs from complete original oracle')
        for key in ('original_gpu_ms', 'candidate_gpu_ms',
                    'original_host_enqueue_wait_ms', 'candidate_host_enqueue_wait_ms'):
            require(type(row[key]) in (float, int) and math.isfinite(row[key]) and row[key] > 0,
                    'Invalid complete component duration')
    measured = pairs[4:]
    result = dict(schema='halogen.prefill-deq.comparison.v1', excluded_warmup_pairs=4, measured_pairs=16,
                  prepared_W_only=True, complete_prep_GEMM_measured=False,
                  serving_prefill_tok_s=None, serving_decode_tok_s=None, native_acceptance=None)
    for metric in ('gpu_ms', 'host_enqueue_wait_ms'):
        a = [r['original_' + metric] for r in measured]
        b = [r['candidate_' + metric] for r in measured]
        delta = [y - x for x, y in zip(a, b)]
        result[metric] = dict(original_mean=statistics.mean(a), candidate_mean=statistics.mean(b),
                            original_median=statistics.median(a), candidate_median=statistics.median(b),
                            paired_candidate_minus_original_mean=statistics.mean(delta),
                            paired_candidate_minus_original_median=statistics.median(delta),
                            candidate_pair_wins=sum(x < 0 for x in delta),
                            order_groups={name: statistics.mean(r['candidate_' + metric] - r['original_' + metric]
                                for r in measured if r['first_arm'] == name) for name in ('original', 'candidate')})
    return result


def run(wrapper_sha, controller_sha):
    for value in (wrapper_sha, controller_sha, SOURCE_SHA, BINARY_SHA):
        require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'Independent source/build pins required')
    pins = {
        SOURCE: (SOURCE_SHA, None), WRAPPER: (wrapper_sha, None), Path(__file__).resolve(): (controller_sha, None),
        HSACO: ('45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83', 17704408),
        BACKEND / '.local/flash_serve': ('ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b', 26052768),
        Path(scope.__file__): (sha(scope.__file__), None),
    }
    for name, (length, digest) in INPUTS.items():
        pins[FIXTURES / name] = digest, length
    for path, (digest, length) in pins.items():
        capture(path, max(length or (1 << 20), 1 << 20), digest, length)
    scope.stopped_controller()
    backend.configure()
    scope.idle()
    require(backend.invoke(backend.WSL + ['sha256sum', BINARY], timeout=20).split()[0] == BINARY_SHA,
            'Compiled executable changed')
    identity = uuid.uuid4().hex
    name = 'alloy-prefill-deq-' + identity
    out = BASE / name
    out.mkdir(exist_ok=False)
    component = out / 'component'
    component.mkdir()

    def write(name, value):
        with (out / name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write('\n')

    cid = owner = error = None
    create_attempted = job_attempted = removed = closed = False
    memory, watch_error = [], []
    stop, lock = threading.Event(), threading.Lock()

    def reserve(floor):
        value = dict(time=time.time(), **frame())
        memory.append(value)
        require(min(value['available_bytes'], value['commit_headroom_bytes']) >= floor * 2**30,
                'Physical/commit reserve below ' + str(floor) + 'GiB')

    def own_container():
        require(isinstance(cid, str) and re.fullmatch('[0-9a-f]{64}', cid), 'Exact owned container ID required')
        info = backend.inspect(cid)
        require(info['Id'] == cid and info['Name'] == '/' + name and info['Config']['Image'] == IMAGE and
                info['Config']['Labels'].get(LABEL) == identity, 'Owned container identity changed')
        return info

    def watch():
        try:
            while not stop.is_set():
                reserve(18)
                stop.wait(.25)
        except BaseException as exc:
            watch_error.append(type(exc).__name__ + ': ' + str(exc))
            with lock:
                if cid and own_container()['State']['Running']:
                    backend.docker('stop', '-t', '0', cid, timeout=30)

    monitor = threading.Thread(target=watch, daemon=True)
    try:
        reserve(22)
        monitor.start()
        mounts = {
            '/candidate/replay': BINARY,
            '/candidate/replay.c': backend.linux_path(SOURCE),
            '/candidate/wrapper.py': backend.linux_path(WRAPPER),
            '/candidate/flash_serve': backend.linux_path(BACKEND / '.local/flash_serve'),
            '/candidate/engine-gfx1151.hsaco': backend.linux_path(HSACO),
            '/fixtures': backend.linux_path(FIXTURES),
            '/usr/lib/libdxcore.so': '/usr/lib/wsl/lib/libdxcore.so',
            '/usr/lib/librocdxg.so': backend.MACHINE['dxg'],
            '/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib/librocroller.so.1':
                backend.linux_path(BACKEND / '.local/librocroller-compat.so.1'),
        }
        command = ['create', '--name', name, '--network=none', '--restart=no', '--read-only',
            '--device=/dev/dxg', '--memory=2g', '--memory-swap=2g', '--pids-limit=128', '--ipc=private',
            '--shm-size=64m', '--ulimit=core=0:0', '--ulimit=memlock=-1:-1',
            '--security-opt=seccomp=unconfined', '--security-opt=label=disable', '--tmpfs=/tmp:rw,size=64m',
            '--label=' + LABEL + '=' + identity]
        for dest, source in sorted(mounts.items()):
            command += ['--mount', 'type=bind,src=' + source + ',dst=' + dest + ',readonly']
        command += ['--mount', 'type=bind,src=' + backend.linux_path(component) + ',dst=/result',
            '--env=HSA_ENABLE_DXG_DETECTION=1', '--env=HSA_ENABLE_SDMA=1', '--env=HSA_DISABLE_COREDUMP_ON_EXCEPTION=1',
            '--env=LD_LIBRARY_PATH=/usr/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib',
            '--entrypoint=timeout', IMAGE, '--signal=TERM', '--kill-after=5s', '60s', 'python3',
            '/candidate/wrapper.py', '--wrapper-sha256', wrapper_sha, '--outer-exclusive-gpu-guard']
        write('plan.json', dict(command=command, source_pins={str(p): h for p, (h, _) in pins.items()},
                               binary=BINARY, binary_sha256=BINARY_SHA, no_model=True, NPU_executed=False))
        scope.idle()
        reserve(22)
        require(monitor.is_alive() and not watch_error, 'Reserve monitor failed')
        create_attempted = True
        cid = backend.docker(*command, timeout=30)
        own_container()
        write('container.json', dict(id=cid, name=name, identity=identity))
        try:
            job_attempted = True
            owner = OwnedProcess([r'C:\Windows\System32\wsl.exe', *backend.WSL[1:], 'docker', 'start', '-a', cid],
                cwd=ROOT, env=dict(os.environ), stdout_path=out / 'stdout.txt', stderr_path=out / 'stderr.txt')
        except BaseException as exc:
            owner = getattr(exc, 'owner', None)
            if owner is None:
                # The pinned constructor exposes an owner only when its setup
                # cleanup failed. Otherwise it has closed all remaining handles.
                closed = True
            raise
        write('process.json', owner.identity)
        owner.verify_live_identity()
        scope.idle()
        reserve(22)
        require(monitor.is_alive() and not watch_error, 'Reserve monitor failed before resume')
        owner.resume()
        print('PREFILL_DEQ_STARTED ' + str(out), flush=True)
        deadline = time.monotonic() + 90
        while owner.exit_code() is None:
            require(not watch_error, '; '.join(watch_error))
            require(time.monotonic() < deadline, 'Owned process deadline expired; no relaunch')
            stop.wait(.1)
        info = own_container()
        write('terminal.json', info['State'])
        require(owner.exit_code() == 0 and not info['State']['Running'] and
                info['State']['ExitCode'] == 0 and not info['State']['OOMKilled'], 'Component process failed')
        raw, digest = capture(component / 'native/timing.json', 1 << 20)
        report = json.loads(raw)
        comparison = compare(report)
        original, original_sha = capture(component / 'native/original-W.u16', 52428800,
                                         report['oracle_sha256'], 52428800)
        candidate, candidate_sha = capture(component / 'native/candidate-W.u16', 52428800,
                                           report['oracle_sha256'], 52428800)
        require(original == candidate, 'Independent complete prepared-W equality failed')
        comparison['qualification_outputs'] = dict(bytes_each=52428800, words_each=26214400,
            original_sha256=original_sha, candidate_sha256=candidate_sha, independently_byte_equal=True)
        del original, candidate
        runtime = json.loads(capture(component / 'runtime.json', 1 << 20)[0])
        require(runtime['schema'] == 'halogen.prefill-deq.runtime-binding.v1' and
                runtime['bindings']['source']['sha256'] == SOURCE_SHA and
                runtime['bindings']['binary']['sha256'] == BINARY_SHA and
                runtime['bindings']['wrapper']['sha256'] == wrapper_sha, 'Runtime/source binding differs')
        for path, (pin, length) in pins.items():
            capture(path, max(length or (1 << 20), 1 << 20), pin, length)
        reserve(18)
        require(monitor.is_alive() and not watch_error, 'Reserve guard failed before result')
        comparison['raw_sha256'] = digest
        write('comparison.json', comparison)
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc)
    finally:
        try:
            with lock:
                if create_attempted and not cid:
                    found = backend.docker('ps', '-aq', '--no-trunc', '--filter', 'name=^/' + name + '$',
                                           '--filter', 'label=' + LABEL + '=' + identity, timeout=30).splitlines()
                    require(len(found) == 1, 'Ambiguous create cannot prove exact owned ID')
                    cid = found[0]
                if cid:
                    if own_container()['State']['Running']:
                        backend.docker('stop', '-t', '0', cid, timeout=30)
                    info = own_container()
                    require(not info['State']['Running'] and info['State']['Pid'] == 0, 'Owned container remains active')
                    backend.docker('rm', cid, timeout=30)
                    removed = True
        except BaseException as exc:
            error = (error + '; ' if error else '') + 'container cleanup: ' + str(exc)
        try:
            if owner:
                owner.close(timeout_ms=5000)
                closed = bool(owner._closed)
        except BaseException as exc:
            error = (error + '; ' if error else '') + 'job cleanup: ' + str(exc)
        stop.set()
        if monitor.is_alive():
            monitor.join(2)
        if monitor.is_alive() or watch_error:
            error = (error + '; ' if error else '') + 'reserve monitor: ' + '; '.join(watch_error)
        write('memory.json', memory)
        write('result.json', dict(schema='halogen.prefill-deq.owned-result.v1',
              passed=error is None and removed and closed, error=error, own_container_removed=removed,
              own_job_closed=closed, monitor_stopped=not monitor.is_alive(), cleanup_pending=create_attempted and not removed,
              create_attempted=create_attempted, owned_job_attempted=job_attempted,
              cleanup_proven=(not create_attempted or removed) and (not job_attempted or closed),
              container_id=cid, container_name=name, identity=identity,
              minimum_physical_GiB=min((r['available_bytes'] / 2**30 for r in memory), default=None),
              minimum_commit_GiB=min((r['commit_headroom_bytes'] / 2**30 for r in memory), default=None),
              NPU_executed=False, serving_prefill_tok_s=None, serving_decode_tok_s=None, native_acceptance=None))
        print('PREFILL_DEQ_FINISHED ' + str(out) + ' error=' + str(error), flush=True)
    return 0 if error is None and removed and closed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wrapper-sha256', required=True)
    parser.add_argument('--controller-sha256', required=True)
    options = parser.parse_args()
    raise SystemExit(run(options.wrapper_sha256, options.controller_sha256))
