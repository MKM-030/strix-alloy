"""Retained HTTP/QPC primitives; private failure capture is explicitly configured.

Import and passing reserve checks perform no writes. Only failed entry22 checks
write an exact captured frame, before the timed request begins. Runtime18 checks
retain their original behavior and do not add writes inside timed HTTP.
"""
import os,sys,json,hashlib,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(r'C:\Projects\strix-alloy-clean')
HERE=Path(__file__).resolve().parent
_failure_directory=None
_failure_ordinal=0


def utc():return datetime.now(timezone.utc).isoformat()
def digest(data):return hashlib.sha256(data).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)


def save_new(path,value,raw=False):
    data=value if raw else (json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
    with Path(path).open('xb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())


def configure_failure_capture(directory):
    global _failure_directory,_failure_ordinal
    directory=Path(directory)
    require(directory.is_absolute() and directory.resolve().is_relative_to(HERE),
            'Failure evidence must remain in this private experiment directory')
    require(not any(item.is_symlink() or getattr(item,'is_junction',lambda:False)()
                    for item in (directory,*directory.parents)), 'Linked failure output is forbidden')
    _failure_directory=directory;_failure_ordinal=0


def record_admission_failure(frame,*,physical_floor_gib,commit_floor_gib,kind='request_entry22',**context):
    global _failure_ordinal
    require(_failure_directory is not None,'Explicit private failure capture directory required')
    # Snapshot the exact one frame that failed. Do not query host memory again.
    owned=json.loads(json.dumps(frame,allow_nan=False))
    _failure_directory.mkdir(parents=True,exist_ok=True)
    value=dict(schema='halogen0203.DNZ-arena2048-failed-memory-frame.v3',utc=utc(),
        kind=kind,frame=owned,physical_floor_gib=physical_floor_gib,commit_floor_gib=commit_floor_gib,
        outside_timed_HTTP_RAW=True,actual_failed_frame=True,second_host_sample_taken=False,**context)
    while True:
        path=_failure_directory/f'memory-admission-failure-{_failure_ordinal:04d}.json'
        _failure_ordinal+=1
        try:save_new(path,value);return dict(path=str(path),sha256=digest(path.read_bytes()))
        except FileExistsError:continue


def load_runtime():
    sys.path.insert(0,str(ROOT/'server/.local/halogen-update-20261025/primary01815'))
    import run_measurement
    return run_measurement.c


def check_reserve(c,floor):
    frame=c.ops.host.frame()
    passed=min(frame['available_bytes'],frame['commit_headroom_bytes'])>=floor*2**30
    if not passed and floor==22 and _failure_directory is not None:
        record_admission_failure(frame,physical_floor_gib=22,commit_floor_gib=22)
    require(passed,str(floor)+'-GiB memory reserve unavailable')
    return frame


async def fetch_http_response(session,url,body):
    async with session.post(url,data=body) as response:
        raw=await response.read();ended_ns=time.perf_counter_ns()
        return raw,response.status,ended_ns
