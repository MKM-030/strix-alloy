#!/usr/bin/env python3
"""Does a Windows gfx1151 ROCm/TheRock artifact exist? Check the likely hosts directly."""
import json
import urllib.request
import urllib.error

def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return None, str(e)

# 1. TheRock releases: list every asset name across recent releases
st, body = get("https://api.github.com/repos/ROCm/TheRock/releases?per_page=5")
print("== GitHub releases API status:", st)
if st == 200:
    for r in json.loads(body):
        names = [a["name"] for a in r.get("assets", [])]
        print(f"  {r['tag_name']}: {names}")

# 2. The S3 nightly index for windows artifacts
for prefix in ("", "?prefix=therock-dist-windows", "?list-type=2&prefix=therock-dist-windows"):
    st, body = get("https://nightly.repo.amd.com/rocm/core/tarball/" + prefix)
    print(f"\n== nightly index '{prefix or '(root)'}' status={st} len={len(body) if body else 0}")
    if body:
        print(body[:800])
