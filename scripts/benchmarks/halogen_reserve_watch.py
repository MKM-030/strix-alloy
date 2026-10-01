"""Additional Windows reserve monitor; existing engine guards remain untouched.
Requests an ordinary owned-controller stop at 18 GiB to leave margin above 16 GiB.
It never changes a memory limit, kills arbitrary processes or relaxes protection.
"""
import argparse,json,math,sys,time
from pathlib import Path
P=argparse.ArgumentParser(description=__doc__)
P.add_argument('--repo',type=Path,required=True)
P.add_argument('--out',type=Path,required=True)
P.add_argument('--wait-seconds',type=int,default=600)

def below_reserve(available):
    if type(available) not in (int,float) or not math.isfinite(available) or available<0:
        raise ValueError('Invalid memory telemetry')
    return available<18.0

def main():
    a=P.parse_args();sys.path.insert(0,str(a.repo/'server'))
    import controller as ctrl
    a.out.mkdir(parents=True,exist_ok=True)
    statefile=a.repo/'server/.local/current.json';run=None;low=None
    deadline=time.monotonic()+a.wait_seconds;stopping=False;reasons=[]
    print('Reserve monitor armed: 18 GiB stop threshold, 16 GiB required reserve.',flush=True)
    try:
        with (a.out/'windows-memory.jsonl').open('x',encoding='utf-8') as log:
            while True:
                value=ctrl.available_gib()
                log.write(json.dumps({'time':time.time(),'available_gib':value,'run_id':run})+'\n');log.flush()
                state=ctrl.read(statefile) if statefile.exists() else {}
                if run is None:
                    if state.get('backend','').startswith('halogen-') and state.get('phase') in ('starting','ready'):
                        run=state['run_id'];print('Watching owned Halogen run '+run,flush=True)
                    elif time.monotonic()>deadline: raise TimeoutError('No new Halogen controller')
                if run and state.get('run_id')!=run: break
                if run:
                    low=value if low is None else min(low,value)
                    if state.get('phase') in ('failed','stopped'):break
                    if below_reserve(value):
                        ctrl.atomic(a.repo/'server/.local/stop.json',{'run_id':run})
                        if not stopping:print('STOP requested: Windows physical reserve threshold.',flush=True)
                        reason='physical-reserve'
                        if reason not in reasons:reasons.append(reason)
                        stopping=True
                time.sleep(.2)
    except BaseException:
        if run:
            ctrl.atomic(a.repo/'server/.local/stop.json',{'run_id':run})
        raise
    result={'run_id':run,'minimum_available_gib':low,'stop_requested':stopping,
            'required_reserve_gib':16,'stop_threshold_gib':18,'stop_reasons':reasons,
            'all_samples_above_16_gib':low is not None and low>=16}
    (a.out/'reserve-summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)
    return 0 if result['all_samples_above_16_gib'] else 2
if __name__=='__main__':raise SystemExit(main())
