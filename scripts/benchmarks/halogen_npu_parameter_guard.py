"""Tiny parameterized-matrix owned-job probe; launch only after root review/grant."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
PY = Path(r'C:\AI\runtimes\winml-npu\Scripts\python.exe')
BUILDER = ROOT / 'scripts/benchmarks/halogen_npu_expert_onnx.py'
PROBE = ROOT / 'scripts/benchmarks/halogen_npu_parameter_probe.py'
TESTS = ROOT / 'scripts/benchmarks/tests/test_halogen_npu_parameter_probe.py'
EXPECTED_BUILDER = '900a4deb32b86a48c6c132bf1326a3174bc5ef11482fd88b98005d0c40a4b722'
EP_DIR = Path(r'C:\AI\halogen-mtp-npu\npu-ep-1.8.75-20261004')
EP_MANIFEST = Path(r'C:\AI\halogen-mtp-npu\provider-copy-20261004.json')
EXPECTED_EP_MANIFEST = '649a90d988b29c7dd4f8b1b57da902d435fb406db13d5a1cc18086907afa83a1'
sys.path.insert(0, str(ROOT / 'server'))
from host_frames import frame
from winjob import OwnedProcess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--npu-timeout', type=int, default=180)
parser.add_argument('--expected-probe-sha256', required=True)
parser.add_argument('--expected-runner-sha256', required=True)
parser.add_argument('--expected-tests-sha256', required=True)
args = parser.parse_args()
if not 1 <= args.npu_timeout <= 180:
    parser.error('NPU stage deadline must be 1..180 seconds')
for value in (args.expected_probe_sha256, args.expected_runner_sha256, args.expected_tests_sha256):
    if len(value) != 64 or any(char not in '0123456789abcdef' for char in value):
        parser.error('reviewed source identities must be lowercase SHA-256 values')
args.out.mkdir(parents=True, exist_ok=False)
GIB = 1024**3
child = None
owner_lock = threading.RLock()
done = threading.Event()
guard_ready = threading.Event()
errors = []
rows = []
min_available = float('inf')
min_commit = float('inf')
sources = {}


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def verify_sources():
    for name, expected in sources.items():
        if digest(Path(name)) != expected:
            raise RuntimeError('Frozen launch source changed: ' + name)


def write(name, data):
    (args.out / name).write_text(json.dumps(data, indent=2), encoding='utf-8')


def quiet_gpu():
    state = json.loads((ROOT / 'server/.local/current.json').read_text(encoding='utf-8-sig'))
    if state.get('phase') not in ('stopped', 'failed') or state.get('active_requests', 0):
        raise RuntimeError('GPU controller is not terminal and idle')
    for port in (8731, 8840, 8877, 52628):
        with socket.socket() as connection:
            connection.settimeout(.1)
            if connection.connect_ex(('127.0.0.1', port)) == 0:
                raise RuntimeError('Known engine/NPU port is still occupied: ' + str(port))
    return state


def reserve(minimum):
    snapshot = frame()
    if min(snapshot['available_bytes'], snapshot['commit_headroom_bytes']) < minimum * GIB:
        raise RuntimeError(f'Physical/commit headroom below {minimum} GiB')
    return snapshot


def stop_own_child():
    global child
    with owner_lock:
        if child is not None:
            child.close(timeout_ms=5000)


def watch():
    global min_available, min_commit
    try:
        with (args.out / 'memory.jsonl').open('x', encoding='utf-8') as output:
            while not done.is_set():
                snapshot = reserve(18)
                min_available = min(min_available, snapshot['available_bytes'] / GIB)
                min_commit = min(min_commit, snapshot['commit_headroom_bytes'] / GIB)
                quiet_gpu()
                verify_sources()
                output.write(json.dumps({'time': time.time(), **snapshot}) + '\n')
                output.flush()
                guard_ready.set()
                done.wait(.1)
    except BaseException as exc:
        errors.append(type(exc).__name__ + ': ' + str(exc))
        try:
            stop_own_child()
        except BaseException as cleanup:
            errors.append('Owned-job cleanup: ' + type(cleanup).__name__ + ': ' + str(cleanup))


def stage(name, command, deadline_seconds):
    global child
    if errors:
        raise RuntimeError(errors[0])
    quiet_gpu()
    verify_sources()
    reserve(22)
    environment = os.environ.copy()
    environment.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    started = time.time()
    row = {'name': name, 'command': command, 'started': started, 'deadline_seconds': deadline_seconds}
    with owner_lock:
        try:
            stage_cwd = args.out if name == 'npu' else ROOT
            row['cwd'] = str(stage_cwd)
            child = OwnedProcess(command, cwd=stage_cwd, env=environment,
                                 stdout_path=args.out / (name + '-stdout.txt'),
                                 stderr_path=args.out / (name + '-stderr.txt'))
        except BaseException as exc:
            # The owner retains recovery handles when constructor cleanup fails.
            retained = getattr(exc, 'owner', None)
            if retained is not None:
                child = retained
                row.update(owned_identity=retained.identity, constructor_cleanup_pending=True)
                rows.append(row)
                write('stages.json', rows)
            raise
        row['owned_identity'] = child.identity
        child.verify_live_identity()
        child.resume()
    rows.append(row)
    write('stages.json', rows)
    deadline = time.monotonic() + deadline_seconds
    try:
        while True:
            with owner_lock:
                code = child.exit_code()
            if code is not None:
                row['exit_code'] = code
                break
            if errors:
                raise RuntimeError(errors[0])
            if time.monotonic() >= deadline:
                raise TimeoutError(name + ' exceeded bounded stage deadline')
            done.wait(.1)
    finally:
        with owner_lock:
            child.close(timeout_ms=5000)
            row['terminal_exit_code'] = child.exit_code()
            row['owned_job_closed'] = child._closed
            child = None
        row['finished'] = time.time()
        write('stages.json', rows)
    if row['exit_code'] != 0 or errors:
        raise RuntimeError(name + ' failed; retained stdout/stderr and JSON report')


monitor = threading.Thread(target=watch, name='parameter-probe-memory-guard', daemon=True)
status = 'failed'
try:
    initial = quiet_gpu()
    initial_memory = reserve(22)
    if digest(BUILDER) != EXPECTED_BUILDER:
        raise RuntimeError('Frozen builder source changed; no child launched')
    if digest(PROBE) != args.expected_probe_sha256 or digest(Path(__file__)) != args.expected_runner_sha256:
        raise RuntimeError('Reviewed probe/runner source changed; no child launched')
    if digest(TESTS) != args.expected_tests_sha256:
        raise RuntimeError('Reviewed fixtures changed; no child launched')
    if digest(EP_MANIFEST) != EXPECTED_EP_MANIFEST:
        raise RuntimeError('Frozen provider copy manifest changed; no child launched')
    sources = {str(path): digest(path) for path in (BUILDER,
        ROOT / 'scripts/benchmarks/hgn_q4c_slice.py',
        ROOT / 'scripts/benchmarks/tests/test_halogen_npu_expert_onnx.py',
        ROOT / 'server/winjob.py', ROOT / 'server/host_frames.py', PROBE, TESTS, Path(__file__))}
    expected_helpers = {
        ROOT / 'scripts/benchmarks/hgn_q4c_slice.py': 'fe0dd1b9974f95bed02f37dddde1ee7c286f3f69d491548008d4a94ea703fdce',
        ROOT / 'scripts/benchmarks/tests/test_halogen_npu_expert_onnx.py': '09c4407b1f47e690379c1a5261553028db319df71d873c800b1a5af7142751f7',
        ROOT / 'server/winjob.py': '3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c',
        ROOT / 'server/host_frames.py': '417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8'}
    if any(sources[str(path)] != expected for path, expected in expected_helpers.items()):
        raise RuntimeError('Frozen helper/test source changed; no child launched')
    write('identity.json', {'python': str(PY), 'sources_sha256': sources,
                          'tensor_limit_bytes': 64 << 20, 'fixture_bytes': 492112,
                          'input_bytes_per_call': 246056, 'hardware_stage_deadline_seconds': args.npu_timeout,
                          'provider_copy_manifest': str(EP_MANIFEST),
                          'provider_copy_manifest_sha256': digest(EP_MANIFEST),
                          'provider_copy_directory': str(EP_DIR),
                          'module_path_observation': 'unavailable; chosen DLL receipt and compiler VFS argv are path evidence',
                          'initial_gpu_state': initial, 'initial_memory': initial_memory,
                          'reserve_gib': 18, 'admission_gib': 22, 'guard_interval_seconds': .1})
    monitor.start()
    if not guard_ready.wait(2) or errors:
        raise RuntimeError('Memory guard did not admit a first valid frame: ' + '; '.join(errors))
    stage('fixtures', [str(PY), '-B', '-m', 'unittest', 'discover', '-s', 'scripts/benchmarks/tests',
                       '-p', 'test_halogen_npu_parameter_probe.py', '-v'], 30)
    graph = args.out / 'tiny-input-matrices.onnx'
    stage('build', [str(PY), '-B', str(PROBE), '--build', str(graph)], 15)
    stage('cpu', [str(PY), '-B', str(PROBE), '--model', str(graph), '--provider', 'cpu',
                  '--reps', '100', '--report', str(args.out / 'cpu.json')], 30)
    stage('npu', [str(PY), '-B', str(PROBE), '--model', str(graph), '--provider', 'npu',
                  '--ep-dir', str(EP_DIR), '--reps', '100', '--report', str(args.out / 'npu.json')], args.npu_timeout)
    status = 'passed'
except BaseException as exc:
    write('failure.json', {'error': type(exc).__name__ + ': ' + str(exc), 'guard_errors': errors})
finally:
    done.set()
    if monitor.is_alive():
        monitor.join(2)
    if errors or monitor.is_alive():
        status = 'failed'
        if monitor.is_alive():
            errors.append('Memory guard thread did not stop within the bounded join')
    cleanup_error = None
    try:
        stop_own_child()
    except BaseException as exc:
        cleanup_error = type(exc).__name__ + ': ' + str(exc)
        status = 'failed'
    try:
        final_memory = frame()
    except BaseException as exc:
        final_memory = {'error': type(exc).__name__ + ': ' + str(exc)}
        status = 'failed'
    try:
        final_gpu_state = quiet_gpu()
    except BaseException as exc:
        final_gpu_state = {'error': type(exc).__name__ + ': ' + str(exc)}
        status = 'failed'
    write('cleanup.json', {'own_child_handle_closed': child is None or child._closed,
                           'cleanup_error': cleanup_error, 'guard_errors': errors,
                           'minimum_available_gib': None if min_available == float('inf') else min_available,
                           'minimum_commit_headroom_gib': None if min_commit == float('inf') else min_commit,
                           'final_memory': final_memory, 'final_gpu_state': final_gpu_state})
    artifact_hashes = {file.name: digest(file) for file in args.out.iterdir()
                       if file.is_file() and file.name != 'memory.jsonl'}
    write('result.json', {'status': status, 'stages': rows, 'guard_errors': errors,
                          'artifacts_sha256': artifact_hashes})
print(json.dumps({'status': status, 'out': str(args.out), 'stages': len(rows)}, indent=2), flush=True)
raise SystemExit(0 if status == 'passed' else 1)
