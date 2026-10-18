"""Desktop Model admission policy; does not change managed runtime/cleanup guards."""
import argparse,ctypes,json,math,os,time
from pathlib import Path
GIB=2**30
POLICY=Path(__file__).with_name('model-start-policy.json')
def load_policy(path=POLICY):
    path=Path(path)
    if path.stat().st_size>65536:raise ValueError('Oversized model start policy')
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    if value.get('schema')!=1:raise ValueError('Unknown model start policy schema')
    for key in ('start_physical_gib','terminal_restart_physical_gib'):
        n=value.get(key)
        if type(n) not in (int,float) or not math.isfinite(n) or not 18<=n<=64:
            raise ValueError('Invalid physical admission threshold: '+key)
    if value.get('runtime_reserve_gib')!=18 or value.get('start_commit_headroom_gib')!=132:
        raise ValueError('Runtime reserve must remain 18 GiB; V2 with Vision needs 132 GiB commit admission')
    return value
def check_start_frame(frame,policy,*,age=0,restart=False):
    physical=policy['terminal_restart_physical_gib' if restart else 'start_physical_gib']
    if not 0<=age<=2:raise ValueError('Model admission memory sample is stale')
    for key,required in (('available_bytes',physical),('commit_headroom_bytes',policy['start_commit_headroom_gib'])):
        observed=frame.get(key)
        if type(observed) is not int or observed<required*GIB:
            gib=observed/GIB if type(observed) is int else None
            raise ValueError(f'Model admission requires {required:g} GiB {key}; observed {gib!r} GiB')
def terminal_restart_passed(frames,policy,*,cleanup_confirmed):
    if cleanup_confirmed is not True or len(frames)<5:return False
    try:
        for frame in frames[-5:]:check_start_frame(frame,policy,restart=True)
    except ValueError:return False
    return True
def windows_frame():
    if os.name!='nt':raise RuntimeError('Model admission must be sampled on Windows')
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_uint32),('load',ctypes.c_uint32)]+[(key,ctypes.c_uint64) for key in
            ('total','available','total_page','available_page','total_virtual','available_virtual','extended')]
    class Performance(ctypes.Structure):
        _fields_=[('length',ctypes.c_uint32)]+[(key,ctypes.c_size_t) for key in
            ('commit_total','commit_limit','commit_peak','physical_total','physical_available','system_cache',
             'kernel_total','kernel_paged','kernel_nonpaged','page_size')]+[(key,ctypes.c_uint32) for key in
            ('handle_count','process_count','thread_count')]
    m,p=Memory(),Performance();m.length=ctypes.sizeof(m);p.length=ctypes.sizeof(p)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) or not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(p),p.length):
        raise OSError('Direct Windows memory telemetry unavailable')
    return dict(available_bytes=m.available,commit_headroom_bytes=(p.commit_limit-p.commit_total)*p.page_size)
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--check-start',action='store_true',required=True);ap.parse_args()
    policy=load_policy();begin=time.monotonic();frame=windows_frame();age=time.monotonic()-begin
    check_start_frame(frame,policy,age=age)
    print(json.dumps(dict(gate='model_start',passed=True,policy=policy,memory=frame,sample_age=age)),flush=True)
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError) as exc:
        import sys
        print('REFUSED: '+str(exc),file=sys.stderr);raise SystemExit(2)
