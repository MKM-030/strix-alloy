"""Root-owned host-only compile; never loads HIP or submits GPU/NPU work."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'server/.local/optimization9h-20261004'
HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'replay.c'
BINARY = '/home/revn/halogen-re/prefill-deq-replay-20261006-v1'
sys.path.insert(0, str(ROOT / 'server'))
from host_frames import frame
from winjob import OwnedProcess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def linux(path):
    path = Path(path).resolve()
    if path.drive.lower() != 'c:':
        raise ValueError('Explicit C-drive source expected')
    return '/mnt/c/' + str(path)[3:].replace('\\', '/')


def main():
    if sys.argv[1:] != ['--compile']:
        raise ValueError('Explicit --compile required')
    out = BASE / ('prefill-deq-host-build-' + uuid.uuid4().hex)
    out.mkdir()
    report = dict(passed=False, source_sha256=sha(SOURCE), binary=BINARY,
                  stages=[], runtime_loaded=False, GPU_executed=False, NPU_executed=False)
    memory = []

    def reserve():
        value = frame()
        memory.append(value)
        if min(value['available_bytes'], value['commit_headroom_bytes']) < 18 * 2**30:
            raise RuntimeError('Physical/commit reserve below18GiB')

    def stage(name, command, expected=0):
        reserve()
        record = dict(name=name, command=command, owned_job_closed=False)
        report['stages'].append(record)
        process = None
        try:
            try:
                process = OwnedProcess(command, cwd=ROOT, env=dict(os.environ),
                    stdout_path=out / (name + '.stdout.txt'), stderr_path=out / (name + '.stderr.txt'))
            except BaseException as error:
                process = getattr(error, 'owner', None)
                raise
            record['identity'] = process.identity
            process.resume()
            deadline = time.monotonic() + 60
            while not process.wait(250):
                reserve()
                if time.monotonic() > deadline:
                    raise TimeoutError('Owned host compile stage deadline')
            record['exit_code'] = process.exit_code()
            if record['exit_code'] != expected:
                raise RuntimeError('Unexpected host stage status: ' + name)
        finally:
            if process is not None:
                process.close()
                record['owned_job_closed'] = True

    try:
        reserve()
        if min(memory[-1]['available_bytes'], memory[-1]['commit_headroom_bytes']) < 22 * 2**30:
            raise RuntimeError('New host stage admission below22GiB')
        wsl = [r'C:\Windows\System32\wsl.exe', '-d', 'Ubuntu-24.04', '-u', 'revn', '--exec']
        stage('absent-destination', wsl + ['test', '-e', BINARY], expected=1)
        stage('compile', wsl + ['gcc', '-O2', '-Wall', '-Wextra', '-Werror', '-D__HIP_PLATFORM_AMD__',
              '-I' + linux(ROOT / 'backends/halogen-wsl2-0.16.2/.local/hip-include'), linux(SOURCE),
              '-ldl', '-lcrypto', '-o', BINARY])
        stage('binary-hash', wsl + ['sha256sum', BINARY])
        report['binary_sha256'] = (out / 'binary-hash.stdout.txt').read_text().split()[0]
        if len(report['binary_sha256']) != 64 or sha(SOURCE) != report['source_sha256']:
            raise RuntimeError('Source/build identity changed')
        for name in ('image_wrapper.py', 'owned_run.py'):
            path = HERE / name
            text = path.read_text()
            if text.count('SOURCE_HASH_PENDING') != 1 or text.count('BINARY_HASH_PENDING') != 1:
                raise RuntimeError('Expected fresh source/build pin placeholders')
            path.write_text(text.replace('SOURCE_HASH_PENDING', report['source_sha256'])
                            .replace('BINARY_HASH_PENDING', report['binary_sha256']))
        report['passed'] = True
    except BaseException as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        report['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        report['minimum_physical_GiB'] = min((m['available_bytes'] / 2**30 for m in memory), default=None)
        report['minimum_commit_GiB'] = min((m['commit_headroom_bytes'] / 2**30 for m in memory), default=None)
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=report['passed'], receipt=str(out / 'result.json'),
          binary_sha256=report.get('binary_sha256'), error=report.get('error'))), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
