import json,sys,time,pathlib,httpx
from huggingface_hub import hf_hub_url
from huggingface_hub.utils import build_hf_headers
r=json.loads(pathlib.Path(sys.argv[1]).read_text())[0];out=pathlib.Path(sys.argv[1]).parent/'http-download-probe.json';t=time.perf_counter();n=0
try:
 with httpx.Client(follow_redirects=True,timeout=httpx.Timeout(25,connect=10)) as c:
  with c.stream('GET',hf_hub_url(r['repo'],r['file'],revision=r['revision']),headers={**build_hf_headers(),'Range':'bytes=0-8388607'}) as resp:
   status=resp.status_code;first=None
   for b in resp.iter_bytes(65536):
    if first is None:first=time.perf_counter()-t
    n+=len(b)
    if n>=8388608:break
 data={'status':status,'bytes':n,'seconds':time.perf_counter()-t,'ttfb':first}
except Exception as e:data={'error_type':type(e).__name__,'bytes':n,'seconds':time.perf_counter()-t}
out.write_text(json.dumps(data));print(json.dumps(data),flush=True)
