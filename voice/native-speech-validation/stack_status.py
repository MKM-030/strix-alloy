"""Read-only status of the installed native SCC voice stack. Never sends inference."""
import concurrent.futures, ctypes, datetime, json, pathlib, shutil, subprocess, sys
import urllib.error, urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[2]
CLEAN=pathlib.Path(r"C:\Projects\strix-alloy-clean")
PROFILE=CLEAN/"server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/halogen0181-version-bracket-20261012/serving0181-full262-exact-cache-candidate-20261013.json"
MODEL=CLEAN/"backends/halogen-wsl2-0.18.1/.local/api-token.txt"
GATEWAY=ROOT/"server/.local/scc-gateway.json"
PORTS=(8731,8840,8841,8850,8851,8852,8853,8860,8861,8862)
EXPECTED={
  8840: str(CLEAN/"server/controller.py"), 8841:str(ROOT/"server/gateway.py"),
  8850:str(ROOT/"voice/bridge.py"),8853:str(ROOT/"voice/bridge.py"),
  8860:str(ROOT/"voice/native-bridge/native_bridge.py"),
  8861:r"C:\AI\build\whisper.cpp\build\bin\whisper-server.exe",
  8862:r"C:\AI\qwentts.cpp\build\Release\tts-server.exe",
}
def read(path): return json.loads(path.read_text(encoding="utf-8-sig"))
def public_error(error):
    return {"error":type(error).__name__,**({"http_status":error.code} if isinstance(error,urllib.error.HTTPError) else {})}
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None
def credential(config_path):
    path=pathlib.Path(read(config_path)["token_file"])
    return path.read_text(encoding="utf-8-sig").strip()
def health(port,path="/health",token=None,json_body=True):
    # Fixed read-only routes only. In particular /api/session allocates a session.
    if (port,path) not in {(8731,"/health"),(8840,"/health"),(8841,"/health"),(8850,"/"),(8860,"/health"),(8861,"/health"),(8862,"/v1/models")}:
        raise ValueError("Route is not a read-only status route")
    request=urllib.request.Request(f"http://127.0.0.1:{port}{path}",method="GET",
        headers={"Authorization":"Bearer "+token} if token else {})
    with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(request,timeout=5) as response:
        value=json.loads(response.read(65536)) if json_body else {}
        result={"http_status":response.status}
        for field in ("busy","draining"):
            if type(value.get(field)) is bool: result[field]=value[field]
        for field in ("in_flight","queued","active_requests","queued_requests","nativeSessions","slots","context","slot_ctx","kv_pool_positions"):
            if type(value.get(field)) is int: result[field]=value[field]
        if value.get("status") in ("ok","ready","unavailable","loading"): result["status"]=value["status"]
        if value.get("authMode") in ("servicenow","deny","loopback-development"): result["auth_mode"]=value["authMode"]
        if port==8731:
            result["expected_model"]=value.get("model")=="halogen-qwen3.8-flash-next"
            result["version_matches"]=value.get("version")=={"api":"0.18.1","engine":"0.18.1","match":True}
            cache=value.get("prompt_cache")
            if isinstance(cache,dict):
                result["prompt_cache"]={key:cache[key] for key,kind in
                    (("mode",int),("enabled",bool),("cap_mb",int),("bitwise_identical_to_cold",bool))
                    if type(cache.get(key)) is kind}
        if port==8862:
            result["expected_model"]=any(item.get("id")=="scc-native-qwen3" for item in value.get("data",[]) if isinstance(item,dict))
        return result
def probe(name,port,path="/health",config=None,token_file=None,json_body=True):
    try:
        token=credential(config) if config else (token_file.read_text(encoding="utf-8-sig").strip() if token_file else None)
        return name,health(port,path,token,json_body)
    except Exception as error: return name,public_error(error)
def memory():
    class Mem(ctypes.Structure):
        _fields_=[("length",ctypes.c_uint32),("load",ctypes.c_uint32)]+[(key,ctypes.c_uint64) for key in ("total","available","total_page","available_page","total_virtual","available_virtual","extended")]
    class Perf(ctypes.Structure):
        _fields_=[("length",ctypes.c_uint32)]+[(key,ctypes.c_size_t) for key in ("commit_total","commit_limit","commit_peak","physical_total","physical_available","system_cache","kernel_total","kernel_paged","kernel_nonpaged","page_size")]+[(key,ctypes.c_uint32) for key in ("handle_count","process_count","thread_count")]
    m,p=Mem(),Perf(); m.length=ctypes.sizeof(m);p.length=ctypes.sizeof(p)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) or not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(p),p.length): raise OSError("memory telemetry unavailable")
    physical=m.available/(1<<30); commit=(p.commit_limit-p.commit_total)*p.page_size/(1<<30)
    return {"free_gib":round(physical,3),"commit_headroom_gib":round(commit,3),"runtime_guard_floor_gib":18,"above_runtime_floor":physical>=18 and commit>=18,"cold_start_floor_met":physical>=35 and commit>=131}
