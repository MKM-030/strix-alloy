"""Read-only upstream inventory. Never installs a driver or silently changes a runtime."""
import concurrent.futures
import datetime
import json
from pathlib import Path
import urllib.request
TARGETS={
 'halogen':('peonist-ai/halogen-flash-server','main'),
 'gufo_upstream':('gufo-org/gufo','main'),
 'gufo_windows_pixmaate':('pixmaate/gufo','windows-port'),
 'gufo_windows_thomas':('thomas9120/gufo','windows-port'),
 'rulith':('rulith-dev/rulith-inference','main'),
 'llama_cpp':('ggml-org/llama.cpp','master')}

def inspect(item):
    name,(repo,branch)=item
    url='https://api.github.com/repos/'+repo+'/commits/'+branch
    try:
        request=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json',
                                                   'User-Agent':'strix-alloy-update-inventory'})
        with urllib.request.urlopen(request,timeout=20) as response:
            raw=response.read(4*1024**2+1)
        if len(raw)>4*1024**2: raise ValueError('Unexpectedly large metadata response')
        value=json.loads(raw)
        return name,{'repository':repo,'branch':branch,'commit':value['sha'],
                     'date':value['commit']['committer']['date'],'url':value['html_url'],
                     'promotion':'requires compatibility, correctness and benchmark validation'}
    except Exception as exc:
        return name,{'error':type(exc).__name__,'status':'not verified'}

def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        observed=dict(pool.map(inspect,TARGETS.items()))
    repo=Path(__file__).resolve().parents[1]
    pins=repo/'backends/halogen-wsl2-0.16.2/profiles/release.json'
    report={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'installed_backend_pin':json.loads(pins.read_text()) if pins.exists() else None,
            'upstreams':observed,'driver_policy':'Check the official AMD release notes; updates are separate controlled A/B tests, never startup actions.',
            'amd_driver_release_notes':'https://www.amd.com/en/support/download/drivers.html',
            'ryzen_ai_release_notes':'https://ryzenai.docs.amd.com/en/latest/relnotes.html'}
    print(json.dumps(report,indent=2))
    return 1 if any('error' in value for value in observed.values()) else 0

if __name__=='__main__': raise SystemExit(main())
