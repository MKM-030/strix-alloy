#!/usr/bin/env python3
"""Find the exact Windows gfx1151/gfx115X tarball name and URL."""
import re
import urllib.request

def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

html = get("https://nightly.repo.amd.com/rocm/core/tarball/")
names = sorted(set(re.findall(r'therock-dist-windows-[A-Za-z0-9._\-]+\.tar\.gz', html)))
print(f"total windows artifacts indexed: {len(names)}")
fams = sorted(set(re.findall(r'therock-dist-windows-([A-Za-z0-9]+?)-(?:dgpu|all|tests)', html)))
print("families:", fams)
# specifically gfx1151 / gfx115X
for pat in ("gfx1151", "gfx115X", "gfx1150"):
    hits = [n for n in names if pat.lower() in n.lower() and "tests" not in n]
    print(f"\n== {pat}: {len(hits)} (non-test) ==")
    for h in hits[-6:]:
        print("  ", h)