def listeners():
    command="$ports=8731,8840,8841,8850,8851,8852,8853,8860,8861,8862; $rows=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort } | ForEach-Object { $p=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$_.OwningProcess); [pscustomobject]@{port=$_.LocalPort;address=$_.LocalAddress;pid=$p.ProcessId;created=$p.CreationDate.ToUniversalTime().ToString('o');exe=$p.ExecutablePath;command=$p.CommandLine} }); ConvertTo-Json -InputObject $rows -Depth 3 -Compress"
    raw=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",command],capture_output=True,text=True,check=True,timeout=20)
    result=[]
    for item in json.loads(raw.stdout or "[]"):
        port=item["port"]; expected=EXPECTED.get(port)
        identity=(expected.lower() in str(item.get("command","")).lower()) if expected else None
        if port in (8861,8862): identity=str(item.get("exe","")).lower()==expected.lower()
        result.append({"port":port,"address":item["address"],"pid":item["pid"],"created_utc":item["created"],"expected_process":identity})
    return sorted(result,key=lambda x:(x["port"],x["address"]))
def funnel():
    exe=shutil.which("tailscale.exe") or r"C:\Program Files\Tailscale\tailscale.exe"
    raw=subprocess.run([exe,"funnel","status","--json"],capture_output=True,text=True,check=True,timeout=10)
    data=json.loads(raw.stdout);handlers={}
    for site in data.get("Web",{}).values(): handlers.update(site.get("Handlers",{}))
    return {"native_route_matches":handlers.get("/scc-native",{}).get("Proxy")=="http://127.0.0.1:8860",
        "gateway_route_matches":handlers.get("/",{}).get("Proxy")=="http://127.0.0.1:8841",
        "callback_route_matches":handlers.get("/scc-voice",{}).get("Proxy")=="http://127.0.0.1:8853",
        "https_443_configured":data.get("TCP",{}).get("443",{}).get("HTTPS") is True,
        "funnel_allowed":any(data.get("AllowFunnel",{}).values()),
        "media_connectivity":"not tested; host ICE requires a reachable LAN/tailnet interface"}
def main():
    if sys.platform!="win32": raise SystemExit("Run this read-only script on the Windows demo host.")
    result={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"read_only":True,"bot_session_count":"not exposed; no session allocated by this check"}
    tasks=[("model",8731,"/health",None,MODEL,True),("controller",8840,"/health",PROFILE,None,True),
        ("gateway",8841,"/health",GATEWAY,None,True),("bot",8850,"/",None,None,False),
        ("native",8860,"/health",None,None,True),("asr",8861,"/health",None,None,True),
        ("tts",8862,"/v1/models",None,None,True)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
        result["services"]=dict(pool.map(lambda args:probe(*args),tasks))
    for name,callback in (("memory",memory),("listeners",listeners),("funnel",funnel)):
        try: result[name]=callback()
        except Exception as error: result[name]=public_error(error)
    services=result["services"];model=services["model"];gateway=services["gateway"];native=services["native"]
    rows=result["listeners"] if isinstance(result["listeners"],list) else []
    legacy=[row["port"] for row in rows if row["port"] in (8851,8852)]
    result["legacy_cpu_ports"]=sorted(set(legacy))
    result["engine_idle"]=model.get("busy") is False and model.get("in_flight")==0 and model.get("queued")==0
    result["gateway_idle"]=gateway.get("active_requests")==0 and gateway.get("queued_requests")==0 and gateway.get("draining") is False
    result["native_idle"]=native.get("nativeSessions")==0
    cache=model.get("prompt_cache",{})
    result["model_cache_matches"]=(cache.get("mode")==1 and cache.get("enabled") is True
        and cache.get("cap_mb",0)>0 and cache.get("bitwise_identical_to_cold") is True)
    listeners_match=all(any(row["port"]==port and row["address"]=="127.0.0.1" and row["expected_process"] is True for row in rows) for port in EXPECTED)
    result["stack_healthy"]=(all(value.get("http_status")==200 for value in services.values())
        and result["memory"].get("above_runtime_floor") is True and not legacy and listeners_match
        and model.get("version_matches") is True and model.get("expected_model") is True
        and model.get("context")==262144 and model.get("slots")==1
        and result["model_cache_matches"] is True
        and services["tts"].get("expected_model") is True and native.get("auth_mode")=="servicenow"
        and result["funnel"].get("native_route_matches") is True and result["funnel"].get("funnel_allowed") is True)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["stack_healthy"] else 2
if __name__=="__main__": raise SystemExit(main())
