"""Observe the current normal launch to readiness; never launch or restart."""
from pathlib import Path
import json,sys,time
ROOT=Path(r'C:\Projects\strix-alloy-clean')
sys.path.insert(0,str(ROOT/'server'))
from controller import read
if __name__=='__main__':
    saved=None;previous=None
    while True:
        current=read(ROOT/'server/.local/current.json')
        backend=read(ROOT/'backends/halogen-wsl2-0.17.2/.local/current-service.json')
        if saved is None and current['phase'] in ('stopped','failed'):
            # A visible console can still be creating its new controller.
            # Observe that same launch; never start another one.
            time.sleep(1)
            continue
        if saved is None:saved=current['run_id']
        assert current['run_id']==saved,'Current launch changed; observe ownership before continuing'
        now=(current.get('phase'),backend.get('phase'),backend.get('run_id'))
        if now!=previous:
            print(json.dumps(dict(controller_phase=now[0],backend_phase=now[1],controller_pid=current.get('pid'),
                backend_pid=backend.get('controller_pid'),controller_run_id=saved,backend_run_id=now[2])),flush=True)
            previous=now
        if now[:2]==('ready','ready'):break
        if current['phase'] in ('failed','stopped'):raise RuntimeError('Current launch terminated')
        time.sleep(1)
