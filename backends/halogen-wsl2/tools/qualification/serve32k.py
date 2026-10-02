"""A finite client window: one health check, then no generated benchmark traffic."""
import argparse
import json
import pathlib
import time
import urllib.request

def check_health(health):
    if not isinstance(health, dict) or health.get('status') != 'ok':
        raise ValueError('Serve32k requires healthy status')
    if health.get('version', {}).get('match') is not True or health.get('prompt_cache', {}).get('enabled') is not False:
        raise ValueError('Serve32k version or cache mismatch')
    for key, expected in [('context',32768),('slot_ctx',32768),('kv_pool_positions',32768),('slots',1)]:
        if type(health.get(key)) is not int or health[key] != expected:
            raise ValueError('Serve32k health mismatch: ' + key)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=300)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    args=parser.parse_args()
    if not 30 <= args.seconds <= 300: parser.error('Duration must be 30..300 seconds')
    with urllib.request.urlopen('http://127.0.0.1:8731/health',timeout=5) as response:
        health=json.load(response)
    check_health(health)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(dict(schema='strix-alloy-serve-v1',health=health,seconds=args.seconds),stream)
    print(f'API ready at http://127.0.0.1:8731 for {args.seconds} seconds. Keep Start.ps1 running.',flush=True)
    deadline=time.monotonic()+args.seconds
    while time.monotonic() < deadline:
        time.sleep(min(0.25,max(0,deadline-time.monotonic())))

if __name__=='__main__': main()
