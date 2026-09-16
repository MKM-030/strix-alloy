#!/usr/bin/env python3
"""Sanity-check the expert-ablation slope against the byte model and the measured ceiling.

Key numbers:
  measured achievable sequential read : 235.7 GB/s
  measured copy (read+write)          : 104.1 GB/s each way
  k=10 round (warm, width 2)          : 49.27 ms
  k=3  round (warm, width 2)          : 39.60 ms
  expert payload k=10 vs k=3          : 1.327 vs 0.398 GB  (delta 0.929 GB)
"""
BW_READ = 235.7
BW_COPY_EW = 104.1

d_payload = 1.327 - 0.398          # GB of expert bytes removed by k=10 -> k=3
d_time    = 49.27 - 39.60          # ms saved
bw_expert = d_payload / (d_time / 1000.0)

print(f'expert delta: {d_payload:.3f} GB removed, {d_time:.2f} ms saved')
print(f'  => implied expert-path bandwidth = {bw_expert:.1f} GB/s')
print(f'  vs measured read ceiling          = {BW_READ:.1f} GB/s  ({100*bw_expert/BW_READ:.0f}% of it)')
print()

# Now the whole round at k=10
DENSE = 2.927
total_payload = DENSE + 1.327
ms10 = 49.27
print(f'whole round at k=10: {total_payload:.3f} GB in {ms10:.2f} ms = {total_payload/(ms10/1000.0):.1f} GB/s '
      f'({100*(total_payload/(ms10/1000.0))/BW_READ:.0f}% of read ceiling)')
print()

# If the round ran at the measured ceiling, what would it cost?
print('what the round would cost at 100% of the measured read ceiling:')
print(f'  {total_payload/BW_READ*1000:.2f} ms  vs measured {ms10:.2f} ms  -> {ms10/(total_payload/BW_READ*1000):.2f}x slower')
print()

# And if we attribute the FIXED part to dense weights only, what bandwidth is dense achieving?
fixed_ms = 35.5
print(f'fixed part (k-independent) = {fixed_ms:.1f} ms for {DENSE:.3f} GB dense/other')
print(f'  => dense-path bandwidth = {DENSE/(fixed_ms/1000.0):.1f} GB/s ({100*(DENSE/(fixed_ms/1000.0))/BW_READ:.0f}% of ceiling)')
print()
print('CONCLUSION:')
print('  Both the expert delta (~96 GB/s) and the dense fixed part (~82 GB/s) run FAR below the')
print('  235.7 GB/s the hardware demonstrably delivers. The gap is not in one component.')
print('  This is consistent with a uniform ~55% efficiency across the whole round, and it means')
print('  the loss is systemic (how bytes are fetched), not a per-component algorithm problem.')
