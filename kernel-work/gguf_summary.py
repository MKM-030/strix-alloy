#!/usr/bin/env python3
import json, sys
d = json.load(open(sys.argv[1] if len(sys.argv) > 1 else 'gguf-inventory-udiq4xs.json'))
print('total GiB: %.2f  params: %.2f G  bpw: %.3f' % (d['total_bytes']/2**30, d['total_params']/1e9, d['bits_per_weight_all']))
for k, v in sorted(d['by_class'].items(), key=lambda x: -x[1]['bytes']):
    print('%-12s %9.3f GiB  %8.3f G  n=%d' % (k, v['bytes']/2**30, v['params']/1e9, v['n']))
print('types GiB:', {k: round(v['bytes']/2**30, 2) for k, v in d['by_type'].items()})
print('layers:', d.get('layer_n'))
print('layer_example (last blk):', d.get('layer_bytes_example'))
moe = d.get('moe_bytes_per_layer', {})
vals = sorted(set(moe.values()))
print('moe_bytes_per_layer distinct values:', [(v/2**20, sum(1 for x in moe.values() if x == v)) for v in vals])
for t in d['big_tensors_gt_500MB'][:10]:
    print('BIG %-60s %8.2f GiB  %s  ne=%s' % (t['name'], t['bytes']/2**30, t['type'], t['ne']))
# architecture keys
meta = d['meta']
keys = [k for k in meta if k.split('.')[0] in ('qwen4exp',) or 'expert' in k or 'attention' in k or k in ('general.architecture','general.name','general.size_label','llama.embedding_length','llama.block_count')]
for k in sorted(keys):
    v = meta[k]
    if isinstance(v, list) and len(v) > 12:
        v = v[:12] + ['...']
    print('%-46s %s' % (k, v))
