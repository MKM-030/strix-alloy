#!/usr/bin/env python3
"""Stats for GT lines of the big decode graph only (n==7322)."""
import re
import statistics
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "expA/expA-on-t.log"
rows = []
for line in open(path):
    m = re.search(r"GT compute n=(\d+) \S+ \S+ graph=(\d) upd=(\d) hostgap=([\d.]+)ms submit=([\d.]+)ms gpu_wait=([\d.]+)ms", line)
    if m and int(m.group(1)) >= 7000:
        rows.append(dict(graph=int(m.group(2)), upd=int(m.group(3)),
                         hostgap=float(m.group(4)), submit=float(m.group(5)), gpu_wait=float(m.group(6))))
print(f"{path}: {len(rows)} big-graph evals")
if rows:
    print("graph=1 frac: %.3f  upd=1 count: %d" % (sum(r["graph"] for r in rows) / len(rows), sum(r["upd"] for r in rows)))
    for k in ("hostgap", "submit", "gpu_wait"):
        vals = [r[k] for r in rows]
        print("%-9s avg=%6.2f med=%6.2f min=%6.2f max=%6.2f ms" % (k, statistics.fmean(vals), statistics.median(vals), min(vals), max(vals)))
    tot = [r["hostgap"] + r["submit"] + r["gpu_wait"] for r in rows]
    print("%-9s avg=%6.2f med=%6.2f ms  (n=%d)" % ("total", statistics.fmean(tot), statistics.median(tot), len(tot)))
