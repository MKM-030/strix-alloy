#!/usr/bin/env python3
"""Grep the nightly tarball index for windows/gfx1151 artifact names, and for the release paths it lists."""
import re
import urllib.request

def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

html = get("https://nightly.repo.amd.com/rocm/core/tarball/")
print("index size:", len(html))

wins = sorted(set(re.findall(r'[A-Za-z0-9._\-]*windows[A-Za-z0-9._\-]*', html, re.I)))
print("\n-- names containing 'windows' --")
print("\n".join(wins[:40]) or "(none)")

gfx = sorted(set(re.findall(r'therock-dist-[a-z0-9\-]+', html, re.I)))
print("\n-- artifact family names found --")
print("\n".join(gfx[:40]) or "(none)")

# the page likely lists release subdirectories; show those
subs = sorted(set(re.findall(r'href="([^"]+)"', html)))
rel = [s for s in subs if re.search(r'rocm|therock|\d', s) and not s.startswith(('http', '#', '/'))]
print("\n-- hrefs (first 40) --")
print("\n".join(rel[:40]) or "(none)")
