#!/usr/bin/env python3
"""Compare trunk vs sidecar block_count / n_layer_nextn to find the loader OOB."""
import sys
sys.path.insert(0, '.')
from gguf_inventory import parse_shard

paths = {
    "trunk (UD shard1)": "/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf",
    "sidecar shared":    "/home/revn/models/flash-next-unsloth/MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf",
}
for name, p in paths.items():
    try:
        m = parse_shard(p)["meta"]
    except Exception as e:
        print(f"{name}: ERROR {e}"); continue
    keys = [k for k in m if any(x in k for x in ('block_count','nextn','predict','compress','expert_used','ple.layers'))]
    print(f"=== {name}")
    for k in sorted(keys):
        v = m[k]
        if isinstance(v, list) and len(v) > 8:
            v = f"[{len(v)} entries] first={v[:4]}"
        print(f"    {k} = {v}")
