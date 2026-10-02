"""A/B Halogen with NPU idle and active work; promote only non-regressing schedules."""
import argparse, json, pathlib, statistics, time, urllib.request
P=argparse.ArgumentParser(); P.add_argument("--token-file",type=pathlib.Path,required=True)
P.add_argument("--npu-port",type=int,default=8877); P.add_argument("--out",type=pathlib.Path,required=True)
P.add_argument("--reps",type=int,default=5); P.add_argument("--max-gpu-loss-pct",type=float,default=1.0)
a=P.parse_args(); a.out.mkdir(parents=True,exist_ok=False); key=a.token_file.read_text().strip()
def post(url,body,timeout=300):
    q=urllib.request.Request(url,data=json.dumps(body).encode(),headers={"Content-Type":"application/json",
        "Authorization":"Bearer "+key} if url.endswith("completions") else {"Content-Type":"application/json"})
    t=time.perf_counter()
    with urllib.request.urlopen(q,timeout=timeout) as r: v=json.load(r)
    return v,time.perf_counter()-t
def halogen():
    body={"model":"halogen-v2","messages":[{"role":"user","content":"Explain why deterministic benchmarking matters. "*80}],
          "max_tokens":128,"temperature":0,"stream":False,"enable_thinking":False,"reasoning_effort":"none","drafter":"mtp"}
    return post("http://127.0.0.1:8840/v1/chat/completions",body)
def npu():
    body={"model":"qwen3:0.6b","messages":[{"role":"user","content":"Reply briefly."}],"max_tokens":32,"temperature":0,"stream":False}
    return post(f"http://127.0.0.1:{a.npu_port}/v1/chat/completions",body,60)
rows=[]
# control -> concurrent -> control; active work is deliberately worst-case evidence.
for phase in ("control-a","concurrent","control-b"):
    for rep in range(a.reps):
        if phase=="concurrent":
            import threading
            holder={}
            th=threading.Thread(target=lambda: holder.update(npu=npu())); th.start()
            value,wall=halogen(); th.join()
        else: value,wall=halogen()
        timing=value.get("timings",{}); tps=float(timing.get("predicted_per_second") or timing.get("decode_tps") or 0)
        rows.append({"phase":phase,"rep":rep,"wall":wall,"decode_tps":tps,"timings":timing})
controls=[x["decode_tps"] for x in rows if x["phase"].startswith("control") and x["decode_tps"]>0]
active=[x["decode_tps"] for x in rows if x["phase"]=="concurrent" and x["decode_tps"]>0]
result={"rows":rows,"control_mean":statistics.fmean(controls),"active_mean":statistics.fmean(active)}
result["gpu_loss_pct"]=(1-result["active_mean"]/result["control_mean"])*100
result["qualified_concurrent"]=result["gpu_loss_pct"]<=a.max_gpu_loss_pct
result["decision"]="idle-only" if not result["qualified_concurrent"] else "concurrent-allowed"
(a.out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps({k:result[k] for k in ("control_mean","active_mean","gpu_loss_pct","decision")},indent=2))
