"""Exclusive two-call original embedding RMS replay with retained ownership.

Root checks actual process/controller/provider handles before invocation. A
live user engine is never stopped/adopted. New fixtures, receipts and owned
container/job are separate from FC and hidden RMS. No model/NPU session is
mounted/created; native gather/full-D/head/acceptance/speed remain unqualified.
An observation timeout fails the window and cleans only matching owned IDs;
no create/start/replay retry or engine restart is performed.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
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
FIXTURES = WORK / 'embedding-rms-fixtures-78c49b8e265c4de9adb9c0cf3cc8254e'
SOURCE = ROOT / 'scripts/benchmarks/halogen0162_embedding_rms_replay.c'
WRAPPER = ROOT / 'scripts/benchmarks/halogen0162_embedding_rms_image_wrapper.py'
HSACO = WORK / 'mtp-route-static-20261004/engine-gfx1151.hsaco'
IMAGE = 'ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a'
BINARY_PATTERN = r'/home/revn/halogen-re/embedding-rms-replay-[0-9a-f]{32}'
SOURCE_SHA = '7ea99028014f590a0938d5a06790f51ce571948706d851c16bfcb72f694f4fa8'
ENGINE_SHA = 'ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b'
CODE_SHA = '45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83'
BRIDGE_SHA = '0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6'
HIP_SHA = '6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5'
FIXTURES_SHA = 'cf7ae0ed36d323ae32b6664ed080bc2b3cdd44863878d51719b53ddef9f72246'
PREPARER_SHA = '669c8dcbb18f2f06584d392130cfe52df24516e639315d855f0c74348536edc0'
GAMMA_SHA = '04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86'
sys.path.insert(0,str(ROOT/'server'))
from host_frames import frame
from winjob import OwnedProcess
sys.path.insert(0,str(BACKEND/'scripts'))
import runner as backend


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def capture(path, maximum, expected_sha=None, exact_bytes=None):
    """Bind the bytes used by the comparison to one unchanged regular file."""
    path = Path(path)
    before = path.lstat()
    fields = ('st_size', 'st_dev', 'st_ino', 'st_mtime_ns')
    # Windows path-stat ctime and handle-stat ctime need not be comparable.
    # Check comparable birth time and preserve each API's ctime stability.
    fields += ('st_birthtime_ns',) if os.name == 'nt' else ('st_ctime_ns',)
    identity = lambda value: tuple(getattr(value, field, None) for field in fields)
    if (not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum or
            exact_bytes is not None and before.st_size != exact_bytes):
        raise RuntimeError('Bounded regular file extent differs: ' + str(path))
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    path_after = path.lstat()
    if (not stat.S_ISREG(opened.st_mode) or len(raw) != before.st_size or
            not identity(before) == identity(opened) == identity(after) == identity(path_after) or
            before.st_ctime_ns != path_after.st_ctime_ns or opened.st_ctime_ns != after.st_ctime_ns):
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


def validate_receipts(replay, runtime, fixture, wrapper_sha, binary, binary_sha):
    required = dict(schema='halogen0162.embedding-rms-original-kernel-replay.v1', passed=True,
        engine_sha256=ENGINE_SHA, codeobject_sha256=CODE_SHA,
        kernel_symbol='_ZN7halogen12_GLOBAL__N_117k_rmsnorm_groupedEPKtS2_Ptii',
        host_identity_rva='0x18d5160', registration_rva='0x1848906',
        gpu_entry_rva='0x22d200', descriptor_rva='0x1f6cc0',
        embedding_host_launch_return_rva='0x17db51c', codeobject_engine_offset=331776, codeobject_bytes=17704408,
        width=2560, groups=1, tensor_bytes=5120, grid=[1,1,1], block=[256,1,1],
        shared_bytes=0, default_stream=True, static_lds_bytes=1024, wave_size=32,
        kernarg_bytes=288, kernarg_alignment=8, hidden_arguments=True,
        user_argument_offsets=[0,8,16,24,28], user_argument_types=['u16*','u16*','u16*','i32','i32'],
        input_output_alias=True, raw_gamma_copied_unchanged=True, epsilon_fp32_bits='0x358637bd',
        native_arithmetic='strided FP32 square FMA; LDS pairwise FP32 reduction; full width mean plus epsilon; native rsq; FP32 x*inverse then*(1+raw BF16 gamma); BF16 RNE store',
        table_gather_replayed=False, full_D_parity_qualified=False, full_head_qualified=False,
        acceptance_claim=False, speed_claim=False, tolerance_adjustment=False, arithmetic_fitting=False,
        logical_calls=2, launch_attempts=2, launches_ok=2, synchronizations_ok=2, copies_ok=6,
        allocations_ok=2, free_ok=2, module_loads=1, module_unloads=1, cleanup_errors=0,
        file_close_errors=0, immutable_files_rechecked=True, output_files_written=2, error='', error_code=0,
        runtime_sha256=HIP_SHA)
    if any(replay.get(key) != value for key,value in required.items()):
        raise RuntimeError('Original embedding RMS kernel/schema/ABI/arithmetic receipt differs')
    runtime_required = dict(schema='halogen0162.embedding-rms-image-runtime-binding.v1', phase='validated-before-exec',
        binary_source_path=binary, replay_sha256=binary_sha,
        fixture_manifest_sha256=FIXTURES_SHA, fixture_preparer_sha256=PREPARER_SHA,
        outer_exclusive_gpu_guard_acknowledged=True, outer_owned_job_guard_required=True,
        host_server_observation_performed=False, admission_gib=22, reserve_gib=18,
        read_only_image_required=True, candidate_fixture_mounts_read_only_required=True,
        models_required=False, model_reads_performed=False, table_gather_replayed=False,
        raw_gamma_copied_unchanged=True, input_output_alias=True, embedding_rms_qualified=False,
        full_d_qualified=False, full_head_qualified=False, acceptance_claim=False, speed_claim=False,
        arithmetic_fitting=False, tolerance_adjustment=False, input_provenance=fixture['bindings'])
    if any(runtime.get(key) != value for key,value in runtime_required.items()):
        raise RuntimeError('Image wrapper guard/scope/fixture binding differs')
    bindings = runtime['file_bindings']
    fixed = {'wrapper':('/candidate/wrapper.py',wrapper_sha),
        'rms_source':('/candidate/halogen0162_embedding_rms_replay.c',SOURCE_SHA),
        'replay':('/candidate/replay',binary_sha), 'bridge':('/usr/lib/librocdxg.so',BRIDGE_SHA),
        'engine':('/candidate/flash_serve',ENGINE_SHA), 'codeobject':('/candidate/engine-gfx1151.hsaco',CODE_SHA),
        'fixtures':('/fixtures/fixtures.json',FIXTURES_SHA),
        'gamma':('/fixtures/raw-gamma.u16',GAMMA_SHA)}
    for row in fixture['rows']:
        label = row['label']
        item = row['files'][label+'-input.u16']
        fixed[label+'_input'] = ('/fixtures/'+item['file'],item['sha256'])
    if any((bindings[key]['path'],bindings[key]['sha256']) != value for key,value in fixed.items()):
        raise RuntimeError('Wrapper paths/hashes differ from root/C/fixtures')
    if (runtime['sha256'] != HIP_SHA or bindings['hip']['sha256'] != HIP_SHA or
            bindings['hip']['path'] != runtime['library']):
        raise RuntimeError('Exact installed HIP path/hash binding differs')
    command = ['/candidate/replay','/candidate/flash_serve','/candidate/engine-gfx1151.hsaco',runtime['library'],HIP_SHA]
    for key in ('A_input','gamma','B_input','gamma'):
        command.extend([bindings[key]['path'],bindings[key]['sha256']])
    command.append('/result/native')
    if runtime['command'] != command or len(command) != 14 or len(replay.get('fixtures',[])) != 2:
        raise RuntimeError('Exact embedding RMS execution arguments/fixture count differ')
    for index,row in enumerate(fixture['rows']):
        label = row['label']
        expected = dict(id=label,input_sha256=row['files'][label+'-input.u16']['sha256'],
            raw_gamma_sha256=GAMMA_SHA, output_file=label+'-embedding-rms-u16.bin',
            input_bytes=5120,gamma_bytes=5120,output_bytes=5120,output_copied=True,completed=True,nonfinite_output=0)
        if any(replay['fixtures'][index].get(key) != value for key,value in expected.items()):
            raise RuntimeError('Native RMS input/gamma/output completion binding differs')


def compare(out,fixture,replay,replay_sha):
    rows = []
    for index,fixture_row in enumerate(fixture['rows']):
        label = fixture_row['label']
        replay_row = replay['fixtures'][index]
        name = label+'-embedding-rms-u16.bin'
        raw,output_sha = capture(out/'native'/name,5120,replay_row['output_sha256'],5120)
        actual = struct.unpack('<2560H',raw)
        values = [struct.unpack('<f',struct.pack('<I',word<<16))[0] for word in actual]
        if not all(math.isfinite(value) for value in values):
            raise RuntimeError('Native embedding RMS contains nonfinite values')
        row = dict(label=label,output_sha256=output_sha,comparisons={})
        for lineage,suffix in (('original_NumPy_RMS','-numpy-rms.u16'),('original_ORT_RMS','-ort-rms.u16')):
            item = fixture_row['files'][label+suffix]
            ref_path = FIXTURES/item['file']
            if ref_path.parent != FIXTURES or item['bytes'] != 5120 or item['file'] != label+suffix:
                raise RuntimeError('Bounded frozen normalization reference differs')
            ref_raw,_ = capture(ref_path,5120,item['sha256'],5120)
            expected = struct.unpack('<2560H',ref_raw)
            reference = [struct.unpack('<f',struct.pack('<I',word<<16))[0] for word in expected]
            if not all(math.isfinite(value) for value in reference):
                raise RuntimeError('Frozen normalization reference contains nonfinite values')
            row['comparisons'][lineage] = dict(
                exact_word_mismatches=sum(a!=b for a,b in zip(actual,expected)),
                max_abs_error=max(abs(a-b) for a,b in zip(values,reference)),
                outside_frozen_cpu_tolerance=sum(abs(a-b)>.0002+.002*abs(b) for a,b in zip(values,reference)),
                tolerance=dict(rtol=.002,atol=.0002),informational_only=True)
        rows.append(row)
    return dict(scope='two original in-place embedding RMS calls on frozen A/B; table-gather/full-D/head/NPU excluded',
        replay_sha256=replay_sha,rows=rows,tolerance_adjustment=False,arithmetic_fitting=False,speed_claim=False)


def run(wrapper_sha,controller_sha,binary,binary_sha):
    for value in (wrapper_sha,controller_sha,binary_sha):
        if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Independent lowercase wrapper/controller/binary SHA256 required')
    if re.fullmatch(BINARY_PATTERN,binary) is None:
        raise ValueError('Exact root-compiled embedding RMS replay path required')
    pins = {SOURCE: SOURCE_SHA,
        WRAPPER: wrapper_sha,
        HSACO: CODE_SHA,
        BACKEND / '.local/flash_serve': ENGINE_SHA,
        FIXTURES / 'fixtures.json': FIXTURES_SHA,
        ROOT / 'server/host_frames.py': '417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8',
        ROOT / 'server/winjob.py': '3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c'}
    pins[Path(__file__)] = controller_sha
    for path, expected in pins.items():
        if sha(path) != expected:
            raise ValueError('Sealed input/source changed: ' + str(path))
    # Reject a live user controller before any WSL/container action.
    state = json.loads((ROOT / 'server/.local/current.json').read_text(encoding='utf-8-sig'))
    if state.get('phase') != 'stopped' or state.get('active_requests', 0):
        raise RuntimeError('User engine remains active; replay deferred without shutdown')
    backend.configure()
    idle()
    observed_binary_sha = backend.invoke(backend.WSL + ['sha256sum', binary], timeout=20).split()[0]
    if observed_binary_sha != binary_sha:
        raise ValueError('Root-compiled original-kernel replay binary changed')
    fixture_raw, _ = capture(FIXTURES / 'fixtures.json', 1 << 20, pins[FIXTURES / 'fixtures.json'])
    fixture = json.loads(fixture_raw)
    identity = uuid.uuid4().hex
    name = 'alloy-embedding-rms-original-' + identity
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
                info['Config']['Labels'].get('strix-alloy.embedding-rms-original') != identity):
            raise RuntimeError('Owned container identity differs')
        return info

    def recover_created_identity():
        # A create timeout may occur after the daemon created our container.
        # Recover only its exact UUID name, label and image; never delete by prefix.
        found = backend.docker('ps', '-aq', '--no-trunc', '--filter', 'name=^/' + name + '$',
                               '--filter', 'label=strix-alloy.embedding-rms-original=' + identity, timeout=20).split()
        if not found:
            return None
        if len(found) != 1:
            raise RuntimeError('Ambiguous exact owned container recovery')
        info = backend.inspect(found[0])
        if (info['Id'] != found[0] or info['Name'] != '/' + name or info['Config']['Image'] != IMAGE or
                info['Config']['Labels'].get('strix-alloy.embedding-rms-original') != identity):
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
        mounts = {'/candidate/replay': binary,
            '/candidate/halogen0162_embedding_rms_replay.c': backend.linux_path(SOURCE),
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
            '--tmpfs=/tmp:rw,size=64m', '--label=strix-alloy.embedding-rms-original=' + identity]
        for dest, source in sorted(mounts.items()):
            args += ['--mount', 'type=bind,src=' + source + ',dst=' + dest + ',readonly']
        args += ['--mount', 'type=bind,src=' + backend.linux_path(out) + ',dst=/result',
            '--env=HSA_ENABLE_DXG_DETECTION=1', '--env=HSA_ENABLE_SDMA=1', '--env=HALOGEN_LQ8_WAVE=1',
            '--env=HSA_DISABLE_COREDUMP_ON_EXCEPTION=1',
            '--env=LD_LIBRARY_PATH=/usr/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib',
            '--entrypoint=timeout', IMAGE, '--signal=TERM', '--kill-after=5s', '60s',
            'python3', '/candidate/wrapper.py', '--source-sha256', wrapper_sha,
            '--binary-source-path', binary, '--replay-sha256', binary_sha, '--outer-exclusive-gpu-guard']
        write('plan.json', dict(schema=1, identity=identity, image=IMAGE, source_pins={str(p): v for p, v in pins.items()},
            binary_path=binary, binary_sha256=binary_sha, command=args, native_kernel_calls=2, models_mounted=False,
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
        validate_receipts(replay, runtime, fixture, wrapper_sha, binary, binary_sha)
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
    parser.add_argument('--controller-sha256', required=True)
    parser.add_argument('--binary', required=True)
    parser.add_argument('--binary-sha256', required=True)
    options = parser.parse_args()
    raise SystemExit(run(options.wrapper_sha256,options.controller_sha256,options.binary,options.binary_sha256))
