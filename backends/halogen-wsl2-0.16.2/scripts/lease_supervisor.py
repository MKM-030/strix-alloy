"""Container liveness uses observed progress, never compares Windows and WSL UTC."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

LEASE_AGE = 45

def fresh(record, run_id, now=None):
    """Same-Windows-clock check retained for the Windows controller and guard."""
    now = time.time() if now is None else now
    stamp = record.get("time")
    return (record.get("run_id") == run_id and type(stamp) in (int,float)
            and -5 <= now - stamp <= LEASE_AGE)

def lease_clock():
    # CLOCK_BOOTTIME includes Linux suspend. No absolute value crosses OS boundaries.
    if hasattr(time, "CLOCK_BOOTTIME"):
        return time.clock_gettime(time.CLOCK_BOOTTIME)
    return time.monotonic()

def lease_record(run_id, sequence):
    return {"schema":2, "run_id":run_id, "sequence":sequence, "time":time.time()}

class ProgressLease:
    """Require a renewal before launch; unchanged/invalid files cannot extend life."""
    def __init__(self, run_id):
        self.run_id = run_id
        self.sequence = None
        self.last_progress = None
        self.renewed = False

    def observe(self, record, now=None):
        now = lease_clock() if now is None else now
        if (type(record) is not dict or type(record.get("schema")) is not int
                or record["schema"] != 2 or record.get("run_id") != self.run_id
                or type(record.get("sequence")) is not int or record["sequence"] < 1):
            raise ValueError("invalid lease schema, run identity or sequence")
        if self.last_progress is not None:
            if now < self.last_progress:
                raise ValueError("local lease clock moved backwards")
            if now - self.last_progress >= LEASE_AGE:
                raise ValueError("lease expired: no observed progress for 45 seconds")
        sequence = record["sequence"]
        if self.sequence is None:
            self.sequence, self.last_progress = sequence, now
        elif sequence < self.sequence:
            raise ValueError("lease sequence moved backwards")
        elif sequence > self.sequence:
            self.sequence, self.last_progress, self.renewed = sequence, now, True
        return self.is_fresh(now)

    def is_fresh(self, now=None):
        now = lease_clock() if now is None else now
        return (self.renewed and self.last_progress is not None
                and 0 <= now - self.last_progress < LEASE_AGE)

def read_record(path):
    return json.loads(path.read_text(encoding="utf-8"))

def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--lease", required=True, type=Path)
    p.add_argument("--run-id", required=True)
    p.add_argument("command", nargs=argparse.REMAINDER)
    args = p.parse_args(argv)
    if not args.command: p.error("Child command required")
    stopping = False
    def request_stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM,request_stop)
    signal.signal(signal.SIGINT,request_stop)
    tracker = ProgressLease(args.run_id)
    deadline = lease_clock() + LEASE_AGE
    last_read_error = None
    print("[lease] Waiting for a new guard sequence; independent local 45-second deadline",flush=True)
    while not stopping and lease_clock() < deadline:
        try:
            if tracker.observe(read_record(args.lease)):
                break
        except OSError as exc:
            # A brief file-sharing/read conflict does not renew the deadline.
            last_read_error = type(exc).__name__
        except ValueError as exc:
            print("[lease] Refusing model launch: " + str(exc),flush=True)
            return 2
        time.sleep(.25)
    if stopping: return 0
    if not tracker.is_fresh():
        print("[lease] Refusing model launch: no renewed guard sequence; last read error="
              + str(last_read_error),flush=True)
        return 2
    print("[lease] Guard progress confirmed; wall-clock offset is irrelevant",flush=True)
    child = subprocess.Popen(args.command, start_new_session=True)
    failure = None
    try:
        while child.poll() is None and not stopping:
            try:
                tracker.observe(read_record(args.lease))
                last_read_error = None
            except OSError as exc:
                last_read_error = type(exc).__name__
            except ValueError as exc:
                failure = str(exc)
                break
            if not tracker.is_fresh():
                failure = "no guard progress for 45 seconds; last read error=" + str(last_read_error)
                break
            time.sleep(1)
        if failure:
            print("[lease] " + failure + "; stopping owned engine",flush=True)
    finally:
        try: os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: child.wait(timeout=10)
        except subprocess.TimeoutExpired: pass
        try: os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        child.wait()
    return 2 if failure else child.returncode

if __name__ == "__main__": raise SystemExit(main())
