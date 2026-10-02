import argparse,json,statistics,time,numpy as np,onnxruntime as ort
p=argparse.ArgumentParser(); p.add_argument("--model",required=True); p.add_argument("--provider",default="CPUExecutionProvider"); p.add_argument("--reps",type=int,default=100); a=p.parse_args()
s=ort.InferenceSession(a.model,providers=[a.provider]); x=np.random.default_rng(1).standard_normal((1,2560),dtype=np.float32)
for _ in range(5): s.run(None,{"x":x})
ts=[]
for _ in range(a.reps):
 t=time.perf_counter(); s.run(None,{"x":x}); ts.append((time.perf_counter()-t)*1000)
print(json.dumps({"provider":a.provider,"reps":a.reps,"mean_ms":statistics.fmean(ts),"median_ms":statistics.median(ts),"min_ms":min(ts),"p95_ms":sorted(ts)[int(.95*len(ts))-1]},indent=2))
