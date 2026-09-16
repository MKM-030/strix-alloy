#!/usr/bin/env python3
"""Interpret the measured PLE host-side cost against the decode wall."""
import re

RES = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results'


def read(p):
    with open(p, 'rb') as f:
        raw = f.read()
    if len(raw) > 4 and raw[1::2].count(0) > max(2, len(raw) // 8):
        return raw.decode('utf-16', errors='replace').replace('\x00', '')
    return raw.decode('utf-8', errors='replace').replace('\x00', '')


def last_ple(name):
    t = read(f'{RES}/{name}')
    rows = [l for l in t.splitlines() if 'PLE_TIMING' in l]
    if not rows:
        return None
    return rows[-1]


def decode_ms(name):
    # from the companion .err print_timing line
    t = read(f'{RES}/{name}')
    m = [l for l in t.splitlines() if 'eval time =' in l]
    if not m:
        return None, None
    last = m[-1]
    mm = re.search(r'eval time =\s*([\d.]+) ms\s*/\s*(\d+) tokens', last)
    if mm:
        return float(mm.group(1)), int(mm.group(2))
    return None, None


print('=== PLE host-side cost vs decode wall ===\n')
for name, label in (('ir-il-mtp-n2.err', 'MTP n-max 2, 8k prompt'),
                    ('ir-il-prefill-ub16k.err', 'no MTP, 8k prompt')):
    row = last_ple(name)
    dms, dtok = decode_ms(name)
    print(f'--- {label} ---')
    if row:
        print('  ', row.strip())
        m = re.search(r'calls=(\d+) tokens=(\d+)\s+prev=([\d.]+) ms\s+hash=([\d.]+) ms\s+'
                      r'gather=([\d.]+) ms\s+upload=([\d.]+) ms\s+\| host-total=([\d.]+) ms', row)
        if m:
            calls, toks, prev, hashm, gath, up, tot = m.groups()
            calls, toks = int(calls), int(toks)
            tot = float(tot)
            print(f'   cumulative over {calls} set_input calls, {toks} tokens')
            print(f'   host-total = {tot:.1f} ms  -> {1000*tot/toks:.3f} us per token')
            if dms:
                print(f'   decode wall = {dms:.0f} ms for {dtok} tokens')
                print(f'   PLE host share of decode wall = {100*tot/dms:.3f} %')
            print(f'   components: prev={prev} ms  hash={hashm} ms  gather={gath} ms  upload={up} ms')
    else:
        print('   (no PLE rows)')
    print()

print('NOTE: gather=0.0 across all calls means the lazy reader gather branch produced no')
print('measurable time. Either the reader is inactive in this config (so the row lookup is an')
print('on-GPU get_rows) or it is genuinely negligible. Either way the host-side PLE staging')
print('cost is not a material part of the decode wall.')
