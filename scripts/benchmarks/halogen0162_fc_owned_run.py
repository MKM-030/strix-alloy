"""Exclusive original Q8 FC replay with retained job and 18 GiB reserve.

Root runs this after checking actual process/controller/provider handles. It
does not stop or adopt a user engine. Only the frozen tiny FC fixtures and
original GPU code are mounted; no model/NPU/complete-head session is created.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'server/.local/optimization9h-20261004'
BACKEND = ROOT / 'backends/halogen-wsl2-0.16.2'
FIXTURES = WORK / 'fc-fixtures-f47a1312c34f47b6a23188247f46741b'
SOURCE = ROOT / 'scripts/benchmarks/halogen0162_fc_replay.c'
WRAPPER = ROOT / 'scripts/benchmarks/halogen0162_fc_image_wrapper.py'
HSACO = WORK / 'mtp-route-static-20261004/engine-gfx1151.hsaco'
IMAGE = 'ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a'
BINARY = '/home/revn/halogen-re/fc-replay-143eee1a74a048769a70d6668b441f31'
BINARY_SHA = 'fc631bcc9f8aecbf38ec457704481dea74603cead686c7da2405572d892beaae'
sys.path.insert(0, str(ROOT / 'server'))
from host_frames import frame
from winjob import OwnedProcess
sys.path.insert(0, str(BACKEND / 'scripts'))
import runner as backend


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def capture(path, maximum, expected_sha=None, exact_bytes=None):
    """Bind the bytes used by the comparison to one unchanged regular file."""
    path = Path(path)
    before = path.lstat()
    fields = ('st_size', 'st_dev', 'st_ino', 'st_mtime_ns', 'st_ctime_ns')
    identity = lambda value: tuple(getattr(value, field) for field in fields)
    if (not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum or
            exact_bytes is not None and before.st_size != exact_bytes):
        raise RuntimeError('Bounded regular file extent differs: ' + str(path))
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    if (not stat.S_ISREG(opened.st_mode) or len(raw) != before.st_size or
            not identity(before) == identity(opened) == identity(after) == identity(path.lstat())):
        raise RuntimeError('File identity changed while capturing: ' + str(path))
    actual_sha = hashlib.sha256(raw).hexdigest()
    if expected_sha is not None and actual_sha != expected_sha:
        raise RuntimeError('Captured file SHA256 differs: ' + str(path))
    return raw, actual_sha


def idle():
    state = json.loads((ROOT / 'server/.local/current.json').read_text(encoding='utf-8-sig'))
    if state.get('phase') != 'stopped' or state.get('active_requests', 0):
        raise RuntimeError('Engine controller must be stopped/idle; user engine will not be stopped')
    for port in (8731, 8840, 8877, 52628):
        with socket.socket() as connection:
            connection.settimeout(.1)
            if connection.connect_ex(('127.0.0.1', port)) == 0:
                raise RuntimeError('Known engine/provider port remains occupied')
    if backend.docker('ps', '-q'):
        raise RuntimeError('Another container is active; no competing GPU window admitted')


def validate_receipts(replay, runtime, fixture, wrapper_sha):
    required = dict(schema='halogen0162.original-q8-fc-kernel-replay.v1', passed=True,
        engine_sha256='ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b',
        codeobject_sha256='45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83',
        codeobject_engine_offset=331776, codeobject_bytes=17704408,
        K=2560, N=2560, grid=[160, 1, 1], block=[256, 1, 1], shared_bytes=0, default_stream=True,
        static_lds_bytes=0, wave_size=32, kernarg_bytes=40, kernarg_alignment=8, hidden_arguments=False,
        user_argument_offsets=[0, 8, 16, 24, 32], user_argument_types=['u8*', 'u16*', 'u16*', 'i64', 'i64'],
        q8_group_size=64, weight_row_bytes=2720, weight_bytes=6963200, raw_weights_copied_unchanged=True,
        native_arithmetic='affine dequant FMA; decoded-weight BF16 RNE; packed BF16 dot2 FP32 accumulation/reduction; output BF16 RNE',
        embedding_rms_qualified=False, full_D_parity_qualified=False, seed_add_implemented=False,
        full_head_qualified=False, acceptance_claim=False, speed_claim=False, tolerance_adjustment=False,
        arithmetic_fitting=False, logical_calls=4, launch_attempts=4, launches_ok=4, synchronizations_ok=4,
        copies_ok=14, allocations_ok=4, free_ok=4, module_loads=1, module_unloads=1,
        cleanup_errors=0, file_close_errors=0, immutable_files_rechecked=True, output_files_written=4,
        error='', error_code=0, halogen_lq8_wave='1')
    kernels = [dict(branch='embedding', symbol='_ZN7halogen12_GLOBAL__N_16k_lq8wILi1ELi16ELi1EEEvPKhPKtPtll',
                   host_identity_rva='0x18d6690', registration_rva='0x184b596', gpu_entry_rva='0x2d1200', descriptor_rva='0x1fa340', M=1),
               dict(branch='hidden', symbol='_ZN7halogen12_GLOBAL__N_16k_lq8wILi4ELi16ELi1EEEvPKhPKtPtll',
                   host_identity_rva='0x18d66f0', registration_rva='0x184b7be', gpu_entry_rva='0x2d7800', descriptor_rva='0x1fa640', M=4)]
    if any(replay.get(key) != value for key, value in required.items()) or replay.get('kernels') != kernels:
        raise RuntimeError('Original kernel/schema/ABI/arithmetic receipt differs')
    runtime_required = dict(schema='halogen0162.fc-image-runtime-binding.v1', phase='validated-before-exec',
        fixture_manifest_sha256='ae61a7924d985b1fd35e5d87eabd47736dbf20b91958bd5d7003dcf1cdb84f11',
        fixture_preparer_sha256='1fadd3b89872e6a1f9c1d5fecfd459e20c556b2d9039581ca2469ae1a435500c',
        outer_exclusive_gpu_guard_acknowledged=True, outer_owned_job_guard_required=True,
        host_server_observation_performed=False, admission_gib=22, reserve_gib=18,
        read_only_image_required=True, candidate_fixture_mounts_read_only_required=True,
        models_required=False, model_reads_performed=False, halogen_lq8_wave='1',
        embedding_rms_qualified=False, full_d_qualified=False, full_head_qualified=False,
        acceptance_claim=False, speed_claim=False, arithmetic_fitting=False, tolerance_adjustment=False)
    if any(runtime.get(key) != value for key, value in runtime_required.items()):
        raise RuntimeError('Image wrapper guard/scope/fixture binding differs')
    bindings = runtime['file_bindings']
    fixed = {'wrapper': ('/candidate/wrapper.py', wrapper_sha),
        'fc_source': ('/candidate/halogen0162_fc_replay.c', '8535dbe608b49f8bbad8a962359de59e78df1bd0b9cae922045277b6a1d77826'),
        'replay': ('/candidate/replay', BINARY_SHA),
        'bridge': ('/usr/lib/librocdxg.so', '0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6'),
        'engine': ('/candidate/flash_serve', required['engine_sha256']),
        'codeobject': ('/candidate/engine-gfx1151.hsaco', required['codeobject_sha256']),
        'fixtures': ('/fixtures/fixtures.json', runtime_required['fixture_manifest_sha256'])}
    for short, branch in (('e', 'embedding'), ('h', 'hidden')):
        row = fixture['raw_weights'][short]
        fixed[short + '_weight'] = ('/fixtures/' + row['file'], row['sha256'])
        if replay['raw_weight_sha256'][branch] != row['sha256']:
            raise RuntimeError('Native raw-weight lineage differs')
    for label in ('A', 'B'):
        for short in ('e', 'h'):
            row = fixture['inputs'][label][short]
            fixed[label + '_' + short] = ('/fixtures/' + row['file'], row['sha256'])
    if any((bindings[key]['path'], bindings[key]['sha256']) != value for key, value in fixed.items()):
        raise RuntimeError('Wrapper file hashes/paths differ from root/C/fixtures')
    hip_sha = replay['runtime_sha256']
    if (not isinstance(hip_sha, str) or len(hip_sha) != 64 or any(c not in '0123456789abcdef' for c in hip_sha) or
            runtime['sha256'] != hip_sha or bindings['hip']['sha256'] != hip_sha or
            bindings['hip']['path'] != runtime['library']):
        raise RuntimeError('Exact installed HIP path/hash binding differs')
    command = ['/candidate/replay', '/candidate/flash_serve', '/candidate/engine-gfx1151.hsaco', runtime['library'], hip_sha]
    for key in ('e_weight', 'h_weight', 'A_e', 'A_h', 'B_e', 'B_h'):
        command.extend([bindings[key]['path'], bindings[key]['sha256']])
    command.append('/result/native')
    if runtime['command'] != command or len(command) != 18 or len(replay.get('fixtures', [])) != 4:
        raise RuntimeError('Exact FC execution arguments/fixture count differ')
    for li, label in enumerate(('A', 'B')):
        for bi, (short, branch, streams) in enumerate((('e', 'embedding', 1), ('h', 'hidden', 4))):
            row = fixture['inputs'][label][short]
            expected = dict(id=label + '-' + branch, input_sha256=row['sha256'],
                output_file=label + '-' + branch + '-fc-u16.bin', input_bytes=row['bytes'], output_bytes=row['bytes'],
                streams=streams, vectors_completed=streams, output_copied=True, completed=True, nonfinite_output=0)
            if any(replay['fixtures'][li * 2 + bi].get(key) != value for key, value in expected.items()):
                raise RuntimeError('Native FC input/output completion binding differs')


def compare(out, fixture, replay, replay_sha):
    rows = []
    for label_index, label in enumerate(('A', 'B')):
        for branch_index, (short, branch, count) in enumerate((('e', 'embedding', 2560), ('h', 'hidden', 10240))):
            replay_row = replay['fixtures'][label_index * 2 + branch_index]
            name = label + '-' + branch + '-fc-u16.bin'
            actual_path = out / 'native' / name
            raw, output_sha = capture(actual_path, count * 2, replay_row['output_sha256'], count * 2)
            if (len(raw) != count * 2 or replay_row['id'] != label + '-' + branch or
                    replay_row['output_file'] != name or replay_row['output_sha256'] != output_sha or
                    replay_row['input_sha256'] != fixture['inputs'][label][short]['sha256']):
                raise RuntimeError('Native output/input/receipt binding differs')
            actual = struct.unpack('<' + str(count) + 'H', raw)
            values = [struct.unpack('<f', struct.pack('<I', word << 16))[0] for word in actual]
            if not all(math.isfinite(value) for value in values):
                raise RuntimeError('Native projection contains nonfinite values')
            row = dict(label=label, branch=branch, output_sha256=output_sha, comparisons={})
            refs = fixture['references'][label][short]
            for lineage, item in (('original_decoded_FP32_numpy', refs['bf16']),
                                  ('BF16_weight_numpy', refs['bf16_weight_reference']['bf16'])):
                ref_path = FIXTURES / item['file']
                if ref_path.parent != FIXTURES or item['bytes'] != count * 2:
                    raise RuntimeError('Bounded independent frozen projection reference differs')
                ref_raw, _ = capture(ref_path, count * 2, item['sha256'], count * 2)
                expected = struct.unpack('<' + str(count) + 'H', ref_raw)
                reference = [struct.unpack('<f', struct.pack('<I', word << 16))[0] for word in expected]
                row['comparisons'][lineage] = dict(exact_word_mismatches=sum(a != b for a, b in zip(actual, expected)),
                    max_abs_error=max(abs(a - b) for a, b in zip(values, reference)),
                    outside_frozen_cpu_tolerance=sum(abs(a - b) > .0002 + .002 * abs(b) for a, b in zip(values, reference)),
                    tolerance=dict(rtol=.002, atol=.0002), informational_only=True)
            rows.append(row)
    return dict(scope='four original Q8 FC calls on frozen normalized A/B; seed/full-head/NPU excluded',
                replay_sha256=replay_sha, rows=rows, tolerance_adjustment=False,
                arithmetic_fitting=False, speed_claim=False)


def run(wrapper_sha):
    if len(wrapper_sha) != 64 or any(c not in '0123456789abcdef' for c in wrapper_sha):
        raise ValueError('Independent lowercase wrapper SHA256 required')
    pins = {SOURCE: '8535dbe608b49f8bbad8a962359de59e78df1bd0b9cae922045277b6a1d77826',
        WRAPPER: wrapper_sha,
        HSACO: '45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83',
        BACKEND / '.local/flash_serve': 'ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b',
        FIXTURES / 'fixtures.json': 'ae61a7924d985b1fd35e5d87eabd47736dbf20b91958bd5d7003dcf1cdb84f11',
        ROOT / 'server/host_frames.py': '417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8',
        ROOT / 'server/winjob.py': '3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c'}
    pins[Path(__file__)] = sha(__file__)
    for path, expected in pins.items():
        if sha(path) != expected:
            raise ValueError('Sealed input/source changed: ' + str(path))
    # Reject a live user controller before any WSL/container action.
    state = json.loads((ROOT / 'server/.local/current.json').read_text(encoding='utf-8-sig'))
    if state.get('phase') != 'stopped' or state.get('active_requests', 0):
        raise RuntimeError('User engine remains active; replay deferred without shutdown')
    backend.configure()
    idle()
    binary_sha = backend.invoke(backend.WSL + ['sha256sum', BINARY], timeout=20).split()[0]
    if binary_sha != BINARY_SHA:
        raise ValueError('Root-compiled original-kernel replay binary changed')
    fixture_raw, _ = capture(FIXTURES / 'fixtures.json', 1 << 20, pins[FIXTURES / 'fixtures.json'])
    fixture = json.loads(fixture_raw)
    identity = uuid.uuid4().hex
    name = 'alloy-fc-original-' + identity
    out = WORK / name
    out.mkdir(exist_ok=False)

    def write(filename, value):
        with (out / filename).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)

    cid = owner = None
    error = None
    memory = []
    closed = cleanup = False
    stop = threading.Event()
    watch_error = []
    cleanup_lock = threading.Lock()
    create_attempted = create_identity_recovered = False

    def reserve(floor):
        value = dict(time=time.time(), **frame())
        memory.append(value)
        if min(value['available_bytes'], value['commit_headroom_bytes']) < floor * 2**30:
            raise RuntimeError('Host reserve below ' + str(floor) + 'GiB')
        return value

    def verify_container():
        info = backend.inspect(cid)
        if (info['Id'] != cid or info['Name'] != '/' + name or info['Config']['Image'] != IMAGE or
                info['Config']['Labels'].get('strix-alloy.fc-original') != identity):
            raise RuntimeError('Owned container identity differs')
        return info

    def recover_created_identity():
        # A create timeout may occur after the daemon created our container.
        # Recover only its exact UUID name, label and image; never delete by prefix.
        found = backend.docker('ps', '-aq', '--no-trunc', '--filter', 'name=^/' + name + '$',
                               '--filter', 'label=strix-alloy.fc-original=' + identity, timeout=20).split()
        if not found:
            return None
        if len(found) != 1:
            raise RuntimeError('Ambiguous exact owned container recovery')
        info = backend.inspect(found[0])
        if (info['Id'] != found[0] or info['Name'] != '/' + name or info['Config']['Image'] != IMAGE or
                info['Config']['Labels'].get('strix-alloy.fc-original') != identity):
            raise RuntimeError('Recovered container ownership differs')
        return found[0]

    def watch():
        try:
            with (out / 'memory.jsonl').open('x') as stream:
                while not stop.is_set():
                    stream.write(json.dumps(reserve(18)) + '\n')
                    stream.flush()
                    stop.wait(.25)
        except BaseException as exc:
            watch_error.append(type(exc).__name__ + ': ' + str(exc))
            with cleanup_lock:
                if cid and not cleanup:
                    try:
                        if verify_container()['State']['Running']:
                            backend.docker('stop', '-t', '0', cid, timeout=30)
                    except BaseException as shutdown:
                        watch_error.append('guard stop: ' + str(shutdown))

    monitor = threading.Thread(target=watch, daemon=True)
    try:
        reserve(22)
        monitor.start()
        mounts = {'/candidate/replay': BINARY,
            '/candidate/halogen0162_fc_replay.c': backend.linux_path(SOURCE),
            '/candidate/flash_serve': backend.linux_path(BACKEND / '.local/flash_serve'),
            '/candidate/engine-gfx1151.hsaco': backend.linux_path(HSACO),
            '/candidate/wrapper.py': backend.linux_path(WRAPPER),
            '/fixtures': backend.linux_path(FIXTURES),
            '/usr/lib/libdxcore.so': '/usr/lib/wsl/lib/libdxcore.so',
            '/usr/lib/librocdxg.so': backend.MACHINE['dxg'],
            '/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib/librocroller.so.1':
                backend.linux_path(BACKEND / '.local/librocroller-compat.so.1')}
        args = ['create', '--name', name, '--network=none', '--restart=no', '--read-only',
            '--device=/dev/dxg', '--memory=2g', '--memory-swap=2g', '--pids-limit=128',
            '--ipc=private', '--shm-size=64m', '--ulimit=core=0:0', '--ulimit=memlock=-1:-1',
            '--security-opt=seccomp=unconfined', '--security-opt=label=disable',
            '--tmpfs=/tmp:rw,size=64m', '--label=strix-alloy.fc-original=' + identity]
        for dest, source in sorted(mounts.items()):
            args += ['--mount', 'type=bind,src=' + source + ',dst=' + dest + ',readonly']
        args += ['--mount', 'type=bind,src=' + backend.linux_path(out) + ',dst=/result',
            '--env=HSA_ENABLE_DXG_DETECTION=1', '--env=HSA_ENABLE_SDMA=1', '--env=HALOGEN_LQ8_WAVE=1',
            '--env=HSA_DISABLE_COREDUMP_ON_EXCEPTION=1',
            '--env=LD_LIBRARY_PATH=/usr/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib',
            '--entrypoint=timeout', IMAGE, '--signal=TERM', '--kill-after=5s', '60s',
            'python3', '/candidate/wrapper.py', '--source-sha256', wrapper_sha, '--outer-exclusive-gpu-guard']
        write('plan.json', dict(schema=1, identity=identity, image=IMAGE, source_pins={str(p): v for p, v in pins.items()},
            binary_sha256=binary_sha, command=args, native_kernel_calls=4, models_mounted=False,
            npu_initialized=False, timing_claim=False, admission_gib=22, runtime_reserve_gib=18))
        idle()
        create_attempted = True
        cid = backend.docker(*args, timeout=30)
        verify_container()
        write('container.json', dict(id=cid, name=name))
        reserve(22)
        try:
            owner = OwnedProcess([r'C:\Windows\System32\wsl.exe', *backend.WSL[1:], 'docker', 'start', '-a', cid], cwd=ROOT,
                env=dict(os.environ), stdout_path=out / 'stdout.txt', stderr_path=out / 'stderr.txt')
        except BaseException as exc:
            owner = getattr(exc, 'owner', None)
            raise
        write('retained-process.json', owner.identity)
        owner.verify_live_identity()
        idle()
        reserve(22)
        if watch_error or not monitor.is_alive():
            raise RuntimeError('Reserve monitor failed before child resume')
        owner.resume()
        print('NATIVE_STARTED ' + str(out) + ' pid=' + str(owner.identity['pid']), flush=True)
        until = time.monotonic() + 90
        while owner.exit_code() is None:
            if watch_error:
                raise RuntimeError(watch_error[0])
            if time.monotonic() > until:
                raise TimeoutError('Owned native window deadline')
            stop.wait(.1)
        exit_code = owner.exit_code()
        info = verify_container()
        write('terminal.json', info['State'])
        if exit_code != 0 or info['State']['Running'] or info['State']['ExitCode'] != 0 or info['State']['OOMKilled']:
            raise RuntimeError('Native replay/container process failed: ' + str(exit_code))
        replay_raw, replay_sha = capture(out / 'native/replay.json', 32768)
        replay = json.loads(replay_raw)
        runtime_raw, runtime_sha = capture(out / 'runtime.json', 65536)
        runtime = json.loads(runtime_raw)
        validate_receipts(replay, runtime, fixture, wrapper_sha)
        comparisons = compare(out, fixture, replay, replay_sha)
        comparisons['runtime_binding_sha256'] = runtime_sha
        capture(out / 'native/replay.json', 32768, replay_sha)
        capture(out / 'runtime.json', 65536, runtime_sha)
        write('comparison.json', comparisons)
        for path, expected_sha in pins.items():
            if sha(path) != expected_sha:
                raise RuntimeError('Source/input changed during replay')
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc)
    finally:
        try:
            with cleanup_lock:
                if create_attempted and not cid:
                    cid = recover_created_identity()
                    create_identity_recovered = cid is not None
                    if not cid:
                        raise RuntimeError('Create outcome remains unproven; exact container recovery found no ID')
                if cid:
                    info = verify_container()
                    if info['State']['Running']:
                        backend.docker('stop', '-t', '0', cid, timeout=30)
                    info = verify_container()
                    if info['State']['Running'] or info['State']['Pid'] != 0:
                        raise RuntimeError('Owned container still running')
                    backend.docker('rm', cid, timeout=30)
                    cleanup = True
                    if create_identity_recovered:
                        # Evidence-write failure must never skip known-ID cleanup.
                        write('recovered-container.json', dict(id=cid, name=name, identity=identity,
                                                              ambiguous_create_preserved=True,
                                                              container_removed_before_evidence_write=True))
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
        if monitor.is_alive():
            error = (error + '; ' if error else '') + 'reserve monitor remains active'
        try:
            final = frame()
        except BaseException as exc:
            final = dict(error=type(exc).__name__ + ': ' + str(exc))
            error = (error + '; ' if error else '') + 'final memory observation: ' + str(exc)
        if watch_error:
            error = (error + '; ' if error else '') + '; '.join(watch_error)
        write('result.json', dict(passed=error is None and cleanup and closed, error=error,
            own_container_removed=cleanup, own_job_closed=closed, monitor_stopped=not monitor.is_alive(),
            create_attempted=create_attempted, create_identity_recovered=create_identity_recovered,
            cleanup_pending=create_attempted and not cleanup,
            container_name=name, container_id=cid, ownership_label=identity,
            physical_minimum_gib=min((x['available_bytes'] / 2**30 for x in memory), default=None),
            commit_minimum_gib=min((x['commit_headroom_bytes'] / 2**30 for x in memory), default=None),
            final_memory=final, timing_claim=False, npu_initialized=False))
        print('NATIVE_FINISHED ' + str(out) + ' error=' + str(error), flush=True)
    return 0 if error is None and cleanup and closed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wrapper-sha256', required=True)
    raise SystemExit(run(parser.parse_args().wrapper_sha256))
