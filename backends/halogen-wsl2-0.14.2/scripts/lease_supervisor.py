# Container-side liveness lease: no fixed service deadline, no orphan engine.
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

LEASE_AGE = 45

def fresh(record, run_id, now=None):
    now = time.time() if now is None else now
    stamp = record.get('time')
    return (record.get('run_id') == run_id and type(stamp) in (int,float)
            and -5 <= now - stamp <= LEASE_AGE)

def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--lease', required=True, type=Path)
    p.add_argument('--run-id', required=True)
    p.add_argument('command', nargs=argparse.REMAINDER)
    args = p.parse_args(argv)
    if not args.command: p.error('Child command required')
    stopping = False
    def request_stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM,request_stop)
    signal.signal(signal.SIGINT,request_stop)
    if not fresh(json.loads(args.lease.read_text()), args.run_id):
        raise SystemExit('Stale controller/guard lease before model launch')
    child = subprocess.Popen(args.command, start_new_session=True)
    try:
        while child.poll() is None and not stopping:
            try: valid = fresh(json.loads(args.lease.read_text()), args.run_id)
            except (ValueError, OSError): valid = False
            if not valid:
                print('[lease] Controller or host guard is unavailable; stopping owned engine',flush=True)
                break
            time.sleep(1)
    finally:
        try: os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: child.wait(timeout=10)
        except subprocess.TimeoutExpired: pass
        try: os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        child.wait()
    return child.returncode if child.returncode is not None else 1

if __name__ == '__main__': raise SystemExit(main())
