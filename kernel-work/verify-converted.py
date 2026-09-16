#!/usr/bin/env python3
"""Verify the re-converted FR-Spec head is byte-correct against the original.

Checks every carried tensor against the source blob, and validates the one synthesized
tensor (eh_proj = row-wise concat of fc_embd + fc_hidden).
"""
import os
import struct
import sys

KW = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work'
sys.path.insert(0, KW)
src = open(os.path.join(KW, 'd2t-inspect.py')).read()
exec(src.split('def main')[0])
from gguf_inventory import GT

O = '/mnt/c/AI/models/qwen38-flash/drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf'
C = '/mnt/c/AI/models/qwen38-flash/projfix/mtp-frspec-65k-pwhead.gguf'


def tsz(ne, ty):
    bb, bl = GT[ty]
    n = 1
    for d in ne:
        n *= d
    return (n + bl - 1) // bl * bb


vo, kvo, to, do = read_gguf(O)
vc, kvc, tc, dc = read_gguf(C)
oby = {t['name']: t for t in to}
cby = {t['name']: t for t in tc}

RENAME = {
    'blk.48.nextn.hc_norm.weight': 'blk.48.nextn.hc_head_norm.weight',
    'blk.48.nextn.hc_down.weight': 'blk.48.nextn.hc_head_down.weight',
    'blk.48.nextn.hc_up.weight': 'blk.48.nextn.hc_head_up.weight',
}
FC_EMBD = 'blk.48.nextn.fc_embd.weight'
FC_HIDDEN = 'blk.48.nextn.fc_hidden.weight'
EH = 'blk.48.nextn.eh_proj.weight'

ok = True
checked = 0
for name, ct in cby.items():
    if name == EH:
        continue
    ot = oby.get(name)
    if ot is None:
        # maybe it's a rename target -> find its source
        srcname = next((k for k, v in RENAME.items() if v == name), None)
        if srcname is None:
            print(f'  ?? no source for {name}')
            ok = False
            continue
        ot = oby[srcname]
        ob = do[ot['off']: ot['off'] + tsz(ot['ne'], ot['ty'])]
    else:
        ob = do[ot['off']: ot['off'] + tsz(ot['ne'], ot['ty'])]
    cb = dc[ct['off']: ct['off'] + tsz(ct['ne'], ct['ty'])]
    same = (ob == cb) and (list(ct['ne']) == list(ot['ne'])) and (ct['ty'] == ot['ty'])
    checked += 1
    if not same:
        print(f'  MISMATCH {name}: ne {ot["ne"]}->{ct["ne"]} ty {ot["ty"]}->{ct["ty"]} byteeq={ob==cb}')
        ok = False

# eh_proj check
e = oby[FC_EMBD]; h = oby[FC_HIDDEN]; eh = cby[EH]
K, M = e['ne'][0], e['ne'][1]
eb = do[e['off']: e['off'] + tsz(e['ne'], e['ty'])]
hb = do[h['off']: h['off'] + tsz(h['ne'], h['ty'])]
rb = len(eb) // M; rb2 = len(hb) // M
exp = bytearray()
for r in range(M):
    exp += eb[r * rb:(r + 1) * rb]
    exp += hb[r * rb2:(r + 1) * rb2]
got = dc[eh['off']: eh['off'] + tsz(eh['ne'], eh['ty'])]
eh_ok = bytes(exp) == got and list(eh['ne']) == [K * 2, M]
print(f'  eh_proj: ne {eh["ne"]} expected [5120,2560] byteeq={bytes(exp)==got}')
ok &= eh_ok
checked += 1

# d2t
d = cby['d2t']
vals = struct.unpack('<65536q', dc[d['off']: d['off'] + 65536 * 8])
d2t_ok = all(0 <= x < 248320 for x in vals)
print(f'  d2t: in-range {sum(1 for x in vals if 0 <= x < 248320)}/65536  first8={vals[:8]}')
ok &= d2t_ok

# no source tensors left unaccounted
print(f'\ndebug: ok after loop={ok!r} eh_ok={eh_ok!r} d2t_ok={d2t_ok!r} types={type(ok)}')
print(f'checked {checked}/{len(cby)} output tensors')
print(f'carried tensors: {len(to)} in, {len(tc)} out (fc_embd+fc_hidden merged into eh_proj)')
print('VERDICT:', 'ALL OK' if ok else 'FAILURES PRESENT')
