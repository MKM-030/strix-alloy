"""Retained HTTP/QPC primitives only; import performs no runtime action."""
import os,sys,json,hashlib,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(r"C:\Projects\strix-alloy-clean")

def utc():
    return datetime.now(timezone.utc).isoformat()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def require(ok, message):
    if not ok:
        raise ValueError(message)

def save_new(path, value, raw=False):
    data = value if raw else (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
    with Path(path).open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())

def load_runtime():
    sys.path.insert(0, str(ROOT / 'server/.local/halogen-update-20261025/primary01815'))
    import run_measurement
    return run_measurement.c

def check_reserve(c, floor):
    frame = c.ops.host.frame()
    require(min(frame['available_bytes'], frame['commit_headroom_bytes']) >= floor * 2**30, str(floor) + '-GiB memory reserve unavailable')
    return frame

async def fetch_http_response(session, url, body):
    async with session.post(url, data=body) as response:
        raw = await response.read()
        ended_ns = time.perf_counter_ns()
        return raw, response.status, ended_ns
