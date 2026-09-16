#!/usr/bin/env python3
"""Search the converted file for the original d2t block to measure the real shift."""
import struct
import sys

sys.path.insert(0, '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work')
src = open('/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/d2t-inspect.py').read()
exec(src.split('def main')[0])

O = '/mnt/c/AI/models/qwen38-flash/drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf'
C = '/mnt/c/AI/models/qwen38-flash/projfix/mtp-frspec-65k-pwhead.gguf'

vo, kvo, to, do = read_gguf(O)
vc, kvc, tc, dc = read_gguf(C)
o_d2t = next(t for t in to if t['name'] == 'd2t')
c_d2t = next(t for t in tc if t['name'] == 'd2t')

# full original d2t block bytes (good)
orig_block = do[o_d2t['off']: o_d2t['off'] + 65536 * 8]
print(f'orig d2t block len {len(orig_block)} first8={struct.unpack("<8q", orig_block[:64])}')

rawc = open(C, 'rb').read()
# find where that block actually is in the converted file
pos = rawc.find(orig_block[:4096])
print(f'orig d2t first 4096 bytes found in converted file at: {pos}')
data_start_c = len(rawc) - len(dc)
print(f'converted data_start (read_gguf) = {data_start_c}')
print(f'converted d2t recorded abs        = {data_start_c + c_d2t["off"]}')
if pos >= 0:
    print(f'shift = pos - (data_start_c + c_d2t["off"]) = {pos - (data_start_c + c_d2t["off"])}')

# also: what does the converter's own header length imply?
print(f'converted file size {len(rawc)}, dc len {len(dc)}, hdr as read_gguf sees = {data_start_c}')
# check: is the converted data_start 32-aligned?
print(f'converted data_start %32 = {data_start_c % 32}')
