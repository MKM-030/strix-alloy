#!/usr/bin/env python3
"""The carve trade-off, with the host-RAM side made explicit.

The device pool is carve-derived ("64 GiB + carve/2"); the model, however, is UMA - its resident
weights come from HOST RAM. So the carve that maximises the GPU pool also minimises the host RAM
available to hold the weights, and past a point the engine cannot load at all.
"""
print(f"{'carve':>7} {'pool GiB':>9} {'win RAM GiB':>12} {'WSL cap':>8}  loadable?")
for carve, pool, winram in ((32, 79.8, 95.6), (48, 87.8, 79.6), (64, 95.8, 63.6), (96, 111.8, 31.6)):
    # resident needs: UD 60.4 GiB, PROJFIX 66.3 GiB; plus ~2-4 GiB kv/compute at 32k ctx
    ud_ok  = winram >= 60.4 + 4
    pf_ok  = winram >= 66.3 + 4
    wsl_ok = (winram - 4) >= 62   # WSL cap must fit the model; it shares host RAM
    print(f"{carve:>5}GB {pool:>9.1f} {winram:>12.1f} {max(0,winram-6):>7.0f}G  "
          f"UD: {'yes' if ud_ok else 'NO '}  PROJFIX: {'yes' if pf_ok else 'NO '}  WSL: {'yes' if wsl_ok else 'NO'}")
print()
print("measured: at 32 GB carve we ran WSL PROJFIX at 839 t/s (host RAM ~95 GB - ample).")
print("measured: at 96 GB carve Windows has 31.6 GB - cannot hold a 60-66 GiB resident model,")
print("          so the native-Vulkan/HIP path we meant to exploit is not loadable at 96.")
