#!/usr/bin/env bash
echo "=== all gfx1151 entries in the TheRock tarball listing ==="
curl -s --max-time 90 "https://rocm.nightlies.amd.com/tarball/" \
  | tr '<>' '\n\n' \
  | grep -iE 'therock-dist-(windows|linux)-gfx1151' \
  | sed 's/.*\(therock-dist[^"]*\.tar\.gz\).*/\1/' \
  | sort -u | tail -30

echo
echo "=== newest windows specifically ==="
curl -s --max-time 90 "https://rocm.nightlies.amd.com/tarball/" \
  | tr '<>' '\n\n' \
  | grep -oiE 'therock-dist-windows-gfx1151-[0-9a-z.]+\.tar\.gz' \
  | sort -u | tail -10

echo
echo "=== newest linux specifically (for comparison) ==="
curl -s --max-time 90 "https://rocm.nightlies.amd.com/tarball/" \
  | tr '<>' '\n\n' \
  | grep -oiE 'therock-dist-linux-gfx1151-[0-9a-z.]+\.tar\.gz' \
  | sort -u | tail -10
