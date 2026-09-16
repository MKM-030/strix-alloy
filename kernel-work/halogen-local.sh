#!/usr/bin/env bash
# halogen-local.sh — what Halogen assets exist locally, and does any Windows build exist?
echo "=== halogen binaries on WSL side ==="
ls -la /home/revn/halogen-flash/bins/ 2>/dev/null | head -10
echo
echo "=== halogen model dirs ==="
ls -d /home/revn/halogen* 2>/dev/null
ls -d /mnt/c/AI/models/halogen* 2>/dev/null
echo
echo "=== any .hgn or flash_serve on the Windows side? ==="
find /mnt/c/AI -maxdepth 3 -iname 'flash_serve*' -o -maxdepth 3 -iname '*.hgn' 2>/dev/null | head -8
echo
echo "=== WSL device support: does /dev/kfd exist (Halogen needs it)? ==="
ls -la /dev/kfd 2>/dev/null || echo "/dev/kfd ABSENT (as always in WSL)"
ls -la /dev/dxg 2>/dev/null
