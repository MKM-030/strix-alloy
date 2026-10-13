"""Start or inspect the owned Voice Studio without changing voice/model services."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RUNTIME = HERE / 'runtime'
PYTHON = ROOT / 'voice/native-bridge/.venv/Scripts/python.exe'
ORIGIN = 'https://strix-alloy.tail7f425a.ts.net'
BASE_PATH = '/voice-studio'
PORT = 8863


def owner_tools():
    spec = importlib.util.spec_from_file_location(
        'scc_studio_owner_tools', ROOT / 'voice/native-start/start_services.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def arguments():
    return [str(PYTHON), '-u', str(HERE / 'studio_server.py'),
            '--host', '127.0.0.1', '--port', str(PORT), '--origin', ORIGIN,
            '--runtime', str(RUNTIME), '--base-path', BASE_PATH]


def health():
    with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health', timeout=3) as response:
        result = json.loads(response.read(4096))
    if result.get('status') != 'ok' or result.get('service') != 'scc-voice-studio':
        raise RuntimeError('Voice Studio health identity differs; inspect the service')
    return result


@contextmanager
def startup_lock():
    import msvcrt
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / 'startup.lock').open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('Voice Studio is already starting; try again shortly') from None
        try:
            yield
        finally:
            handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def retention_catchup():
    # A stopped/offline exhibition PC catches up on its next Studio start.
    # Before the fixed deadline the helper makes no recording/service changes.
    path = HERE / 'retention_cleanup.py'
    if not path.is_file():
        return {'status': 'deferred', 'reason': 'retention_helper_missing'}
    spec = importlib.util.spec_from_file_location('scc_studio_retention', path)
    helper = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)
    if not helper.due():
        return {'status': 'not_due'}
    try:
        completed = subprocess.run([str(PYTHON), '-u', str(path), '--apply'],
            cwd=ROOT, check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=180)
        if len(completed.stdout) > 8192:
            return {'status': 'deferred', 'reason': 'retention_report_oversized'}
        value = json.loads(completed.stdout.decode('utf-8-sig'))
        if value.get('status') not in ('not_due', 'purged', 'deferred'):
            return {'status': 'deferred', 'reason': 'retention_report_invalid'}
        return value
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'status': 'deferred', 'reason': 'retention_catchup_failed'}


def start(access_file):
    owner = owner_tools()
    args = arguments()
    retention = retention_catchup()
    with startup_lock():
        pid = owner.owned_listener(PORT, args)
        if pid:
            return {'ok': True, 'reused': True, 'pid': pid, 'url': ORIGIN + BASE_PATH + '/',
                    'health': health(), 'retention': retention}
        for path in (PYTHON, HERE / 'studio_server.py', HERE / 'web/index.html'):
            if not path.is_file():
                raise FileNotFoundError(path)
        if not (RUNTIME / 'auth.json').is_file():
            subprocess.run(args + ['--init-auth', '--access-file', str(access_file)],
                           cwd=ROOT, check=True)
        with (RUNTIME / 'studio.stdout.log').open('ab') as stdout, (RUNTIME / 'studio.stderr.log').open('ab') as stderr:
            child = subprocess.Popen(args, cwd=ROOT, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError('Voice Studio exited; inspect voice/voice-studio/runtime/studio.stderr.log')
            pid = owner.owned_listener(PORT, args)
            if pid:
                try:
                    info = health()
                except (OSError, ValueError):
                    time.sleep(.2)
                    continue
                import psutil
                process = psutil.Process(pid)
                receipt = {'pid': pid, 'created': process.create_time(),
                           'exe': process.exe(), 'cmdline': process.cmdline()}
                (RUNTIME / 'studio-owner.json').write_text(json.dumps(receipt), encoding='utf-8')
                return {'ok': True, 'reused': False, 'pid': pid,
                        'url': ORIGIN + BASE_PATH + '/', 'health': info, 'retention': retention}
            time.sleep(.2)
        raise RuntimeError('Voice Studio was not ready in 20 seconds; inspect its logs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'status'))
    parser.add_argument('--access-file', type=Path,
                        default=Path.home() / 'Desktop/Voice-Studio-Zugang.txt')
    args = parser.parse_args()
    try:
        if args.action == 'start':
            result = start(args.access_file)
        else:
            pid = owner_tools().owned_listener(PORT, arguments())
            result = {'ok': True, 'running': bool(pid), 'pid': pid,
                      'url': ORIGIN + BASE_PATH + '/', 'health': health() if pid else None}
        print(json.dumps(result, ensure_ascii=True), flush=True)
        return 0
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=True), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
