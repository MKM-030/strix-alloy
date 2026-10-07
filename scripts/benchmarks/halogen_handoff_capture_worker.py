"""One sealed NPU production + prospective ETW/PDH GPU consumption window."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'server'))
from owned_child import JobChild
from host_frames import frame


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2,allow_nan=False)


def require(value,message):
    if not value:
        raise RuntimeError(message)


def reserve(floor=18):
    value = frame()
    require(min(value['available_bytes'],value['commit_headroom_bytes']) >= floor*2**30,'Physical/commit reserve lost')


def wait(child,deadline):
    while child.poll() is None:
        reserve()
        require(time.monotonic() < deadline,'Bounded child deadline; retained own job will close')
        time.sleep(.05)
    return child.poll()


def wait_marker(child,path,deadline):
    while not path.exists():
        reserve()
        require(child.poll() is None,'Producer exited before '+path.name)
        require(time.monotonic()<deadline,'Producer marker deadline: '+path.name)
        time.sleep(.05)
    return read(path)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--sha256',required=True)
    args=p.parse_args()
    require(sha(args.plan)==args.sha256,'Study plan changed')
    plan=read(args.plan)
    for path,digest in plan['source_pins'].items():
        require(sha(path)==digest,'Changed capture input: '+path)
    out=Path(plan['out'])
    out.mkdir()
    handoff=Path(plan['handoff_out'])
    errors=[]
    reserve(22)
    producer_env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    producer=JobChild(plan['producer_command'],cwd=ROOT,env=producer_env,
                      stdout_path=out/'producer.stdout',stderr_path=out/'producer.stderr')
    recorder=pdh=None
    recorded=False
    decoded=False
    decode_attempted=False
    try:
        write(out/'producer-retained.json',dict(identity=producer.owner.verify_live_identity(),
              thread_environment={key:producer_env[key] for key in
                                  ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')}))
        deadline=time.monotonic()+180
        while not (handoff/'npu-prepared.json').exists():
            reserve()
            require(producer.poll() is None,'NPU producer exited before prepared marker; see producer.stderr')
            require(time.monotonic()<deadline,'NPU preparation deadline; no GPU release')
            time.sleep(.1)
        prepared=read(handoff/'npu-prepared.json')
        require(producer.contains(prepared['windows_pid']),'Prepared NPU producer PID outside retained own job')
        recorder=JobChild(plan['record_command'],cwd=ROOT,env=os.environ.copy(),
                          stdout_path=out/'record.jsonl',stderr_path=out/'record.stderr')
        write(out/'record-retained.json',recorder.owner.verify_live_identity())
        until=time.monotonic()+10
        while True:
            reserve()
            lines=(out/'record.jsonl').read_text(encoding='utf-8').splitlines()
            rows=[]
            for line in lines:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            if any(row.get('event')=='capture_ready' for row in rows):
                break
            require(recorder.poll() is None,'Recorder failed before ready; no GPU release')
            require(time.monotonic()<until,'Capture-ready deadline; no GPU release')
            time.sleep(.05)
        write(handoff/'gpu-release.json',dict(schema=prepared['schema'],windows_pid=prepared['windows_pid'],
                                             release=True,qpc_ns=time.perf_counter_ns()))
        # The explicit PDH epoch must start after GPU context creation and end
        # before its destruction. ETW still encloses the entire birth/lifetime.
        rows_ready=wait_marker(producer,handoff/'gpu-rows-ready.json',time.monotonic()+60)
        require(rows_ready['schema']==prepared['schema'] and
                rows_ready['windows_pid']==prepared['windows_pid'],'GPU row marker identity changed')
        pdh=JobChild(plan['pdh_command'],cwd=ROOT,env=os.environ.copy(),
                     stdout_path=out/'pdh.jsonl',stderr_path=out/'pdh.stderr')
        write(out/'pdh-retained.json',pdh.owner.verify_live_identity())
        # PDH baseline establishes a sampling interval before the known copy.
        time.sleep(.7)
        require(pdh.poll() is None,'PDH collector exited before GPU release')
        write(handoff/'gpu-rows-release.json',dict(schema=prepared['schema'],windows_pid=prepared['windows_pid'],
                                             release=True,qpc_ns=time.perf_counter_ns()))
        rows_complete=wait_marker(producer,handoff/'gpu-rows-complete.json',time.monotonic()+45)
        require(rows_complete['schema']==prepared['schema'] and
                rows_complete['windows_pid']==prepared['windows_pid'],'GPU row completion identity changed')
        # Retain a trailing PDH interval before the GPU is permitted to close.
        time.sleep(.6)
        Path(plan['pdh_stop']).touch(exist_ok=False)
        require(wait(pdh,time.monotonic()+15)==0,'PDH capture failed')
        pdh.close();pdh=None
        write(handoff/'gpu-cleanup-release.json',dict(schema=prepared['schema'],windows_pid=prepared['windows_pid'],
                                             release=True,qpc_ns=time.perf_counter_ns()))
        code=wait(producer,time.monotonic()+45)
        require(code==0,'NPU handoff failed; see producer.stderr')
        Path(plan['record_stop']).touch(exist_ok=False)
        require(wait(recorder,time.monotonic()+15)==0,'ETW recorder failed')
        recorded=True
        producer.close();producer=None
        recorder.close();recorder=None
        decode_attempted=True
        with contextlib.closing(JobChild(plan['decode_command'],cwd=ROOT,env=os.environ.copy(),
             stdout_path=out/'decode.stdout',stderr_path=out/'decode.stderr')) as decoder:
            write(out/'decode-retained.json',decoder.owner.verify_live_identity())
            require(wait(decoder,time.monotonic()+90)==0,'ETW offline decoder failed')
            decoded=True
    except BaseException as error:
        errors.append(type(error).__name__+': '+str(error))
    finally:
        # A failed collector must not strand a successfully completed consumer
        # at the cleanup barrier. Permit its owned teardown before job closure.
        if producer is not None and producer.poll() is None and (handoff/'gpu-rows-complete.json').exists():
            marker=handoff/'gpu-cleanup-release.json'
            if not marker.exists():
                completed=read(handoff/'gpu-rows-complete.json')
                write(marker,dict(schema=completed['schema'],windows_pid=completed['windows_pid'],release=True))
            try:
                wait(producer,time.monotonic()+20)
            except BaseException as error:
                errors.append('Producer cleanup: '+str(error))
        # Preserve complete diagnostic intervals even when the producer fails.
        # Stop only collectors launched by this worker through their own markers.
        for child,stop_key,label in ((pdh,'pdh_stop','PDH'),(recorder,'record_stop','Recorder')):
            if child is None:
                continue
            marker=Path(plan[stop_key])
            if not marker.exists():
                marker.touch()
            try:
                code=wait(child,time.monotonic()+15)
                require(code==0,label+' cleanup capture failed')
                if label=='Recorder':
                    recorded=True
            except BaseException as error:
                errors.append(label+' cleanup: '+str(error))
        for child in (producer,pdh,recorder):
            if child is not None:
                child.close()
        if recorded and not decode_attempted:
            try:
                decode_attempted=True
                with contextlib.closing(JobChild(plan['decode_command'],cwd=ROOT,env=os.environ.copy(),
                     stdout_path=out/'decode.stdout',stderr_path=out/'decode.stderr')) as decoder:
                    write(out/'decode-retained.json',decoder.owner.verify_live_identity())
                    require(wait(decoder,time.monotonic()+90)==0,'ETW offline decoder failed')
                    decoded=True
            except BaseException as error:
                errors.append('Diagnostic decode: '+str(error))
        result=dict(errors=errors,passed=not errors,engine_gain_measured=False,
                    pid4_whitelisted=False,handoff_report=str(handoff/'handoff.json'),
                    ETW_ownership_qualified=False,capture_complete=recorded,decode_complete=decoded)
        write(out/'capture-result.json',result)
        print(json.dumps(dict(out=str(out),**result)),flush=True)
    return 0 if not errors else 1


if __name__=='__main__':
    raise SystemExit(main())
