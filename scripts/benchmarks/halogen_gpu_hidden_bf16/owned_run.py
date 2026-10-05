"""One exclusive, owned original/candidate GPU H timing window.

Root prepares and verifies the stopped server before invoking this controller.
The controller rejects active ports/containers, retains its own suspended job,
and removes only the exact UUID container that it created. Admission requires
22 GiB physical/commit headroom; a continuous 18 GiB reserve guards the window.
No model mount, NPU session, engine hook, full-head, acceptance or prefill claim.
A timeout fails the window; no create/start/replay retry or restart is made.
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


ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / 'server/.local/optimization9h-20261004'
BACKEND = ROOT / 'backends/halogen-wsl2-0.16.2'
HERE = ROOT / 'scripts/benchmarks/halogen_gpu_hidden_bf16'
SOURCE = HERE / 'replay.c'
WRAPPER = HERE / 'image_wrapper.py'
FIXTURES = WORK / 'fc-fixtures-f47a1312c34f47b6a23188247f46741b'
HSACO = WORK / 'mtp-route-static-20261004/engine-gfx1151.hsaco'
CANDIDATE = WORK / 'gpu-hidden-bf16-build-3d8f021748a24748b2a241348d3cbb96/hidden-bf16.hsaco'
BF16 = WORK / 'gpu-hidden-bf16-prepared-8b92a2862ca548249a1c5e1ff099fa7a/hidden-row-major-bf16.bin'
IMAGE = 'ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a'
BINARY = '/home/revn/halogen-re/gpu-hidden-bf16-replay-672dceacdb4d44f18639b8b6e400a736'
BINARY_SHA = 'a5392de7d6dbf8677effb11fbde5f203ac0577a47197db5bc9d793d1ee7cb032'
SOURCE_SHA = '7c8fbd355997b0eed15e812958b714fbf00af9f8d1bcebacef66c04163ca4941'
ENGINE_SHA = 'ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b'
CODE_SHA = '45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83'
CANDIDATE_SHA = '50cb29fde867f1a3a9c58e41bd3bfaf1bbde4941ab75076918eac8a39eb53a4b'
BF16_SHA = '6c324951fa67bf51b66e3911f1dc31560f05a18f5143312714c47f7d38acb008'
BRIDGE_SHA = '0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6'
HIP_SHA = '6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5'
FIXTURES_SHA = 'ae61a7924d985b1fd35e5d87eabd47736dbf20b91958bd5d7003dcf1cdb84f11'
RAW_SHA = '018511894df3996e3a2fcb1dff60860c45a808b65036fd38db472b6e985bdd3f'
INPUT_SHA = {
    'A': 'bf43576e6a9d47efb9a15bcba42d74618ade2ea64b025e747d1c6960e2ddff34',
    'B': '0a46c80b3de775d94eee31b1ca4b3927fe8368353f12f5a40314d88591a31711'}
OUTPUT_SHA = {
    'A': '9a5ee795e87adaf5b1778dfc5e108789fbef4731b5d8d323bf6279435c743fcc',
    'B': 'cd2b863552798729181fe5670859f3f272ddd694370c2803b84271b3c456a138'}
ORIGINAL_SYMBOL = '_ZN7halogen12_GLOBAL__N_16k_lq8wILi4ELi16ELi1EEEvPKhPKtPtll'
CANDIDATE_SYMBOL = 'halogen_gpu_hidden_bf16'
LABEL_KEY = 'strix-alloy.gpu-hidden-bf16'
HIP_BASE = '/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/'
sys.path.insert(0, str(ROOT / 'server'))
from host_frames import frame
from winjob import OwnedProcess
sys.path.insert(0, str(BACKEND / 'scripts'))
import runner as backend


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None,
            'Independent lowercase wrapper/controller SHA256 required')
    return value


def capture(path, maximum, expected_sha=None, exact_bytes=None):
    """Bind compared bytes to an unchanged bounded regular file."""
    path = Path(path)
    before = path.lstat()
    fields = ('st_size', 'st_dev', 'st_ino', 'st_mtime_ns')
    fields += ('st_birthtime_ns',) if os.name == 'nt' else ('st_ctime_ns',)
    identity = lambda value: tuple(getattr(value, field, None) for field in fields)
    require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum and
            (exact_bytes is None or before.st_size == exact_bytes),
            'Bounded regular file extent differs: ' + str(path))
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    path_after = path.lstat()
    require(stat.S_ISREG(opened.st_mode) and len(raw) == before.st_size and
            identity(before) == identity(opened) == identity(after) == identity(path_after) and
            before.st_ctime_ns == path_after.st_ctime_ns and opened.st_ctime_ns == after.st_ctime_ns,
            'File identity changed while capturing: ' + str(path))
    actual_sha = hashlib.sha256(raw).hexdigest()
    require(expected_sha is None or actual_sha == expected_sha,
            'Captured file SHA256 differs: ' + str(path))
    return raw, actual_sha


def stopped_controller():
    state = json.loads((ROOT / 'server/.local/current.json').read_text(encoding='utf-8-sig'))
    require(state.get('phase') == 'stopped' and state.get('active_requests', 0) == 0,
            'User engine remains active; GPU replay deferred without shutdown')


def idle():
    stopped_controller()
    for port in (8731, 8840, 8877, 52628):
        with socket.socket() as connection:
            connection.settimeout(.1)
            require(connection.connect_ex(('127.0.0.1', port)) != 0,
                    'Known engine/provider port remains occupied')
    require(not backend.docker('ps', '-q'), 'Another container is active; GPU window not admitted')


def matching(record, expected, message):
    require(isinstance(record, dict) and all(key in record and type(record[key]) is type(value) and
            record[key] == value for key, value in expected.items()), message)


def finite_time(value, positive=False):
    return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)


def validate_receipts(replay, runtime, fixture, wrapper_sha):
    required = dict(schema='halogen.gpu-hidden-bf16.replay.v1', passed=True,
        engine_sha256=ENGINE_SHA, original_codeobject_sha256=CODE_SHA,
        candidate_codeobject_sha256=CANDIDATE_SHA, candidate_codeobject_bytes=5928,
        runtime_sha256=HIP_SHA, raw_weight_sha256=RAW_SHA, decoded_row_major_sha256=BF16_SHA,
        input_sha256=[INPUT_SHA['A'], INPUT_SHA['B']],
        expected_output_sha256=[OUTPUT_SHA['A'], OUTPUT_SHA['B']],
        original_symbol=ORIGINAL_SYMBOL, candidate_symbol=CANDIDATE_SYMBOL,
        K=2560, N=2560, M=4, grid=[160, 1, 1], block=[256, 1, 1],
        default_stream=True, dynamic_shared_bytes=0, public_argument_count=5,
        raw_weight_bytes=6963200, bf16_weight_bytes=13107200,
        input_bytes_each=20480, output_bytes_each=20480,
        warmup_pairs=4, measured_pairs=16, first_pair_is_warmup=True,
        balanced_A_B_and_arm_order=True, input_sequence='A,B,B,A repeated',
        pairs_completed=20, outputs_equal=40, launch_attempts=40, launches_ok=40,
        copies_ok=84, allocations_ok=6, free_ok=6, module_loads=2, module_unloads=2,
        event_creates=3, event_records=60, event_waits=20, event_elapsed=60, event_destroys=3,
        cleanup_sync_attempts=1, cleanup_sync_ok=1, cleanup_errors=0, file_close_errors=0,
        immutable_files_rechecked=True, output_files_written=4,
        full_head_qualified=False, acceptance_claim=False, end_to_end_speed_claim=False,
        prefill_gain_claim=False, tolerance_adjustment=False, arithmetic_fitting=False,
        error='', error_code=0)
    matching(replay, required, 'GPU H replay schema/ABI/hash/count/scope receipt differs')
    require(finite_time(replay.get('initialization_host_ms')), 'Invalid initialization time')
    pairs = replay.get('timing_pairs')
    require(isinstance(pairs, list) and len(pairs) == 20, 'Exact 4 warmup/16 measured pairs required')
    for index, row in enumerate(pairs):
        matching(row, dict(sequence=index, label='B' if ((index ^ (index >> 1)) & 1) else 'A',
            first_arm='candidate' if index & 1 else 'original', measured=index >= 4,
            outputs_byte_equal=True), 'Paired input/arm order or equality receipt differs')
        require(all(finite_time(row.get(key)) for key in
                    ('original_gpu_ms', 'candidate_gpu_ms', 'host_pair_enqueue_wait_ms')) and
                finite_time(row.get('pair_gpu_ms'), positive=True), 'Invalid paired timing')
    runtime_required = dict(schema='halogen.gpu-hidden-bf16.image-runtime-binding.v1',
        phase='validated-before-exec', binary_source_path=BINARY, replay_sha256=BINARY_SHA,
        fixture_manifest_sha256=FIXTURES_SHA, decoded_row_major_sha256=BF16_SHA,
        original_codeobject_sha256=CODE_SHA, candidate_codeobject_sha256=CANDIDATE_SHA,
        outer_exclusive_gpu_guard_acknowledged=True, outer_owned_job_guard_required=True,
        host_server_observation_performed=False, admission_gib=22, reserve_gib=18,
        read_only_image_required=True, candidate_fixture_mounts_read_only_required=True,
        models_required=False, model_reads_performed=False, npu_initialized=False,
        warmup_pairs=4, measured_pairs=16, alternating_arm_order=True,
        full_head_qualified=False, acceptance_claim=False, end_to_end_speed_claim=False,
        prefill_gain_claim=False, arithmetic_fitting=False, tolerance_adjustment=False)
    matching(runtime, runtime_required, 'Image wrapper guard/scope/fixture binding differs')
    fixed = {
        'wrapper': ('/candidate/wrapper.py', wrapper_sha, None),
        'source': ('/candidate/replay.c', SOURCE_SHA, None),
        'replay': ('/candidate/replay', BINARY_SHA, None),
        'bridge': ('/usr/lib/librocdxg.so', BRIDGE_SHA, None),
        'engine': ('/candidate/flash_serve', ENGINE_SHA, 26052768),
        'codeobject': ('/candidate/engine-gfx1151.hsaco', CODE_SHA, 17704408),
        'candidate': ('/candidate/hidden-bf16.hsaco', CANDIDATE_SHA, 5928),
        'decoded': ('/candidate/hidden-row-major-bf16.bin', BF16_SHA, 13107200),
        'fixtures': ('/fixtures/fixtures.json', FIXTURES_SHA, 9656),
        'raw_weight': ('/fixtures/h-weight.q8g64', RAW_SHA, 6963200),
        'A_input': ('/fixtures/A-h-norm.u16', INPUT_SHA['A'], 20480),
        'B_input': ('/fixtures/B-h-norm.u16', INPUT_SHA['B'], 20480)}
    bindings = runtime.get('file_bindings')
    require(isinstance(bindings, dict) and set(bindings) == set(fixed) | {'hip'},
            'Exact mounted file binding set required')
    for key, (path, expected_sha, exact_bytes) in fixed.items():
        matching(bindings[key], dict(path=path, sha256=expected_sha), 'Mounted path/hash binding differs')
        require(type(bindings[key].get('bytes')) is int and bindings[key]['bytes'] > 0 and
                (exact_bytes is None or bindings[key]['bytes'] == exact_bytes), 'Mounted extent differs')
    library = runtime.get('library')
    require(isinstance(library, str) and library.startswith(HIP_BASE) and
            Path(library).name.startswith('libamdhip64.so') and '..' not in library.split('/'),
            'Exact installed HIP package path required')
    matching(bindings['hip'], dict(path=library, sha256=HIP_SHA), 'Installed HIP binding differs')
    require(runtime.get('sha256') == HIP_SHA, 'Installed HIP runtime hash differs')
    command = ['/candidate/replay', '/candidate/flash_serve', '/candidate/engine-gfx1151.hsaco',
        '/candidate/hidden-bf16.hsaco', CANDIDATE_SHA, library, HIP_SHA,
        '/fixtures/h-weight.q8g64', '/candidate/hidden-row-major-bf16.bin',
        '/fixtures/A-h-norm.u16', '/fixtures/B-h-norm.u16', '/result/native']
    require(runtime.get('command') == command and len(command) == 12, 'Exact execution arguments differ')
    require(fixture.get('schema') == 1 and fixture['raw_weights']['h']['entry']['dims'] == [2560, 2560],
            'Frozen H manifest geometry differs')
    matching(fixture['raw_weights']['h'], dict(file='h-weight.q8g64', bytes=6963200, sha256=RAW_SHA),
             'Frozen raw H weight record differs')
    for label in ('A', 'B'):
        matching(fixture['inputs'][label]['h'], dict(file=label + '-h-norm.u16', bytes=20480,
            sha256=INPUT_SHA[label], shape=[1, 10240], source='original native hidden RMS'),
            'Frozen native whole-row-normalized H input differs')


def compare(out, replay, replay_sha):
    outputs = []
    for label in ('A', 'B'):
        original, original_sha = capture(out / 'native' / (label + '-original-hidden-u16.bin'),
                                         20480, OUTPUT_SHA[label], 20480)
        candidate, candidate_sha = capture(out / 'native' / (label + '-candidate-hidden-u16.bin'),
                                           20480, OUTPUT_SHA[label], 20480)
        require(original == candidate, 'Candidate/native H output bytes differ')
        require(all((word & 0x7f80) != 0x7f80 for (word,) in struct.iter_unpack('<H', original)),
                'Hidden output contains nonfinite BF16 values')
        outputs.append(dict(label=label, original_sha256=original_sha, candidate_sha256=candidate_sha,
                            bytes=20480, exact_word_mismatches=0, nonfinite_values=0))
    measured = replay['timing_pairs'][4:]
    timings = {}
    for arm in ('original', 'candidate'):
        values = [row[arm + '_gpu_ms'] for row in measured]
        timings[arm] = dict(mean_gpu_ms=sum(values) / len(values), minimum_gpu_ms=min(values),
                            maximum_gpu_ms=max(values), measured_pairs=len(values))
    delta = [row['original_gpu_ms'] - row['candidate_gpu_ms'] for row in measured]
    timings['paired_original_minus_candidate'] = dict(mean_gpu_ms=sum(delta) / len(delta),
        minimum_gpu_ms=min(delta), maximum_gpu_ms=max(delta), measured_pairs=len(delta))
    return dict(schema='halogen.gpu-hidden-bf16.comparison.v1',
        scope='standalone fixed M4 hidden FC on frozen A/B; resident GPU event comparison only',
        timing_scope=replay['timing_scope'], host_pair_scope=replay['host_pair_scope'],
        initialization_host_ms=replay['initialization_host_ms'], replay_sha256=replay_sha,
        outputs=outputs, timings=timings, output_bytes_equal=True,
        full_head_qualified=False, acceptance_claim=False, end_to_end_speed_claim=False,
        prefill_gain_claim=False, tolerance_adjustment=False, arithmetic_fitting=False)


def run(wrapper_sha, controller_sha):
    wrapper_sha, controller_sha = digest(wrapper_sha), digest(controller_sha)
    pins = {
        SOURCE: (SOURCE_SHA, 1 << 20, None), WRAPPER: (wrapper_sha, 1 << 20, None),
        Path(__file__).resolve(): (controller_sha, 1 << 20, None),
        HSACO: (CODE_SHA, 17704408, 17704408), CANDIDATE: (CANDIDATE_SHA, 5928, 5928),
        BF16: (BF16_SHA, 13107200, 13107200),
        BACKEND / '.local/flash_serve': (ENGINE_SHA, 26052768, 26052768),
        FIXTURES / 'fixtures.json': (FIXTURES_SHA, 9656, 9656),
        FIXTURES / 'h-weight.q8g64': (RAW_SHA, 6963200, 6963200),
        FIXTURES / 'A-h-norm.u16': (INPUT_SHA['A'], 20480, 20480),
        FIXTURES / 'B-h-norm.u16': (INPUT_SHA['B'], 20480, 20480),
        ROOT / 'server/host_frames.py': ('417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8', 1 << 20, None),
        ROOT / 'server/winjob.py': ('3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c', 1 << 20, None)}
    for path, (expected_sha, maximum, exact_bytes) in pins.items():
        capture(path, maximum, expected_sha, exact_bytes)
    # This observation precedes every WSL/container action in this invocation.
    stopped_controller()
    backend.configure()
    idle()
    require(backend.invoke(backend.WSL + ['sha256sum', BINARY], timeout=20).split()[0] == BINARY_SHA,
            'Root-compiled replay binary changed')
    fixture_raw, _ = capture(FIXTURES / 'fixtures.json', 9656, FIXTURES_SHA, 9656)
    fixture = json.loads(fixture_raw)
    identity = uuid.uuid4().hex
    name = 'alloy-gpu-hidden-bf16-' + identity
    out = WORK / name
    out.mkdir(exist_ok=False)

    def write(filename, value):
        with (out / filename).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write('\n')

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
        require(min(value['available_bytes'], value['commit_headroom_bytes']) >= floor * 2**30,
                'Host reserve below ' + str(floor) + ' GiB')
        return value

    def verify_container():
        require(isinstance(cid, str) and re.fullmatch('[0-9a-f]{64}', cid) is not None,
                'Exact full owned container ID required')
        info = backend.inspect(cid)
        require(info['Id'] == cid and info['Name'] == '/' + name and info['Config']['Image'] == IMAGE and
                info['Config']['Labels'].get(LABEL_KEY) == identity, 'Owned container identity differs')
        return info

    def recover_created_identity():
        found = backend.docker('ps', '-aq', '--no-trunc', '--filter', 'name=^/' + name + '$',
                               '--filter', 'label=' + LABEL_KEY + '=' + identity, timeout=20).split()
        if not found:
            return None
        require(len(found) == 1 and re.fullmatch('[0-9a-f]{64}', found[0]) is not None,
                'Ambiguous exact owned container recovery')
        info = backend.inspect(found[0])
        require(info['Id'] == found[0] and info['Name'] == '/' + name and info['Config']['Image'] == IMAGE and
                info['Config']['Labels'].get(LABEL_KEY) == identity, 'Recovered container ownership differs')
        return found[0]

    def watch():
        try:
            with (out / 'memory.jsonl').open('x') as stream:
                while not stop.is_set():
                    stream.write(json.dumps(reserve(18), allow_nan=False) + '\n')
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
        mounts = {
            '/candidate/replay': BINARY,
            '/candidate/replay.c': backend.linux_path(SOURCE),
            '/candidate/flash_serve': backend.linux_path(BACKEND / '.local/flash_serve'),
            '/candidate/engine-gfx1151.hsaco': backend.linux_path(HSACO),
            '/candidate/hidden-bf16.hsaco': backend.linux_path(CANDIDATE),
            '/candidate/hidden-row-major-bf16.bin': backend.linux_path(BF16),
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
            '--tmpfs=/tmp:rw,size=64m', '--label=' + LABEL_KEY + '=' + identity]
        for dest, source in sorted(mounts.items()):
            args += ['--mount', 'type=bind,src=' + source + ',dst=' + dest + ',readonly']
        args += ['--mount', 'type=bind,src=' + backend.linux_path(out) + ',dst=/result',
            '--env=HSA_ENABLE_DXG_DETECTION=1', '--env=HSA_ENABLE_SDMA=1', '--env=HALOGEN_LQ8_WAVE=1',
            '--env=HSA_DISABLE_COREDUMP_ON_EXCEPTION=1',
            '--env=LD_LIBRARY_PATH=/usr/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib',
            '--entrypoint=timeout', IMAGE, '--signal=TERM', '--kill-after=5s', '60s',
            'python3', '/candidate/wrapper.py', '--source-sha256', wrapper_sha, '--outer-exclusive-gpu-guard']
        write('plan.json', dict(schema='halogen.gpu-hidden-bf16.owned-plan.v1', identity=identity,
            image=IMAGE, source_pins={str(path): value[0] for path, value in pins.items()},
            binary_path=BINARY, binary_sha256=BINARY_SHA, command=args, kernel_launches=40,
            warmup_pairs=4, measured_pairs=16, models_mounted=False, npu_initialized=False,
            end_to_end_speed_claim=False, prefill_gain_claim=False, admission_gib=22, runtime_reserve_gib=18))
        idle()
        reserve(22)
        require(not watch_error and monitor.is_alive(), 'Reserve monitor failed before container create')
        create_attempted = True
        cid = backend.docker(*args, timeout=30)
        verify_container()
        write('container.json', dict(id=cid, name=name, identity=identity))
        reserve(22)
        try:
            owner = OwnedProcess([r'C:\Windows\System32\wsl.exe', *backend.WSL[1:], 'docker', 'start', '-a', cid],
                cwd=ROOT, env=dict(os.environ), stdout_path=out / 'stdout.txt', stderr_path=out / 'stderr.txt')
        except BaseException as exc:
            owner = getattr(exc, 'owner', None)
            raise
        write('retained-process.json', owner.identity)
        owner.verify_live_identity()
        idle()
        reserve(22)
        require(not watch_error and monitor.is_alive(), 'Reserve monitor failed before child resume')
        owner.resume()
        print('NATIVE_STARTED ' + str(out) + ' pid=' + str(owner.identity['pid']), flush=True)
        until = time.monotonic() + 90
        while owner.exit_code() is None:
            require(not watch_error, watch_error[0] if watch_error else 'Reserve monitor failed')
            if time.monotonic() > until:
                raise TimeoutError('Owned native window deadline')
            stop.wait(.1)
        exit_code = owner.exit_code()
        info = verify_container()
        write('terminal.json', info['State'])
        require(exit_code == 0 and not info['State']['Running'] and info['State']['ExitCode'] == 0 and
                not info['State']['OOMKilled'], 'Native replay/container process failed: ' + str(exit_code))
        replay_raw, replay_sha = capture(out / 'native/timing.json', 65536)
        runtime_raw, runtime_sha = capture(out / 'runtime.json', 65536)
        replay, runtime = json.loads(replay_raw), json.loads(runtime_raw)
        validate_receipts(replay, runtime, fixture, wrapper_sha)
        comparisons = compare(out, replay, replay_sha)
        comparisons['runtime_binding_sha256'] = runtime_sha
        capture(out / 'native/timing.json', 65536, replay_sha)
        capture(out / 'runtime.json', 65536, runtime_sha)
        for label in ('A', 'B'):
            for arm in ('original', 'candidate'):
                capture(out / 'native' / (label + '-' + arm + '-hidden-u16.bin'), 20480, OUTPUT_SHA[label], 20480)
        for path, (expected_sha, maximum, exact_bytes) in pins.items():
            capture(path, maximum, expected_sha, exact_bytes)
        require(backend.invoke(backend.WSL + ['sha256sum', BINARY], timeout=20).split()[0] == BINARY_SHA,
                'Root-compiled replay binary changed during window')
        reserve(18)
        require(not watch_error and monitor.is_alive(), 'Reserve monitor failed before qualification')
        write('comparison.json', comparisons)
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc)
    finally:
        try:
            with cleanup_lock:
                if create_attempted and not cid:
                    cid = recover_created_identity()
                    create_identity_recovered = cid is not None
                    require(cid is not None, 'Create outcome unproven; exact recovery found no owned ID')
                if cid:
                    info = verify_container()
                    if info['State']['Running']:
                        backend.docker('stop', '-t', '0', cid, timeout=30)
                    info = verify_container()
                    require(not info['State']['Running'] and info['State']['Pid'] == 0,
                            'Owned container still running')
                    backend.docker('rm', cid, timeout=30)
                    cleanup = True
                    if create_identity_recovered:
                        write('recovered-container.json', dict(id=cid, name=name, identity=identity,
                            ambiguous_create_preserved=True, container_removed_before_evidence_write=True))
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
        write('result.json', dict(schema='halogen.gpu-hidden-bf16.owned-result.v1',
            passed=error is None and cleanup and closed, error=error,
            own_container_removed=cleanup, own_job_closed=closed, monitor_stopped=not monitor.is_alive(),
            create_attempted=create_attempted, create_identity_recovered=create_identity_recovered,
            cleanup_pending=create_attempted and not cleanup, container_name=name, container_id=cid,
            ownership_label=identity,
            physical_minimum_gib=min((x['available_bytes'] / 2**30 for x in memory), default=None),
            commit_minimum_gib=min((x['commit_headroom_bytes'] / 2**30 for x in memory), default=None),
            final_memory=final, npu_initialized=False, full_head_qualified=False, acceptance_claim=False,
            end_to_end_speed_claim=False, prefill_gain_claim=False))
        print('NATIVE_FINISHED ' + str(out) + ' error=' + str(error), flush=True)
    return 0 if error is None and cleanup and closed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wrapper-sha256', required=True)
    parser.add_argument('--controller-sha256', required=True)
    options = parser.parse_args()
    raise SystemExit(run(options.wrapper_sha256, options.controller_sha256))
