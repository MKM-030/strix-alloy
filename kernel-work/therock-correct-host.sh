#!/usr/bin/env bash
# Query the CORRECT TheRock source that our SDK actually came from.
echo "=== nightly.repo.amd.com/rocm/core/tarball/ ==="
curl -s --max-time 90 "https://nightly.repo.amd.com/rocm/core/tarball/" \
  | grep -oiE 'therock-dist-windows-gfx1151-[0-9]+[0-9a-z.-]*\.tar\.gz' | sort -uV | tail -15
echo
echo "=== any after 2026-09-15 on that host? ==="
curl -s --max-time 90 "https://nightly.repo.amd.com/rocm/core/tarball/" \
  | grep -oiE 'therock-dist-windows-gfx1151-[0-9]+[0-9a-z.-]*\.tar\.gz' | sort -uV \
  | grep -E '2026(09(1[6-9]|[2-9][0-9])|1[0-2])' || echo "  none newer than 20260915"
echo
echo "=== confirm our exact file resolves ==="
for h in nightly.repo.amd.com/rocm/core/tarball rocm.nightlies.amd.com/tarball; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 \
    "https://$h/therock-dist-windows-gfx1151-10.2.0a20260915.tar.gz")
  echo "  $h -> HTTP $code"
done
