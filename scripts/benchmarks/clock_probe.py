"""Read-only guest clocks, calibrated against host QueryPerformanceCounter."""
import atexit, json, subprocess, time
CODE='import sys,time,json\nfor line in sys.stdin:\n print(json.dumps(dict(mono=time.monotonic(),raw=time.clock_gettime(time.CLOCK_MONOTONIC_RAW),utc=time.time())),flush=True)'
class ClockProbe:
    def __init__(self, distribution, user):
        self.p=subprocess.Popen(['wsl.exe','-d',distribution,'-u',user,'--exec','python3','-u','-c',CODE],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        atexit.register(self.close)
        self.sample()
    def sample(self):
        t0=time.perf_counter(); self.p.stdin.write('sample\n'); self.p.stdin.flush()
        r=json.loads(self.p.stdout.readline()); t1=time.perf_counter()
        r.update(qpc=(t0+t1)/2,roundtrip=t1-t0)
        return r
    def compare(self,before,after):
        raw=after['raw']-before['raw']; mono=after['mono']-before['mono']
        qpc=after['qpc']-before['qpc']
        if min(raw,mono,qpc)<=0: raise RuntimeError('Clock interval nonpositive')
        uncertainty=(before['roundtrip']+after['roundtrip'])/2
        if abs(raw-qpc)>max(.01,uncertainty+.002*qpc): raise RuntimeError('Guest raw clock disagrees with Windows QPC')
        return dict(before=before,after=after,monotonic_per_raw=mono/raw,raw_per_qpc=raw/qpc,
                    window_seconds=qpc,handshake_uncertainty_seconds=uncertainty)
    def close(self):
        if self.p.poll() is None:
            self.p.stdin.close()
            try: self.p.wait(timeout=5)
            except subprocess.TimeoutExpired: self.p.terminate()
