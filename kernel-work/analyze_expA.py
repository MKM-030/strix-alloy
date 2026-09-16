#!/usr/bin/env python3
"""Parse experiment A logs into a compact summary."""
import json
import os
import re
import statistics

OUT = os.path.dirname(os.path.abspath(__file__)) + "/expA"

def parse_bench_table(path):
    if not os.path.exists(path):
        return None
    rows = []
    for line in open(path):
        m = re.match(r"\|\s*qwen4exp[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|\s*(tg\d+|pp\d+)\s*\|\s*([\d.]+)\s*±\s*([\d.]+)", line)
        if m:
            rows.append({"test": m.group(1), "tps": float(m.group(2)), "std": float(m.group(3)),
                         "ms_per_tok": 1000.0 / float(m.group(2))})
    return rows or None

def parse_gt(path):
    """GT compute lines: n, graph, upd, hostgap, submit, gpu_wait."""
    if not os.path.exists(path):
        return None
    rows = []
    for line in open(path):
        m = re.search(r"GT compute n=(\d+) first=\S+.*graph=(\d) upd=(\d) hostgap=([\d.]+)ms submit=([\d.]+)ms gpu_wait=([\d.]+)ms", line)
        if m:
            rows.append({"n": int(m.group(1)), "graph": int(m.group(2)), "upd": int(m.group(3)),
                         "hostgap": float(m.group(4)), "submit": float(m.group(5)), "gpu_wait": float(m.group(6))})
    return rows or None

def parse_diag(path):
    if not os.path.exists(path):
        return None
    rows = []
    for line in open(path):
        m = re.search(r"GRAPH_DIAG nodes=(\d+) key=\S+ enabled=(\d) compatible=(\d) warmup_complete=(\d) uid=(\d+)", line)
        if m:
            rows.append({"nodes": int(m.group(1)), "enabled": int(m.group(2)), "compatible": int(m.group(3)),
                         "warmup": int(m.group(4)), "uid": int(m.group(5))})
    return rows or None

summary = {}
for tag in ["on-p0", "off-p0", "on-t", "off-t", "on-p2k", "off-p2k"]:
    p = f"{OUT}/expA-{tag}.log"
    summary[tag] = {"bench": parse_bench_table(p), "gt": parse_gt(p), "diag": parse_diag(p)}

# steady-state GT stats (exclude first 5 evals = warmup/capture)
for tag in ["on-t", "off-t"]:
    g = summary[tag]["gt"]
    if g:
        steady = g[5:]
        if steady:
            summary[tag]["steady"] = {
                "n_evals": len(g), "n_steady": len(steady),
                "graph_frac": sum(r["graph"] for r in steady) / len(steady),
                "upd_frac": sum(r["upd"] for r in steady) / len(steady),
                "hostgap_ms_avg": round(statistics.fmean(r["hostgap"] for r in steady), 2),
                "submit_ms_avg": round(statistics.fmean(r["submit"] for r in steady), 2),
                "gpu_wait_ms_avg": round(statistics.fmean(r["gpu_wait"] for r in steady), 2),
                "total_ms_avg": round(statistics.fmean(r["hostgap"] + r["submit"] + r["gpu_wait"] for r in steady), 2),
            }

print(json.dumps(summary, indent=1))
json.dump(summary, open(f"{OUT}/expA-summary.json", "w"), indent=1)
