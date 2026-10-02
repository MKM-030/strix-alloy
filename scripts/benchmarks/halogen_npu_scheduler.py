"""Schedule an NPU sidecar around Halogen GPU-critical work and fail closed."""
import argparse, json, pathlib, subprocess, threading, time, urllib.request
P=argparse.ArgumentParser(); P.add_argument("--flm",type=pathlib.Path,required=True)
P.add_argument("--model",default="qwen3:0.6b"); P.add_argument("--port",type=int,default=8877)
P.add_argument("--idle-ms",type=int,default=4000); P.add_argument("--state",type=pathlib.Path,required=True)
P.add_argument("--pmode",choices=("powersaver","balanced","performance","turbo"),default="performance")
a=P.parse_args(); a.state.parent.mkdir(parents=True,exist_ok=True)
state={"schema":1,"enabled":False,"model":a.model,"idle_ms":a.idle_ms,"reason":"not-qualified"}
def save(): a.state.write_text(json.dumps(state,indent=2),encoding="utf-8")
save()
# This supervisor never changes Halogen. It only owns a separate NPU process.
cmd=[str(a.flm),"serve",a.model,"--host","127.0.0.1","--port",str(a.port),"--pmode",a.pmode,
     "--socket","1","--q-len","1","--cors","0"]
proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
state.update(pid=proc.pid,started=time.time()); save()
try:
    deadline=time.time()+120
    while time.time()<deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{a.port}/v1/models",timeout=.5).read(); break
        except Exception:
            if proc.poll() is not None: raise RuntimeError("NPU sidecar exited during startup")
            time.sleep(.5)
    else: raise RuntimeError("NPU sidecar readiness timeout")
    state.update(enabled=True,reason="ready-idle-only"); save()
    # Qualification harness controls request timing. The service itself stays idle otherwise.
    while proc.poll() is None: time.sleep(1)
finally:
    if proc.poll() is None: proc.terminate()
    try: proc.wait(timeout=10)
    except subprocess.TimeoutExpired: proc.kill()
    state.update(enabled=False,stopped=time.time(),reason="stopped"); save()
