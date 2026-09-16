#!/usr/bin/env python3
"""Validate the FR-Spec MTP head GGUF: metadata + tensor list."""
import sys
sys.path.insert(0, '.')
from gguf_inventory import parse_shard, GT, NAME2TYPE

s = parse_shard('/home/revn/models/mtp-heads/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf')
m = s['meta']
print('arch:', m.get('general.architecture'), '| name:', m.get('general.name'))
for k in sorted(m):
    if any(x in k for x in ('expert', 'block_count', 'embedding_length', 'ssm', 'head_count',
                            'context_length', 'mtp', 'draft')):
        v = m[k]
        if isinstance(v, list) and len(v) > 10:
            v = v[:10] + ['...']
        print(' ', k, '=', v)
tlist = s['tensors']
print('tensors:', len(tlist))
tot = 0
for t in tlist:
    bb, bl = GT[t['type']]
    n = 1
    for d_ in t['ne']:
        n *= d_
    tot += (n + bl - 1) // bl * bb
for t in tlist[:8] + tlist[-6:]:
    bb, bl = GT[t['type']]
    n = 1
    for d_ in t['ne']:
        n *= d_
    b = (n + bl - 1) // bl * bb
    print('  %-56s %-6s ne=%-24s %8.1f MiB' % (t['name'], NAME2TYPE.get(t['type'], t['type']),
                                               str(t['ne']), b / 2**20))
print('total head size: %.2f GiB' % (tot / 2**30))
